param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $ReleaseDir).Path
$sumFile = Join-Path $resolved 'SHA256SUMS.txt'
$files = Get-ChildItem -LiteralPath $resolved -File |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
    Sort-Object Name

if ($files.Count -eq 0) {
    throw "No release assets found in $resolved"
}

$lines = foreach ($file in $files) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($file.Name)"
}
$lines | Set-Content -LiteralPath $sumFile -Encoding ascii
Write-Output "Wrote $sumFile"
