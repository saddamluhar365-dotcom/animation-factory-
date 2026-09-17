$ErrorActionPreference = 'Stop'
$installerDir = Join-Path $PSScriptRoot '..\data\installers'
New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
$installer = Join-Path $installerDir 'postgresql-installer.exe'
# PostgreSQL is intentionally not downloaded from an unverified mirror.
# Set POSTGRES_INSTALLER_URL to an official PostgreSQL/EDB distribution URL chosen by the maintainer.
$url = $env:POSTGRES_INSTALLER_URL
if (-not $url) { throw 'POSTGRES_INSTALLER_URL is not set. Configure an official PostgreSQL distribution URL before installation.' }
Invoke-WebRequest -Uri $url -OutFile $installer
if (-not (Test-Path $installer)) { throw 'PostgreSQL installer download failed.' }
Write-Host "Downloaded PostgreSQL installer to $installer"
Write-Host 'Installer execution is intentionally explicit; review the official installer options before running it.'
