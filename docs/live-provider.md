# Terra live setup

The adapter is ready for a bounded GPT-5.6 Terra pilot and has been tested with mocked responses. No paid model call is part of setup. A credit balance is funding, not an authorization to spend the balance; agree on a specific run ceiling before generation.

## Supply the key locally

From an interactive Terminal in this checkout:

```sh
python3 -m swarm_lab.credentials setup
```

Paste the API key at the hidden prompt and press Return. The input is not echoed or saved as a shell command. Setup writes only `.env`, with owner-only permissions (0600), and refuses to run unless Git ignores that file. It refuses to overwrite an existing file unless `setup --replace` is supplied. Interrupted setup temporary files also match the existing `.env.*` Git exclusion. The local file is plain text protected by filesystem permissions, not an encrypted vault.

The provider first uses `OPENAI_API_KEY` from its process environment, if present; otherwise it reads the protected `.env` in the current working directory. The file is parsed as data without shell evaluation. It is never copied into run settings or artifacts. Do not paste the key into chat, a price snapshot, source code or a command-line argument. If you already provide secrets through a shell or secret manager, keep using the environment instead of the setup command.

Check configuration and model visibility without generating output:

```sh
python3 -m swarm_lab.credentials status
python3 -m swarm_lab.credentials check --model gpt-5.6-terra
```

The check sends only an authenticated GET to the model metadata endpoint. It prints neither the key nor API error bodies. A successful check establishes model visibility for that key, not its Responses write permission or credit balance. HTTP 403 may mean the key lacks model-read permission; HTTP 404 may mean model access is unavailable. Inspect the key's project permissions if necessary. Your existing API key can be used if it has the required access; a separate project key is optional.

OpenAI documents key-based authentication and server-side environment/secret handling in the [API authentication reference](https://developers.openai.com/api/reference/overview#authentication).

## Prepared pilot and prices

The nonsecret [Terra price snapshot](../configs/gpt-5.6-terra-price.json) was checked against [official standard pricing](https://developers.openai.com/api/docs/pricing) on 2026-09-09. For short context, per million tokens: ordinary input USD 2.00; cache reads USD 0.20; cache writes USD 2.50; output USD 12.00. The effective date describes when this local snapshot was verified, not the original introduction date of the provider tariff. Confirm prices again on the day of the run; `verified_on` must equal that date.

After explicit authorization, the proposed first pilot is:

```sh
python3 -m swarm_lab run --mode live --allow-live \
  --model gpt-5.6-terra --price-file configs/gpt-5.6-terra-price.json \
  --reasoning-effort medium --timeout 120 \
  --m 12 --agents 1 --condition solo --steps 3 --concurrency 1 \
  --max-output 25000 --max-retries 0 \
  --token-limit 100000 --cost-limit 2.00 \
  --out runs/terra-pilot
```

This allows at most three generation attempts across the run, with no automatic retry. Both total ceilings apply to the whole run. They do not authorize the remainder of an account's credit balance. Use a new empty output directory for a new run.

The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) recommends initial reasoning/output headroom. `max_output_tokens` includes reasoning and visible output, so the old 512-token fixture setting is not the proposed live setting. Live effort is explicitly recorded (medium by default), and the CLI exposes the HTTP timeout so a deliberate reasoning call is not automatically cut off at the old 30-second default.

The old offline observations imply a conservative three-call reservation of approximately 84,231 units and USD 0.9231 with explicit medium reasoning and 25,000 output tokens per call. This uses a byte-based input estimate and the highest applicable input-bucket rate. It is planning arithmetic, not measured tokenization or a promise that live context will match an algorithmic trace.

## Accounting and execution limits

Requests use the [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), default service tier, `store=false`, an explicit model/effort and a strict candidate/message schema. There are no hosted tools, image/audio inputs, batch calls or arbitrary code execution. The context bound keeps these requests below the long-context pricing threshold. Other providers, regional endpoints, tools and billing tiers require their own verified configuration.

[Current caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching) reports cache reads and writes as disjoint subsets of input. The ledger computes ordinary input as input minus reads minus writes, then prices each bucket once. Reasoning is a subset of output and is not added twice. Reservations use the highest applicable ordinary/read/write input rate. If a new-tariff response omits required read/write counters, its token totals can be known while cost remains unresolved; the conservative currency reservation stays held. Legacy offline traces retain their original three-bucket semantics.

Each real attempt, failure and retry belongs to the same run budget. Input reservations include request bytes, schema, explicit settings and a framing allowance; they remain estimates. Unknown transport outcomes retain reservations. A timeout does not establish that server work was cancelled, and measured usage or later billing may exceed a local reservation. The ledger reports overshoot rather than promising an absolute provider billing cutoff. Every returned model/version, tier and raw usage object is retained without authorization headers or credentials.

Calculated cost from provider usage is distinct from a reconciled billing charge. `actual_model_cost` remains unknown until real charges are reconciled; `calculated_model_cost` shows the known estimate. No silent fallback substitutes offline output for failed live inference. Per-run ceilings exist; there is no automatic live campaign runner or shared multi-run ceiling yet.
