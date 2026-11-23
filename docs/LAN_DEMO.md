# Demo over Wi-Fi: one backend, every device's camera

One laptop (the **host**) runs the backend and the frontend. Every other laptop or phone on the **same Wi-Fi** opens
the host's address in a browser and uses **its own camera**. Frames go to the host, which runs face recognition,
liveness and emotion and sends the result back. Nothing is installed on the other devices.

```
phone / laptop (browser + its camera)  --https-->  host :5173 (Vite)  --proxy-->  host :8000 (FastAPI + models)
```

Only port 5173 has to be reachable. The backend stays on the host (`localhost:8000`); Vite forwards `/api`, `/videos`
and `/photos` to it.

**Why https:** browsers only allow the camera on `https://` pages or on `localhost`. On `http://192.168.x.x:5173` the
camera is blocked on every device except the host. `npm run dev:lan` therefore serves https with a self-signed
certificate; each device accepts a warning once (step 5), and browsers label the page "Not secure". To remove the
warning, see "No 'Not secure' warning" below.

## 1. Host setup (once)

Do the normal setup from the root [README](../README.md) ("Run it"), then check:

| Check | How |
| --- | --- |
| Backend packages, including torch, OpenCV < 5 and ultralytics | `backend/.venv/bin/pip install -r requirements.txt` (Windows: `backend\.venv\Scripts\pip ...`) |
| Frontend packages | `cd frontend && npm install` (adds `@vitejs/plugin-basic-ssl`) |
| Model weights | `ml/face_recognition/face_recognition.pt`, `ml/anti_spoofing/anti_spoofing.pt`, `ml/emotion/emotion.pt`. `GET /api/features-demo/status` shows `"found": true` for each |
| Registered students | `HAWKEYE_DRIVE_ROOT` / `HAWKEYE_VIDEO_ROOT` in `backend/.env` point at the synced Drive, and the photo folders are **available offline**. The Features demo page lists the registered people |
| Laptop power | Plugged in, sleep off for the demo |

## 2. Put every device on the same network

- All devices join the **same Wi-Fi**.
- Campus or guest Wi-Fi often blocks devices from reaching each other ("client isolation"). If step 6 cannot load,
  use a **phone hotspot** instead and connect the host and the other devices to it.

## 3. Start the backend on the host

```bash
cd backend
.venv/bin/uvicorn app.main:app --port 8000
```

Windows: `.venv\Scripts\uvicorn app.main:app --port 8000`. Leave this terminal open.

## 4. Start the frontend in Wi-Fi mode on the host

```bash
cd frontend
npm run dev:lan
```

Vite prints two addresses:

```
➜  Local:   https://localhost:5173/
➜  Network: https://192.168.68.118:5173/
```

The **Network** line is the address for the other devices. If it is missing, find the host's IP with
`ipconfig getifaddr en0` (macOS) or `ipconfig` → "IPv4 Address" (Windows).

**Firewall:** the first time, macOS asks whether `node` may accept incoming connections → **Allow**. On Windows,
allow Node.js on **Private networks** when Windows Defender Firewall asks.

`npm run dev` (without `:lan`) still works as before: http, this machine only.

## 5. Open it on another device

1. Open the Network address with the page path, e.g. `https://192.168.68.118:5173/features-demo`.
2. Accept the certificate warning once (the certificate is self-signed, made by the host):

   | Browser | Steps |
   | --- | --- |
   | Chrome / Edge | **Advanced** → **Proceed to 192.168.x.x (unsafe)** |
   | Safari (macOS, iPhone) | **Show Details** → **visit this website** → confirm |
   | Firefox | **Advanced…** → **Accept the Risk and Continue** |

3. Allow the camera when the browser asks.

| Page | Path | Uses the device's camera for |
| --- | --- | --- |
| Camera | `/camera` | Sending its video to the host's **Live cameras** page (see below) |
| Features demo | `/features-demo` | Face recognition, liveness and emotion on every frame |
| Home | `/` | Live camera tile |
| Add person | `/add` | Taking registration photos |
| MultiCam | `/demo` | Recorded takes only (no camera) |

Several devices can use the Features demo at once: each browser tab has its own ID, so liveness keeps a separate
frame buffer per device. All the computing happens on the host (about 75–90 ms per frame on Mai Chi's Mac, measured
2026-11-23), so with many devices at once each one gets fewer results per second.

## Phones as cameras, everything shown on the host

For the three-camera demo (corridor, classroom, doorway), the other devices are only cameras and the host shows all
of them, with detection, tracking and recognition drawn on the video.

1. **Each phone / laptop:** open `https://<host IP>:5173/camera` and tap where it stands: **CAM 1 Corridor**,
   **CAM 2 Classroom** or **Attendance camera Doorway** (or open `/camera?cam=cam_1` to skip the choice).
   It shows its own preview and "sending to the host · n fps". **Switch camera** picks the front or back camera;
   the screen is kept on while it sends.
2. **The host:** open **Live cameras** in the sidebar (`/live`). Each camera tile shows the device's video with:
   - corridor / classroom: a box per person with its track ID (YOLO11n + ByteTrack, the same settings as the
     recorded takes; a person hidden for up to 3 s keeps the ID);
   - doorway: a box per face with the name, liveness (**Spoof** in red) and emotion; the list under the tile repeats it.

How it works: the device sends a JPEG frame (640 px wide, at most 10 a second) over the WebSocket
`/ws/camera/<cam_id>` and waits for the host's answer before sending the next, so a busy host lowers the frame rate
instead of falling behind. The host runs the camera's pipeline from `backend/pipeline.json` and serves the drawn frames
as an MJPEG stream (`/api/live/<cam_id>/stream`). Measured on Mai Chi's Mac with recorded frames sent as a phone would:
corridor ~12 fps (about 15–25 ms of work a frame), doorway ~4–6 fps (about 170 ms: face, liveness, recognition,
emotion).

Recognition runs on each frame, so a face's name is the most frequent answer since that face appeared (faces are
linked across frames by box overlap, with gaps up to 1.5 s); a spoof never gets a name. The cross-camera matcher
(one shared ID per person across cameras) is not built yet, so each camera numbers its own people.

## No "Not secure" warning (optional, recommended for the video)

With the default setup the address bar says **Not secure**: the certificate was made by the host for itself, so no
device trusts it. The connection is still encrypted and the camera works; only the label and the warning page remain.
To remove them, make a certificate with [mkcert](https://github.com/FiloSottile/mkcert) and trust its authority once
on every device. `npm run dev:lan` uses it automatically when `frontend/certs/lan.pem` and `lan-key.pem` exist
(git-ignored).

**On the host (once):**

```bash
brew install mkcert                     # Windows: choco install mkcert   (or: scoop install mkcert)
mkcert -install                         # trusts mkcert's authority on this computer; asks for your password
```

Then, from `frontend/`, with the host's current IP from step 4:

```bash
mkdir -p certs
mkcert -cert-file certs/lan.pem -key-file certs/lan-key.pem 192.168.68.118 localhost 127.0.0.1
```

Restart `npm run dev:lan`. The host's own browser now shows no warning.

**On every other device (once):** `mkcert -CAROOT` prints a folder. Send only **`rootCA.pem`** from it to the device
(AirDrop, email, USB). **Never share `rootCA-key.pem`**: anyone who has it can make certificates your devices trust.

| Device | Trust `rootCA.pem` |
| --- | --- |
| iPhone / iPad | Open the file → Settings → **Profile Downloaded** → Install. Then Settings → General → About → **Certificate Trust Settings** → turn on full trust for it |
| Android | Rename it `rootCA.crt` → Settings → Security → Encryption & credentials → **Install a certificate** → CA certificate (Chrome uses it) |
| Mac | Double-click it → Keychain Access, **System** keychain → open the certificate → Trust → **Always Trust** |
| Windows | Rename it `rootCA.crt` → double-click → Install Certificate → Local Machine → **Trusted Root Certification Authorities** |
| Firefox (any OS) | Firefox keeps its own list: Settings → Privacy & Security → Certificates → View Certificates → Authorities → **Import** |

Reopen the browser and load the Network address: no warning, padlock shown.

- **If the host's IP changes:** run the `mkcert -cert-file ...` line again with the new IP. The devices keep trusting
  the authority, so nothing to redo there.
- **After the project:** run `mkcert -uninstall` on the host, delete `frontend/certs/`, and remove the certificate or
  profile from each device.

## 6. Check before recording

- [ ] Host: backend terminal shows no errors; `https://localhost:5173/features-demo` works on the host itself
- [ ] Each device opens the Network address and shows its camera
- [ ] A registered member is named, liveness says **Live**, an emotion icon and label show
- [ ] A printed photo or a phone screen held to the camera shows **Spoof**
- [ ] Host IP has not changed since the devices opened it (it can change after reconnecting to Wi-Fi)

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| `ERR_ADDRESS_UNREACHABLE` on the other device | Its browser may not reach the local network (macOS 15+, iOS 14+ ask per app) | **Mac:** System Settings → Privacy & Security → **Local Network** → turn on Chrome (or the browser used), restart it. **iPhone/iPad:** Settings → Chrome → **Local Network** on |
| `ERR_ADDRESS_UNREACHABLE`, permission already on | The device is not on the host's network: mobile data, a guest Wi-Fi, another network name, a VPN, or iCloud Private Relay | Same Wi-Fi name as the host; turn off VPN / Private Relay; check the device's IP starts like the host's (e.g. `192.168.68.`) |
| Page does not load on the other device (timeout) | Client isolation on campus/guest Wi-Fi, or the host's firewall | Try a phone hotspot; allow `node` in the host's firewall |
| Camera blocked or no camera prompt | Opened `http://`, or permission denied earlier | Use the `https://` Network address; reset the camera permission in the browser's site settings |
| "Not secure" in the address bar | Self-signed certificate (expected) | Harmless; to remove it, set up the trusted certificate (section above) |
| "backend offline" on the page | Backend not running on the host, or it crashed | Restart step 3 and read its terminal |
| A model shows "weights not found" | Weight file missing on the host | See the table in step 1; `anti_spoofing.pt` comes with PR #6 |
| Everyone is "Unknown" | No registered faces loaded | Drive photo folders not available offline, or the Drive path in `backend/.env` is wrong |
| Results lag | One host computes for every device | Fewer devices at once; close other heavy apps on the host |
| Address stopped working | Host's IP changed | Read the new Network line from `npm run dev:lan` |
| Backend error mentioning `cv2` or `CascadeClassifier` | Two OpenCV packages, or OpenCV 5, in the backend venv | `pip uninstall opencv-python-headless`, then `pip install --force-reinstall --no-deps "opencv-python<5"` |
| A newly registered person is not recognised | Their photos are still being embedded | Wait a few seconds after Add person; the Features demo page lists them with their photo count when ready |
