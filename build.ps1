#!/usr/bin/env pwsh
# build.ps1 —— 一键把 GUI 打包成单文件 exe。
# 首次会自动建 venv 并装依赖；产物在 dist\ECC-Enable-Local-tool.exe
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$py = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $py)) {
  Write-Host '[build] 创建 venv...' -ForegroundColor Cyan
  py -3.12 -m venv $venv
}

Write-Host '[build] 安装依赖...' -ForegroundColor Cyan
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r (Join-Path $root 'requirements.txt') --quiet

Write-Host '[build] PyInstaller 打包...' -ForegroundColor Cyan
$icon = Join-Path $root 'assets\icon.ico'
& $py -m PyInstaller --noconfirm --onefile --windowed `
  --name ECC-Enable-Local-tool `
  --icon $icon `
  --add-data "$icon;assets" `
  --collect-submodules ecc_local `
  (Join-Path $root 'ecc_local_gui.py')

$exe = Join-Path $root 'dist\ECC-Enable-Local-tool.exe'
if (Test-Path $exe) { Write-Host "[build] 完成 → $exe" -ForegroundColor Green }
else { Write-Error '打包失败：未找到 exe' }
