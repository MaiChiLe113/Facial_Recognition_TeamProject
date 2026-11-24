# Restart backend (:8000) and frontend (:5173): stop whatever start.ps1 launched, then run start.ps1 again.
# Use after changing data files the backend caches (e.g. data/calibration/*.json), which --reload does not watch.
param([int[]]$Ports = @(8000, 5173))
$root = $PSScriptRoot

# This shell and its ancestors must survive (restart.ps1 may itself be run from one of those windows).
$keep = @{}
$p = [int]$PID
while ($p -and -not $keep.ContainsKey($p)) {
    $keep[$p] = $true
    $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue).ParentProcessId
    $p = if ($parent) { [int]$parent } else { 0 }
}

foreach ($port in $Ports) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        # Walk up to the PowerShell window start.ps1 opened, so the window closes too (it was started with -NoExit).
        $target = $procId
        $cur = $procId
        while ($cur) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue
            if (-not $proc) { break }
            if ($proc.Name -in @('powershell.exe', 'pwsh.exe')) {
                if (-not $keep.ContainsKey([int]$cur)) { $target = $cur }
                break
            }
            $cur = $proc.ParentProcessId
        }
        Write-Host "Port ${port}: stopping process tree $target"
        taskkill /PID $target /T /F | Out-Null
    }
}

# Wait until the ports are free (uvicorn's reloader can take a moment to exit).
foreach ($port in $Ports) {
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
}

& "$root\start.ps1"
Write-Host "Restarted backend and frontend."
