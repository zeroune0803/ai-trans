param(
    [int]$RetentionDays = 7
)

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$threshold = (Get-Date).AddDays(-1 * [math]::Abs($RetentionDays))

$targets = @(
    @{ Name = '_tmp_smoke'; Filter = '*' },
    @{ Name = '_tmp_pdf_review'; Filter = '*' },
    @{ Name = 'temp'; Filter = '*' },
    @{ Name = 'uploads'; Filter = '*' },
    @{ Name = 'logs'; Filter = '*.log' }
)

$totalDeletedFiles = 0
$totalDeletedBytes = 0

Write-Output ('[cleanup] RetentionDays=' + [math]::Abs($RetentionDays) + ', Threshold=' + $threshold.ToString('yyyy-MM-dd HH:mm:ss'))

foreach ($target in $targets) {
    $name = $target.Name
    $filter = $target.Filter
    $path = Join-Path $root $name

    if (-not (Test-Path $path)) {
        Write-Output ('[cleanup] skip missing: ' + $name)
        continue
    }

    $candidateFiles = Get-ChildItem $path -Recurse -File -Filter $filter |
        Where-Object { $_.LastWriteTime -lt $threshold }

    $fileCount = ($candidateFiles | Measure-Object).Count
    $byteCount = ($candidateFiles | Measure-Object Length -Sum).Sum
    if (-not $byteCount) { $byteCount = 0 }

    if ($fileCount -gt 0) {
        $candidateFiles | Remove-Item -Force
        $totalDeletedFiles += $fileCount
        $totalDeletedBytes += $byteCount
    }

    # Remove empty directories bottom-up.
    Get-ChildItem $path -Recurse -Directory |
        Sort-Object FullName -Descending |
        ForEach-Object {
            if (-not (Get-ChildItem $_.FullName -Force)) {
                Remove-Item $_.FullName -Force
            }
        }

    Write-Output ('[cleanup] ' + $name + ': deleted_files=' + $fileCount + ', deleted_mb=' + [math]::Round($byteCount / 1MB, 2))
}

Write-Output ('[cleanup] done: deleted_files=' + $totalDeletedFiles + ', deleted_mb=' + [math]::Round($totalDeletedBytes / 1MB, 2))
