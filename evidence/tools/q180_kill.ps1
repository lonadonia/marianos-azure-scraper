# Stage Q: the planned hard interruption of a running collector (TEST_PLAN_180 Amendment 3).
# Finds the collector's "run" process (the venv launcher and its interpreter child), records them, and kills the
# whole tree with taskkill /F /T: no signal handler, no cleanup, as a power loss or an OOM kill would leave it.
# usage: powershell -File q180_kill.ps1 <evidence file>
param([Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = 'Stop'
$all = Get-CimInstance Win32_Process -Filter "Name='python.exe'"
$hits = @($all | Where-Object { $_.CommandLine -match 'marianos_headless\.cli' -and $_.CommandLine -match ' (run|resume) ' -or ($_.CommandLine -match 'marianos_headless\.cli' -and $_.CommandLine -match ' (run|resume)$') })
if ($hits.Count -eq 0) { "no collector process found"; exit 2 }
$ids = $hits | ForEach-Object { $_.ProcessId }
# The tree's root: a hit whose parent is not itself a hit.
$roots = @($hits | Where-Object { $ids -notcontains $_.ParentProcessId })
$lines = @()
$lines += "kill requested " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
foreach ($h in $hits) { $lines += ("pid {0} parent {1} started {2:yyyy-MM-ddTHH:mm:ssZ} cmd {3}" -f $h.ProcessId, $h.ParentProcessId, $h.CreationDate.ToUniversalTime(), $h.CommandLine) }
foreach ($r in $roots) {
    $res = & taskkill.exe /F /T /PID $r.ProcessId 2>&1 | Out-String
    $lines += ("taskkill /F /T /PID {0}: exit {1}: {2}" -f $r.ProcessId, $LASTEXITCODE, $res.Trim())
}
$lines += "kill done " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
Start-Sleep -Milliseconds 500
$left = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $ids -contains $_.ProcessId })
$lines += ("processes left: {0}" -f $left.Count)
$lines | Out-File -FilePath $Out -Encoding utf8 -Append
$lines
