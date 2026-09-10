param(
    [string]$ConfigPath = 'C:\ProgramData\MySQL\MySQL Server 9.0\my.ini',
    [string]$ServiceName = 'MySQL90',
    [string]$CaSource = 'C:\ProgramData\MySQL\MySQL Server 9.0\Data\ca.pem',
    [string]$CaDestination = ''
)

$ErrorActionPreference = 'Stop'
$backendDir = Split-Path -Parent $PSScriptRoot
if (-not $CaDestination) {
    $CaDestination = Join-Path $backendDir '.secrets\mysql-ca.pem'
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "MySQL configuration not found: $ConfigPath"
}
if (-not (Test-Path -LiteralPath $CaSource -PathType Leaf)) {
    throw "MySQL CA certificate not found: $CaSource"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$ConfigPath.codex-backup-$timestamp"
Copy-Item -LiteralPath $ConfigPath -Destination $backupPath -ErrorAction Stop

$content = Get-Content -LiteralPath $ConfigPath -Raw
function Set-MysqldOption([string]$Text, [string]$Name, [string]$Value) {
    $optionPattern = "(?im)^\s*$([regex]::Escape($Name))\s*=.*$"
    if ([regex]::IsMatch($Text, $optionPattern)) {
        return [regex]::Replace($Text, $optionPattern, "$Name=$Value")
    }
    $sectionPattern = '(?im)^\s*\[mysqld\]\s*$'
    if (-not [regex]::IsMatch($Text, $sectionPattern)) {
        throw '[mysqld] section not found'
    }
    return [regex]::Replace($Text, $sectionPattern, "[mysqld]`r`n$Name=$Value", 1)
}

$content = Set-MysqldOption $content 'bind-address' '127.0.0.1'
$content = Set-MysqldOption $content 'require_secure_transport' 'ON'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, $content, $utf8NoBom)

$secretDir = Split-Path -Parent $CaDestination
New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
Copy-Item -LiteralPath $CaSource -Destination $CaDestination -Force
$principal = (& whoami.exe).Trim()
& icacls.exe $secretDir /inheritance:r /grant:r "${principal}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict MySQL secret directory ACL' }

Restart-Service -Name $ServiceName -Force
$service = Get-Service -Name $ServiceName
if ($service.Status -ne 'Running') {
    throw "MySQL service did not restart successfully; restore $backupPath"
}

Write-Output "MySQL bind/TLS hardening applied. Backup: $backupPath"
Write-Output "CA copy: $CaDestination"
