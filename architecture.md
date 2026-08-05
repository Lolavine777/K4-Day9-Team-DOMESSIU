# Architecture — EC_POLICY_V2 Multi-Agent Pipeline

## Runtime graph

```text
Coordinator (Ollama / Qwen3-8B)
  -> Customer (OpenRouter / Nemotron Nano 9B V2 free)
  -> Order & Product (NVIDIA NIM / Llama-3.1-8B)
  -> Payment (Ollama / Qwen3-8B)
  -> Delivery (NVIDIA NIM / Llama-3.1-8B)
  -> Policy (Ollama / Qwen3-8B)
  -> Verifier (NVIDIA NIM / Llama-3.1-8B)
  -> Coordinator writes the validated JSON
```

The graph is implemented with LangGraph. Each node invokes its assigned OpenAI-compatible provider endpoint, receives only a domain-specific handoff, and logs the model call. Python tools calculate money, timestamps, joins and ID existence deterministically; agents are not allowed to create facts that are absent from the CSV files.

## Handoff contracts and permissions

| Agent | Model | Read permission | Handoff |
|---|---|---|---|
| Coordinator | Ollama / `qwen3:8b` | input JSON and validated handoffs | case task / final synthesis acknowledgement |
| Customer | OpenRouter / `nvidia/nemotron-nano-9b-v2:free` | orders, customers | `customer_unique_id`, ordered related order IDs |
| Order & Product | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | orders, items, products, sellers, category translation | item, seller, product, category and shipping-limit facts |
| Payment | Ollama / `qwen3:8b` | payments plus item/freight facts | payment IDs/types/totals/reconciliation |
| Delivery | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | orders and item shipping limits | delivery/handoff variance and late sellers |
| Policy | Ollama / `qwen3:8b` | typed handoffs and EC_POLICY_V2 only | primary/secondary issue, cause, party, refund, actions |
| Verifier | NVIDIA NIM / `meta/llama-3.1-8b-instruct` | typed draft and validation results | approval acknowledgement; deterministic schema gate is final |

`reviews` and `geolocation` are loaded with the source repository for audit completeness, but do not affect a policy decision or evidence because the lab output schema has no fields or permitted evidence IDs for them.

## Reliability and data controls

- `OPENROUTER_API_KEY` and `NVIDIA_API_KEY` are loaded only from `.env`; Ollama is called locally without a key. Secrets are ignored by Git.
- The model configuration is static in source and keeps every assigned model at or below 10B parameters. OpenRouter's selected model is an explicitly free variant; NVIDIA exposes the selected NIM as a free development endpoint.
- Every model call retries twice. The submission runner is strict: an agent failure aborts the case and leaves the current `output/` untouched.
- Outputs are written to a staging directory, validated as a complete 50-file set, then promoted to `output/`.
- All BRL calculations use `Decimal`; all timestamps retain CSV formatting or become `null`.
- `trace.jsonl` is overwritten each run and records agent/model/provider/timing/status without secrets or chain-of-thought.
