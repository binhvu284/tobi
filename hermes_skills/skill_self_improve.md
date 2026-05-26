# Self-Improvement Skill
# Tobi tự học và cải thiện theo thời gian

## Khi nào trigger skill này
- Sau khi hoàn thành task quan trọng
- Khi Thomas feedback (tốt hoặc xấu)
- Khi gặp lỗi lặp lại >2 lần
- Cuối mỗi tuần (weekly reflection)

## Lesson capture format
Sau mỗi task đáng chú ý, ghi vào DB:
{
  "title": "[ngắn gọn, searchable]",
  "type": "success|failure|insight|warning",
  "context": "task loại gì, hoàn cảnh ra sao",
  "what_happened": "kết quả thực tế",
  "why": "nguyên nhân cốt lõi",
  "next_time": "làm gì khác đi",
  "impact": 1-10
}

## Skill file update rules
Chỉ update skill file khi:
- Pattern xuất hiện ≥3 lần
- Thomas explicitly feedback
- Impact score ≥7

Update bằng cách:
hermes memory add "[insight ngắn gọn]"
Và append vào skill file liên quan

## Weekly reflection (Chủ nhật 20:00 GMT+7)
Tự hỏi:
1. Task nào làm tốt nhất tuần này? Tại sao?
2. Task nào thất bại? Root cause?
3. Thomas feedback gì? Đã adjust chưa?
4. Skill nào cần improve tuần tới?

Ghi summary → gửi Telegram Thomas

## Hermes memory commands
hermes memory add "lesson: [insight]"
hermes memory search "[topic]"
hermes -z "[prompt với context từ memory]"
