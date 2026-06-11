param(
  [int]$RefreshMs = 1000
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

function Show-Tail {
  param(
    [string]$Path,
    [int]$Lines = 12
  )

  if (-not (Test-Path $Path)) {
    Write-Host "[waiting] $([IO.Path]::GetFileName($Path))"
    return
  }

  $content = Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue
  if (-not $content) {
    Write-Host "[waiting] $([IO.Path]::GetFileName($Path))"
    return
  }

  $content | ForEach-Object { Write-Host $_ }
}

Write-Host "[fruit-live] waiting for latest soak folder..."
Write-Host "[fruit-live] Ctrl+C to exit"

$lastFolder = $null
while ($true) {
  $folder = Get-LatestSoakFolder
  Clear-Host

  if ($null -eq $folder) {
    Write-Host "[fruit-live] no soak folder found under $artifactsRoot"
    Start-Sleep -Milliseconds $RefreshMs
    continue
  }

  $folderPath = $folder.FullName
  if ($folderPath -ne $lastFolder) {
    $lastFolder = $folderPath
  }

  $touchLog = Join-Path $folderPath "touch_events.log"
  $diagLog = Join-Path $folderPath "diagnostic_values.log"

  Write-Host "[fruit-live] folder: $folderPath"
  Write-Host "[fruit-live] refreshing every $([Math]::Round($RefreshMs / 1000, 1))s; Ctrl+C to exit"
  Write-Host ""
  Write-Host "=== DIAGNOSTIC ==="
  Show-Tail -Path $diagLog -Lines 12
  Write-Host ""
  Write-Host "=== TOUCH ==="
  Show-Tail -Path $touchLog -Lines 12

  Start-Sleep -Milliseconds $RefreshMs
}
