"""Local event-log display, with headless, deterministic projections.

The display reads only persisted public events. Importing this module does not
import tkinter or create a window, so replay/accounting checks work in CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


EDGE_COLORS = {
    "assignment": "#7c8cff",
    "message": "#32baa3",
    "artifact": "#e7ad54",
    "verification": "#eb829e",
}
SYSTEM_ACTORS = {"scheduler", "verifier", "evaluator", "runtime", "system"}


@dataclass
class AgentView:
    agent_id: str
    role: str = "unspecified"
    state: str = "idle"
    task_id: str | None = None


@dataclass(frozen=True)
class EdgeView:
    actor: str
    recipient: str
    category: str
    event_id: int


@dataclass(frozen=True)
class UsageView:
    attempt_id: str
    agent_id: str
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    currency: str
    source: str
    elapsed_seconds: float


@dataclass
class UsageTotals:
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    unknown_input: int = 0
    unknown_output: int = 0
    costs: dict[str, Decimal] = field(default_factory=dict)
    unknown_cost: int = 0

    def add(self, usage: UsageView) -> None:
        self.attempts += 1
        if usage.input_tokens is None:
            self.unknown_input += 1
        else:
            self.input_tokens += usage.input_tokens
        if usage.output_tokens is None:
            self.unknown_output += 1
        else:
            self.output_tokens += usage.output_tokens
        if usage.cost is None:
            self.unknown_cost += 1
        else:
            self.costs[usage.currency] = self.costs.get(usage.currency, Decimal(0)) + usage.cost


def _tokens(value: Any) -> int | None:
    # bool is an int in Python, but is not valid usage telemetry.
    return value if type(value) is int and value >= 0 else None


def _money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _elapsed(event: dict[str, Any]) -> float:
    try:
        value = float(event.get("elapsed_seconds", 0))
        return value if math.isfinite(value) and value >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


class EventProjection:
    """Fold public events into display state without running agent policies.

    Duplicate event IDs are ignored. Later usage records for the same attempt
    replace prior telemetry, so a correction cannot duplicate spend. Sources
    stay separate: simulated, estimated, reported, reconciled, or unknown.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.mode = str(self.config.get("mode", "unknown"))
        self.agents: dict[str, AgentView] = {}
        self.events: list[dict[str, Any]] = []
        self.event_by_id: dict[int, dict[str, Any]] = {}
        self.edges: list[EdgeView] = []
        self.usage: dict[str, UsageView] = {}
        self.lower_bound: int | None = None
        self.upper_bound: int | None = None
        self.stopping_reason: str | None = None
        self.summary: dict[str, Any] = {}
        self.budget: dict[str, Any] = {}
        self.elapsed_seconds = 0.0
        self._register_team(self.config.get("team", []))

    def _register_team(self, team: Iterable[dict[str, Any]]) -> None:
        for item in team:
            if isinstance(item, dict) and item.get("agent_id"):
                node = self._agent(str(item["agent_id"]))
                node.role = str(item.get("role", "unspecified"))

    def _agent(self, actor: str) -> AgentView:
        if actor not in self.agents:
            role = "infrastructure" if actor in SYSTEM_ACTORS else "unspecified"
            self.agents[actor] = AgentView(actor, role)
        return self.agents[actor]

    def apply(self, event: dict[str, Any]) -> bool:
        event_id = event.get("event_id")
        if type(event_id) is not int:
            raise ValueError("Every event needs an integer event_id")
        if event_id in self.event_by_id:
            return False
        self.events.append(event)
        self.event_by_id[event_id] = event
        self.elapsed_seconds = max(self.elapsed_seconds, _elapsed(event))
        actor = str(event.get("actor") or "")
        recipient = str(event.get("recipient") or "")
        kind = str(event.get("event_type") or "unknown")
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        for identity in (actor, recipient):
            if identity:
                self._agent(identity)
        if kind == "run_started":
            self.config.update(payload.get("config") or payload)
            self.mode = str(self.config.get("mode", "unknown"))
            self._register_team(payload.get("team") or [])
            self.upper_bound = _tokens(self.config.get("m"))
            self.lower_bound = 0
        elif kind == "assignment" and recipient:
            self.agents[recipient].state = "working"
            self.agents[recipient].task_id = event.get("task_id")
        elif kind == "candidate_submitted" and actor:
            self.agents[actor].state = "awaiting verification"
        elif kind == "verification":
            self._set_bounds(payload)
            if recipient:
                valid = payload.get("valid")
                self.agents[recipient].state = (
                    "verified candidate" if valid is True else
                    "rejected candidate" if valid is False else "verification returned"
                )
        elif kind == "evaluation" and actor == "evaluator":
            self._set_bounds(payload)
        elif kind in {"task_completed", "agent_completed"} and actor:
            self.agents[actor].state = "complete"
        elif kind in {"task_cancelled", "agent_cancelled"} and actor:
            self.agents[actor].state = "cancelled"
        elif kind in {"agent_failed", "task_failed"} and actor:
            self.agents[actor].state = "failed"
        elif kind == "run_finished":
            self.summary = dict(payload.get("summary") or payload)
            self._set_bounds(self.summary)
            self.stopping_reason = self.summary.get("stopping_reason")
            for node in self.agents.values():
                if node.role != "infrastructure" and node.state not in {"failed", "cancelled"}:
                    node.state = "stopped"
        if kind == "usage":
            self._apply_usage(actor, payload, event)
        category = None
        if kind == "assignment":
            category = "assignment"
        elif kind in {"message_sent", "message_delivered", "message_read"}:
            category = "message"
        elif kind in {"artifact_used", "artifact_shared", "share_artifact"}:
            category = "artifact"
        elif kind == "verification":
            category = "verification"
        if category and actor and recipient:
            self.edges.append(EdgeView(actor, recipient, category, event_id))
        elif category == "artifact" and actor:
            # Consumption events name the delivered artifact through provenance.
            # This is a reference edge, not an inference of beneficial influence.
            for parent_id in event.get("parent_event_ids") or []:
                parent = self.event_by_id.get(parent_id, {})
                if parent.get("event_type") == "message_delivered" and parent.get("recipient") == actor:
                    origin = parent.get("actor")
                    if origin:
                        self.edges.append(EdgeView(str(origin), actor, category, event_id))
        return True

    def _set_bounds(self, payload: dict[str, Any]) -> None:
        # Only trusted verification/summary events may establish bounds.
        for name in ("lower_bound", "upper_bound"):
            value = _tokens(payload.get(name))
            if value is not None:
                setattr(self, name, value)

    def _apply_usage(self, actor: str, payload: dict[str, Any], event: dict[str, Any]) -> None:
        attempt_id = payload.get("attempt_id")
        if not attempt_id:
            return  # Unattributable telemetry cannot be counted as an attempt.
        status = str(payload.get("status", payload.get("usage_status", "")))
        if payload.get("simulated") is True:
            source = "simulated"
        elif status in {"estimated", "reconciled"}:
            source = status
        elif payload.get("simulated") is False or status in {"observed", "reported", "provider_reported"}:
            source = "reported"
        else:
            source = "unknown"
        self.usage[str(attempt_id)] = UsageView(
            str(attempt_id), actor,
            _tokens(payload.get("input_tokens")), _tokens(payload.get("output_tokens")),
            _money(payload.get("cost")), str(payload.get("currency", "USD")),
            source, _elapsed(event),
        )
        for key in ("committed_cost", "remaining_cost", "committed_tokens", "remaining_tokens"):
            if key in payload:
                self.budget[key] = payload[key]

    @property
    def gap(self) -> int | None:
        if self.lower_bound is None or self.upper_bound is None:
            return None
        return self.upper_bound - self.lower_bound

    def totals(self) -> dict[str, UsageTotals]:
        result: dict[str, UsageTotals] = {}
        for usage in self.usage.values():
            result.setdefault(usage.source, UsageTotals()).add(usage)
        return result

    def agent_totals(self) -> dict[tuple[str, str], UsageTotals]:
        result: dict[tuple[str, str], UsageTotals] = {}
        for usage in self.usage.values():
            result.setdefault((usage.agent_id, usage.source), UsageTotals()).add(usage)
        return result

    def usage_timeline(self) -> list[dict[str, Any]]:
        """Latest per-attempt records, by recorded time; corrections replace.

        Each point contains a cumulative snapshot for its own source. Token
        subsets such as cached and reasoning tokens are deliberately not added.
        """
        running: dict[str, UsageTotals] = {}
        points = []
        for entry in sorted(self.usage.values(), key=lambda item: (item.elapsed_seconds, item.attempt_id)):
            total = running.setdefault(entry.source, UsageTotals())
            total.add(entry)
            points.append({
                "elapsed_seconds": entry.elapsed_seconds,
                "source": entry.source,
                "tokens": total.input_tokens + total.output_tokens,
                "unknown_tokens": total.unknown_input + total.unknown_output,
                "costs": dict(total.costs),
                "unknown_cost": total.unknown_cost,
            })
        return points

    def provenance(self, event_id: int) -> dict[str, Any]:
        selected = self.event_by_id[event_id]
        seen = {event_id}
        parents: list[dict[str, Any]] = []
        missing: list[int] = []
        stack = list(reversed(selected.get("parent_event_ids") or []))
        while stack:
            parent_id = stack.pop()
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = self.event_by_id.get(parent_id)
            if parent is None:
                missing.append(parent_id)
                continue
            parents.append(parent)
            stack.extend(reversed(parent.get("parent_event_ids") or []))
        artifact_id = selected.get("artifact_id")
        artifact_events = [
            item for item in self.events
            if artifact_id is not None and item.get("artifact_id") == artifact_id
        ]
        return {
            "selected_event": selected,
            "parent_events": parents,
            "missing_parent_event_ids": missing,
            "artifact_history": artifact_events,
        }


def project_events(events: Iterable[dict[str, Any]], config: dict[str, Any] | None = None) -> EventProjection:
    result = EventProjection(config)
    for event in events:
        result.apply(event)
    return result


def graph_position(identity: str, team_size: int) -> tuple[float, float]:
    """Stable normalized positions, unaffected by an agent's state or arrival."""
    fixed = {"scheduler": (0.32, 0.40), "verifier": (0.68, 0.40),
             "evaluator": (0.62, 0.57), "runtime": (0.38, 0.57), "system": (0.50, 0.57)}
    if identity in fixed:
        return fixed[identity]
    suffix = identity.removeprefix("agent-")
    if identity.startswith("agent-") and suffix.isdigit() and int(suffix) < max(team_size, 1):
        angle = 2 * math.pi * int(suffix) / max(team_size, 1) - math.pi / 2
    else:
        number = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big")
        angle = 2 * math.pi * number / (2 ** 64)
    return 0.5 + 0.39 * math.cos(angle), 0.44 + 0.30 * math.sin(angle)


@dataclass
class LogRead:
    events: list[dict[str, Any]]
    warnings: list[str]
    reset: bool = False


class JsonlTail:
    """Incrementally read complete JSONL records, retaining partial UTF-8 lines."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b""
        self.line_number = 0
        self.identity: tuple[int, int] | None = None

    def poll(self) -> LogRead:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return LogRead([], [])
        identity = (stat.st_dev, stat.st_ino)
        reset = self.identity is not None and (identity != self.identity or stat.st_size < self.offset)
        if reset:
            self.offset, self.pending, self.line_number = 0, b"", 0
        self.identity = identity
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            chunk = stream.read()
            self.offset = stream.tell()
        lines = (self.pending + chunk).split(b"\n")
        self.pending = lines.pop()
        events, warnings = [], []
        for line in lines:
            self.line_number += 1
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or type(event.get("event_id")) is not int:
                    raise ValueError("expected object with integer event_id")
                events.append(event)
            except (ValueError, UnicodeDecodeError) as exc:
                warnings.append(f"Line {self.line_number}: {exc}")
        return LogRead(events, warnings, reset)


def _amount(value: int, unknown: int) -> str:
    return f"{value:,}" + (" + ?" if unknown else "")


def _cost_text(total: UsageTotals) -> str:
    parts = [f"{amount:.6f} {currency}" for currency, amount in sorted(total.costs.items())]
    if total.unknown_cost:
        parts.append(f"{total.unknown_cost} unpriced")
    return " + ".join(parts) if parts else "—"


def launch(run_dir: str | Path) -> None:
    """Open a desktop window; requires a Python installation with Tk support."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise RuntimeError("The desktop display requires Python with Tkinter support.") from exc

    directory = Path(run_dir).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"Run directory does not exist: {directory}")
    config_path = directory / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Cannot open the desktop display. Run it in a graphical desktop session with Tk installed.") from exc
    _Display(window, directory, config, tk, ttk)
    window.mainloop()


class _Display:
    """Tk widgets are constructed only by launch(), never during headless import."""

    def __init__(self, window: Any, directory: Path, config: dict[str, Any], tk: Any, ttk: Any):
        self.window, self.directory, self.config = window, directory, config
        self.tk, self.ttk = tk, ttk
        self.reader = JsonlTail(directory / "events.jsonl")
        self.events: list[dict[str, Any]] = []
        self.projection = EventProjection(config)
        self.cursor = 0
        self.playing = False
        self.seeking = False
        self.error_text = ""
        self.follow = tk.BooleanVar(value=True)
        self.speed = tk.StringVar(value="8")
        self._build()
        self._poll()
        self._tick()

    def _build(self) -> None:
        tk, ttk, w = self.tk, self.ttk, self.window
        w.title(f"Agent Swarm Lab · {self.directory.name}")
        available_width, available_height = w.winfo_screenwidth() - 50, w.winfo_screenheight() - 100
        w.geometry(f"{min(1400, available_width)}x{min(940, available_height)}+20+40")
        w.minsize(min(1040, available_width), min(720, available_height))
        w.configure(background="#eef1f6")
        style = ttk.Style(w)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef1f6")
        style.configure("TLabel", background="#eef1f6", foreground="#172338", font=("Helvetica", 11))
        style.configure("Title.TLabel", font=("Helvetica", 22, "bold"))
        style.configure("Caption.TLabel", foreground="#52637a", font=("Helvetica", 10))
        style.configure("Status.TLabel", font=("Helvetica", 12, "bold"), padding=10,
                        background="#dfe8ff", foreground="#1f3d72")
        style.configure("Treeview", rowheight=25, font=("Helvetica", 10), background="#ffffff",
                        fieldbackground="#ffffff", foreground="#172338")
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
        outer = ttk.Frame(w, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="AGENT SWARM LAB", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text=str(self.directory), style="Caption.TLabel").pack(anchor="w", pady=(2, 9))
        self.banner = ttk.Label(outer, text="Waiting for recorded events", style="Status.TLabel")
        self.banner.pack(fill="x")
        self.metrics = ttk.Label(outer, text="", padding=(0, 10))
        self.metrics.pack(fill="x")
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 10))
        self.play_button = ttk.Button(controls, text="Play", command=self._toggle_play)
        self.play_button.pack(side="left")
        ttk.Button(controls, text="Step", command=self._step).pack(side="left", padx=5)
        ttk.Button(controls, text="Replay", command=self._replay).pack(side="left")
        ttk.Checkbutton(controls, text="Follow live log", variable=self.follow,
                        command=self._follow_changed).pack(side="left", padx=15)
        ttk.Label(controls, text="Events/sec").pack(side="left")
        ttk.Combobox(controls, textvariable=self.speed, values=("1", "4", "8", "20", "100"),
                     width=5, state="readonly").pack(side="left", padx=5)
        self.position = ttk.Label(controls, text="0 / 0")
        self.position.pack(side="right", padx=5)
        self.slider = ttk.Scale(controls, from_=0, to=1, command=self._seek)
        self.slider.pack(side="right", fill="x", expand=True, padx=14)

        upper = ttk.Panedwindow(outer, orient="horizontal")
        upper.pack(fill="both", expand=True)
        graph_frame = ttk.Frame(upper)
        right = ttk.Frame(upper)
        upper.add(graph_frame, weight=3)
        upper.add(right, weight=2)
        ttk.Label(graph_frame, text="TEAM · recorded state", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=4)
        self.graph = tk.Canvas(graph_frame, background="#101b2d", highlightthickness=0, height=325)
        self.graph.pack(fill="both", expand=True)
        self.graph.bind("<Configure>", lambda _event: self._draw_graph())
        legend = ttk.Frame(graph_frame)
        legend.pack(fill="x", pady=5)
        for category, color in EDGE_COLORS.items():
            ttk.Label(legend, text=f"● {category}  ", foreground=color).pack(side="left")
        ttk.Label(graph_frame, text="Recent recorded edges; connectivity does not establish cooperation.",
                  style="Caption.TLabel").pack(anchor="w")
        ttk.Label(right, text="PUBLIC EVENT & PROVENANCE", font=("Helvetica", 11, "bold")).pack(anchor="w", padx=10, pady=4)
        inspector_frame = ttk.Frame(right)
        inspector_frame.pack(fill="both", expand=True, padx=(10, 0))
        self.inspector = tk.Text(inspector_frame, wrap="word", font=("Menlo", 10), width=45,
                                 background="#ffffff", foreground="#172338", padx=10, pady=10,
                                 borderwidth=0, state="disabled")
        inspect_scroll = ttk.Scrollbar(inspector_frame, command=self.inspector.yview)
        self.inspector.configure(yscrollcommand=inspect_scroll.set)
        inspect_scroll.pack(side="right", fill="y")
        self.inspector.pack(side="left", fill="both", expand=True)
        self._inspect_text("Select an event below to inspect its public payload, assumptions, verification status, parent events, and artifact history.\n\nNo private reasoning is collected or synthesized by this display.")

        lower = ttk.Notebook(outer)
        lower.pack(fill="both", expand=True, pady=(12, 4))
        event_panel = ttk.Frame(lower)
        usage_panel = ttk.Frame(lower)
        lower.add(event_panel, text=" Activity & events ")
        lower.add(usage_panel, text=" Usage & budget ")
        self.event_table = self._table(event_panel, ("id", "time", "actor", "recipient", "event", "task", "verification"),
                                       (50, 85, 115, 115, 175, 135, 100), height=8)
        self.event_table.bind("<<TreeviewSelect>>", self._select_event)
        self.usage_description = ttk.Label(usage_panel, text="", style="Caption.TLabel", padding=5)
        self.usage_description.pack(fill="x")
        self.usage_graph = tk.Canvas(usage_panel, background="#ffffff", highlightthickness=0, height=135)
        self.usage_graph.pack(fill="x")
        self.usage_graph.bind("<Configure>", lambda _event: self._draw_usage())
        self.usage_table = self._table(usage_panel, ("agent", "source", "attempts", "input", "output", "cost"),
                                       (125, 105, 70, 130, 130, 250), height=4)
        self.footer = ttk.Label(outer, text="", style="Caption.TLabel")
        self.footer.pack(fill="x", pady=(5, 0))

    def _table(self, parent: Any, columns: tuple[str, ...], widths: tuple[int, ...], height: int) -> Any:
        frame = self.ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = self.ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for column, width in zip(columns, widths):
            table.heading(column, text=column.replace("_", " ").title())
            table.column(column, width=width, minwidth=45, stretch=True)
        scrollbar = self.ttk.Scrollbar(frame, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        table.pack(fill="both", expand=True)
        return table

    def _inspect_text(self, value: str) -> None:
        self.inspector.configure(state="normal")
        self.inspector.delete("1.0", "end")
        self.inspector.insert("1.0", value)
        self.inspector.configure(state="disabled")

    def _select_event(self, _event: Any = None) -> None:
        selection = self.event_table.selection()
        if selection:
            event_id = int(selection[0])
            if event_id in self.projection.event_by_id:
                self._inspect_text(json.dumps(self.projection.provenance(event_id), indent=2, ensure_ascii=False))

    def _toggle_play(self) -> None:
        self.playing = not self.playing
        self.follow.set(False)
        self._refresh_controls()

    def _step(self) -> None:
        self.playing = False
        self.follow.set(False)
        self._set_cursor(min(self.cursor + 1, len(self.events)))

    def _replay(self) -> None:
        self.follow.set(False)
        self.playing = True
        self._set_cursor(0)

    def _follow_changed(self) -> None:
        self.playing = False
        if self.follow.get():
            self._set_cursor(len(self.events))
        self._refresh_controls()

    def _seek(self, value: str) -> None:
        if self.seeking:
            return
        self.playing = False
        self.follow.set(False)
        self._set_cursor(round(float(value)))

    def _set_cursor(self, value: int) -> None:
        value = max(0, min(value, len(self.events)))
        if value < self.cursor:
            self.projection = EventProjection(self.config)
            self.cursor = 0
            self._inspect_text("Select a visible event to inspect public payload and provenance.")
        for event in self.events[self.cursor:value]:
            self.projection.apply(event)
        self.cursor = value
        self._render()

    def _poll(self) -> None:
        try:
            batch = self.reader.poll()
            if batch.reset:
                self.events.clear()
                self.cursor = 0
                self.projection = EventProjection(self.config)
            self.events.extend(batch.events)
            if batch.warnings:
                self.error_text = "Log warning: " + " | ".join(batch.warnings[-2:])
            if self.follow.get():
                self._set_cursor(len(self.events))
            else:
                self._refresh_controls()
        except (OSError, ValueError) as exc:
            self.error_text = f"Log read error: {exc}"
        self.footer.configure(text=self.error_text or
            "Only persisted public events are shown. Partial final JSONL records wait for a newline.")
        self.window.after(500, self._poll)

    def _tick(self) -> None:
        if self.playing:
            if self.cursor < len(self.events):
                self._set_cursor(self.cursor + 1)
            else:
                self.playing = False
                self._refresh_controls()
        self.window.after(max(10, round(1000 / int(self.speed.get()))), self._tick)

    def _refresh_controls(self) -> None:
        self.play_button.configure(text="Pause" if self.playing else "Play")
        self.position.configure(text=f"{self.cursor:,} / {len(self.events):,}")
        self.seeking = True
        self.slider.configure(to=max(1, len(self.events)))
        self.slider.set(self.cursor)
        self.seeking = False

    def _render(self) -> None:
        p = self.projection
        sources = ", ".join(sorted(p.totals())) or "no usage records"
        mode = p.mode.upper()
        if p.mode == "algorithmic":
            detail = "Deterministic/seeded computation · no LLM inference"
        elif p.mode == "scripted":
            detail = "Predetermined replay · no inference or emergence claims"
        elif p.mode == "live":
            detail = "Live-provider execution mode · usage status shown separately"
        else:
            detail = "Execution mode not recorded"
        self.banner.configure(text=f"{mode}   |   {detail}   |   Usage: {sources}")
        bound = lambda value: "?" if value is None else str(value)
        stop = p.stopping_reason or "not recorded"
        self.metrics.configure(text=(f"Verified bounds  {bound(p.lower_bound)} ≤ optimum ≤ {bound(p.upper_bound)}"
            f"     Gap {bound(p.gap)}     Recorded elapsed {p.elapsed_seconds:.3f}s"
            f"     Stop reason: {stop}"))
        self._refresh_controls()
        selected = self.event_table.selection()
        self.event_table.delete(*self.event_table.get_children())
        for event in p.events[-1500:]:
            self.event_table.insert("", "end", iid=str(event["event_id"]), values=(
                event["event_id"], f"{_elapsed(event):.3f}s", event.get("actor") or "—",
                event.get("recipient") or "—", event.get("event_type"), event.get("task_id") or "—",
                event.get("verification_status") or "—"))
        if selected and self.event_table.exists(selected[0]):
            self.event_table.selection_set(selected)
        elif p.events:
            self.event_table.see(str(p.events[-1]["event_id"]))
        self.usage_table.delete(*self.usage_table.get_children())
        for (agent, source), total in sorted(p.agent_totals().items()):
            self.usage_table.insert("", "end", values=(agent, source, total.attempts,
                _amount(total.input_tokens, total.unknown_input),
                _amount(total.output_tokens, total.unknown_output), _cost_text(total)))
        budget = []
        for key in ("token_limit", "cost_limit"):
            if key in p.config:
                budget.append(f"{key.replace('_', ' ')}: {p.config[key]}")
        for key, value in p.budget.items():
            budget.append(f"{key.replace('_', ' ')}: {value if value is not None else '?'}")
        self.usage_description.configure(text=(" · ".join(budget) or "No budget telemetry recorded") +
            "\nKnown cumulative totals only; ? means unknown. Cached/reasoning subsets are not added again.")
        self._draw_graph()
        self._draw_usage()

    def _draw_graph(self) -> None:
        c, p = self.graph, self.projection
        c.delete("all")
        width, height = max(c.winfo_width(), 600), max(c.winfo_height(), 300)
        count = p.config.get("agents", 0)
        if type(count) is not int or count < 1:
            count = max(1, sum(node.role != "infrastructure" for node in p.agents.values()))
        positions = {name: (x * width, y * height)
                     for name in p.agents for x, y in [graph_position(name, count)]}
        # Draw only the latest edge for each route/category; trace remains complete below.
        recent = {}
        for edge in p.edges[-60:]:
            recent[(edge.actor, edge.recipient, edge.category)] = edge
        for edge in recent.values():
            start, end = positions[edge.actor], positions[edge.recipient]
            if start == end:
                continue
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            inset = min(25, length / 3)
            c.create_line(start[0] + dx / length * inset, start[1] + dy / length * inset,
                          end[0] - dx / length * inset, end[1] - dy / length * inset,
                          fill=EDGE_COLORS[edge.category], width=1.5, arrow="last",
                          dash=(5, 3) if edge.category == "artifact" else ())
        for name, node in p.agents.items():
            x, y = positions[name]
            infrastructure = node.role == "infrastructure"
            radius = 13 if infrastructure else 19
            fill = "#27354a" if infrastructure else "#335083"
            if node.state == "working":
                fill = "#177568"
            elif node.state in {"failed", "rejected candidate"}:
                fill = "#96465b"
            tag = "node:" + name
            c.create_oval(x-radius, y-radius, x+radius, y+radius, fill=fill,
                          outline="#b4c9e7", width=1.5, tags=(tag,))
            c.create_text(x, y + radius + 12, text=name, fill="#f3f6ff", font=("Helvetica", 11, "bold"), tags=(tag,))
            label = node.role if infrastructure else f"{node.role} · {node.state}"
            if node.task_id:
                label += f"\n{node.task_id}"
            c.create_text(x, y + radius + 29, text=label, fill="#a9bbd3", font=("Helvetica", 9), tags=(tag,))
            c.tag_bind(tag, "<Button-1>", lambda _event, identity=name: self._inspect_agent(identity))
        if not p.agents:
            c.create_text(width / 2, height / 2, text="Waiting for recorded team and events", fill="#b4c9e7")

    def _inspect_agent(self, identity: str) -> None:
        node = self.projection.agents[identity]
        relevant = [event for event in self.projection.events
                    if identity in (event.get("actor"), event.get("recipient"))]
        self._inspect_text(json.dumps({"agent": vars(node), "recent_public_events": relevant[-8:]}, indent=2))

    def _draw_usage(self) -> None:
        c = self.usage_graph
        c.delete("all")
        width, height = max(c.winfo_width(), 850), max(c.winfo_height(), 135)
        points = self.projection.usage_timeline()
        if not points:
            c.create_text(width / 2, height / 2, text="No usage attempts recorded. No consumption is inferred.",
                          fill="#52637a", font=("Helvetica", 11))
            return
        colors = {"simulated": "#947345", "estimated": "#9578aa", "reported": "#178b7b",
                  "reconciled": "#426ece", "unknown": "#787878"}
        currencies = sorted({currency for point in points for currency in point["costs"]})
        charts = [("tokens", None)] + [("cost", currency) for currency in currencies]
        panel_width = width / len(charts)
        max_time = max(0.001, max(point["elapsed_seconds"] for point in points))
        for panel_index, (metric, currency) in enumerate(charts):
            left, right = panel_index * panel_width + 55, (panel_index + 1) * panel_width - 18
            top, bottom = 32, height - 26
            values = [float(point["tokens"] if metric == "tokens" else point["costs"].get(currency, 0)) for point in points]
            maximum = max(values, default=0) or 1
            title = "Known input + output tokens" if metric == "tokens" else f"Known cost ({currency})"
            c.create_text(left, 13, anchor="w", text=title, fill="#172338", font=("Helvetica", 10, "bold"))
            c.create_line(left, top, left, bottom, right, bottom, fill="#b7c1d1")
            c.create_text(left - 6, top, anchor="e", text=f"{maximum:.4g}", fill="#52637a", font=("Helvetica", 9))
            c.create_text(left - 6, bottom, anchor="e", text="0", fill="#52637a", font=("Helvetica", 9))
            c.create_text(right, bottom + 12, anchor="e", text=f"{max_time:.3f}s recorded", fill="#52637a", font=("Helvetica", 9))
            for source in sorted({point["source"] for point in points}):
                coords = [left, bottom]
                for point, value in zip(points, values):
                    if point["source"] == source:
                        x = left + point["elapsed_seconds"] / max_time * (right-left)
                        y = bottom - value / maximum * (bottom-top)
                        coords.extend([x, coords[-1], x, y])
                c.create_line(*coords, fill=colors.get(source, "#787878"), width=2,
                              dash=(4, 3) if source in {"simulated", "estimated", "unknown"} else ())
        legend_x = width - 10
        for source in sorted({point["source"] for point in points}, reverse=True):
            item = c.create_text(legend_x, 13, text=f"● {source}  ", anchor="e", fill=colors.get(source, "#787878"),
                                 font=("Helvetica", 9))
            bbox = c.bbox(item)
            if bbox:
                legend_x = bbox[0] - 2


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Replay or tail a saved Agent Swarm Lab run in a local desktop window")
    parser.add_argument("run_dir", type=Path)
    launch(parser.parse_args().run_dir)
