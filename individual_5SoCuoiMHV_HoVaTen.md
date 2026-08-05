# Member Role Report — Day 9: Multi-Agent E-commerce Dispute Resolution

> Rename this file to `individual_<5 số cuối MSSV>_<HoVaTen>.md` and replace bracketed identity fields before submission.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | [Họ và tên] |
| MSSV | [MSSV] |
| Khóa/Lớp | K4 |
| Vai trò chính | Multi-agent pipeline, policy engine và verifier |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phần việc sở hữu

| Deliverable | Input | Output | Xác minh |
|---|---|---|---|
| Payment/Delivery tools | order items, payments, order timestamps | reconciliation và variance handoff | `pytest` và source-backed `validate` |
| Policy Agent | bốn typed handoff, `EC_POLICY_V2` | issue, cause, party, refund, actions | policy priority/distribution tests |
| Verifier/CLI | policy draft, CSV-backed IDs, runtime trace | 50 JSON, trace, metadata, submission zip | `validate` và zip manifest check |

## 3. Giải thích kỹ thuật

### Vấn đề giải quyết

Pipeline xử lý 50 complaint case, join chín CSV bằng `claimed_order_id`, phân loại theo đúng ưu tiên EC_POLICY_V2 và hard-gate mọi trường có trọng số trước khi nộp.

### Cách triển khai

Mỗi node LangGraph gọi model ≤10B qua NVIDIA hoặc OpenRouter rồi xác nhận một Pydantic handoff do tool CSV dựng. `Decimal` và datetime được tính trong Python; model không được tạo amount, timestamp hoặc evidence ID. NVIDIA được pace chủ động; HTTP 429 backoff 35 giây; response rỗng/sai schema bị retry rồi fail strict.

### Contract

| Thành phần | Nội dung |
|---|---|
| Input | Case JSON và domain-specific CSV/tool facts |
| Output | Typed handoff hoặc `CaseOutput` đúng schema |
| Consumer | Agent kế tiếp, Policy, Verifier và CLI artifact gate |
| Failure handling | Hai attempt, 429 backoff, Pydantic reject, atomic staging |

## 4. Xác minh

```powershell
python -m pip install -e .
python -m pytest -q
python -m dispute_agents preflight-models
python -m dispute_agents run
python -m dispute_agents validate
```

- Kết quả thực tế: 17 test passed; 50/50 output source-backed hợp lệ; 400 model call thành công sau 402 attempt; 2 lần HTTP 429 được backoff và retry thành công.
- Phân bố issue: 8 canceled, 6 unavailable, 10 seller-late, 10 logistics-late, 8 valid split-payment, 8 unsupported claim.
- Artifact: `output/`, root-level `trace.jsonl`, root-level `metadata.json`.

## 5. Một quyết định kỹ thuật

- Bối cảnh: policy cần kết quả chính xác và tái lập, trong khi từng agent vẫn phải sử dụng model ≤10B.
- Phương án cân nhắc: để LLM tự tính toàn bộ; hoặc dùng LLM phân tích facts do tool xác định.
- Phương án chọn: model-backed agent với tool tính `Decimal`, datetime, join CSV và verifier schema.
- Lý do: đảm bảo multi-agent thật, đồng thời không suy diễn và không sai số tiền/timestamp.

## 6. Hiểu biết end-to-end

1. `claimed_order_id` đi vào Coordinator, sau đó các domain agent tạo customer/order/payment/delivery handoff.
2. Policy Agent áp dụng EC_POLICY_V2 theo thứ tự ưu tiên; Verifier kiểm tra lại evidence, limits, refund và schema.
3. Chỉ output đã qua verifier mới được ghi staging rồi promote thành 50 JSON chính thức.
4. Root-level `trace.jsonl` là bằng chứng runtime của agent/model/tool handoff; `metadata.json` là cấu hình và thống kê run.
5. Không có item thì totals item/freight là `0.0`, còn expected/difference/reconciled là `null`; đây là trường hợp cần kiểm thử riêng.

## 7. Cam kết

- [ ] Nội dung phản ánh đúng phần việc trực tiếp thực hiện.
- [ ] Không chứa API key, token hoặc secret.
- [ ] Đã chạy lệnh xác minh thực tế trước khi ký.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]
