param(
  [int]$RefreshMs = 1000,
  [switch]$Once,
  [int]$TailLines = 12,
  [int]$StaleWarnSec = 8,
  [int]$SummaryTailLines = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactsRoot = Join-Path $repoRoot "artifacts"

function Get-LatestSoakFolder {
  if (-not (Test-Path $artifactsRoot)) {
    return $null
  }

  Get-ChildItem -Path $artifactsRoot -Directory -Filter "fruit_soak_*" |
    Where-Object { $_.Name -notmatch '^fruit_soak_live$' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

function Get-TokenValue {
  param(
    [string]$Line,
    [string]$Key
  )

  if ([string]::IsNullOrWhiteSpace($Line)) {
    return $null
  }

  foreach ($token in $Line.Split(' ')) {
    if ($token.StartsWith("$Key=")) {
      return $token.Substring($Key.Length + 1)
    }
  }

  return $null
}

function Get-LineColor {
  param([string]$Line)

  if ($Line -match 'TOQUE INICIO') { return 'Green' }
  if ($Line -match 'TOQUE FIN') { return 'Cyan' }
  if ($Line -match 'fsm=TOUCH_ACTIVE') { return 'Green' }
  if ($Line -match 'fsm=POSSIBLE_TOUCH|fsm=POSSIBLE_RELEASE') { return 'Yellow' }
  if ($Line -match 'fsm=LOCKOUT') { return 'DarkCyan' }
  if ($Line -match 'fsm=IDLE|track/idle') { return 'DarkGray' }
  if ($Line -match 'fsm=|entry_reason=|exit_reason=') { return 'White' }
  if ($Line -match 'track/contact') { return 'Yellow' }
  if ($Line -match 'cal_fast|cal_refine') { return 'Magenta' }
  if ($Line -match 'raw=3\.3000|raw=0\.0000') { return 'Red' }
  if ($Line -match 'sigma=0\.0[0-2]') { return 'DarkGreen' }
  return 'Gray'
}

function Get-FsmColor {
  param([string]$Fsm)

  switch ($Fsm) {
    'IDLE' { 'DarkGray' }
    'POSSIBLE_TOUCH' { 'Yellow' }
    'TOUCH_ACTIVE' { 'Green' }
    'POSSIBLE_RELEASE' { 'Yellow' }
    'LOCKOUT' { 'DarkCyan' }
    default { 'Gray' }
  }
}

function Get-LogTail {
  param(
    [string]$Path,
    [int]$Lines = 12
  )

  if (-not (Test-Path $Path)) {
    return @()
  }

  $content = Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue
  if ($null -eq $content) {
    return @()
  }

  return @($content)
}

function Get-LatestLogLine {
  param([string]$Path)

  $tail = Get-LogTail -Path $Path -Lines 1
  if ($tail.Count -gt 0) {
    return $tail[0]
  }

  return $null
}

function Get-FileStatus {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return $null
  }

  $item = Get-Item -Path $Path
  $ageSec = [math]::Round((New-TimeSpan -Start $item.LastWriteTime -End (Get-Date)).TotalSeconds, 1)
  return [pscustomobject]@{
    Exists = $true
    Path = $Path
    Length = $item.Length
    LastWriteTime = $item.LastWriteTime
    AgeSec = $ageSec
    Fresh = ($ageSec -le $StaleWarnSec)
  }
}

function Count-Pattern {
  param(
    [string[]]$Lines,
    [string]$Pattern
  )

  if ($null -eq $Lines -or $Lines.Count -eq 0) {
    return 0
  }

  $count = 0
  foreach ($line in $Lines) {
    if ($line -match $Pattern) {
      $count++
    }
  }
  return $count
}

function Show-StatusLine {
  param(
    [string]$Label,
    [pscustomobject]$Status
  )

  if ($null -eq $Status) {
    Write-Host ("[{0}] missing" -f $Label) -ForegroundColor Red
    return
  }

  $color = if ($Status.Fresh) { 'Green' } else { 'Red' }
  Write-Host (
    "[{0}] {1} bytes | age {2}s | updated {3}" -f
    $Label,
    $Status.Length,
    $Status.AgeSec,
    $Status.LastWriteTime.ToString("HH:mm:ss")
  ) -ForegroundColor $color
}

function Show-KeyValueRow {
  param(
    [string]$Label,
    [string]$Value,
    [ConsoleColor]$Color = 'Gray'
  )

  Write-Host ("{0,-20} {1}" -f $Label, $Value) -ForegroundColor $Color
}

Write-Host "[fruit-live] advanced control panel active" -ForegroundColor Cyan
Write-Host "[fruit-live] Ctrl+C to exit" -ForegroundColor DarkCyan

$lastFolder = $null
$lastDiagStamp = $null
$lastTouchStamp = $null

while ($true) {
  $folder = Get-LatestSoakFolder
  Clear-Host

  if ($null -eq $folder) {
    Write-Host ("[fruit-live] no soak folder found under {0}" -f $artifactsRoot) -ForegroundColor Red
    Start-Sleep -Milliseconds $RefreshMs
    if ($Once) { break }
    continue
  }

  $folderPath = $folder.FullName
  $touchLog = Join-Path $folderPath "touch_events.log"
  $diagLog = Join-Path $folderPath "diagnostic_values.log"

  $diagStatus = Get-FileStatus -Path $diagLog
  $touchStatus = Get-FileStatus -Path $touchLog
  $diagStamp = if ($diagStatus) { "{0}:{1}" -f $diagStatus.LastWriteTime.ToFileTimeUtc(), $diagStatus.Length } else { "missing" }
  $touchStamp = if ($touchStatus) { "{0}:{1}" -f $touchStatus.LastWriteTime.ToFileTimeUtc(), $touchStatus.Length } else { "missing" }

  $folderChanged = ($folderPath -ne $lastFolder)
  $diagChanged = ($diagStamp -ne $lastDiagStamp)
  $touchChanged = ($touchStamp -ne $lastTouchStamp)

  if ($folderChanged) { $lastFolder = $folderPath }
  $lastDiagStamp = $diagStamp
  $lastTouchStamp = $touchStamp

  $diagTail = Get-LogTail -Path $diagLog -Lines $SummaryTailLines
  $touchTail = Get-LogTail -Path $touchLog -Lines $SummaryTailLines
  $latestDiag = Get-LatestLogLine -Path $diagLog
  $latestTouch = Get-LatestLogLine -Path $touchLog

  $latestFsm = Get-TokenValue -Line $latestDiag -Key 'fsm'
  $latestEntry = Get-TokenValue -Line $latestDiag -Key 'entry_reason'
  $latestExit = Get-TokenValue -Line $latestDiag -Key 'exit_reason'
  $latestRaw = Get-TokenValue -Line $latestDiag -Key 'raw'
  $latestFilt = Get-TokenValue -Line $latestDiag -Key 'filt'
  $latestBase = Get-TokenValue -Line $latestDiag -Key 'base'
  $latestDv = Get-TokenValue -Line $latestDiag -Key 'dv'
  $latestSlope = Get-TokenValue -Line $latestDiag -Key 'slope'
  $latestSigma = Get-TokenValue -Line $latestDiag -Key 'sigma'
  $latestThUp = Get-TokenValue -Line $latestDiag -Key 'th_up'
  $latestThDown = Get-TokenValue -Line $latestDiag -Key 'th_down'
  $latestFsmAge = Get-TokenValue -Line $latestDiag -Key 'fsm_age_ms'
  $latestPossTouch = Get-TokenValue -Line $latestDiag -Key 'poss_touch_ms'
  $latestPossRelease = Get-TokenValue -Line $latestDiag -Key 'poss_release_ms'
  $latestPeakDv = Get-TokenValue -Line $latestDiag -Key 'peak_dv'
  $latestPeakRaw = Get-TokenValue -Line $latestDiag -Key 'peak_raw'

  $fsmColor = if ($latestFsm) { Get-FsmColor -Fsm $latestFsm } else { 'Gray' }
  $healthColor = if ($diagStatus -and $touchStatus -and $diagStatus.Fresh -and $touchStatus.Fresh) { 'Green' } else { 'Yellow' }
  $signalColor = if ($latestRaw -match '^(3\.3000|0\.0000)$') { 'Red' } else { 'White' }
  $touchEventCount = Count-Pattern -Lines $touchTail -Pattern 'TOQUE INICIO|TOQUE FIN'
  $diagContactCount = Count-Pattern -Lines $diagTail -Pattern 'track/contact|fsm=TOUCH_ACTIVE|fsm=POSSIBLE_TOUCH|fsm=POSSIBLE_RELEASE'
  $diagIdleCount = Count-Pattern -Lines $diagTail -Pattern 'track/idle|fsm=IDLE'
  $diagCalCount = Count-Pattern -Lines $diagTail -Pattern 'cal_fast|cal_refine'
  $diagRailCount = Count-Pattern -Lines $diagTail -Pattern 'raw=3\.3000|raw=0\.0000'

  Write-Host ("[fruit-live] folder: {0}" -f $folderPath) -ForegroundColor Cyan
  Write-Host ("[fruit-live] refresh: {0} ms | now: {1}" -f $RefreshMs, (Get-Date).ToString("HH:mm:ss")) -ForegroundColor DarkCyan
  if ($folderChanged) {
    Write-Host "[fruit-live] folder changed" -ForegroundColor Magenta
  } elseif ($diagChanged -or $touchChanged) {
    Write-Host "[fruit-live] data updated" -ForegroundColor Green
  } else {
    Write-Host "[fruit-live] no file change this cycle" -ForegroundColor DarkYellow
  }

  Write-Host ""
  Write-Host "==================== CONTROL ====================" -ForegroundColor White
  Show-StatusLine -Label "DIAG" -Status $diagStatus
  Show-StatusLine -Label "TOUCH" -Status $touchStatus

  $captureHealth = if ($diagStatus -and $touchStatus -and $diagStatus.Fresh -and $touchStatus.Fresh) { "ACTIVE" } else { "STALE" }
  $captureColor = if ($captureHealth -eq "ACTIVE") { 'Green' } else { 'Red' }
  Show-KeyValueRow -Label "capture" -Value $captureHealth -Color $captureColor
  Show-KeyValueRow -Label "diag/touch" -Value ("{0}/{1} bytes" -f ($(if ($diagStatus) { $diagStatus.Length } else { 0 }), $(if ($touchStatus) { $touchStatus.Length } else { 0 }))) -Color $healthColor
  Show-KeyValueRow -Label "tail events" -Value ("touch={0} contact={1} idle={2} cal={3} rail={4}" -f $touchEventCount, $diagContactCount, $diagIdleCount, $diagCalCount, $diagRailCount) -Color $healthColor

  Write-Host ""
  Write-Host "===================== FSM =======================" -ForegroundColor White
  Show-KeyValueRow -Label "fsm" -Value ($(if ($latestFsm) { $latestFsm } else { "?" })) -Color $fsmColor
  Show-KeyValueRow -Label "entry_reason" -Value ($(if ($latestEntry) { $latestEntry } else { "?" })) -Color $fsmColor
  Show-KeyValueRow -Label "exit_reason" -Value ($(if ($latestExit) { $latestExit } else { "?" })) -Color $fsmColor
  Show-KeyValueRow -Label "fsm_age_ms" -Value ($(if ($latestFsmAge) { $latestFsmAge } else { "?" })) -Color $fsmColor
  Show-KeyValueRow -Label "poss_touch_ms" -Value ($(if ($latestPossTouch) { $latestPossTouch } else { "?" })) -Color $fsmColor
  Show-KeyValueRow -Label "poss_release_ms" -Value ($(if ($latestPossRelease) { $latestPossRelease } else { "?" })) -Color $fsmColor

  Write-Host ""
  Write-Host "==================== SIGNAL =====================" -ForegroundColor White
  Show-KeyValueRow -Label "raw" -Value ($(if ($latestRaw) { $latestRaw } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "filt" -Value ($(if ($latestFilt) { $latestFilt } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "base" -Value ($(if ($latestBase) { $latestBase } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "dv" -Value ($(if ($latestDv) { $latestDv } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "slope" -Value ($(if ($latestSlope) { $latestSlope } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "sigma" -Value ($(if ($latestSigma) { $latestSigma } else { "?" })) -Color $signalColor
  Show-KeyValueRow -Label "th_up/th_down" -Value ("{0}/{1}" -f ($(if ($latestThUp) { $latestThUp } else { "?" }), $(if ($latestThDown) { $latestThDown } else { "?" }))) -Color $signalColor
  Show-KeyValueRow -Label "peak_dv/raw" -Value ("{0}/{1}" -f ($(if ($latestPeakDv) { $latestPeakDv } else { "?" }), $(if ($latestPeakRaw) { $latestPeakRaw } else { "?" }))) -Color $signalColor

  Write-Host ""
  Write-Host "==================== EVENTS =====================" -ForegroundColor White
  $touchWindowText = "waiting for touch log"
  $touchWindowColor = if ($touchStatus -and $touchStatus.Fresh) { 'Cyan' } else { 'DarkYellow' }
  if ($latestTouch) {
    $touchEventType = if ($latestTouch -match 'TOQUE FIN') { 'TOQUE FIN' } elseif ($latestTouch -match 'TOQUE INICIO') { 'TOQUE INICIO' } else { 'TOUCH' }
    $touchStamp = if ($latestTouch -match '^\[(?<ts>[^\]]+)\]') { $Matches['ts'] } else { 'unknown' }
    $touchWindowText = "{0} @ {1}" -f $touchEventType, $touchStamp
    $touchWindowColor = if ($touchEventType -eq 'TOQUE FIN') { 'Cyan' } elseif ($touchEventType -eq 'TOQUE INICIO') { 'Green' } else { $touchWindowColor }
  }
  Show-KeyValueRow -Label "touch window" -Value $touchWindowText -Color $touchWindowColor

  Write-Host ""
  Write-Host "==================== DIAG TAIL ==================" -ForegroundColor White
  if ($diagTail.Count -eq 0) {
    Write-Host "[waiting] diagnostic_values.log" -ForegroundColor DarkYellow
  } else {
    foreach ($line in $diagTail) {
      $color = Get-LineColor -Line $line
      Write-Host $line -ForegroundColor $color
    }
  }

  Write-Host ""
  Write-Host "==================== TOUCH TAIL =================" -ForegroundColor White
  if ($touchTail.Count -eq 0) {
    Write-Host "[waiting] touch_events.log" -ForegroundColor DarkYellow
  } else {
    foreach ($line in $touchTail) {
      $color = Get-LineColor -Line $line
      Write-Host $line -ForegroundColor $color
    }
  }

  Start-Sleep -Milliseconds $RefreshMs
  if ($Once) { break }
}
