# SignCite UAT: the survey form (Google Forms)

Build the form exactly from this file.
- **Every scored question's title starts with its code in square brackets** (`[ID]`, `[SUS1]` …). `eval/uat/score_sus.py` finds columns by these codes, so the codes must stay; the rest of the title can change.
- Linear-scale questions export the number, which is what the script reads.
- Choice questions (`[OK1]`…, `[GROUP]`) export the option text; keep the options' first words as written.
- Mark every question **Required** except the open questions in section 5.
- Settings: don't collect email addresses; don't limit to one response (testers may lack a Google account).

---

## Section 1. Giới thiệu và đồng ý

Description (paste as is):

> Phiếu này thu thập đánh giá của bạn về SignCite, một đồ án tốt nghiệp. Phiếu không hỏi họ tên hay email. Câu trả lời chỉ dùng ở dạng tổng hợp trong báo cáo đồ án và sẽ bị xóa sau buổi bảo vệ (19/12/2026). Bạn có thể dừng bất cứ lúc nào.

| Code | Question | Type | Options |
|---|---|---|---|
| — | Tôi đồng ý tham gia và cho phép dùng câu trả lời ở dạng tổng hợp. | Checkbox, required | Tôi đồng ý |
| `[ID]` | **[ID] Mã người tham gia** (trên phiếu nhiệm vụ, ví dụ P07) | Short answer, required | — |

## Section 2. Về bạn

| Code | Question | Type | Options |
|---|---|---|---|
| `[GROUP]` | **[GROUP] Bạn thuộc nhóm nào nhất?** | Multiple choice | Người lái xe · Sinh viên · Người am hiểu luật giao thông (giảng viên, cán bộ, luật sư, giáo viên dạy lái…) · Khác |
| — | Bạn có giấy phép lái xe không? | Multiple choice | Không có · Hạng A1/A (xe máy) · Hạng B trở lên (ô tô) |
| — | Tuổi | Multiple choice | Dưới 18 · 18–24 · 25–34 · 35–49 · 50 trở lên |
| — | Bạn đã dùng thiết bị nào để thử? | Multiple choice | Máy tính · Điện thoại · Máy tính bảng |
| — | Bạn có hay dùng các trợ lý AI dạng trò chuyện (ChatGPT, Gemini…) không? | Multiple choice | Chưa bao giờ · Thỉnh thoảng · Hằng tuần · Hằng ngày |

## Section 3. Năm nhiệm vụ

For each task, ask two questions. `[OKn]` records whether the tester finished the task. It is what the script uses when there is no moderator's log (an unmoderated session). `[Tn]` records how easy the task was (the Single Ease Question, on a 1–5 scale).

| Code | Question | Type |
|---|---|---|
| `[OK1]` | **[OK1] Nhiệm vụ 1 (hỏi ý nghĩa biển báo): bạn có hoàn thành không?** | Multiple choice: Có · Một phần · Không |
| `[T1]` | **[T1] Nhiệm vụ 1 dễ hay khó?** | Linear scale 1–5: 1 = Rất khó, 5 = Rất dễ |
| `[OK2]` | **[OK2] Nhiệm vụ 2 (xe ô tô có được đi không, và căn cứ luật): bạn có hoàn thành không?** | Có · Một phần · Không |
| `[T2]` | **[T2] Nhiệm vụ 2 dễ hay khó?** | 1–5 |
| `[OK3]` | **[OK3] Nhiệm vụ 3 (hỏi tiếp về xe máy, chỉ biển trên ảnh): bạn có hoàn thành không?** | Có · Một phần · Không |
| `[T3]` | **[T3] Nhiệm vụ 3 dễ hay khó?** | 1–5 |
| `[OK4]` | **[OK4] Nhiệm vụ 4 (hỏi bằng giọng nói): bạn có hoàn thành không?** | Có · Một phần · Không |
| `[T4]` | **[T4] Nhiệm vụ 4 dễ hay khó?** | 1–5 |
| `[OK5]` | **[OK5] Nhiệm vụ 5 (đánh giá câu trả lời, xem lại lịch sử): bạn có hoàn thành không?** | Có · Một phần · Không |
| `[T5]` | **[T5] Nhiệm vụ 5 dễ hay khó?** | 1–5 |

## Section 4. Đánh giá chung (SUS)

Description: *Với mỗi câu, chọn mức bạn đồng ý. Hãy trả lời theo cảm nhận đầu tiên, đừng suy nghĩ quá lâu.*

All ten are linear scales from 1 to 5, labelled **1 = Hoàn toàn không đồng ý** and **5 = Hoàn toàn đồng ý**.
- **Keep the order:** odd items are positive and even items are negative. The script scores them that way (Brooke 1996).
- **Don't** shuffle the question order.

| Code | Question |
|---|---|
| `[SUS1]` | **[SUS1] Tôi nghĩ rằng tôi sẽ muốn dùng SignCite thường xuyên.** |
| `[SUS2]` | **[SUS2] Tôi thấy SignCite phức tạp một cách không cần thiết.** |
| `[SUS3]` | **[SUS3] Tôi thấy SignCite dễ sử dụng.** |
| `[SUS4]` | **[SUS4] Tôi nghĩ tôi sẽ cần người rành kỹ thuật giúp thì mới dùng được SignCite.** |
| `[SUS5]` | **[SUS5] Tôi thấy các chức năng của SignCite được kết hợp tốt với nhau.** |
| `[SUS6]` | **[SUS6] Tôi thấy SignCite có quá nhiều chỗ không nhất quán.** |
| `[SUS7]` | **[SUS7] Tôi nghĩ hầu hết mọi người sẽ học cách dùng SignCite rất nhanh.** |
| `[SUS8]` | **[SUS8] Tôi thấy SignCite rất rườm rà, khó dùng.** |
| `[SUS9]` | **[SUS9] Tôi cảm thấy rất tự tin khi dùng SignCite.** |
| `[SUS10]` | **[SUS10] Tôi cần học nhiều thứ trước khi có thể dùng được SignCite.** |

## Section 5. Mức hài lòng và góp ý

| Code | Question | Type |
|---|---|---|
| `[CSAT]` | **[CSAT] Nhìn chung, bạn hài lòng với SignCite ở mức nào?** | Linear scale 1–5: 1 = Rất không hài lòng, 5 = Rất hài lòng |
| — | Bạn có tin câu trả lời của SignCite không? Vì sao? | Paragraph, optional |
| — | Điều bạn thích nhất ở SignCite là gì? | Paragraph, optional |
| — | Điều làm bạn khó chịu hoặc bối rối nhất là gì? | Paragraph, optional |
| — | Bạn muốn SignCite có thêm hoặc thay đổi điều gì? | Paragraph, optional |

The open answers are read by hand and summarised into the top three complaints in the report. Quote them without the participant's ID.
