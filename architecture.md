# Architecture — EC_POLICY_V2 Multi-Agent Pipeline

## Runtime graph

```text
Coordinator (Qwen3-8B)
  -> Customer (Qwen2.5-7B)
  -> Order & Product (Llama-3.1-8B)
  -> Payment (Qwen2.5-7B)
  -> Delivery (Llama-3.1-8B)
  -> Policy (DeepSeek-R1-Distill-Qwen-7B)
  -> Verifier (Qwen3-8B)
  -> Coordinator writes the validated JSON
```

The graph is implemented with LangGraph. Each node invokes its assigned Hugging Face model, receives only a domain-specific handoff, and logs the model call. Python tools calculate money, timestamps, joins and ID existence deterministically; agents are not allowed to create facts that are absent from the CSV files.

## Handoff contracts and permissions

| Agent | Model | Read permission | Handoff |
|---|---|---|---|
| Coordinator | Qwen3-8B | input JSON and validated handoffs | case task / final synthesis acknowledgement |
| Customer | Qwen2.5-7B | orders, customers | `customer_unique_id`, ordered related order IDs |
| Order & Product | Llama-3.1-8B | orders, items, products, sellers, category translation | item, seller, product, category and shipping-limit facts |
| Payment | Qwen2.5-7B | payments plus item/freight facts | payment IDs/types/totals/reconciliation |
| Delivery | Llama-3.1-8B | orders and item shipping limits | delivery/handoff variance and late sellers |
| Policy | DeepSeek Distill 7B | typed handoffs and EC_POLICY_V2 only | primary/secondary issue, cause, party, refund, actions |
| Verifier | Qwen3-8B | typed draft and validation results | approval acknowledgement; deterministic schema gate is final |

`reviews` and `geolocation` are loaded with the source repository for audit completeness, but do not affect a policy decision or evidence because the lab output schema has no fields or permitted evidence IDs for them.

## Reliability and data controls

- `HF_TOKEN` is loaded only from `.env`; it is ignored by Git.
- Every model call retries twice. The submission runner is strict: an agent failure aborts the case and leaves the current `output/` untouched.
- Outputs are written to a staging directory, validated as a complete 50-file set, then promoted to `output/`.
- All BRL calculations use `Decimal`; all timestamps retain CSV formatting or become `null`.
- `trace.jsonl` is overwritten each run and records agent/model/provider/timing/status without secrets or chain-of-thought.
