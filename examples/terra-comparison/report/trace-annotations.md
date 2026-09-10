# Annotated public trace

Selection rule: earliest scheduled adaptive run containing a delivered message; select its first delivery, the first receiver observation containing that delivery, and a valid candidate from that receiver in the same decision task.

These are recorded public actions and policy-reported provenance. Temporal order and a reported use do not establish that the message caused an improvement. No private reasoning text is collected.

Receiver reported using this delivery in the selected candidate task: True. Matching artifact-used event IDs: [16].

Run: `r01-adaptive`; repetition 1; condition adaptive; status failed.

## Event 9: message_delivered

Actor: `agent-0`; recipient: `agent-1`; task: `None`; elapsed: 5.471468708943576 seconds.

```json
{
  "content": {
    "assumptions": "Find and verify any larger 3-term-AP-free subset of 1..24; this size-8 ternary-digit construction is a baseline.",
    "candidate": [
      1,
      2,
      4,
      5,
      10,
      11,
      13,
      14
    ]
  },
  "recipient": "agent-1",
  "type": "request_help"
}
```

## Event 13: observation

Actor: `agent-1`; recipient: `None`; task: `task-1`; elapsed: 5.4720774999586865 seconds.

```json
{
  "agent_id": "agent-1",
  "condition": "adaptive",
  "m": 24,
  "mailbox": [
    {
      "actor": "agent-0",
      "content": {
        "assumptions": "Find and verify any larger 3-term-AP-free subset of 1..24; this size-8 ternary-digit construction is a baseline.",
        "candidate": [
          1,
          2,
          4,
          5,
          10,
          11,
          13,
          14
        ]
      },
      "event_id": 9,
      "type": "request_help"
    }
  ],
  "peers": [
    "agent-0",
    "agent-2",
    "agent-3"
  ],
  "private_best": [],
  "role": "searcher",
  "round": 0,
  "task_id": "task-1"
}
```

## Event 18: verification

Actor: `verifier`; recipient: `agent-1`; task: `task-1`; elapsed: 70.63460358395241 seconds.

```json
{
  "assumptions": "Universe 1..24; no distinct 3-term AP",
  "candidate": [
    1,
    2,
    4,
    5,
    10,
    11,
    13,
    14
  ],
  "lower_bound": 8,
  "parent_event_ids": [
    17
  ],
  "reason": "valid",
  "upper_bound": 24,
  "valid": true
}
```
