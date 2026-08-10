[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\..\battery_soc_project_macos_transfer")
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) {
    throw "Destination already exists: $Destination. Choose an empty destination to prevent overwrite."
}

$staging = Join-Path ([IO.Path]::GetTempPath()) ("battery_soc_macos_" + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $Destination, $staging | Out-Null
    $stagingProject = Join-Path $staging 'battery_soc_project'
    New-Item -ItemType Directory -Path $stagingProject | Out-Null
    foreach ($name in @('configs', 'docs', 'scripts', 'src', 'tests', 'README.md', 'requirements.txt', 'pyproject.toml')) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $name) -Destination $stagingProject -Recurse -Force
    }
    Get-ChildItem -LiteralPath $stagingProject -Recurse -Force -Directory -Filter '__pycache__' |
        Remove-Item -Recurse -Force
    $zip = Join-Path $Destination 'battery_soc_project_macos_source.zip'
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipArchive]::new(
        [System.IO.File]::Open($zip, [System.IO.FileMode]::Create),
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        Get-ChildItem -LiteralPath $staging -Recurse -Force -File | ForEach-Object {
            $entryName = $_.FullName.Substring($staging.Length).TrimStart('\').Replace('\', '/')
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $input = [System.IO.File]::OpenRead($_.FullName)
            $output = $entry.Open()
            try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
        }
    } finally {
        $archive.Dispose()
    }
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    Set-Content -LiteralPath (Join-Path $Destination 'SHA256.txt') -Value "$hash  battery_soc_project_macos_source.zip" -Encoding utf8

    # paths.json is UTF-8; specify its encoding so Windows PowerShell 5.1 does
    # not reinterpret Chinese directory names through the active code page.
    $dataRoot = (Get-Content -LiteralPath (Join-Path $ProjectRoot 'configs\paths.json') -Raw -Encoding utf8 | ConvertFrom-Json).data_center_root
    $inventory = Join-Path $Destination 'data_inventory.csv'
    if (Test-Path -LiteralPath $dataRoot -PathType Container) {
        Get-ChildItem -LiteralPath $dataRoot -Recurse -Force -File | ForEach-Object {
            [pscustomobject]@{
                relative_path = $_.FullName.Substring($dataRoot.Length).TrimStart('\')
                bytes = $_.Length
                last_write_utc = $_.LastWriteTimeUtc.ToString('o')
            }
        } | Export-Csv -LiteralPath $inventory -NoTypeInformation -Encoding utf8
    } else {
        Set-Content -LiteralPath (Join-Path $Destination 'DATA_CENTER_NOT_FOUND.txt') -Value "Configured data center was unavailable: $dataRoot" -Encoding utf8
    }
    Write-Host "Created Mac transfer bundle: $Destination"
    Write-Host "Copy the whole data-center directory separately to the Mac, then use macos_setup.sh to select its new location."
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
