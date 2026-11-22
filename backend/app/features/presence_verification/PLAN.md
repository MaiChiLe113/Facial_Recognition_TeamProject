# PLAN — Xác minh sự có mặt (Presence Verification)

Tính năng sáng tạo cá nhân của Đức Mạnh (COS30082, mục 7 của đề bài).

## 1. Mục tiêu

Check-in đúng khuôn mặt **chưa đủ** để chứng minh sinh viên có mặt. Tính năng này kiểm tra **sau khi check-in**: người đó có thật sự vào lớp và ở lại hay không, dựa trên đường đi trên bản đồ 2D, thời gian có mặt và tính nhất quán giữa các camera.

Kết quả: mỗi sinh viên trong mỗi buổi có một **điểm bất thường** (0–1) và một danh sách **lý do**. Các cảnh báo hiện trên dashboard và trên bản đồ 2D.

### Ranh giới với phần của người khác (không overlap)

| Module | Chủ | Tính năng này làm gì với nó |
| --- | --- | --- |
| Anti-spoofing (`liveness.py`) | Hồng Minh | Chỉ **đọc** số lần bị báo `spoof`, dùng làm một đặc trưng phụ. Không tự phát hiện ảnh giả |
| Nhận diện (`recognizer.py`) | Thuận Minh | Chỉ đọc `student_id` và độ tự tin |
| Tracking, multi-camera, homography | Mai Chi | Chỉ đọc track và tọa độ trên bản đồ. Không sửa `matcher.py`, `ml/tracking/` |
| Emotion | Minh Thành | Không dùng |

Câu trả lời khi phỏng vấn: *"Anti-spoofing kiểm tra khuôn mặt có thật tại thời điểm check-in; tính năng của em kiểm tra người đó có thật sự ở trong lớp suốt buổi."*

## 2. Các trường hợp cần phát hiện

| Mã | Tình huống | Dữ liệu cần |
| --- | --- | --- |
| R1 | Check-in ở cửa nhưng **không có track nào đi vào phòng** (x > 0.3 trên bản đồ) trong N giây | check_in + track cam_2 / bản đồ |
| R2 | Check-in xong nhưng **thời gian trong lớp quá ngắn** (< X% buổi học) | presence_intervals / track |
| R3 | **Một tên ở hai nơi** cùng lúc trên bản đồ (khoảng cách quá lớn so với thời gian) | tọa độ bản đồ + tên đã gán |
| R4 | **Check-in trùng** (cùng tên, nhiều lần) hoặc nhiều tên khác nhau gán cho cùng một track | sự kiện check_in |
| R5 | **Ra về sớm** rồi không quay lại | sự kiện `out` / track |
| M  | Mô hình học máy: hành vi khác hẳn số đông (không cần luật cụ thể) | vector đặc trưng (mục 4) |

Các luật R1–R5 dễ giải thích. Mô hình M bắt những trường hợp luật không viết ra, và là phần "build và train" cho báo cáo cá nhân.

## 3. Tech stack

Chỉ dùng những gì repo đã có hoặc thư viện nhỏ, phổ biến.

| Phần | Công nghệ | Ghi chú |
| --- | --- | --- |
| Backend feature | Python 3.10+, FastAPI, plug-in `@register_feature` | Theo mẫu `features/event_counter/`, routes ở `/api/features/presence_verification/` |
| Event bus | `app/core/events.py` | Subscribe `check_in`, `seen`, `in`, `out`, `spoof`; publish `alert` |
| Lưu trữ | SQLite qua SQLAlchemy Core (`app/db/`) | Thêm bảng `presence_alerts`, `presence_features`, `presence_feedback` |
| Hình học | NumPy + homography có sẵn (`data/calibration/<cam>_homography.json`) | Chỉ đọc; chuyển box → điểm chân → tọa độ bản đồ |
| Mô hình | scikit-learn: `IsolationForest` (không nhãn) và `LogisticRegression` / `RandomForestClassifier` (có nhãn) | Lưu bằng `joblib`; cần thêm `scikit-learn` vào `requirements.txt` (hỏi nhóm) |
| Đánh giá | scikit-learn metrics (precision, recall, F1, ROC-AUC), matplotlib | Notebook trong thư mục của mình |
| Frontend | Vue 3 + Vite, SVG trong `RoomMap.vue` | Chấm đỏ nhấp nháy, vệt đường đi, panel Cảnh báo |
| Test | `unittest` (stdlib) trong `backend/tests/` | Theo quyết định 2026-11-16 |

## 4. Đặc trưng (feature vector) cho mỗi sinh viên × buổi

| Đặc trưng | Ý nghĩa |
| --- | --- |
| `checkin_offset_s` | Check-in muộn bao nhiêu giây so với giờ bắt đầu |
| `n_checkins` | Số lần check-in |
| `n_spoof_flags` | Số lần liveness báo spoof (đọc từ Hồng Minh) |
| `recog_conf_mean` | Độ tự tin nhận diện trung bình |
| `door_to_room_s` | Thời gian từ check-in đến lúc xuất hiện trong phòng (∞ nếu không xuất hiện) |
| `time_in_room_ratio` | Tỉ lệ thời gian trong phòng / độ dài buổi |
| `n_exits` | Số lần ra khỏi phòng |
| `path_length` | Quãng đường đi trên bản đồ |
| `max_speed` | Tốc độ lớn nhất (phát hiện "nhảy" vị trí, liên quan R3) |
| `seat_stability` | Độ lệch vị trí khi ngồi (ngồi yên hay đi lại) |
| `n_name_conflicts` | Số lần tên này bị gán cho track khác cùng lúc |

## 5. Dữ liệu cần

| Dữ liệu | Có chưa | Nguồn / việc cần làm |
| --- | --- | --- |
| Track từng camera (box theo thời gian) | **Có**: `data/tracks/take1..8/` | Mai Chi |
| Homography cam_1, cam_2 → bản đồ | **Có (ước lượng)**: `data/calibration/` | Mai Chi |
| Bản đồ phòng 204 | **Có**: `data/calibration/room204_map.json` | Mai Chi |
| Tên gán cho track (handoff qua cửa) | **Có một phần**: take 1, 3, 4, 8 | `link_names.py` (Mai Chi) |
| Sự kiện check-in / spoof live | **Chưa**: stub `NotImplementedError` | Dùng tạm sự kiện giả lập từ track |
| ID chung giữa camera (`GlobalMatcher`) | **Chưa** | R3 tạm dùng tên handoff |
| **Video gian lận có kịch bản** | **Chưa** | Nhóm quay thêm 6–10 take: check-in rồi bỏ đi, ngồi 1 phút rồi ra, hai người đổi chỗ… |
| Nhãn bình thường / gian lận | **Chưa** | Ghi tay theo kịch bản (`data/eval/presence_labels.csv`) |
| Dữ liệu bình thường số lượng lớn | **Thiếu** | **Mô phỏng**: sinh đường đi tổng hợp trên bản đồ (bình thường + các kiểu gian lận) để train và kiểm thử |

Định dạng cần thống nhất với Mai Chi (mỗi điểm trên bản đồ):

```json
{ "take": 1, "global_id": 5, "name": "Le Mai Chi", "t": 5.7, "x": 0.42, "y": 0.61, "cam_id": "cam_2" }
```

## 6. Các bước thực hiện

| Bước | Việc | Kết quả | Phụ thuộc |
| --- | --- | --- | --- |
| 0 | Báo Mai Chi và Hồng Minh về phạm vi; chốt định dạng dữ liệu vị trí | Ghi vào `.agents/decisions.md` | — |
| 1 | Tạo khung feature: `features/presence_verification/__init__.py`, bật trong `pipeline.json`, trả `not_ready` | `/api/pipeline/status` thấy feature | — |
| 2 | Script chuyển track → tọa độ bản đồ (đọc homography, điểm chân box) | `data/presence/take<N>.json` | Homography (có) |
| 3 | Bộ mô phỏng: sinh đường đi bình thường + 5 kiểu gian lận R1–R5 | Tập train/test tổng hợp có nhãn | Bước 2 (để khớp phân phối) |
| 4 | Trích đặc trưng (mục 4) + luật R1–R5 | Hàm `extract_features()`, `apply_rules()` + unittest | Bước 2–3 |
| 5 | Train `IsolationForest` trên dữ liệu bình thường; train classifier trên dữ liệu có nhãn; so sánh | Notebook + `model.joblib` + bảng precision/recall/F1/AUC | Bước 4 |
| 6 | Quay take gian lận theo kịch bản và gán nhãn; đánh giá trên dữ liệu thật | Kết quả thật cho báo cáo | Cả nhóm (quay) |
| 7 | Nối vào event bus: chấm điểm khi kết thúc buổi và theo thời gian thực; publish `alert`; lưu SQLite | Bảng `presence_alerts` | Bước 4–5 |
| 8 | API: `GET /alerts?session_id=`, `GET /trail/{global_id}`, `POST /alerts/{id}/feedback` | Routes dưới `/api/features/presence_verification/` | Bước 7 |
| 9 | Frontend: panel Cảnh báo, chấm đỏ + vệt đường đi trên `RoomMap.vue`, nút Xác nhận/Bỏ qua, phát lại khi bấm cảnh báo | Demo trên trang Demo/Home | Bước 8 |
| 10 | Vòng phản hồi: nhãn giáo viên → train lại classifier | Nút "Retrain" + version model | Bước 8–9 |
| 11 | Kịch bản demo cho video (một take liền) + phần báo cáo cá nhân | Script demo, hình ROC, bảng kết quả | Tất cả |

**Thứ tự ưu tiên khi thiếu thời gian:** bước 1–2–4 (luật) → 9 (giao diện) → 5 (mô hình) → 3, 6, 10.

## 7. Đánh giá (cho báo cáo)

- **Luật:** precision / recall từng luật trên take có kịch bản.
- **Mô hình:** so sánh Isolation Forest và classifier có giám sát: precision, recall, F1, ROC-AUC; ma trận nhầm lẫn.
- **Ablation:** bỏ từng nhóm đặc trưng (thời gian, không gian, nhận diện) để xem nhóm nào quan trọng.
- **Độ nhạy với sai số homography:** thêm nhiễu vào tọa độ, xem kết quả giảm bao nhiêu.
- **Báo động giả:** số cảnh báo sai trên các take bình thường (1, 3, 4, 8).

## 8. Rủi ro

| Rủi ro | Cách xử lý |
| --- | --- |
| `GlobalMatcher` chưa xong → R3 không chạy | Dùng tên handoff từ `link_names.py`; R3 để sau |
| Homography chỉ là ước lượng | Ngưỡng có biên an toàn; báo cáo phân tích độ nhạy |
| Ít dữ liệu gian lận thật | Mô phỏng + Isolation Forest (không cần nhãn) + vài take có kịch bản |
| Tracker đổi ID (ví dụ take 3: ID 1 → ID 5) gây báo động giả | Gộp track cùng tên gần nhau theo thời gian; đặc trưng `n_name_conflicts` |
| Bị cho là overlap với anti-spoofing | Spoof chỉ là một đặc trưng phụ; trọng tâm là thời gian + không gian (mục 1) |
| Quyền riêng tư | Chỉ lưu tọa độ, không lưu ảnh; cảnh báo cần giáo viên xác nhận, không tự trừ điểm |

## 9. File sẽ tạo / sửa

- Mới: `backend/app/features/presence_verification/` (`__init__.py`, `features.py`, `rules.py`, `model.py`, `simulate.py`, notebook)
- Mới: `backend/tests/test_presence_verification.py`
- Sửa: `backend/pipeline.json` (bật feature), `backend/app/db/schema.sql` (3 bảng mới)
- Sửa: `frontend/src/components/RoomMap.vue`, thêm `AlertPanel.vue`, `api.js`
- Cần nhóm đồng ý: `requirements.txt` (`scikit-learn`, `joblib`), video take mới trong `data/`
