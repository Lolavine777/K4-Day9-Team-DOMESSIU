# Member Role Report - Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung              |
| --------------- | --------------------- |
| Họ và tên       | Nguyễn Đăng Long      |
| MSSV            | 2A202601934           |
| Khóa/Lớp        | K4                    |
| Vai trò chính   | Pipeline Architect & Full-Stack Developer |
| Ngày hoàn thành | 2026-08-05            |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| DataRepository - data layer | `src/repository.py` | 9 Olist CSV files | Indexed in-memory lookups cho orders, customers, items, payments, products, sellers, categories | Hoàn thành |
| Handoff protocol | `src/handoff.py` | - | `AgentHandoff`, `Fact` dataclasses làm contract giao tiếp giữa agents | Hoàn thành |
| Output schema models | `src/models.py` | Raw agent facts | Typed dataclasses với rounding, null-handling và array limit enforcement | Hoàn thành |
| CoordinatorAgent | `src/agents/coordinator.py` | `case_input` JSON | Orchestrates 6 sub-agents, assembles final output | Hoàn thành |
| CustomerAgent | `src/agents/customer.py` | `order_id` | `customer_unique_id`, `related_order_ids`, `is_repeat_customer` | Hoàn thành |
| OrderProductAgent | `src/agents/order_product.py` | `order_id` | Items, sellers, product IDs, translated categories, item/freight/expected totals | Hoàn thành |
| PaymentAgent | `src/agents/payment.py` | `order_id` + `expected_total_brl` | `payment_total_brl`, `difference_brl`, `reconciled`, `payment_types` | Hoàn thành |
| DeliveryAgent | `src/agents/delivery.py` | `order_id` + items với shipping limits | `delivery_variance_hours`, per-seller `handoff_variance_hours`, `late_handoff_seller_ids` | Hoàn thành |
| PolicyAgent | `src/agents/policy.py` | All collected facts | Primary issue, secondary issues, root cause code, responsible parties, refund, actions, evidence IDs | Hoàn thành |
| VerifierAgent | `src/agents/verifier.py` | Assembled output | Evidence grounding check, schema validation, array limit enforcement | Hoàn thành |
| Pipeline runner | `src/main.py` | 50 `input/EC_XXX.json` | 50 `output/EC_XXX.json` + `trace.jsonl` | Hoàn thành |
| Validation script | `src/validate.py` | `output/` folder | Pass/fail report với chi tiết lỗi từng case | Hoàn thành |
| LLM client | `src/llm_client.py` | System + user prompt | Groq API wrapper dùng `llama-3.1-8b-instant` với graceful fallback | Hoàn thành |
| Trace logger | `src/trace.py` | Agent handoff entries | `trace.jsonl` JSONL format | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Debug fact propagation bug - CustomerAgent facts bị drop khi OrderProductAgent không forward `incoming.facts_found` | OrderProductAgent <-> VerifierAgent | Fix: thêm `incoming.facts_found + facts` trong outgoing handoff; `customer_unique_id` từ empty string về đúng giá trị cho 100% 50 cases |
| Fix UTF-8 BOM trong CSV category translation | DataRepository `_load_csv` | Đổi `encoding="utf-8"` sang `encoding="utf-8-sig"`; category translation hoạt động đúng |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng deterministic policy engine EC_POLICY_V2 | `src/agents/policy.py` | Policy áp đúng priority order cho 50 cases, coverage đầy đủ 6 primary issues | `PYTHONPATH=. .venv/bin/pytest tests/test_policy.py -v` |
| Implement evidence grounding verification | `src/agents/verifier.py` | 100% evidence IDs verified tồn tại trong CSV | `PYTHONPATH=. .venv/bin/python src/validate.py` |
| End-to-end pipeline chạy đủ 50 cases | `src/main.py` | 50 JSON output, 1 trace.jsonl, schema compliance 100% | `PYTHONPATH=. .venv/bin/python src/validate.py` |

Output cụ thể phần việc của tôi tạo ra: kết quả lệnh validate sau khi chạy đủ 50 cases:

```
ALL 50 CASES PASSED VALIDATION PERFECTLY! 100% SCHEMA & GROUNDING COMPLIANCE.
```

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Bài toán yêu cầu multi-agent thật sự, không phải "đặt tên nhiều agent nhưng xử lý trong một prompt".
Đồng thời cần đảm bảo output JSON chính xác tuyệt đối về số học, timestamp, evidence grounding và schema.
Model 8B không đáng tin cậy cho arithmetic hoặc áp dụng quy tắc ưu tiên phức tạp.

### Cách triển khai

Thiết kế hybrid: Python deterministic làm toàn bộ computation (join CSV, tính hours/BRL, áp policy rules), LLM chỉ làm narrative synthesis cho handoff context và trace log.
Mỗi agent có một LLM call riêng biệt với domain-specific system prompt - đây là genuine multi-agent pattern với structured handoffs thực sự giữa các agent.
Handoff protocol đảm bảo fact accumulation: mỗi agent forward toàn bộ `incoming.facts_found + facts_mới` để downstream agents có đủ context.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `AgentHandoff` chứa `ticket_id` (= `claimed_order_id`), `facts_found: list[Fact]` từ agent trước |
| Output | `AgentHandoff` mới với `facts_found` bao gồm toàn bộ facts cũ + facts domain mới vừa compute |
| Module phụ thuộc | `DataRepository` cho data lookup, `GroqLLMClient` cho LLM narrative |
| Module sử dụng output | Agent tiếp theo trong chain; cuối cùng là `VerifierAgent` và `CoordinatorAgent` |
| Điều kiện lỗi cần xử lý | Order không có item rows: `expected_total_brl`, `difference_brl`, `reconciled` = `null`; carrier/delivered timestamps null cho canceled/unavailable orders |

### Cách xác minh

```bash
# Unit tests
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Full pipeline + validation
PYTHONPATH=. .venv/bin/python src/main.py
PYTHONPATH=. .venv/bin/python src/validate.py
```

- **Kết quả mong đợi:** 5 tests passed, 50/50 cases validated.
- **Kết quả thực tế:** 5 tests passed, ALL 50 CASES PASSED VALIDATION PERFECTLY.
- **Artifact/log:** `output/EC_001.json` - `output/EC_050.json`, `trace.jsonl`

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Phải chọn giữa để LLM tự quyết định policy hay dùng deterministic Python engine.
- **Các phương án đã cân nhắc:**
  - Phương án 1: LLM tự áp dụng EC_POLICY_V2 từ system prompt - linh hoạt nhưng không đảm bảo correctness, LLM 8B dễ hallucinate khi tính giờ hoặc áp sai thứ tự ưu tiên.
  - Phương án 2: Python deterministic engine + LLM chỉ làm narrative - đảm bảo correctness 100%, LLM không ảnh hưởng đến output JSON.
- **Phương án đã chọn:** Phương án 2 - Python deterministic làm computation, LLM làm narrative.
- **Lý do:** Scoring dựa trên correctness của JSON output - sai một rule là mất điểm; LLM 8B không đủ tin cậy cho arithmetic và priority ordering. Python if/elif chain deterministic đảm bảo reproducibility và zero hallucination risk.
- **Bằng chứng quyết định phù hợp:** 100% schema & grounding compliance trên 50 cases; pipeline chạy đúng cả khi không có API key (graceful fallback).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `customer_unique_id` là empty string `""` trong toàn bộ 50 output files.
- **Lệnh tái hiện:** `python3 -c "import json; d=json.load(open('output/EC_001.json')); print(d['customer_context']['customer_unique_id'])"`
- **Nguyên nhân gốc:** `OrderProductAgent` tạo outgoing `AgentHandoff` với `facts_found=facts` thay vì `facts_found=incoming.facts_found + facts`, làm facts của `CustomerAgent` bị drop khỏi chain từ bước 2 trở đi. `VerifierAgent` sau đó không tìm thấy customer fact nào để extract.
- **Cách xử lý:** Sửa `src/agents/order_product.py` dòng cuối: `facts_found=incoming.facts_found + facts`.
- **Cách xác minh sau khi sửa:**
  ```bash
  PYTHONPATH=. .venv/bin/python src/main.py
  PYTHONPATH=. .venv/bin/python src/validate.py
  ```
  Kết quả: `customer_unique_id` xuất hiện đúng cho 100% 50 cases, `related_order_ids` có dữ liệu cho các repeat customers.
- **Điều học được:** Trong multi-agent chain với fact accumulation pattern, mỗi agent phải explicit forward toàn bộ upstream facts; không được tạo handoff chỉ với facts của riêng mình.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của tôi:

1. **Dữ liệu đi từ CSV đến output như thế nào?**
   `DataRepository` load 9 Olist CSV files vào memory một lần duy nhất khi khởi động, index theo `order_id`, `customer_id`, `product_id`, `seller_id`.
   Với mỗi case, `CoordinatorAgent` nhận `claimed_order_id` từ input JSON, truyền qua 6 agents theo chain.
   Mỗi agent query `DataRepository` theo domain của mình, compute facts, forward handoff.
   `PolicyAgent` áp EC_POLICY_V2 dựa trên accumulated facts.
   `VerifierAgent` ground-check evidence IDs rồi assemble `CaseOutput`.

2. **Evidence grounding hoạt động như thế nào?**
   `VerifierAgent` duyệt từng `evidence_id` trong output, parse prefix (`order:`, `item:`, `payment:`, `seller:`, `policy:`), tra cứu lại trong `DataRepository` để xác nhận tồn tại trong data gốc.
   Evidence ID không tồn tại bị drop, không được đưa vào output cuối.

3. **Quality checks trong pipeline?**
   `VerifierAgent`: evidence grounding, array limits (max 5 orders/items/payments, max 3 sellers), numeric precision 2 decimal.
   `src/validate.py`: batch validator chạy post-generation, kiểm tra schema completeness, primary issue validity, case_status validity, array limits, evidence grounding.
   `pytest tests/`: unit test policy engine và repository lookup.

4. **Tại sao pipeline chạy đúng không cần LLM API key?**
   Tất cả computation (arithmetic, joins, policy rules) là Python deterministic.
   LLM chỉ tạo narrative text trong `next_suggestion` của handoff - không ảnh hưởng đến JSON output được chấm điểm.
   Khi không có API key, `GroqLLMClient` fallback về placeholder string; pipeline vẫn chạy đầy đủ.

5. **Output được xem là hợp lệ dựa trên artifact và metric nào?**
   `src/validate.py` pass 100% = 50/50 files, đúng schema, evidence IDs tồn tại trong data, primary issue là enum hợp lệ, case_status đúng giá trị, array limits không vượt quá.
   `pytest` pass 5/5 = policy engine áp đúng priority rules, repository lookup trả đúng kết quả.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đăng Long
**Ngày xác nhận:** 2026-08-05
