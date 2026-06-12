param(
  [string]$SoakDir = "",
  [int]$TouchPort = 5006,
  [int]$DiagPort = 5007
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactsRoot = Join-Path $repoRoot "artifacts"
$listener = Join-Path $repoRoot "tools\fruit_diag_listener.py"

function Get-LatestTodaySoakFolder {
  if (-not (Test-Path $artifactsRoot)) {
    return $null
  }

  $todayPrefix = ("fruit_soak_{0:yyyyMMdd}_" -f (Get-Date))
  Get-ChildItem -Path $artifactsRoot -Directory -Filter "fruit_soak_*" |
    Where-Object { $_.Name -like "$todayPrefix*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

function Resolve-PythonCommand {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd) {
    return @{
      FilePath = $pythonCmd.Source
      PrefixArgs = @()
    }
  }

  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCmd) {
    return @{
      FilePath = $pyCmd.Source
      PrefixArgs = @('-3')
    }
  }

  throw "No se encontró python ni py en PATH."
}

function Quote-Args {
  param([string[]]$ArgumentList)
  $quoted = $ArgumentList | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }
  return ($quoted -join ' ')
}

if (-not (Test-Path $listener)) {
  throw "No existe el listener: $listener"
}

if ([string]::IsNullOrWhiteSpace($SoakDir)) {
  $latestToday = Get-LatestTodaySoakFolder
  if ($latestToday) {
    $SoakDir = $latestToday.FullName
  } else {
    $SoakDir = Join-Path $artifactsRoot ("fruit_soak_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
  }
}

$SoakDir = if ([IO.Path]::IsPathRooted($SoakDir)) {
  [IO.Path]::GetFullPath($SoakDir)
} else {
  [IO.Path]::GetFullPath((Join-Path $repoRoot $SoakDir))
}
New-Item -ItemType Directory -Path $SoakDir -Force | Out-Null

$touchCsv = Join-Path $SoakDir "touch_events.csv"
$diagCsv = Join-Path $SoakDir "diagnostic_values.csv"
$touchLog = Join-Path $SoakDir "touch_events.log"
$diagLog = Join-Path $SoakDir "diagnostic_values.log"
$touchErr = Join-Path $SoakDir "touch_events.err"
$diagErr = Join-Path $SoakDir "diagnostic_values.err"

$python = Resolve-PythonCommand
$pythonArgs = @()
if ($python.PrefixArgs.Count -gt 0) {
  $pythonArgs += $python.PrefixArgs
}

$touchArgs = $pythonArgs + @(
  '-u', $listener,
  '--bind', '0.0.0.0',
  '--port', $TouchPort,
  '--touch-events',
  '--csv', $touchCsv
)
$diagArgs = $pythonArgs + @(
  '-u', $listener,
  '--bind', '0.0.0.0',
  '--port', $DiagPort,
  '--csv', $diagCsv
)

$touchProc = Start-Process -FilePath $python.FilePath -ArgumentList (Quote-Args -ArgumentList $touchArgs) -RedirectStandardOutput $touchLog -RedirectStandardError $touchErr -WindowStyle Hidden -PassThru -WorkingDirectory $repoRoot
$diagProc = Start-Process -FilePath $python.FilePath -ArgumentList (Quote-Args -ArgumentList $diagArgs) -RedirectStandardOutput $diagLog -RedirectStandardError $diagErr -WindowStyle Hidden -PassThru -WorkingDirectory $repoRoot

Write-Host "[fruit-soak] capture dir: $SoakDir" -ForegroundColor Cyan
Write-Host "[fruit-soak] touch events: UDP $TouchPort (pid $($touchProc.Id))" -ForegroundColor Green
Write-Host "[fruit-soak] diagnostic values: UDP $DiagPort (pid $($diagProc.Id))" -ForegroundColor Green
Write-Host "[fruit-soak] logs:"
Write-Host "  touch: $touchLog"
Write-Host "  diag : $diagLog"
Write-Host "[fruit-soak] CSV:"
Write-Host "  touch: $touchCsv"
Write-Host "  diag : $diagCsv"
Write-Host "[fruit-soak] listeners launched in background. Keep the watcher window open until 4 pm." -ForegroundColor Yellow
