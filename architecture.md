# Architecture — EC_POLICY_V2 Multi-Agent Pipeline

## Runtime graph

```text
Coordinator (NVIDIA NIM / Llama-3.1-8B)
  -> Customer (NVIDIA / Llama-3.1-8B; EC_001 canary: OpenRouter / Nemotron Nano 9B V2 free)
  -> Order & Product (NVIDIA NIM / Llama-3.1-8B)
  -> Payment (NVIDIA NIM / Llama-3.1-8B)
  -> Delivery (NVIDIA NIM / Llama-3.1-8B)
  -> Policy (NVIDIA NIM / Llama-3.1-8B)
  -> Verifier (NVIDIA NIM / Llama-3.1-8B)
  -> Coordinator writes the validated JSON
```

The graph is implemented with LangGraph. Each node invokes its assigned OpenAI-compatible provider endpoint, receives only a domain-specific handoff, and logs the model call. Python tools calculate money, timestamps, joins and ID existence deterministically; agents are not allowed to create facts that are absent from the CSV files.

## Handoff contracts and permissions

| Agent | Model | Read permission | Handoff |
|---|---|---|---|
| Coordinator | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | input JSON and validated handoffs | case task / final synthesis acknowledgement |
| Customer | NVIDIA / `meta/llama-3.1-8b-instruct`; `EC_001` canary: OpenRouter / `nvidia/nemotron-nano-9b-v2:free` | orders, customers | `customer_unique_id`, ordered related order IDs |
| Order & Product | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | orders, items, products, sellers, category translation | item, seller, product, category and shipping-limit facts |
| Payment | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | payments plus item/freight facts | payment IDs/types/totals/reconciliation |
| Delivery | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | orders and item shipping limits | delivery/handoff variance and late sellers |
| Policy | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | typed handoffs and EC_POLICY_V2 only | primary/secondary issue, cause, party, refund, actions |
| Verifier | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | typed draft and validation results | approval acknowledgement; deterministic schema gate is final |

`reviews` and `geolocation` are loaded with the source repository for audit completeness, but do not affect a policy decision or evidence because the lab output schema has no fields or permitted evidence IDs for them.

## Reliability and data controls

- `OPENROUTER_API_KEY` and `NVIDIA_API_KEY` are loaded only from `.env`; secrets are ignored by Git.
- The model configuration is static in source and keeps every assigned model at or below 10B parameters. OpenRouter's selected model is an explicitly free variant; NVIDIA exposes the selected NIM as a free development endpoint.
- OpenRouter is scoped to the `EC_001` Customer canary. All remaining calls use NVIDIA so one complete 50-case run stays inside the basic OpenRouter free-request budget.
- Every model call retries twice. The submission runner is strict: an agent failure aborts the case and leaves the current `output/` untouched.
- NVIDIA calls are paced at a 1.7-second minimum interval. HTTP 429 schedules a traced 35-second backoff before the final retry; other errors retry without provider fallback.
- Outputs are written to a staging directory, validated as a complete 50-file set, then promoted to `output/`.
- Final validation reconstructs every scored field independently from CSV facts and the deterministic EC_POLICY_V2 engine. A schema-valid but source-inconsistent output is rejected.
- All BRL calculations use `Decimal`; all timestamps retain CSV formatting or become `null`.
- Root-level `trace.jsonl` is overwritten each run and records agent/model/provider/timing/status without secrets or chain-of-thought. Root-level `metadata.json` records the same run ID, model limits, provider/agent counts, retry statistics and issue distribution.
