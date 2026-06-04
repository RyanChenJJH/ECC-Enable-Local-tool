#!/usr/bin/env pwsh
<#
.SYNOPSIS
  在「当前(或指定)项目」内停用/卸载 ECC。只删除 ecc-on.ps1 创建的文件，绝不动全局，
  也不会误删你启用前就已存在的同名 .claude\ / .codex\ / AGENTS.md。

.DESCRIPTION
  读取项目根的 .ecc-local.json 清单，按记录精确移除：
    Claude → .\.claude\          (仅当该目录由本工具创建时)
    Codex  → .\.codex\ 和/或 .\AGENTS.md / .\AGENTS.override.md (仅当由本工具创建时)
  若清单缺失，则进入「保守模式」：仅在 -Force 时按标准路径删除，否则只提示不动手。

.PARAMETER Harness
  both(默认) | claude | codex —— 选择本次停用哪个/哪些。

.PARAMETER Path
  目标项目根目录。默认 = 当前目录。

.PARAMETER DryRun
  只打印将要删除的内容，不实际删除。

.PARAMETER Force
  无清单时也按标准路径强制删除(谨慎使用，可能删到你自己的 .claude\/.codex\)。

.EXAMPLE
  cd D:\my\project ; E:\Work2\AI_Work\tool\ECC\ECC局部启用工具\ecc-off.ps1

.EXAMPLE
  ecc-off.ps1 -Harness codex        # 只停 Codex，保留 Claude

.EXAMPLE
  ecc-off.ps1 -DryRun               # 先看会删什么
#>
[CmdletBinding()]
param(
  [ValidateSet('both', 'claude', 'codex')]
  [string]$Harness = 'both',

  [string]$Path = (Get-Location).Path,

  [switch]$DryRun,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Info($m) { Write-Host "[ECC] $m" -ForegroundColor Cyan }
function Good($m) { Write-Host "[ECC] $m" -ForegroundColor Green }
function Note($m) { Write-Host "[ECC] $m" -ForegroundColor Yellow }
function Bad($m)  { Write-Host "[ECC] $m" -ForegroundColor Red }

if (-not (Test-Path $Path)) { Bad "目标项目目录不存在：$Path"; exit 1 }
$Path = (Resolve-Path $Path).Path
$doClaude = $Harness -in @('both', 'claude')
$doCodex  = $Harness -in @('both', 'codex')

$manifestPath = Join-Path $Path '.ecc-local.json'
$man = $null
if (Test-Path $manifestPath) {
  try { $man = Get-Content $manifestPath -Raw | ConvertFrom-Json } catch { $man = $null }
}

Info "目标项目 : $Path"
Info "停用对象 : $Harness"

# 收集待删路径
$toRemove = New-Object System.Collections.Generic.List[string]
$keepClaudeRecord = $false
$keepCodexRecord = $false

if (-not $man) {
  Note '未找到 .ecc-local.json 清单。'
  if (-not $Force) {
    Note '保守模式：不确定哪些是本工具创建的，已中止。'
    Note '若确认要按标准路径删除，请加 -Force(会删 .\.claude\ 和/或 .\.codex\ \AGENTS*.md)。'
    exit 0
  }
  Note '已指定 -Force：按标准路径删除。'
  if ($doClaude) { $toRemove.Add((Join-Path $Path '.claude')) }
  if ($doCodex) {
    $toRemove.Add((Join-Path $Path '.codex'))
    $toRemove.Add((Join-Path $Path 'AGENTS.md'))
    $toRemove.Add((Join-Path $Path 'AGENTS.override.md'))
  }
}
else {
  # 依清单精确删除
  if ($doClaude) {
    if ($man.claude -and $man.claude.enabled) {
      if ($man.claude.createdByUs) { $toRemove.Add((Join-Path $Path '.claude')) }
      else { Note '.claude\ 启用前已存在(非本工具创建)，保留不动；如需清理请手动处理。' }
    }
  } else { if ($man.claude) { $keepClaudeRecord = $true } }

  if ($doCodex) {
    if ($man.codex -and $man.codex.enabled) {
      if ($man.codex.mode -eq 'full' -and $man.codex.codexCreatedByUs) { $toRemove.Add((Join-Path $Path '.codex')) }
      elseif ($man.codex.mode -eq 'full') { Note '.codex\ 启用前已存在(非本工具创建)，保留不动。' }
      if ($man.codex.agentsFile -and $man.codex.agentsCreatedByUs) { $toRemove.Add((Join-Path $Path $man.codex.agentsFile)) }
      elseif ($man.codex.agentsFile) { Note "$($man.codex.agentsFile) 启用前已存在，保留不动。" }
    }
  } else { if ($man.codex) { $keepCodexRecord = $true } }
}

# 去重 + 仅保留实际存在的
$targets = $toRemove | Sort-Object -Unique | Where-Object { Test-Path $_ }
if (-not $targets -or $targets.Count -eq 0) {
  Note '没有需要删除的内容(可能本来就没启用，或都是你自己的文件)。'
} else {
  Info '将删除：'
  foreach ($t in $targets) { Write-Host "        - $t" }
  if ($DryRun) { Note 'DryRun：未实际删除。'; exit 0 }
  foreach ($t in $targets) {
    Remove-Item -Recurse -Force $t
    Good "已删除 $t"
  }
}

if ($DryRun) { exit 0 }

# 更新/删除清单
if ($man) {
  $stillClaude = $keepClaudeRecord -and $man.claude
  $stillCodex  = $keepCodexRecord -and $man.codex
  if ($stillClaude -or $stillCodex) {
    $new = [ordered]@{ tool = 'ecc-local'; version = 1; updatedAt = (Get-Date).ToString('s'); eccRepo = $man.eccRepo }
    if ($stillClaude) { $new.claude = $man.claude; $new.harness = 'claude' }
    if ($stillCodex)  { $new.codex  = $man.codex;  $new.harness = 'codex' }
    $new | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    Good '清单已更新(保留了未停用的一侧记录)。'
  } else {
    if (Test-Path $manifestPath) { Remove-Item -Force $manifestPath; Good '清单 .ecc-local.json 已移除。' }
  }
}

Write-Host ''
Good '停用完成。全局配置(~/.claude、~/.codex)未受任何影响。'
