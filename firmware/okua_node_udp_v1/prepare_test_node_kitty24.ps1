param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("EB2", "EC2", "ED2")]
    [string]$NodeLabel,

    [Parameter(Mandatory = $false)]
    [string]$WifiSsid = "Kitty_2.4",

    [Parameter(Mandatory = $true)]
    [string]$WifiPass,

    [Parameter(Mandatory = $false)]
    [string]$ControlSecret,

    [Parameter(Mandatory = $false)]
    [string]$PcIp,

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, 13)]
    [int]$WifiChannel = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$nodeMap = @{
    "EB2" = 6
    "EC2" = 7
    "ED2" = 8
}

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Resolve-SecretFromFile([string]$pathValue) {
    if (-not (Test-Path $pathValue)) {
        return $null
    }
    $raw = (Get-Content -Path $pathValue -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw
}

function Resolve-ControlSecret {
    if (-not [string]::IsNullOrWhiteSpace($ControlSecret)) {
        return $ControlSecret.Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($env:CKV2_CONTROL_SECRET)) {
        return $env:CKV2_CONTROL_SECRET.Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($env:CKV2_CONTROL_SECRET_FILE)) {
        $candidate = Resolve-SecretFromFile $env:CKV2_CONTROL_SECRET_FILE
        if ($null -ne $candidate) {
            return $candidate
        }
    }

    $repoRoot = Resolve-RepoRoot
    $localCandidates = @(
        (Join-Path $repoRoot ".control_plane_secret"),
        (Join-Path $repoRoot "control_plane_secret.txt")
    )
    foreach ($candidatePath in $localCandidates) {
        $candidate = Resolve-SecretFromFile $candidatePath
        if ($null -ne $candidate) {
            return $candidate
        }
    }

    $artifactSecret = Get-ChildItem -Path (Join-Path $repoRoot "artifacts") -Filter "control_plane_secret.txt" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -ne $artifactSecret) {
        $candidate = Resolve-SecretFromFile $artifactSecret.FullName
        if ($null -ne $candidate) {
            return $candidate
        }
    }

    throw "No se pudo resolver OKUA control secret. Usa -ControlSecret o define CKV2_CONTROL_SECRET/CKV2_CONTROL_SECRET_FILE."
}

function Resolve-PreferredPcIp {
    if (-not [string]::IsNullOrWhiteSpace($PcIp)) {
        return $PcIp.Trim()
    }

    $preferred = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "169.254.*" -and
            $_.IPAddress -notlike "127.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object InterfaceMetric, SkipAsSource |
        Select-Object -First 1

    if ($null -eq $preferred -or [string]::IsNullOrWhiteSpace($preferred.IPAddress)) {
        throw "No se pudo detectar IP local para PC destino. Usa -PcIp."
    }

    return $preferred.IPAddress.Trim()
}

function Parse-IPv4Octets([string]$ipText) {
    $ip = [System.Net.IPAddress]::Parse($ipText)
    if ($ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw "PcIp debe ser IPv4: $ipText"
    }
    return $ip.ToString().Split(".")
}

$nodeId = $nodeMap[$NodeLabel]
$resolvedSecret = Resolve-ControlSecret
$resolvedPcIp = Resolve-PreferredPcIp
$octets = Parse-IPv4Octets $resolvedPcIp

$targetPath = Join-Path $PSScriptRoot "okua_node_secrets.h"
$timestampUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$content = @"
#pragma once
// AUTO-GENERATED local override (not tracked by git).
// Generated at: $timestampUtc
// Intended test node: $NodeLabel ($nodeId)

#define WIFI_SSID "$WifiSsid"
#define WIFI_PASS "$WifiPass"
#define OKUA_CONTROL_SECRET "$resolvedSecret"

#define NODE_LABEL "$NodeLabel"
#define NODE_ID $nodeId

// Use 0 to allow station scan/connect without forcing fixed channel.
#define WIFI_CHANNEL $WifiChannel

// CKv2 host IP (EVT/STAT destination)
#define PC_IP_A $($octets[0])
#define PC_IP_B $($octets[1])
#define PC_IP_C $($octets[2])
#define PC_IP_D $($octets[3])
"@

Set-Content -Path $targetPath -Value $content -Encoding UTF8

Write-Host "okua_node_secrets.h generado:" -ForegroundColor Green
Write-Host "  Path      : $targetPath"
Write-Host "  Node      : $NodeLabel ($nodeId)"
Write-Host "  Wi-Fi     : $WifiSsid"
Write-Host "  PC_IP     : $resolvedPcIp"
Write-Host "  Wi-Fi ch  : $WifiChannel"
