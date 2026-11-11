# Only mounts image FILES read-only; never opens or writes an optical drive.
param([string]$Prefix = 'cd-support-20261104')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$reportPath = Join-Path $root "evidence\$Prefix\mounts.json"
if (Test-Path -LiteralPath $reportPath) { throw "Choose a fresh report path: $reportPath already exists" }
$rows = @()
foreach ($kind in @('rings', 'random', 'grid', 'tiles')) {
    $imagePath = [IO.Path]::GetFullPath((Join-Path $root "iso\$Prefix-$kind.iso"))
    $mounted = $false
    try {
        $image = Mount-DiskImage -ImagePath $imagePath -Access ReadOnly -NoDriveLetter -PassThru
        $mounted = $true
        $volumes = @($image | Get-Volume)
        if ($volumes.Count -ne 1 -or $volumes[0].FileSystem -ne 'CDFS') {
            throw "Expected one CDFS volume: $imagePath"
        }
        $rows += [ordered]@{ kind = $kind; path = $imagePath; file_system = $volumes[0].FileSystem;
                            label = $volumes[0].FileSystemLabel; access = 'ReadOnly'; passed = $true }
        Write-Output "$kind : CDFS, read-only"
    } finally {
        if ($mounted) { Dismount-DiskImage -ImagePath $imagePath | Out-Null }
    }
}
[IO.File]::WriteAllText($reportPath, (ConvertTo-Json -Depth 5 -InputObject $rows), [Text.UTF8Encoding]::new($false))
