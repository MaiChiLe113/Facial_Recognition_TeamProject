# Start the backend (FastAPI :8000) and the frontend (Vite, Wi-Fi mode: https://<IP>:5173) in two windows.
# The frontend starts only once the backend answers HTTP; otherwise Vite logs proxy errors (ECONNREFUSED) for the
# first seconds while the backend loads its models.
param([int]$TimeoutS = 90)
$root = $PSScriptRoot

Start-Process powershell -ArgumentList '-NoExit', '-Command', "& '$root\.venv\Scripts\Activate.ps1'; cd '$root\backend'; uvicorn app.main:app --reload --port 8000"

# With --reload the port is bound before the app has started, so wait for a real HTTP answer, not an open port.
Write-Host -NoNewline "Waiting for the backend on :8000 "
$ready = $false
$deadline = (Get-Date).AddSeconds($TimeoutS)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/live' -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true; break
    } catch {
        if ($_.Exception.Response) { $ready = $true; break }   # any HTTP status means the app is up
    }
    Write-Host -NoNewline "."
    Start-Sleep -Milliseconds 500
}
Write-Host ""
if ($ready) { Write-Host "Backend ready." } else { Write-Host "Backend did not answer within $TimeoutS s; starting the frontend anyway (check the backend window)." }

Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\frontend'; npm run dev:lan"
