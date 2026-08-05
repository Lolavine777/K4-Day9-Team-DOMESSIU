# Member Role Report — Day 9: Multi-Agent E-commerce Dispute Resolution

> Rename this file to `individual_<5 số cuối MSSV>_<HoVaTen>.md` and replace bracketed identity fields before submission.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | [Họ và tên] |
| MSSV | [MSSV] |
| Khóa/Lớp | K4 |
| Vai trò chính | [Vai trò trong nhóm] |
| Ngày hoàn thành | [YYYY-MM-DD] |

## 2. Vai trò và phần việc sở hữu

| Deliverable | Input | Output | Xác minh |
|---|---|---|---|
| [Ví dụ: Payment Agent] | order items, payments | reconciliation handoff | `pytest` và `validate` |
| [Ví dụ: Verifier] | policy draft, CSV-backed IDs | output JSON hợp schema | `python -m dispute_agents validate` |

Chỉ liệt kê phần trực tiếp thực hiện. Ghi rõ người/module nhận handoff từ phần việc này.

## 3. Giải thích kỹ thuật

### Vấn đề giải quyết

[Mô tả domain agent phụ trách: customer history, order/product, payment, delivery, policy hoặc verification.]

### Cách triển khai

[Mô tả model dùng, tool CSV được phép gọi, Pydantic handoff schema, cách tránh suy diễn dữ liệu và cách xử lý lỗi.]

### Contract

| Thành phần | Nội dung |
|---|---|
| Input | [Case/handoff/tool facts] |
| Output | [Tên handoff hoặc artifact] |
| Consumer | [Agent/module nhận kết quả] |
| Failure handling | [Retry, reject, schema validation] |

## 4. Xác minh

```powershell
python -m pip install -e .
python -m pytest -q
python -m dispute_agents preflight-models
python -m dispute_agents run
python -m dispute_agents validate
```

- Kết quả mong đợi: 50 output JSON hợp schema; trace thể hiện đủ model invocation; metadata ghi model/runtime.
- Artifact: `output/`, `logging/trace.jsonl`, `logging/metadata.json`.

## 5. Một quyết định kỹ thuật

- Bối cảnh: policy cần kết quả chính xác và tái lập, trong khi từng agent vẫn phải sử dụng model ≤10B.
- Phương án cân nhắc: để LLM tự tính toàn bộ; hoặc dùng LLM phân tích facts do tool xác định.
- Phương án chọn: model-backed agent với tool tính `Decimal`, datetime, join CSV và verifier schema.
- Lý do: đảm bảo multi-agent thật, đồng thời không suy diễn và không sai số tiền/timestamp.

## 6. Hiểu biết end-to-end

1. `claimed_order_id` đi vào Coordinator, sau đó các domain agent tạo customer/order/payment/delivery handoff.
2. Policy Agent áp dụng EC_POLICY_V2 theo thứ tự ưu tiên; Verifier kiểm tra lại evidence, limits, refund và schema.
3. Chỉ output đã qua verifier mới được ghi staging rồi promote thành 50 JSON chính thức.
4. `trace.jsonl` là bằng chứng runtime của agent/model/tool handoff; `metadata.json` là cấu hình và thống kê run.
5. Không có item thì totals item/freight là `0.0`, còn expected/difference/reconciled là `null`; đây là trường hợp cần kiểm thử riêng.

## 7. Cam kết

- [ ] Nội dung phản ánh đúng phần việc trực tiếp thực hiện.
- [ ] Không chứa API key, token hoặc secret.
- [ ] Đã chạy lệnh xác minh thực tế trước khi ký.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]
