param(
    [string]$BuildCache = "",
    [switch]$SkipToolInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
if (-not $BuildCache) {
    $BuildCache = if (Test-Path "E:\") { "E:\Codex\installer-build-cache" } else { Join-Path $env:LOCALAPPDATA "SOCTrainingLabBuildCache" }
}
$BuildCache = [System.IO.Path]::GetFullPath($BuildCache)
$PythonUrl = "https://www.nuget.org/api/v2/package/python/3.12.10"
$PythonSha256 = "0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8"
$PythonPackage = Join-Path $BuildCache "python.3.12.10-full.nupkg"
$OutputDir = Join-Path $ProjectRoot "dist\installer"
$IssPath = Join-Path $ProjectRoot "installer\SOCTrainingLab.iss"
$ArtifactName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("U09D55S15rGg6K6t57uD5bmz5Y+w5a6J6KOF56iL5bqPLmV4ZQ=="))
$Artifact = Join-Path $OutputDir $ArtifactName

New-Item -ItemType Directory -Force -Path $BuildCache, $OutputDir | Out-Null
if (-not (Test-Path -LiteralPath $PythonPackage -PathType Leaf)) {
    Write-Host "Downloading official CPython 3.12.10 NuGet runtime..."
    & curl.exe -L --retry 5 --retry-delay 2 --fail --output $PythonPackage $PythonUrl
    if ($LASTEXITCODE -ne 0) { throw "CPython package download failed: $LASTEXITCODE" }
}
$actualPythonHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonPackage).Hash
if ($actualPythonHash -ne $PythonSha256) {
    throw "CPython SHA-256 mismatch. Expected $PythonSha256, got $actualPythonHash"
}

$builderCandidates = @(
    (Join-Path $ProjectRoot "..\..\work\soc_venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
if (-not $builderCandidates) { throw "A project build interpreter was not found." }
$BuilderPython = (Resolve-Path -LiteralPath @($builderCandidates)[0]).Path
& $BuilderPython -m pip install --disable-pip-version-check "PyInstaller==6.21.0"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed: $LASTEXITCODE" }
$GuiDist = Join-Path $BuildCache "gui-dist"
$GuiWork = Join-Path $BuildCache "gui-work"
$GuiSpec = Join-Path $BuildCache "gui-spec"
New-Item -ItemType Directory -Force -Path $GuiDist, $GuiWork, $GuiSpec | Out-Null
& $BuilderPython -m PyInstaller --noconfirm --clean --onefile --windowed --name SOCTrainingLab `
    --paths $ProjectRoot --distpath $GuiDist --workpath $GuiWork --specpath $GuiSpec `
    --exclude-module torch --exclude-module numpy --exclude-module openpyxl `
    (Join-Path $ProjectRoot "src\desktop\app.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller GUI build failed: $LASTEXITCODE" }
$GuiExecutable = Join-Path $GuiDist "SOCTrainingLab.exe"
if (-not (Test-Path -LiteralPath $GuiExecutable -PathType Leaf)) { throw "GUI executable was not created." }

$isccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
if (-not $isccCandidates -and -not $SkipToolInstall) {
    Write-Host "Installing Inno Setup with winget..."
    & winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "winget failed to install Inno Setup: $LASTEXITCODE" }
    $isccCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
}
if (-not $isccCandidates) { throw "ISCC.exe was not found. Install JRSoftware.InnoSetup." }
$Iscc = @($isccCandidates)[0]

Get-ChildItem -LiteralPath $OutputDir -Filter "*.exe" -File | Remove-Item -Force
& $Iscc "/DPythonPackage=$PythonPackage" "/DGuiExecutable=$GuiExecutable" "/O$OutputDir" $IssPath
if ($LASTEXITCODE -ne 0) { throw "ISCC.exe failed with exit code $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) { throw "Installer artifact was not created: $Artifact" }

$artifactHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Artifact).Hash
$artifactSize = (Get-Item -LiteralPath $Artifact).Length
Write-Host "Installer: $Artifact"
Write-Host "Bytes: $artifactSize"
Write-Host "SHA256: $artifactHash"
