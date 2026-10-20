$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$source = Join-Path $root "Code Cleanliness\datasets\processed\mlcq_29f\source_batch\mlcq_java_repo"
$analyzer = Join-Path $root "Code Cleanliness\analyzer"
$out = Join-Path $root "Code Cleanliness\evaluation\results\final_evaluation\scalability"

New-Item -ItemType Directory -Force $out | Out-Null

$cpFile = Join-Path $analyzer "target\classpath.txt"
if (!(Test-Path $cpFile)) { throw "Analyzer classpath missing. Build the analyzer first." }

$cp = (Join-Path $analyzer "target\classes") + ";" +
      (Get-Content $cpFile -Raw).Trim()

# Deterministic subset: smallest sources first, to keep the
# preliminary benchmark within available time and memory.
$files = @(
    Get-ChildItem $source -Recurse -Filter "*.java" -File |
    Sort-Object Length, FullName |
    Select-Object -First 40
)

if ($files.Count -lt 40) {
    throw "Expected at least 40 Java source files."
}

$measurements = @()

foreach ($count in @(5, 10, 20, 40)) {
    $batch = Join-Path $out "batch_$count"
    New-Item -ItemType Directory -Force $batch | Out-Null

    foreach ($file in $files | Select-Object -First $count) {
        $id = Split-Path $file.DirectoryName -Leaf
        $destination = Join-Path $batch $id
        New-Item -ItemType Directory -Force $destination | Out-Null
        Copy-Item $file.FullName $destination -Force
    }

    $evidence = Join-Path $out "evidence_$count.json"
    $stdout = Join-Path $out "stdout_$count.txt"
    $stderr = Join-Path $out "stderr_$count.txt"

    $arguments = @(
        "-Xmx2g",
        "-cp",
        ('"' + $cp + '"'),
        "lk.sliit.codecleanliness.analysis.MaintainabilityTriageCli",
        ('"' + $batch + '"'),
        ('"' + $evidence + '"')
    )

    Write-Host "`nAnalyzing $count Java files..."

    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath "java" `
        -ArgumentList $arguments `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr

    $peakWorkingSet = 0L

    while (-not $process.HasExited) {
        $p = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if ($p) {
            $peakWorkingSet = [Math]::Max(
                $peakWorkingSet,
                [long]$p.WorkingSet64
            )
        }
        Start-Sleep -Milliseconds 100
        $process.Refresh()
    }

    $process.WaitForExit()
    $timer.Stop()

    if (!(Test-Path $evidence) -or (Get-Item $evidence).Length -eq 0) {
        throw "Analyzer failed for batch $count. Inspect $stderr"
    }

    $elapsed = [Math]::Round($timer.Elapsed.TotalSeconds, 3)
    $bytes = ($files | Select-Object -First $count |
        Measure-Object Length -Sum).Sum

    $measurements += [PSCustomObject]@{
        java_files = $count
        source_bytes = $bytes
        runtime_seconds = $elapsed
        sampled_peak_working_set_mb = [Math]::Round(
            $peakWorkingSet / 1MB, 2
        )
        throughput_files_per_second = [Math]::Round(
            $count / [Math]::Max($timer.Elapsed.TotalSeconds, 0.001), 3
        )
        exit_code = $process.ExitCode
    }
}

$csv = Join-Path $out "java_analyzer_scalability.csv"
$measurements | Export-Csv $csv -NoTypeInformation

Write-Host "`nSCALABILITY RESULTS:"
$measurements | Format-Table -AutoSize
Write-Host "Saved: $csv"

