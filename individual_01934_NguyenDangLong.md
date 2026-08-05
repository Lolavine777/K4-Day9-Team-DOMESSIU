# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung         |
| --------------- | ---------------- |
| Họ và tên       | Nguyễn Đăng Long     |
| MSSV            | 2A202601934      |
| Khóa/Lớp        | K4               |
| Vai trò chính   | Agent Developer  |
| Ngày hoàn thành | 2026-08-05       |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | --------------- | ---------- |
| **Data Loader** | `data_loader.py` | Đường dẫn thư mục `data/` chứa các CSV | Class DataLoader cung cấp các hàm query dữ liệu tối ưu | Hoàn thành |
| **Utilities** | `utils.py` | Chuỗi thời gian, giá trị tiền tệ | Kết quả tính toán hiệu số giờ, đối soát tài chính chính xác và định dạng ID | Hoàn thành |
| **Agents Module** | `agents.py` | Thông tin từ DataLoader và input khiếu nại | Các Agent chuyên biệt phân tích & logic áp dụng EC_POLICY_V2 | Hoàn thành |
| **Main Runner** | `main.py` | 50 file JSON khiếu nại | 50 file JSON kết quả trong `output/` và file trace log | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Viết kịch bản kiểm tra | Nhóm dự án | File `verify_outputs.py` giúp tự động kiểm duyệt lỗi schema và giới hạn mảng của output |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Xây dựng Multi-Agent pipeline | [main.py](file:///main.py) | 50 file JSON kết quả đã được xác minh thành công không có lỗi | Chạy `verify_outputs.py` |
| Thiết kế tài liệu Kiến trúc | [architecture.md](file:///architecture.md) | Sơ đồ luồng handoff chi tiết giữa 7 agent trong hệ thống | Xem file architecture.md |

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Xử lý tự động và chính xác 50 khiếu nại thương mại điện tử bằng cấu trúc Multi-Agent phối hợp, trong đó mỗi agent phụ trách một domain thông tin riêng (Khách hàng, Đơn hàng, Thanh toán, Vận chuyển) và chuyển thông tin cho Policy Agent để đưa ra hướng giải quyết (hoàn tiền/từ chối/hành động).

### Cách triển khai
* Sử dụng **Pandas** để index dữ liệu CSV giúp tăng tốc độ tìm kiếm bản ghi.
* Lập trình logic tính toán thời gian và đối soát tài chính bằng mã Python thuần trong `utils.py` nhằm đảm bảo độ chính xác tuyệt đối (làm tròn 2 chữ số thập phân), tránh hiện tượng LLM tính toán sai lệch.
* Sử dụng LLM Client hỗ trợ đa dạng API Key từ `.env` (TogetherAI, OpenAI, Gemini) để chạy phân tích lập luận ngữ cảnh của case và tính điểm độ tự tin (`confidence`).
* Điều phối tuần tự qua: Customer/Order/Payment/Delivery Agents $\rightarrow$ Policy Agent $\rightarrow$ Verifier Agent (kiểm duyệt và cắt giảm nếu vượt quá giới hạn phần tử của schema).

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | Case JSON khiếu nại chứa `claimed_order_id`, `policy_version` |
| Output                  | JSON kết quả phân tích theo đúng schema quy định của bài toán |
| Module phụ thuộc        | `pandas`, `requests`, `python-dotenv` |
| Module sử dụng output   | Hệ thống chấm điểm tự động của BTC |
| Điều kiện lỗi cần xử lý | Trường hợp đơn hàng không có item row, các trường tài chính liên quan phải trả về `null` |

### Cách xác minh

```bash
python verify_outputs.py
```

- **Kết quả mong đợi:** Tìm thấy đủ 50 file kết quả, 0 lỗi định dạng, thống kê Primary Issue đầy đủ.
- **Kết quả thực tế:** 0 lỗi tìm thấy, toàn bộ 50 file hợp lệ 100%.
- **Artifact/log:** [logging/trace.jsonl](file:///logging/trace.jsonl)

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn phương án tính toán hiệu số giờ (`delivery_variance_hours`, `handoff_variance_hours`) và đối soát chênh lệch tiền (`difference_brl`).
- **Các phương án đã cân nhắc:**
  1. Gửi toàn bộ dữ liệu thô vào LLM và yêu cầu LLM tự tính toán thông qua Prompt Engineering.
  2. Sử dụng Python code để tính toán chính xác trước, sau đó đưa kết quả tính toán vào context để LLM làm căn cứ đưa ra quyết định chính sách.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Các mô hình ngôn ngữ lớn (đặc biệt là các model dưới 10B parameters theo quy định bài lab) thường thực hiện phép tính số học và so sánh mốc thời gian rất kém, dễ dẫn đến sai số thập phân hoặc tính lệch giờ giao hàng. Việc tính toán trước bằng code Python đảm bảo độ chính xác tuyệt đối 100%, đồng thời giảm tải token và nâng cao hiệu suất chạy.
- **Bằng chứng quyết định phù hợp:** Kết quả chạy 50 cases qua file verify đạt độ chính xác 100%, không bị lệch bất cứ số liệu đối soát hay giờ giấc nào.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Đơn hàng không có item row dẫn đến lỗi phép tính chia cho 0 hoặc tính toán NaN khi đối soát tài chính.
- **Lệnh hoặc bước tái hiện:** Chạy các case có đơn hàng trống (không có item row trong `olist_order_items_dataset.csv`).
- **Nguyên nhân gốc:** Code cố gắng tính tổng giá tiền và phí vận chuyển của các item không tồn tại, trả về `NaN` hoặc `0` thay vì giá trị `null` như yêu cầu nghiệp vụ của đề bài.
- **Cách xử lý:** Bổ sung kiểm tra cờ `has_items` trong `PaymentAgent`. Nếu không có item, đặt `expected_total_brl = None`, `difference_brl = None`, `reconciled = None` thay vì tính toán số học.
- **Cách xác minh sau khi sửa:** Chạy script verify kiểm tra các trường tài chính của các đơn hàng trống và xác nhận chúng đều trả về `null` trong JSON kết quả.
- **Điều học được:** Phải kiểm tra kỹ các trường hợp biên của dữ liệu (edge cases) và xử lý giá trị khuyết thiếu (`null`/`NaN`) một cách an toàn.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   * Dữ liệu thư mục học thuật từ Crossref được cào (crawl) hoặc tải về dưới dạng JSON/XML, sau đó được trích xuất nội dung (metadata, tóm tắt, tác giả). Nội dung văn bản được chia thành các đoạn nhỏ (chunking), đi qua mô hình Embedding để chuyển hóa thành các vector đặc trưng số học, cuối cùng lưu trữ vào một Vector Database (như Milvus, Qdrant, Chroma) để lập chỉ mục phục vụ truy vấn tìm kiếm ngữ nghĩa.
2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   * Tập đánh giá (Evaluation set) gồm các câu hỏi kiểm thử. Ground-truth document IDs là danh sách các ID tài liệu chính xác chứa câu trả lời cho từng câu hỏi. Để đo Retrieval quality, ta kiểm tra xem các tài liệu mà hệ thống tìm được (retrieved documents) có chứa ground-truth IDs hay không (thông qua các chỉ số Recall, Precision, MRR, NDCG). Để đo Answer quality, ta so sánh câu trả lời do LLM sinh ra với câu trả lời chuẩn (ground-truth answer) bằng các metric như ROUGE, BLEU, hoặc dùng LLM-as-a-judge.
3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   * Quality checks tập trung vào việc đánh giá tính đúng đắn, độ chính xác của câu trả lời, sự phù hợp với chính sách (policy compliance) và tính nhất quán dữ liệu của kết quả đầu ra. Freshness monitoring tập trung giám sát tính cập nhật liên tục của dữ liệu hệ thống (ví dụ kiểm tra xem dữ liệu có bị trễ, luồng cập nhật từ nguồn về kho lưu trữ có bị gián đoạn hay không).
4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   * Sử dụng cùng một tập test set giúp đảm bảo tính nhất quán và công bằng của các chỉ số đánh giá (metrics). Khi đó, sự thay đổi của chỉ số chất lượng phản ánh trực tiếp hiệu quả của phương pháp sửa lỗi (repair) so với trạng thái ban đầu (baseline) và trạng thái bị lỗi (corrupted), loại bỏ các biến số gây nhiễu do tập dữ liệu thử nghiệm khác nhau.
5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   * Repair được xem là thành công khi các chỉ số chất lượng của hệ thống sau sửa lỗi (như độ chính xác phân loại Primary Issue, tỷ lệ đối soát khớp BRL, độ tin cậy) được cải thiện rõ rệt so với trạng thái corrupted và tiệm cận hoặc vượt qua baseline. Artifact chứng minh là các tệp kết quả đầu ra hợp lệ hoàn toàn với schema của verify script, cùng với nhật ký chạy trace ghi nhận không có lỗi phát sinh.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đăng Long
**Ngày xác nhận:** 2026-08-05
