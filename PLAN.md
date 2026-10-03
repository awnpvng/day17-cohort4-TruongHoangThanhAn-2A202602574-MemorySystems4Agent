# PLAN – Day 17: Memory Systems for AI Agent

Đánh dấu `[x]` khi hoàn thành. Làm tuần tự từ trên xuống.

## Quy tắc cần nhớ
- [x] Import phẳng (`from config import ...`), luôn chạy từ thư mục gốc repo
- [x] Không sửa `data/`
- [x] `make_config()` trong test phải điền đủ 7 trường của `LabConfig`
- [x] `SessionState` của Baseline khóa theo `thread_id`, không theo `user_id`
- [x] Token cộng dồn từng lượt trong `_reply_offline()`; `compaction_count()` của Baseline luôn là 0
- [x] Test viết theo hành vi quan sát được, không assert `write_text` đã được gọi
- [x] Đọc file JSON bằng `encoding="utf-8"`; in ra stdout UTF-8 trên Windows
- [x] Xóa state trước mỗi lần benchmark: `Remove-Item -Recurse -Force state`

## B0. Chuẩn bị
- [x] `.venv` có đủ package (langchain, pytest, tabulate, python-dotenv)
- [x] Đọc toàn bộ turn trong `data/` để viết regex cho khớp

## B1. `model_provider.py` + `config.py`
- [x] `normalize_provider()` (alias như `anthorpic` → `anthropic`)
- [x] `build_chat_model()` cho 6 provider (import trễ)
- [x] `load_config()`: nạp `.env`, tạo `state/`, mặc định threshold + keep_messages
- [x] Kiểm tra: `python -c "import sys; sys.path.insert(0,'src'); from config import load_config; print(load_config())"`

## B2. `memory_store.py`
- [x] `estimate_tokens()`
- [x] `UserProfileStore`: `path_for`, `read_text`, `write_text`, `edit_text`, `file_size`
- [x] `UserProfileStore`: `facts()`, `upsert_fact()` (ghi đè fact khi correction)
- [x] `extract_profile_updates()`: tên, nơi ở, nghề, style, đồ uống, món ăn, thú cưng, sở thích
- [x] Bỏ qua câu hỏi; không lấy nhiễu (đi họp Hà Nội, product manager đùa)
- [x] `summarize_messages()`
- [x] `CompactMemoryManager`: `append`, `context`, `compaction_count`

## B3. `agent_baseline.py`
- [x] `reply()` định tuyến live/offline
- [x] `_reply_offline()` theo `thread_id`, cộng token + prompt token mỗi lượt
- [x] `token_usage()`, `prompt_token_usage()`
- [x] `_maybe_build_langchain_agent()` (try/except, rơi về offline)
- [x] Thread mới hỏi lại thì Baseline không nhớ

## B4. `agent_advanced.py`
- [x] `reply()`
- [x] `_reply_offline()`: trích fact → `User.md` → compact → ước lượng prompt → trả lời
- [x] `_estimate_prompt_context_tokens()` (User.md + summary + recent)
- [x] `_offline_response()` trả lời được câu hỏi ở cả hai bộ data (kể cả "3 bullet", "DũngCT Stress")
- [x] `token_usage()`, `prompt_token_usage()`, `memory_file_size()`, `compaction_count()`
- [x] `_maybe_build_langchain_agent()`

## B5. `benchmark.py`
- [x] `load_conversations()`
- [x] `recall_points()` (0 / 0.5 / 1)
- [x] `heuristic_quality()`
- [x] `run_agent_benchmark()` (recall hỏi ở thread mới)
- [x] `format_rows()` đủ 6 cột
- [x] `main()` in bảng Standard và bảng Long-Context Stress
- [x] `python src/benchmark.py` chạy được, không lỗi encoding

## B6. `test_agents.py`
- [x] `make_config(tmp_path)` (threshold 80, keep 2, đủ 7 trường)
- [x] `test_user_markdown_read_write_edit`
- [x] `test_compact_trigger`
- [x] `test_cross_session_recall` (Advanced nhớ, Baseline không)
- [x] `test_compact_reduces_prompt_load_on_long_thread`
- [x] `pytest src/test_agents.py -v`: 4 test pass, không cần API key

## B7. Xác minh kết quả
- [x] Xóa `state/` rồi chạy lại benchmark
- [x] Baseline không nhớ qua thread mới (recall thấp) — thực tế đạt 0.0 ở cả hai bộ
- [x] Advanced recall cao, `Memory growth (bytes)` > 0 — recall 1.0/1.0, memory growth 306/242 bytes
- [x] Bảng Stress: `Prompt tokens processed` của Advanced < Baseline — 10739 < 24094
- [x] Bảng Stress: `Compactions` > 0 — 28 lần
- [x] Mỗi bảng có đủ dòng Baseline/Advanced và 6 cột

## B8. Phân tích `STEP8.md`
- [x] Vì sao Advanced có recall tốt hơn Baseline
- [x] Vì sao Advanced có thể tốn hơn ở hội thoại ngắn
- [x] Vì sao compact giúp ở hội thoại dài (tối ưu `prompt tokens processed`)
- [x] File memory tăng trưởng ra sao và rủi ro (phình file, lưu sai fact)

## B9. Bonus (90–100 điểm)
- [x] Conflict handling: correction mới ghi đè fact cũ (`upsert_fact` ghi đè theo key + lọc cụm phủ định `_is_negated_before`)
- [x] Bỏ qua câu hỏi, không lưu nhầm thành fact (lọc `?`, `đùa`, `họp`/`bay`)
- [ ] Confidence threshold trước khi ghi `User.md` — **chưa làm**, hiện tại ghi trực tiếp khi regex khớp, không có điểm tin cậy
- [x] Ghi vào `STEP8.md`: bonus giải quyết gì, cải thiện gì, rủi ro gì

## B10. Nộp bài
- [ ] Đổi tên repo/thư mục thành `KX-DAY17-HoVaTen-MSSV` — **cần họ tên + MSSV từ bạn**
- [x] Không có `.env`, API key hay `state/` trong repo (đã xoá `state/` sau mỗi lần chạy, `.gitignore` đã chặn)
- [x] Có `STEP8.md`
- [x] Chạy lại `python src/benchmark.py` từ trạng thái sạch
- [x] Chạy lại `pytest src/test_agents.py -v`
- [ ] Commit và push lên GitHub — **chưa commit, đang chờ xác nhận từ bạn**
- [ ] Dán link repo vào bài nộp trên VLearn — **cần bạn tự làm sau khi push**

## Cần xác nhận
- [ ] Họ tên + MSSV (để đặt tên repo)
- [x] Chỉ offline hay có thêm live mode → đã chọn: **offline là chính** (deterministic, không cần API key); có thêm đường live-mode phụ (`_maybe_build_langchain_agent` + `_reply_live`) tự fallback về offline khi thiếu API key/import lỗi
