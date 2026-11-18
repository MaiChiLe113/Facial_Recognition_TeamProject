# Khởi động backend (FastAPI :8000) và frontend (Vite :5173) trong 2 cửa sổ riêng
$root = $PSScriptRoot

Start-Process powershell -ArgumentList '-NoExit', '-Command', ".\.venv\Scripts\Activate.ps1; cd '$root\backend'; uvicorn app.main:app --reload --port 8000"

Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\frontend'; npm run dev"
