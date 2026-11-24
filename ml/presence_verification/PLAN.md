# PLAN — Presence verification + Door audit

Tính năng sáng tạo cá nhân của Đức Mạnh (COS30082, mục 7 của đề). Workspace: `ml/presence_verification/`.
Trạng thái (2026-11-23): **đã triển khai bước 1–6 và 8–10** (xem `README.md` để chạy, `TEST.md` để kiểm thử tay, `outputs/eval/report.md` cho số liệu). Chưa làm: bước 0 (nói với Mai Chi), bước 7 (quay take gian lận), bước 11. Những chỗ khác với kế hoạch được ghi ở mục 13.

Thay cho `backend/app/features/presence_verification/PLAN.md` (bản cũ, chỉ có tính năng 1).

## 0. Tóm tắt

Hai tính năng, cùng dùng vị trí của mỗi người trên bản đồ 2D phòng 204:

| | Tính năng 2: **Door audit** | Tính năng 1: **Presence verification** |
| --- | --- | --- |
| Câu hỏi | Số người **đi qua cửa** có khớp với số lần **check-in** không? | Người đã check-in có **thật sự ở lại lớp** không? |
| Đơn vị | Một sự kiện ở cửa (vài giây) | Một sinh viên trong một buổi |
| Phát hiện | Vào lớp không check-in, một check-in mà hai người vào, check-in mà không ai vào | Không vào lớp, ở quá ngắn, về sớm, một tên ở hai nơi, hành vi lạ |
| Phần học máy | Mô hình xác suất Δt (check-in → qua cửa) + ghép cặp tối ưu; classifier cho cặp mơ hồ | `IsolationForest` (không nhãn) so với classifier có nhãn |
| Đầu ra | Danh sách cảnh báo ở cửa + bảng ghép check-in ↔ track | Điểm bất thường 0–1 + lý do, cho mỗi sinh viên × buổi |

**Thứ tự làm: 2 trước, 1 sau.** Tính năng 2 ghép mỗi check-in với track đã đi vào phòng, tức là gắn `student_id` cho track trong lớp. Tính năng 1 cần đúng thông tin đó để tính thời gian ở trong lớp. Vì vậy 2 là nền của 1, không phải hai việc riêng.

Câu trả lời khi phỏng vấn: *"Anti-spoofing kiểm tra khuôn mặt có thật lúc check-in. Door audit kiểm tra mỗi người qua cửa đều đã check-in. Presence verification kiểm tra người đã check-in có ở lại lớp suốt buổi."*

## 1. Ranh giới với phần của người khác

| Module | Chủ | Mình dùng thế nào | Không làm |
| --- | --- | --- | --- |
| `ml/tracking/` (tracks, homography, `ground_model.py`) | Mai Chi | **Đọc** `data/tracks/take<N>/*.json` và `data/calibration/*` | Không sửa file nào trong `ml/tracking/`, không ghi đè `data/tracks/` |
| `ml/tracking/link_names.py` (door handoff) | Mai Chi | **Đọc** kết quả (`name`, `name_from` trong tracks) làm một đặc trưng | Không đặt tên lại cho track. Xem ghi chú bên dưới |
| `ml/face_recognition/` | Thuận Minh | Đọc `student_id` + `similarity` của sự kiện check-in | Không nhận diện lại |
| `ml/anti_spoofing/` | Hồng Minh | Đọc số lần báo spoof (một đặc trưng phụ của tính năng 1) | Không tự phát hiện ảnh giả |
| `ml/emotion/` | Minh Thành | Không dùng | |

**Ghi chú về `link_names.py`, cần nói với Mai Chi trước khi làm.** `link_names.py` **đặt tên** cho track ở cửa theo luật cố định. Khi có hai người trở lên ở cửa, nó bỏ qua và chỉ ghi vào report. Door audit **kiểm tra** chứ không đặt tên: nó đếm người qua cửa so với số check-in trong cả buổi, ghép cặp theo xác suất, rồi báo **cảnh báo** cho phần không khớp. Đúng những ca `link_names.py` bỏ qua (nhiều người ở cửa) lại là ca door audit cần bắt. Hai phần bổ sung cho nhau. Kết quả ghép của door audit **không** ghi vào `data/tracks/`.

## 2. Dữ liệu thật đang có (đã kiểm tra 2026-11-23)

| Dữ liệu | Thực tế | Hệ quả cho kế hoạch |
| --- | --- | --- |
| Tracks | 8 take × 3 camera, mỗi take **6–49 s**, tối đa 4 người (các thành viên nhóm) | "Một buổi" của dữ liệu thật chỉ dài vài chục giây. Mọi đặc trưng thời gian phải tính **theo tỉ lệ độ dài buổi**, không tính theo phút |
| Tên trên track | Có ở take 1, 3, 4, 8 (attendance_cam, một phần cam_1/cam_2). Take 2, 5, 6, 7 không có tên | Chỉ 4 take dùng được làm "buổi bình thường có danh tính" |
| Ground truth | `data/ground_truth/take1.csv`, `take3.csv`: `check_in`, `enter_class`, `seen` theo người | Đủ để **ước lượng phân phối Δt** và đo false alarm. Take 1: Δt (check_in → enter_class) = 3,0–4,5 s |
| Homography | cam_1, cam_2 → bản đồ, **ước lượng** (`ground_model.py`, không có mốc đo trên sàn) | Ngưỡng vị trí cần biên an toàn. Báo cáo phải có phân tích độ nhạy với nhiễu tọa độ |
| Bản đồ | `room204_map.json`: hành lang x 0–0,3, phòng x 0,3–1, cửa x = 0,3, y 0,727–0,906 | Định nghĩa vùng: hành lang / cửa / phòng |
| attendance_cam | Thấy mặt, không thấy chân, nên **không chiếu được lên bản đồ** | Check-in là một sự kiện tại vị trí cửa cố định, không phải một quỹ đạo |
| Đồng hồ camera | Đồng hồ CAM 2 lệch khoảng 23,4 s, đã chỉnh bằng `offset_s` trong `video_config.json` | Sai lệch đồng bộ còn sót lại làm Δt bị lệch, nên mô hình Δt phải chịu được độ lệch vài giây |
| Dữ liệu gian lận | **Chưa có** | Cần quay take có kịch bản (bước 7) và mô phỏng (bước 3) |

**Kết luận:** dữ liệu thật quá ít để train. Kế hoạch dùng **dữ liệu thật để ước lượng tham số và đánh giá**, và **dữ liệu mô phỏng để train**, với tham số mô phỏng lấy từ dữ liệu thật.

## 3. Cấu trúc thư mục dự kiến

```
ml/presence_verification/
  PLAN.md               kế hoạch này
  README.md             cách chạy, số liệu cho báo cáo (viết ở bước cuối)
  trajectories.py       tracks + homography → quỹ đạo trên bản đồ, gắn vùng (dùng chung cho 1 và 2)
  simulate.py           sinh buổi học tổng hợp: bình thường + các kiểu gian lận, có nhãn
  door_audit.py         tính năng 2: phát hiện lần qua cửa, mô hình Δt, ghép cặp, cảnh báo
  presence.py           tính năng 1: vector đặc trưng, luật R1–R5, chấm điểm bằng mô hình
  train.py              train và lưu mô hình (cả hai tính năng) → presence_verification.joblib
  evaluate.py           số liệu và hình cho báo cáo
  infer.py              API ổn định cho backend (mục 9), cùng quy ước với ml/<feature>/infer.py
  notebooks/            khám phá dữ liệu, hình cho báo cáo
  outputs/              quỹ đạo đã tính, dữ liệu mô phỏng, kết quả đánh giá (git-ignored, mục 12)
```

Quy ước giống các module khác: `infer.py` cộng một file mô hình (`presence_verification.joblib`, không commit). Backend tìm chúng qua `backend/app/core/ml_models.py` sau khi thêm `"presence_verification"` vào `FEATURES`.

## 4. Bước chung: quỹ đạo trên bản đồ (`trajectories.py`)

Với mỗi take, mỗi track của cam_1 / cam_2:

1. **Điểm chân** = tâm cạnh dưới của box. Bỏ keyframe có chân bị cắt bởi mép khung (giống `feet_on_map` của `link_names.py`: bỏ khi `y + h >= 0,995`).
2. **Chiếu** qua `H` của camera đó → (x, y) trên bản đồ.
3. **Làm mượt** bằng trung vị trượt (khoảng 0,5 s), để loại các điểm nhảy do box rung.
4. **Gắn vùng** cho mỗi điểm: `corridor` (x < 0,3), `door` (gần x = 0,3 và y trong khoảng cửa, có biên), `room` (x > 0,3).
5. **Gộp hai camera** khi cùng tên (từ `link_names`) và trùng thời gian. Nếu không có tên thì giữ riêng. Không tự làm Re-ID, vì đó là phần của Mai Chi.

Đầu ra (`outputs/trajectories/take<N>.json`), mỗi điểm:

```json
{ "take": 1, "cam_id": "cam_2", "track_id": 5, "name": "Le Mai Chi", "t": 5.7, "x": 0.42, "y": 0.61, "zone": "room" }
```

Kiểm tra: vẽ quỹ đạo take 1 và take 3 lên bản đồ, đối chiếu bằng mắt với ground truth (ai vào lúc nào).

## 5. Tính năng 2: Door audit (`door_audit.py`)

### 5.1 Đầu vào

- **Sự kiện check-in:** `{t, student_id, similarity}`. Dữ liệu thật lấy từ track có tên của attendance_cam (thời điểm `name_from`, hoặc keyframe đầu). Khi chạy live thì lấy từ event bus.
- **Quỹ đạo trên bản đồ** từ mục 4.

### 5.2 Phát hiện "lần qua cửa" (crossing)

Một crossing là một track chuyển từ `corridor` sang `room` qua vùng `door`, gồm thời điểm qua và hướng (vào hoặc ra). Có hai cách nhận ra, vì camera thấy mỗi đoạn khác nhau:

- **Thấy cả quá trình:** quỹ đạo có điểm ở hành lang, rồi ở cửa, rồi ở trong phòng (cam_1 thấy đoạn hành lang, cam_2 thấy đoạn trong phòng).
- **Chỉ thấy một đầu:** track của cam_2 **xuất hiện lần đầu** ở gần cửa rồi đi vào trong. Đây cũng là một lần vào, nhưng độ tin cậy thấp hơn.

Mỗi crossing có `confidence` (0–1) theo số keyframe ở vùng cửa và việc thấy được một hay cả hai đầu. Hướng **ra** cũng được ghi lại, để tính năng 1 dùng cho R5 (về sớm).

### 5.3 Ghép check-in ↔ crossing (phần học máy)

**Mô hình Δt.** Gọi Δt = t(crossing) − t(check-in). Với người bình thường, Δt nhỏ và dương (take 1: 3–4,5 s). Ước lượng phân phối p(Δt) bằng **KDE hoặc phân phối log-normal**, fit trên ground truth (take 1, 3) cùng các take có tên (take 4, 8). Mô hình có thêm một thành phần nền đều (uniform) để chịu được sai lệch đồng bộ đồng hồ.

**Ghép cặp.** Chi phí của cặp (check-in i, crossing j) = −log p(Δt) − log(confidence). Dùng **thuật toán Hungarian** (`scipy.optimize.linear_sum_assignment`) để ghép một-một với tổng chi phí nhỏ nhất. Có cửa chặn: cặp có |Δt| lớn hơn một mức (ví dụ 15 s) thì không được ghép. Mức này được chọn trên dữ liệu.

**Classifier cho ca mơ hồ (tùy chọn, làm nếu còn thời gian).** Khi có nhiều người ở cửa gần nhau, chỉ dùng Δt là chưa đủ. Train `LogisticRegression` trên các cặp, với đặc trưng: Δt, khoảng cách thời gian tới crossing gần nhất, số người ở vùng cửa cùng lúc, số check-in trong cửa sổ ±10 s, confidence của crossing. Nhãn lấy từ mô phỏng. Đầu ra là P(cặp này đúng), dùng thay cho −log p(Δt) trong chi phí.

> Vì sao gọi đây là học máy: phân phối Δt và classifier được **học từ dữ liệu**, không phải luật viết tay. Bài toán là *probabilistic data association*, cùng họ với cách ghép trong multi-object tracking.

### 5.4 Cảnh báo

| Mã | Tình huống | Điều kiện |
| --- | --- | --- |
| **D1** | Vào lớp **không check-in** | Crossing hướng vào không ghép được với check-in nào |
| **D2** | **Một check-in, hai người vào** (tailgating) | Một check-in, và từ hai crossing trở lên trong cùng cửa sổ thời gian. Một crossing được ghép, crossing còn lại không ghép được |
| **D3** | Check-in nhưng **không ai vào** | Check-in không ghép được với crossing nào. Kết quả này chuyển sang tính năng 1 làm luật R1 |

Mỗi cảnh báo gồm: thời điểm, các track liên quan, điểm tin cậy, và lý do bằng chữ (ví dụ "2 người qua cửa trong 3 s, chỉ 1 check-in").

### 5.5 Đánh giá tính năng 2

- **Take bình thường** (1, 3, 4, 8): số cảnh báo sai trên mỗi take, và tỉ lệ ghép đúng (so với ground truth hoặc tên của `link_names`).
- **Take có kịch bản** (bước 7): precision và recall của từng loại D1, D2, D3.
- **Mô phỏng:** precision, recall, F1 theo mật độ người ở cửa (1, 2, 3 người trong 5 s), và theo mức nhiễu tọa độ.
- **So sánh:** ghép theo luật cửa sổ cố định (như `link_names`) so với ghép theo mô hình Δt + Hungarian, so với có thêm classifier.

## 6. Tính năng 1: Presence verification (`presence.py`)

Giữ ý tưởng của PLAN cũ, chỉnh lại cho phù hợp dữ liệu thật.

### 6.1 Danh tính trong lớp

Track trong phòng nhận `student_id` từ **kết quả ghép của door audit**, và từ tên của `link_names` nếu có. Track không có danh tính không được dùng để chấm điểm cho ai, nhưng được đếm làm đặc trưng ("có người lạ trong phòng").

### 6.2 Vector đặc trưng (mỗi sinh viên × buổi)

Mọi đặc trưng thời gian được chuẩn hóa theo **độ dài buổi**, để take 30 s và buổi học 4 tiếng (mô phỏng) dùng chung một mô hình.

| Đặc trưng | Ý nghĩa |
| --- | --- |
| `checkin_offset_ratio` | Check-in muộn bao nhiêu, tính theo tỉ lệ độ dài buổi |
| `n_checkins` | Số lần check-in |
| `door_match_cost` | Chi phí ghép của door audit (cao = ghép gượng) |
| `door_to_room_s` | Từ check-in tới lúc vào phòng (giây, không chuẩn hóa vì đây là đi bộ). Nếu không vào thì đặt giá trị trần |
| `time_in_room_ratio` | Tỉ lệ thời gian trong phòng |
| `n_exits` | Số lần ra (crossing hướng ra) |
| `max_speed` | Tốc độ lớn nhất trên bản đồ (m/s, quy đổi theo `scale_per_m`). Dùng để bắt vị trí "nhảy" (R3) |
| `seat_stability` | Độ lệch vị trí khi đứng yên |
| `n_name_conflicts` | Số lần tên này xuất hiện ở hai nơi cùng lúc |
| `n_spoof_flags` | Số lần liveness báo spoof (đặc trưng phụ) |
| `recog_similarity` | Similarity lúc check-in |

### 6.3 Luật (dễ giải thích, cho ra **lý do**)

| Mã | Tình huống | Điều kiện (ngưỡng chọn trên dữ liệu) |
| --- | --- | --- |
| R1 | Check-in nhưng không vào lớp | D3 của door audit |
| R2 | Ở trong lớp quá ngắn | `time_in_room_ratio` < ngưỡng |
| R3 | Một tên ở hai nơi | `n_name_conflicts` > 0, hoặc `max_speed` vượt tốc độ đi bộ hợp lý |
| R4 | Check-in trùng | `n_checkins` > 1 |
| R5 | Về sớm, không quay lại | Crossing hướng ra cuối cùng xảy ra trước khi buổi kết thúc một khoảng |

### 6.4 Mô hình

- **`IsolationForest`:** train trên các buổi **bình thường** (mô phỏng cộng take bình thường), không cần nhãn. Đầu ra là điểm bất thường.
- **Classifier có giám sát** (`LogisticRegression` so với `RandomForestClassifier`): train trên dữ liệu mô phỏng có nhãn.
- **Điểm cuối** = kết hợp điểm của mô hình với luật. Luật nào kích hoạt thì thêm lý do đó vào danh sách. Cách kết hợp chọn trên tập validation.
- Mô hình chỉ **gợi ý**. Mọi cảnh báo cần giáo viên xác nhận, và không tự trừ điểm.

### 6.5 Đánh giá tính năng 1

- So sánh `IsolationForest` với classifier: precision, recall, F1, ROC-AUC, ma trận nhầm lẫn.
- **Ablation:** bỏ từng nhóm đặc trưng (thời gian, không gian, nhận diện, door audit) để xem nhóm nào quan trọng.
- **Độ nhạy với homography:** thêm nhiễu Gaussian vào tọa độ, vẽ F1 theo mức nhiễu.
- **Chuyển giao mô phỏng sang thật:** train trên mô phỏng, đo trên take thật. Đây là con số trung thực nhất, nên báo cáo riêng.

## 7. Bộ mô phỏng (`simulate.py`, dùng cho cả hai tính năng)

Sinh buổi học tổng hợp trên bản đồ. Tham số **ước lượng từ take thật**, không tự đặt:

- Tốc độ đi bộ, đường đi từ cửa tới chỗ ngồi, độ rung khi ngồi: lấy từ quỹ đạo take 1, 3.
- Δt check-in → qua cửa: lấy từ ground truth.
- Nhiễu tọa độ: lấy từ độ lệch của quỹ đạo khi đứng yên.
- Mất track (ID switch, bị che sau cửa kính): tỉ lệ lấy từ `data/eval/tracking_baseline.csv`.

Các kịch bản, mỗi buổi gán nhãn theo kịch bản:

| Kịch bản | Nhãn | Tính năng bắt |
| --- | --- | --- |
| Bình thường: check-in, vào, ngồi, có thể ra ngoài một lần rồi quay lại | normal | |
| Vào không check-in | D1 | 2 |
| Hai người vào sát nhau, một check-in | D2 | 2 |
| Check-in rồi đi tiếp ngoài hành lang | D3 / R1 | 2, 1 |
| Ở lại một phần nhỏ của buổi rồi về | R2 / R5 | 1 |
| Hai người đổi danh tính (một tên xuất hiện ở hai nơi) | R3 | 1 |
| Check-in hai lần | R4 | 1 |

Chia tập: train, validation, test theo **buổi** (không trộn cùng một buổi vào hai tập). Có seed cố định để chạy lại ra cùng kết quả.

## 8. Các bước thực hiện (mỗi bước dừng lại cho bạn duyệt rồi mới commit)

| Bước | Việc | Kết quả để duyệt | Phụ thuộc |
| --- | --- | --- | --- |
| 0 | Nói với Mai Chi về ranh giới với `link_names.py` (mục 1). Nhóm đồng ý thêm thư viện (mục 11) | Ghi vào `.agents/decisions.md` | |
| 1 | `trajectories.py`: quỹ đạo trên bản đồ cho 8 take | Hình quỹ đạo take 1, 3 trên bản đồ | Homography (có sẵn) |
| 2 | Crossing + mô hình Δt + Hungarian (tính năng 2, chưa có classifier) | Bảng ghép take 1, 3, 4, 8 so với ground truth, số cảnh báo sai | Bước 1 |
| 3 | `simulate.py` với tham số fit từ bước 1–2 | Hình so sánh phân phối thật với mô phỏng (tốc độ, Δt) | Bước 1–2 |
| 4 | Tính năng 2 đầy đủ: classifier cho ca mơ hồ, đánh giá trên mô phỏng | Bảng precision, recall, F1 cho D1–D3 | Bước 3 |
| 5 | Tính năng 1: đặc trưng + luật R1–R5 + unittest | Bảng đặc trưng cho mỗi take thật | Bước 2 |
| 6 | Tính năng 1: `IsolationForest` so với classifier, ablation, độ nhạy | Bảng số + hình ROC | Bước 3, 5 |
| 7 | Quay take gian lận có kịch bản (cả nhóm), ghi ground truth cùng định dạng `data/ground_truth/` | Đánh giá trên dữ liệu thật | Cả nhóm |
| 8 | `infer.py` + `presence_verification.joblib` | Hợp đồng ở mục 9 có unittest | Bước 4, 6 |
| 9 | Backend: feature plug-in `backend/app/features/presence_verification/` (`@register_feature`), API cảnh báo | Routes dưới `/api/features/presence_verification/` | Bước 8 |
| 10 | Frontend: panel cảnh báo, chấm đỏ và vệt đường trên `RoomMap.vue` | Demo trên trang Demo | Bước 9 |
| 11 | Kịch bản quay video demo + phần báo cáo cá nhân | | Tất cả |

**Nếu thiếu thời gian, ưu tiên:** 1 → 2 → 5 (luật) → 10 (demo) → 3 → 4 → 6 → 7. Tính năng 2 với mô hình Δt đã đủ để demo và báo cáo phần "model". Classifier và tính năng 1 bằng `IsolationForest` là phần cộng thêm.

## 9. Hợp đồng `infer.py` (cho backend, chốt ở bước 8)

Không import thư viện nặng ở đầu file. Mô hình nạp một lần khi dùng lần đầu.

| Hàm | Vào | Ra |
| --- | --- | --- |
| `to_map(cam_id, box)` | Box chuẩn hóa `[x, y, w, h]` | `(x, y)` trên bản đồ, hoặc `None` nếu chân bị cắt |
| `audit_door(check_ins, points)` | Check-in `[{t, student_id, similarity}]`, điểm bản đồ `[{t, track_id, x, y}]` | `{"matches": [{student_id, track_id, cost}], "alerts": [{code, t, track_ids, student_id, score, reason}]}` |
| `score_session(session, check_ins, points, door_result)` | Thông tin buổi + như trên | `[{student_id, score, reasons: [...], features: {...}}]` |

Các dạng dữ liệu này là **API contract** (quy tắc 2 của `.agents/`). Sau khi chốt thì chỉ được thêm trường, không đổi tên.

## 10. Tích hợp vào app (bước 9–10, chỉ phác thảo)

- Event bus: subscribe `check_in`, `seen`, `in`, `out`, `spoof`; publish `alert`. Door audit chạy theo cửa sổ trượt (gần thời gian thực). Presence verification chấm điểm khi buổi kết thúc, và có thể chấm tạm giữa buổi.
- Lưu: SQLite, thêm bảng `presence_alerts` (cảnh báo) và `presence_feedback` (giáo viên xác nhận hoặc bỏ qua).
- Giao diện: panel cảnh báo trên trang Demo/Home. Bấm một cảnh báo thì bản đồ phát lại đoạn đó và tô đỏ các track liên quan.
- Phản hồi của giáo viên trở thành nhãn thật để train lại classifier (tùy chọn, sau cùng).

## 11. Rủi ro

| Rủi ro | Cách xử lý |
| --- | --- |
| Take thật quá ngắn và ít (8 take, 4 người) | Train trên mô phỏng, dùng dữ liệu thật để fit tham số và đánh giá. Báo riêng con số "mô phỏng sang thật" |
| Homography chỉ là ước lượng | Vùng cửa có biên. Có phân tích độ nhạy |
| Sai lệch đồng bộ đồng hồ giữa các camera | Mô hình Δt có thành phần nền đều. Cửa chặn Δt chọn trên dữ liệu |
| ID switch (take 3: ID 1 thành 5) gây cảnh báo giả D1 | Crossing cần đi qua vùng cửa, không chỉ xuất hiện. Track bắt đầu sâu trong phòng không tính là crossing |
| Bị cho là overlap với `link_names.py` / anti-spoofing | Mục 1: mình kiểm tra, không đặt tên. Spoof chỉ là đặc trưng phụ |
| Mô phỏng quá "dễ" nên kết quả đẹp giả | Tham số lấy từ dữ liệu thật. Có nhiễu và mất track. Đánh giá chính trên take thật |
| Quyền riêng tư | Chỉ lưu tọa độ và thời gian, không lưu ảnh. Cảnh báo cần người xác nhận |

## 12. Cần quyết định / cần nhóm đồng ý

1. **Thư viện mới:** `scikit-learn` (`IsolationForest`, classifier, metrics), `scipy` (Hungarian, KDE), `joblib` (lưu mô hình). Cần thêm vào `requirements.txt`, mà đây là file chung.
2. **`.gitignore`** (file chung): thêm `*.joblib` và `ml/presence_verification/outputs/`.
3. **Mai Chi:** đồng ý ranh giới với `link_names.py`. Mình chỉ đọc `data/tracks/` và không ghi vào đó.
4. **Cả nhóm:** quay 6–10 take có kịch bản (mục 7), mỗi take 30–60 s, ghi ground truth theo định dạng `data/ground_truth/take<N>.csv`. Định dạng này có thể cần thêm event `tailgate`, `leave`.
5. **Ngôn ngữ tài liệu:** `.agents/` quy định tài liệu viết bằng tiếng Anh. Kế hoạch này viết tiếng Việt để bạn duyệt (giống PLAN cũ). Code, comment và README cuối cùng sẽ viết bằng tiếng Anh.

## 13. Khác với kế hoạch khi triển khai (2026-11-23)

Phát hiện khi chạy trên dữ liệu thật, đã sửa trong code:

- **Vùng hợp lệ của homography:** cam_1 nhìn xuyên kính vào phòng, cam_2 "thấy" một tấm poster ở hành lang; điểm chiếu ra ngoài vùng đó bị **bỏ**, không kẹp vào biên (`trajectories.VALID_X`).
- **Thời điểm vào lớp** = lúc track của cam_2 rời vùng cửa (take 1: 4/4 lần vào lệch ≤ 0,7 s so với ground truth). cam_2 thường mất người ngay sau cửa, nên track chỉ có ở cửa cũng tính là "vào".
- **Có mặt cho tới khi thấy đi ra:** track biến mất trong phòng (chưa có Re-ID) không có nghĩa là về.
- **Gộp check-in trùng trong 20 s** (take 3 có hai check-in của cùng một người cách 12 s do ID switch).
- **Đặc trưng mạnh nhất của classifier ghép cặp:** người check-in đang đứng ở cửa (camera điểm danh nằm ngay cửa), nên lần đứng ở cửa của track đúng phải chứa thời điểm check-in (take 1, 4, 8: 6/6). Thêm đặc trưng này đưa F1 cảnh báo vào lớp từ ~0,45 lên ~0,74 trên tập test mô phỏng.
- **Điểm cảnh báo + ngưỡng tối thiểu** học trên tập validation, cùng chi phí "không ghép".
- **Thời gian trong lớp tính từ lúc vào**, không từ lúc check-in (thời gian đi từ cửa là `door_to_room_s`).
- **Mô phỏng chỉnh theo dữ liệu thật:** tốc độ đi 0,9–1,8 m/s, nhiễu tọa độ đuôi dài (Student-t), người xếp hàng vào theo thứ tự check-in.
- **Take thật được chấm như phần đầu của một buổi 90 phút** (`sessions.CLASS_S`): take chỉ quay lúc mọi người đến; chấm theo độ dài take làm ai đến sau cũng thành "muộn".
- Hàm `infer.audit_door(check_ins, points)` / `score_session(...)` / `analyze_take(take)` như mục 9; API backend: `GET /api/features/presence_verification/take/{take}`, `/model`, `/live`.
