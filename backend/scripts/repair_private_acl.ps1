param(
    [string[]]$TargetPaths = @(
        'D:\PythonProject\ResearchAgemt\backend\backups',
        'D:\PythonProject\ResearchAgemt\backend\.artifacts',
        'D:\PythonProject\ResearchAgemt\backend\data\bm25',
        'D:\PythonProject\ResearchAgemt\backend\data\chroma',
        'D:\PythonProject\ResearchAgemt\backend\data\documents',
        'D:\PythonProject\ResearchAgemt\backend\data\uploads',
        'D:\PythonProject\ResearchAgemt\backend\log'
    )
)

$ErrorActionPreference = 'Stop'
$principal = (& whoami.exe).Trim()
$results = @()
$backendRoot = (Resolve-Path -LiteralPath 'D:\PythonProject\ResearchAgemt\backend').Path

foreach ($target in $TargetPaths) {
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if (-not $resolved.StartsWith($backendRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing ACL repair outside backend: $resolved"
    }

    & takeown.exe /F $resolved /R /D Y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "takeown failed: $resolved" }
    & icacls.exe $resolved /setowner $principal /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "setowner failed: $resolved" }

    # Protect only the root. Descendants then inherit these three private ACEs;
    # applying directory inheritance flags directly to files can create empty ACLs.
    & icacls.exe $resolved /inheritance:r /grant:r "${principal}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "private root ACL failed: $resolved" }
    $childrenPattern = Join-Path $resolved '*'
    & icacls.exe $childrenPattern /reset /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "descendant ACL reset failed: $resolved" }

    $items = @((Get-Item -Force -LiteralPath $resolved)) + @(Get-ChildItem -Force -LiteralPath $resolved -Recurse)
    $broadCount = 0
    $missingPrincipal = 0
    foreach ($item in $items) {
        $acl = Get-Acl -LiteralPath $item.FullName
        $broadCount += @($acl.Access | Where-Object {
            $_.IdentityReference.Value -match 'Authenticated Users|BUILTIN\\Users|S-1-5-11|S-1-5-32-545'
        }).Count
        if (@($acl.Access | Where-Object {
            $_.IdentityReference.Value -ieq $principal -and $_.AccessControlType -eq 'Allow'
        }).Count -eq 0) {
            $missingPrincipal += 1
        }
    }
    $rootAcl = Get-Acl -LiteralPath $resolved
    $results += [pscustomobject]@{
        Path = $resolved
        Items = $items.Count
        RootProtected = $rootAcl.AreAccessRulesProtected
        BroadEntries = $broadCount
        MissingCurrentUser = $missingPrincipal
    }
}

$results | ConvertTo-Json -Compress
if (@($results | Where-Object {
    -not $_.RootProtected -or $_.BroadEntries -ne 0 -or $_.MissingCurrentUser -ne 0
}).Count -ne 0) {
    exit 1
}
