param([string]$Source = "vendor/rhwp")
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$commit = git -C $sourcePath rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $commit -ne '1a76570e833917d15817415a53c09ad61ab3203f') { throw 'Unexpected rhwp source commit' }
$wrapper = Join-Path $sourcePath 'scripts/wasm-pack-locked.sh'
$wrapperText = [System.IO.File]::ReadAllText($wrapper).Replace("`r`n", "`n")
[System.IO.File]::WriteAllText($wrapper, $wrapperText, [System.Text.UTF8Encoding]::new($false))
docker build -f viewer/Dockerfile.rhwp -t hwpx-rhwp-builder:1.93.1 viewer
if ($LASTEXITCODE -ne 0) { throw 'Renderer build image failed' }
docker run --rm --mount "type=bind,source=$sourcePath,target=/app" --mount type=volume,source=hwpx-rhwp-target,target=/build-target --mount type=volume,source=hwpx-rhwp-cargo,target=/usr/local/cargo/registry hwpx-rhwp-builder:1.93.1
if ($LASTEXITCODE -ne 0) { throw 'Optimized renderer build failed' }
python viewer/package_renderer.py --source $sourcePath --optimized
if ($LASTEXITCODE -ne 0) { throw 'Renderer packaging failed' }
