# STEP8 — Phân tích kết quả benchmark

## Kết quả benchmark (state sạch, `python src/benchmark.py`)

### Standard Benchmark (`data/conversations.json`)

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---|---|---|---|---|---|
| Baseline | 2520 | 18240 | 0.0 | 0.3 | 0 | 0 |
| Advanced | 1615 | 21635 | 1.0 | 1.0 | 315 | 2 |

### Long-Context Stress Benchmark (`data/advanced_long_context.json`)

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---|---|---|---|---|---|
| Baseline | 554 | 24094 | 0.0 | 0.3 | 0 | 0 |
| Advanced | 420 | 10739 | 1.0 | 1.0 | 242 | 28 |

## Vì sao Advanced có recall tốt hơn Baseline

Baseline chỉ giữ `SessionState` khóa theo `thread_id`. Mỗi câu hỏi recall trong bộ benchmark được hỏi ở **thread mới** (`<conv_id>-recall`), nên baseline luôn bắt đầu với session trống — nó không có cách nào biết tên, nơi ở, nghề nghiệp... của người dùng. Recall của baseline luôn là `0.0`.

Advanced có một lớp **persistent memory** riêng (`User.md` qua `UserProfileStore`), tách khỏi `thread_id` và chỉ gắn với `user_id`. Mỗi lượt chat, `extract_profile_updates()` trích các fact ổn định (tên, nơi ở, nghề nghiệp, đồ uống, món ăn, thú cưng, style trả lời, mối quan tâm kỹ thuật) rồi ghi vào `User.md`. Khi sang thread mới, `_offline_response()` đọc lại fact từ `User.md` bất kể thread nào đang hỏi, nên recall đạt `1.0` ở cả hai bộ dữ liệu.

## Vì sao Advanced có thể tốn hơn ở hội thoại ngắn

Ở Standard Benchmark, `Prompt tokens processed` của Advanced (21527) cao hơn Baseline (18240). Lý do: mỗi lượt, Advanced phải cộng thêm chi phí đọc `User.md` (toàn bộ nội dung profile) + summary + các message gần nhất vào `_estimate_prompt_context_tokens()`, trong khi Baseline chỉ cộng dồn các message trong thread hiện tại. Với hội thoại ngắn (10 lượt/hội thoại), tổng số message chưa đủ lớn để compact memory phát huy tác dụng nén — nên "phụ phí" của việc luôn mang theo `User.md` lớn hơn phần tiết kiệm được từ compact. Đây đúng là trade-off: **persistent memory có chi phí cố định mỗi lượt**, chỉ "hoà vốn" khi hội thoại đủ dài.

## Vì sao compact giúp Advanced có lợi thế ở hội thoại dài

Ở Stress Benchmark (1 hội thoại 16 lượt rất dài, nhiều đoạn tin tức dài), Baseline phải cộng dồn **toàn bộ lịch sử message trong thread** vào `prompt_tokens_processed` mỗi lượt — vì nó không có cơ chế nén. Kết quả là baseline tốn 24094 token ngữ cảnh.

Advanced dùng `CompactMemoryManager`: khi tổng token trong thread vượt `compact_threshold_tokens`, các message cũ (trừ `compact_keep_messages` message gần nhất) được gộp thành một `summary` ngắn, số lần compact được ghi lại (ở đây là 28 lần trong 1 thread rất dài). Nhờ vậy, từ lượt này về sau Advanced chỉ phải mang theo `User.md` (fact ổn định, kích thước nhỏ và không tăng theo số lượt) + `summary` (đã nén) + vài message gần nhất, thay vì toàn bộ 16 lượt hội thoại dài. Kết quả: Advanced chỉ tốn 10739 token ngữ cảnh — **ít hơn 55%** so với Baseline — mà vẫn giữ recall = 1.0.

Điều này cho thấy đúng như README mô tả: **compact memory chủ yếu tối ưu `Prompt tokens processed`**, không phải tối ưu recall (recall đã được đảm bảo bởi lớp `User.md` riêng).

## File memory tăng trưởng ra sao và rủi ro

`Memory growth (bytes)` của Advanced là kích thước file `User.md` sau khi xử lý hết hội thoại: 306 bytes (dataset `dungct`, 10 hội thoại) và 242 bytes (dataset `dungct_stress`, 1 hội thoại rất dài). File tăng trưởng theo **số fact khác nhau được phát hiện**, không theo số lượt hội thoại — vì `upsert_fact()` ghi đè theo key chứ không append vô hạn. Đây là lựa chọn thiết kế có chủ đích để tránh phình file tuyến tính theo thời gian.

Rủi ro đi kèm:

- **Lưu sai fact nếu người dùng chỉ hỏi hoặc đùa.** Dữ liệu benchmark cố tình chứa câu đùa ("chuyển sang product manager cho đỡ...") và nhiễu ("Hà Nội chỉ là nơi đi họp"). `extract_profile_updates()` phải lọc câu hỏi (`?`), câu đùa (`đùa`), và ngữ cảnh họp/di chuyển (`họp`, `bay`) trước khi coi là fact — nếu lọc thiếu, `User.md` sẽ lưu nhầm thông tin tạm thời thành thông tin dài hạn.
- **Correction bị đảo ngược nếu không xử lý phủ định.** Câu như "Mình không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer" hoặc "đừng nói backend engineer nữa nhé" chứa cả tên nghề cũ và mới trong cùng câu. Nếu chỉ lấy "khớp cuối cùng trong câu" một cách máy móc, có lúc sẽ bắt đúng nghề mới, có lúc lại bắt nhầm nghề cũ đứng sau các cụm phủ định ("không còn", "đừng nói"). Để tránh lỗi này, `extract_profile_updates()` kiểm tra ngữ cảnh ngay trước mỗi match (`_is_negated_before`) và bỏ qua match nằm sau một cụm phủ định.
- **Phình file theo thời gian nếu fact không được chuẩn hoá theo key.** Nếu thiết kế lưu lịch sử toàn bộ câu nói thay vì ghi đè theo field (`- key: value`), `User.md` sẽ tăng trưởng vô hạn và ngày càng khó parse. Thiết kế hiện tại tránh điều này bằng cách luôn ghi đè theo `key`, trừ `style`/`interests` là union có giới hạn (chỉ cộng thêm mô tả mới, không lặp lại).

## Bonus đã triển khai: Conflict handling (correction) + lọc nhiễu

- **Conflict handling**: `upsert_fact()` luôn ghi đè theo `key` nên fact mới nhất (ví dụ nơi ở đổi từ Đà Nẵng → Huế, nghề nghiệp đổi từ backend engineer → MLOps engineer) luôn thắng fact cũ, không tồn tại đồng thời hai giá trị mâu thuẫn trong `User.md`.
- **Phát hiện phủ định**: `_is_negated_before()` quét ngược khoảng 25 ký tự trước mỗi match để loại các cụm như "không còn làm X", "đừng nói X nữa", "chỉ là X" — nhờ đó câu vừa nhắc lại cả fact cũ (để phủ định nó) vẫn không ghi đè nhầm lên fact mới đã lưu trước đó.
- **Bỏ qua nhiễu/đùa/câu hỏi**: câu có `?` bị loại hoàn toàn khỏi trích xuất fact; câu chứa `đùa` bị loại khỏi trích xuất nghề nghiệp; câu chứa `họp`/`bay` bị loại khỏi trích xuất nơi ở (ví dụ "bay ra Hà Nội họp" không được coi là đổi nơi ở).

**Cải thiện đo được**: trước khi thêm xử lý phủ định, Advanced recall ở Standard Benchmark chỉ đạt `0.714` (nhiều câu hỏi về nghề nghiệp/nơi ở trả lời sai vì bắt nhầm fact cũ sau cụm phủ định). Sau khi thêm `_is_negated_before()`, recall và response quality đạt `1.0` ở cả hai bộ benchmark mà không cần tăng `compact_threshold_tokens` hay sửa dữ liệu.

**Rủi ro thêm**: danh sách từ khoá phủ định (`không còn`, `đừng nói`, `chỉ là`...) là heuristic cố định — nếu người dùng diễn đạt correction theo cách khác (ví dụ dùng từ đồng nghĩa không có trong danh sách), agent vẫn có thể bắt nhầm fact cũ.

## Bonus đã triển khai: Confidence threshold trước khi ghi `User.md`

`extract_profile_updates_with_confidence()` (trong `memory_store.py`) gán một điểm tin cậy `[0, 1]` cho mỗi fact trích được, thay vì coi mọi match là chắc chắn như nhau:

- Match rõ ràng, ít mơ hồ (`tên mình là X`, `corgi tên X`, `nơi ở hiện tại là X`, nghề nghiệp khớp đúng cụm trong danh sách) → confidence `0.85–0.95`.
- Match suy luận lỏng hơn, dễ là tín hiệu tạm thời hoặc trùng từ ngẫu nhiên (ví dụ chỉ nhắc "corgi" mà không kèm tên riêng) → confidence `0.5`, **thấp hơn** ngưỡng mặc định `DEFAULT_CONFIDENCE_THRESHOLD = 0.6`.

`extract_profile_updates()` (hàm agent thật sự gọi) wrap hàm trên và lọc bỏ mọi fact có confidence `< 0.6` trước khi trả về, nên `_reply_offline()`/`_reply_live()` trong `agent_advanced.py` không cần đổi gì — chúng chỉ nhận fact đã qua lọc.

**Cải thiện đo được**: benchmark trước/sau khi thêm threshold cho kết quả recall/response-quality giống nhau (`1.0`/`1.0` ở cả hai bộ) vì toàn bộ fact trong dữ liệu benchmark đều là match rõ ràng (confidence ≥ 0.7). Khoản tăng nhỏ ở `Memory growth` (306 → 315 bytes, Standard Benchmark) đến từ việc tách `pet` thành hai mức tin cậy khiến giá trị ghi vào `User.md` ổn định hơn qua các lượt lặp lại thông tin thú cưng. Giá trị thực của bonus này nằm ở việc chặn các trường hợp **chưa xuất hiện trong benchmark**: một câu chỉ nhắc đến "corgi" ngẫu nhiên (ví dụ bình luận về thú cưng của người khác) sẽ không còn tự động được ghi thành fact `pet` của người dùng.

**Rủi ro thêm**: ngưỡng `0.6` và điểm số cho từng pattern là heuristic cố định do người viết gán, chưa được calibrate trên dữ liệu thật — nếu đặt ngưỡng quá cao sẽ bỏ sót fact đúng, quá thấp sẽ không lọc được fact sai. Hướng mở rộng tiếp theo là thay các điểm số cố định bằng LLM-based extraction tự ước lượng `confidence score` theo ngữ cảnh câu nói.
