param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^https://")]
    [string]$TraderXUrl,
    [Parameter(Mandatory = $true)]
    [string]$AgentId,
    [string]$EnrollmentCode,
    [string]$TerminalPath = "C:\Program Files\MetaTrader 5\terminal64.exe",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bridgeData = Join-Path $env:APPDATA "TraderX\mt5-bridge"
$connectionState = Join-Path $bridgeData "connection.json"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "TraderX MT5 Bridge requires uv. Install it from https://docs.astral.sh/uv/ and run this script again."
}

if (-not (Test-Path -LiteralPath $TerminalPath)) {
    Write-Host "The default MT5 terminal was not found. Enter the path to your broker's terminal64.exe."
    $TerminalPath = Read-Host "MT5 terminal path"
    if (-not (Test-Path -LiteralPath $TerminalPath)) {
        throw "No MT5 terminal was found at the supplied path."
    }
}

if (-not $EnrollmentCode -and -not (Test-Path -LiteralPath $connectionState)) {
    $EnrollmentCode = Read-Host "Paste the one-time MT5 bridge code shown in TraderX"
}
if (-not $EnrollmentCode -and -not (Test-Path -LiteralPath $connectionState)) {
    throw "An enrollment code is required on the first run."
}

# The investor password is never sent to TraderX or written to disk. It only exists in the
# child bridge process for this run. The bridge refuses a terminal that reports trading enabled.
$password = Read-Host "MT5 investor password" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
try {
    $env:TRADERX_MT5_INVESTOR_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    New-Item -ItemType Directory -Force -Path $bridgeData | Out-Null
    & icacls $bridgeData /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" | Out-Null

    $arguments = @(
        "--api-url", "$($TraderXUrl.TrimEnd('/'))/api/v1",
        "--agent-id", $AgentId,
        "--terminal-path", $TerminalPath
    )
    if ($EnrollmentCode) { $arguments += @("--enrollment-code", $EnrollmentCode) }
    if ($Once) { $arguments += "--once" }

    Push-Location $repoRoot
    try {
        & uv run --project "$repoRoot\apps\mt5_bridge" --python 3.13 python -m traderx_mt5_bridge.agent @arguments
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    Remove-Item Env:TRADERX_MT5_INVESTOR_PASSWORD -ErrorAction SilentlyContinue
}
