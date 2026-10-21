param(
 [string]$SourceRepository = '',
 [int[]]$Sizes = @(100,250,500,1000)
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$analyzer=Join-Path $repo 'Code Cleanliness\analyzer'
$out=Join-Path $PSScriptRoot 'benchmark_results'
New-Item -ItemType Directory -Force -Path $out | Out-Null
if (-not (Test-Path (Join-Path $analyzer 'pom.xml'))) { throw 'Analyzer pom.xml not found; extract ZIP into repository ROOT, keeping folder hierarchy.' }
if ([string]::IsNullOrWhiteSpace($SourceRepository)) {
 Write-Host 'No large real Java source repository specified. Skipping 100–1000-file benchmark; no result is invented.'
} else {
 $source=(Resolve-Path $SourceRepository).Path
 $all=@(Get-ChildItem $source -Recurse -File -Filter '*.java' | Where-Object { $_.FullName -notmatch '[\\/](target|build|generated|gen-src)[\\/]' } | Sort-Object FullName)
 Write-Host "Found $($all.Count) Java source files (excluding common generated/build paths)."
 if ($all.Count -lt 100) { Write-Warning 'Under 100 files: 100–1000-file benchmark unavailable; use a real bigger repository.' }
 $jar=@(Get-ChildItem (Join-Path $analyzer 'target') -Filter '*.jar' -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '(sources|javadoc|original)' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
 if (-not $jar) { throw 'Analyzer jar absent. Run `mvn -B -f "Code Cleanliness\analyzer\pom.xml" package` first.' }
 # The plain jar may lack dependency jars. Build full runtime classpath with Maven.
 $cpfile=Join-Path $out 'runtime-classpath.txt'
 & mvn -q -f (Join-Path $analyzer 'pom.xml') dependency:build-classpath "-Dmdep.outputFile=$cpfile"
 if ($LASTEXITCODE -ne 0 -or -not (Test-Path $cpfile)) { throw 'Maven classpath resolution failed.' }
 $cp=($jar[0].FullName + [IO.Path]::PathSeparator + (Get-Content $cpfile -Raw).Trim())
 $rows=@()
 foreach($size in $Sizes) {
  if($all.Count -lt $size) { Write-Host "Skipping ${size}: only $($all.Count) available.";continue }
  $tmp=Join-Path $env:TEMP "codecleanliness_bench_$size"
  if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force};New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
   $subset=$all | Select-Object -First $size
   # Flatten into unique numbered paths; this tests parsing and throughput, not intact dependency structures.
   $i=0;foreach($f in $subset){ $i++; $dir=Join-Path $tmp ('sample'+$i);New-Item -ItemType Directory -Path $dir | Out-Null;Copy-Item $f.FullName (Join-Path $dir $f.Name) }
   $json=Join-Path $out "analysis_$size.json"
   $watch=[Diagnostics.Stopwatch]::StartNew()
   & java -cp $cp lk.sliit.codecleanliness.analysis.MaintainabilityTriageCli $tmp $json 2>&1 | Out-File (Join-Path $out "console_$size.txt")
   $code=$LASTEXITCODE;$watch.Stop()
   $rows += [pscustomobject]@{source_repository=$source;selected_files=$size;elapsed_seconds=[math]::Round($watch.Elapsed.TotalSeconds,3);exit_code=$code;json_exists=(Test-Path $json);method='single_run_copied_java_sources_flattened_dependency_structure'}
  } finally {if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force}}
 }
 $rows | Export-Csv (Join-Path $out 'benchmark_measurements.csv') -NoTypeInformation -Encoding UTF8
 $rows | Format-Table -AutoSize
 Write-Host 'Benchmark is preliminary: copied sources, one run per size, not full intact repositories, no peak RSS claim.'
}
Write-Host 'Evidence report at:' (Join-Path $PSScriptRoot 'FINAL_COMPLETION_STATUS.md')
Write-Host 'Current git state (nothing committed automatically):'
& git -C $repo status --short
