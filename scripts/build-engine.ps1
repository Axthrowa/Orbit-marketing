# Python motorunu tek dosyalık exe olarak paketler ve Tauri yan süreç (sidecar) klasörüne koyar.
# Kullanım (depo kökünden):  powershell -ExecutionPolicy Bypass -File scripts\build-engine.ps1
# Not: PyInstaller'ı ve Playwright sürücüsünü pakete ekler; ilk çalıştırmada indirme yapar.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "engine\.venv\Scripts\python.exe"
$binaries = Join-Path $root "src-tauri\binaries"
$triple = "x86_64-pc-windows-msvc"

if (-not (Test-Path $python)) { throw "engine\.venv bulunamadı. README > Geliştirme kurulumu adımlarını izleyin." }

& $python -m pip install --quiet "pyinstaller>=6"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller kurulamadı" }

& $python -m PyInstaller --noconfirm --clean --onefile --console `
    --name "etkilesim-engine" `
    --distpath $binaries `
    --workpath (Join-Path $root "engine\build") `
    --specpath (Join-Path $root "engine\build") `
    --paths (Join-Path $root "engine") `
    --collect-data etkilesim `
    --collect-all playwright `
    --collect-submodules keyring `
    --copy-metadata keyring `
    --copy-metadata apscheduler `
    --hidden-import openpyxl `
    (Join-Path $root "engine\run_engine.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız" }

# Tauri externalBin, hedef üçlüsü ekli dosya adı bekler.
$plain = Join-Path $binaries "etkilesim-engine.exe"
$target = Join-Path $binaries "etkilesim-engine-$triple.exe"
Move-Item -Force $plain $target
Write-Host "Motor hazır: $target"
