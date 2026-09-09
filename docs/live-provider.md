# Live provider configuration

The adapter is implemented but has only been exercised with mocked provider responses. No credentials or paid model calls were used in the implementation campaign. Obtain a concrete run ceiling before a paid experiment; repository/PR permission does not authorize inference spend.

The request uses the [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create) with an explicit model, default service tier, `store=false`, a strict JSON action schema, and `max_output_tokens`. Official documentation checked 2026-09-09 says this output limit includes reasoning tokens. There are no hosted tools, image/audio inputs, batch calls, cache writes/storage products, or arbitrary code execution. Providers with different billing rules require a separate adapter and ledger normalization.

Set `OPENAI_API_KEY` using your shell or secret manager. The application does not load `.env` automatically. Never put credentials in the price snapshot, command line, source, prompt or Git history.

Create a local ignored price file, for example under `runs/config/price.json`. Verify the current official price page and exact model before filling the fields below. These strings are placeholders and deliberately cannot be used as rates:

```json
{
  "provider": "openai",
  "model": "EXACT_MODEL_ID",
  "service_tier": "default",
  "currency": "USD",
  "version": "OWNER_ASSIGNED_SNAPSHOT_VERSION",
  "rate_units": "per_million_tokens",
  "input_per_million": "VERIFIED_DECIMAL_RATE",
  "cached_input_per_million": "VERIFIED_DECIMAL_RATE",
  "output_per_million": "VERIFIED_DECIMAL_RATE",
  "effective_date": "YYYY-MM-DD",
  "retrieved_date": "YYYY-MM-DD",
  "verified_on": "YYYY-MM-DD",
  "source_url": "https://developers.openai.com/api/docs/pricing",
  "simulated": false
}
```

`verified_on` must equal the run date. This is the operator's attestation, not automatic verification of the website. Read the official source and account-specific pricing; a URL alone does not establish correctness. The frozen snapshot must match the requested model and default service tier. Price files are copied into run metadata, so they must contain prices only.

After authorization, substitute the agreed ceilings and model:

```sh
python -m swarm_lab run --mode live --allow-live \
  --model EXACT_MODEL_ID --price-file runs/config/price.json \
  --agents 1 --condition solo --steps 3 --concurrency 1 \
  --max-output 512 --max-retries 0 \
  --token-limit AGREED_TOKEN_CEILING --cost-limit AGREED_USD_CEILING \
  --out runs/live-pilot
```

All actual attempts, including failed requests and retries, share both ceilings. Input reservations use a conservative UTF-8-byte count of the complete request, schema and framing allowance. Context-component attribution is estimated. Output reservation includes the configured maximum generation; reasoning subsets are not charged twice. These limits reduce overshoot but cannot promise absolute billing control: actual tokenization or provider accounting may differ, and a transport timeout does not prove the provider stopped. Pending/ambiguous charges keep their reservations, and overshoot is reported explicitly.

The adapter waits for bounded HTTP calls and does not silently retry inside an SDK. Runtime retries have separate attempt IDs and go through budget admission. Missing usage is retained as unknown. If a returned service tier differs from the frozen price, the request retains a conservative unresolved reservation and its raw usage is preserved in the event log for investigation. Actual model/version and tier are recorded in provider-result events and usage metadata when available.

The next proposed paid experiment is the three-decision solo pilot above, with no automatic retries. Its purpose is to verify provider usage, schema behavior and reconciliation before any team comparison. No amount is preauthorized by this document.
