# TEST — Kiểm thử tay: Presence verification + Door audit

Các bước để tự kiểm tra tính năng, kèm kết quả mong đợi. Chạy mọi lệnh từ **thư mục gốc của repo** bằng Git Bash.
Môi trường Python là `.venv` ở thư mục gốc (backend cũng dùng nó). Trên PowerShell, thay `.venv/Scripts/python`
bằng `.venv\Scripts\python`.

Số liệu bên dưới lấy từ lần chạy ngày 2026-11-23 (scikit-learn 1.9.1, numpy 2.5.5, seed cố định). Cùng phiên bản
thư viện thì ra **đúng** các số này. Khác phiên bản thì có thể lệch ở chữ số thứ hai, nhưng thứ tự giữa các phương pháp phải giữ nguyên.

---

## 0. Chuẩn bị (một lần)

```bash
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install matplotlib
.venv/Scripts/python -c "import sklearn, scipy, joblib; print('ok')"
```

**Mong đợi:** in ra `ok`.

---

## 1. Unit test (chưa cần mô hình)

```bash
.venv/Scripts/python -m unittest discover -s ml/presence_verification/tests -v
```

**Mong đợi:**
- Nếu **chưa** train: `Ran 19 tests ... OK (skipped=3)`. Ba test `InferContract` bỏ qua vì chưa có `presence_verification.joblib`.
- Nếu **đã** train: `Ran 19 tests ... OK`.
- Trong danh sách có `test_take1_entries_match_ground_truth ... ok`, nghĩa là trên take 1 tìm đủ 4 lần vào lớp, mỗi lần lệch ≤ 2,5 s so với nhãn tay.

---

## 2. Xem quỹ đạo trên bản đồ (kiểm tra bằng mắt)

```bash
.venv/Scripts/python ml/presence_verification/trajectories.py --take 1 --plot
```

**Mong đợi:**
- In ra `take 1: 9 trajectories, 794 points -> take1.json` và đường dẫn tới `outputs/trajectories/take1.png`.
- Mở file PNG. Bốn đường nét đứt (cam_1, có tên 4 thành viên) đi dọc hành lang (x < 0,3) tới **dải xanh của cửa** (x = 0,3, y ≈ 0,8–0,96).
  Đường liền tím (`cam_2 5 Le Mai Chi`) đi tiếp từ cửa vào trong phòng tới chỗ ngồi (x ≈ 0,48, y ≈ 0,5).
- **Không có điểm nào nằm sát mép** x = −0,5 hay 1,5. Điểm chiếu sai đã bị bỏ, không bị kẹp vào biên.

Chạy `--take all` để có file JSON cho cả 8 take (bỏ `--plot` nếu không cần hình).

---

## 3. Train và đánh giá

```bash
.venv/Scripts/python ml/presence_verification/train.py        # khoảng 1,5–2 phút
.venv/Scripts/python ml/presence_verification/evaluate.py     # khoảng 1–2 phút
```

**Mong đợi khi train** (4 dòng chính):

```
dt model from 9 real samples: median 5.8 s, sigma 0.64  ([4.5, 3.5, 3.0, 3.5, 9.9, 12.8, 13.3, 13.5, 0.5])
simulated 900 train + 250 val sessions (...)
door audit: mode clf, val mean F1 window 0.1321 | dt 0.3104 | clf 0.4296 (...)
presence: val AUC {'iforest': 0.7792, 'logreg': 0.797, 'rf': 0.8272} -> rf, threshold 0.42 (val F1 0.504) (...)
```

- 9 mẫu Δt: 4 từ ground truth take 1, 3 từ take 3 (nhóm đứng ở cửa nên Δt khoảng 10–13 s), 1 từ take 4, 1 từ take 8.
- Chọn `mode clf` (classifier ghép cặp) và `rf` (Random Forest).
- Tạo ra `ml/presence_verification/presence_verification.joblib` và `outputs/train_report.json`.

**Mong đợi khi evaluate:** tạo `outputs/eval/report.md`, `report.json`, `presence_roc.png`, `door_f1.png`. Mở `report.md` và kiểm tra:

| Mục | Giá trị mong đợi |
| --- | --- |
| Door audit, F1 cảnh báo vào lớp: cửa sổ cố định / Δt / classifier | 0,2156 / 0,4809 / **0,6777** (classifier tốt nhất) |
| Door audit, độ chính xác ghép cặp của classifier | 0,6981 |
| Presence, AUC chỉ dùng luật | 0,7132 |
| Presence, AUC của mô hình (iforest / logreg / rf) | 0,7887 / 0,8118 / **0,8603** |
| Recall loại `late` (đến rất muộn): luật / mô hình + luật | 0,08 / **0,94**: mô hình bắt được thứ luật không bắt |
| Nhiễu tọa độ 0,12 / 0,3 / 0,6 m | AUC 0,8661 / 0,8193 / 0,7724 (giảm dần, không sụp) |

Bảng **Recorded takes** ở cuối `report.md`:

| Take | Mong đợi |
| --- | --- |
| 1 | 4 check-in, 4 lần vào, `4/4` khớp ground truth, `4/4` khớp `link_names`, **không cảnh báo, không ai bị gắn cờ** |
| 2 | Không check-in, không lần vào, không cảnh báo |
| 3 | `D3 at 12.4 s; D1 at 22.8 s`, Hồng Minh bị gắn cờ. **Đây là báo nhầm đã biết:** ba người đứng ở cửa khoảng 10 s, tracker đổi ID |
| 4, 8 | 1 check-in, 1 lần vào, `1/1` khớp `link_names`, không cảnh báo |
| 5, 6, 7 | Một `D1` mỗi take: có người vào nhưng camera điểm danh không nhận ra ai. Đúng hay sai tùy kịch bản của take, hiện chưa ghi ("TBC") |

---

## 4. Thử kịch bản tự dựng (door audit)

```bash
.venv/Scripts/python ml/presence_verification/tests/manual_scenarios.py
```

**Mong đợi** (cần đã train ở bước 3):

```
== 1. Normal: A and B check in, each walks in
   matches: [('A', 'cam_2:1', 3.0), ('B', 'cam_2:2', 3.0)]
   alerts:  none
== 2. Tailgating: A checks in, two people walk in together
   matches: [('A', 'cam_2:1', 3.0)]
   alerts:  [('D2', 15.0, 'Entered 2.0 s behind A without a check-in of their own (tailgating)')]
== 3. Nobody checks in, someone walks in
   alerts:  [('D1', 8.5, 'Walked into the room with no matching check-in')]
== 4. A checks in and walks off down the corridor
   alerts:  [('D3', 10.0, 'A checked in but nobody was seen walking into the room')]
```

Bạn có thể sửa file đó để thử thêm, ví dụ đổi `walk_in("cam_2:2", 11.5)` thành `walk_in("cam_2:2", 40)`.
Người thứ hai giờ vào cách xa 25 s, nên cảnh báo đổi từ `D2` (theo đuôi) sang `D1` (vào không check-in).

---

## 5. Test backend

```bash
cd backend && ../.venv/Scripts/python -m unittest discover -s tests -t . ; cd ..
```

**Mong đợi:** `Ran 33 tests ... OK`. Trong đó có 3 test mới ở `tests/test_presence_feature.py`:
- Thiếu mô hình thì feature báo `failed`, có chữ "not found", và không làm sập engine.
- Không bật trong config thì feature ở trạng thái `disabled`.
- Route take 1 trả về 4 cặp ghép và không có cảnh báo.

---

## 6. API khi chạy backend

```bash
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Mở trên trình duyệt (hoặc vào http://localhost:8000/docs và thử ở đó):

| URL | Mong đợi |
| --- | --- |
| http://localhost:8000/api/pipeline/status | Trong `features` có `{"feature": "presence_verification", "status": "ready", "error": null, ...}`, và `info.model.door_mode = "clf"`, `presence_model = "rf"` |
| http://localhost:8000/api/features/presence_verification/take/1 | `alerts: []`; 4 `matches` (Le Mai Chi → `cam_2:5` dt 4.7, Do Trinh Thuan Minh → `cam_2:6` 4.8, Nguyen Duc Manh → `cam_2:16` 3.9, Nguyen Hong Minh → `cam_2:25` 4.0); 4 `students`, tất cả `flagged: false`, score < 0,15; `duration: 49.1`, `scored_as_class_s: 5400`; 9 `trails` |
| …/take/3 | `alerts`: `D3` lúc 12.4 và `D1` lúc 22.8; Nguyen Hong Minh `flagged: true`, `score: 0.8`, lý do `R1: checked in at 12.4 s but was never seen walking into the room` |
| …/take/5 | Một `D1` lúc 8.6, `students: []` |
| …/take/99 | HTTP **404**, `"No data for take 99: data/tracks/take99/ does not exist"` |
| http://localhost:8000/api/features/presence_verification/model | `door_mode: "clf"`, `presence_model: "rf"`, `threshold: 0.42`, `dt_model.median_s: 5.77` |
| http://localhost:8000/api/dashboard, /api/demo/config, /api/tracks/cam_1 | Vẫn trả 200 và **đúng dạng cũ** (tính năng chỉ thêm route mới) |

---

## 7. Giao diện: trang MultiCam (Demo)

Chạy backend (bước 6) và frontend:

```bash
cd frontend && npm run dev        # http://localhost:5173
```

Mở trang **MultiCam** (Demo).

1. **Take 3 được chọn sẵn** (mặc định trong `video_config.json`). Cuộn xuống dưới bản đồ.
   - **Mong đợi:** có panel **Presence verification**, góc phải ghi `door: clf · presence: rf · threshold 0.42`.
   - Phần *Door audit* ghi `3 check-in(s) · 3 entries · 2 matched`, kèm 2 dòng cảnh báo: `0:12 D3 Checked in, never entered …` và `0:22 D1 Entered without check-in …`.
   - Bảng *Students* có 3 dòng. Hong Minh đứng đầu với `80%` và nhãn đỏ **Check**, hai người còn lại nhãn xanh **OK**.
   - Bản đồ phòng 204 hiện **vệt đường đi** (xanh dương). Vệt dính tới cảnh báo màu **đỏ**, chấm cuối nhấp nháy.
     Lúc này các chấm "ID n / tên" giả lập của bản đồ cũ không còn hiện.
2. **Chọn take 1** trong bảng *Recorded takes* ở cuối trang.
   - **Mong đợi:** dòng xanh *No door alert: every entry has a check-in and every check-in an entry.*; 4 sinh viên đều **OK**; cột *Entered* ghi giờ vào kèm `(+4.7 s)`, … Không có vệt đỏ.
3. **Bấm Play** (cần video: `HAWKEYE_VIDEO_ROOT` trong `backend/.env`).
   - **Mong đợi:** vệt trên bản đồ **dài dần theo video**.
   - Ở take 3, hai cảnh báo hiện mờ với chữ *later in the take* cho tới khi video tới 0:12 và 0:22, rồi mới hiện rõ lý do.
   - Kéo thanh thời gian về đầu thì cảnh báo mờ lại.
   - Không có video thì panel vẫn hiện đầy đủ, chỉ không chạy theo thời gian.
4. **Chọn take 5.**
   - **Mong đợi:** một cảnh báo `D1` lúc 0:08, và dòng *Nobody was recognised at the attendance camera in this take.*
5. **Tắt backend** (Ctrl+C) rồi tải lại trang.
   - **Mong đợi:** panel ghi *The backend is not running.* Phần còn lại của trang vẫn chạy bằng dữ liệu mock (quy tắc offline fallback).

---

## 8. Khi thiếu mô hình

1. Tắt backend. Đổi tên `ml/presence_verification/presence_verification.joblib` thành `presence_verification.joblib.bak`.
2. Bật lại backend.
   - **Mong đợi:** `/api/pipeline/status` ghi `presence_verification` ở trạng thái `failed`, với `error` chứa `presence_verification.joblib not found. Train it: python ml/presence_verification/train.py`. Các feature và trang khác vẫn chạy.
   - Trang MultiCam: panel ghi đỏ *Presence verification is not running. Train the model (ml/presence_verification/train.py), then restart the backend.*
3. Đổi tên file về như cũ và bật lại backend: panel hiện lại bình thường.

---

## 9. Những gì **chưa** kiểm thử được (cần làm thêm)

- **Gian lận thật:** chưa có take nào quay cảnh gian lận. Mọi con số về phát hiện gian lận ở bước 3 đến từ mô phỏng. Gợi ý kịch bản quay (mỗi take 30–60 s):
  (a) hai người vào sát nhau, chỉ một người nhìn camera điểm danh: mong đợi **D2**;
  (b) một người đi qua cửa, cúi mặt: mong đợi **D1**;
  (c) check-in rồi đi tiếp ngoài hành lang: mong đợi **D3** và **R1**;
  (d) vào lớp rồi đi ra trước khi take kết thúc: mong đợi **R5**.
  Ghi ground truth cùng định dạng `data/ground_truth/take<N>.csv`, tính track và gán tên cho take mới bằng script của nhóm (`ml/tracking/precompute_tracks.py`, rồi
  `ml/face_recognition/name_tracks.py`, script này gọi luôn `link_names.py`), rồi chạy lại bước 3.
- **Chế độ live:** route `/live` chỉ mới ghi lại các sự kiện `check_in` từ pipeline, chưa chạy audit theo thời gian thực, vì pipeline live chưa phát ra vị trí trên bản đồ.
