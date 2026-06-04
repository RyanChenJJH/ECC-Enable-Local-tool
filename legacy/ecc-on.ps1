#!/usr/bin/env pwsh
<#
.SYNOPSIS
  在「当前(或指定)项目」内按项目启用 ECC —— 支持 Claude Code 与 Codex，二者互不影响。
  全局始终保持禁用：本脚本只往项目目录写文件，绝不改动 ~/.claude、~/.codex 等全局配置。

.DESCRIPTION
  Claude 端：调用 ECC 仓库的 install.ps1 --target claude-project，把 agents/skills/commands/hooks
            写进项目的 .\.claude\，再把 rules 复制到 .\.claude\rules\ecc\。
  Codex  端：
    - 档位①(默认)        ：只把 ECC 的 AGENTS.md 放到项目根（追加式指令，不改你平时的运行策略/MCP）。
    - 档位②(-CodexFull)  ：把整个 .codex\ 复制进项目（config.toml + agents + AGENTS.md），
                           并「自动裁剪」掉用不到的 MCP server，且在 Windows 下自动注释掉
                           依赖 macOS terminal-notifier 的 notify 设置。
  脚本会在项目根写一个 .ecc-local.json 清单，记录到底装了什么，供 ecc-off.ps1 精确卸载。

.PARAMETER Harness
  both(默认) | claude | codex —— 选择本次要启用哪个/哪些。

.PARAMETER Profile
  Claude 安装规模：minimal | core(默认) | full。仅对 Claude 生效，Codex 不用此项。

.PARAMETER Rules
  要复制到 .\.claude\rules\ecc\ 的规则目录，逗号分隔。默认 common。
  可选：common, zh, typescript, python, golang, java, rust, react, web ... (见 ECC 仓库 rules\)。

.PARAMETER CodexFull
  Codex 用档位②(整个 .codex\)。不加则用档位①(只 AGENTS.md)。

.PARAMETER CodexOverride
  Codex 指令用 AGENTS.override.md(优先级高于全局 ~/.codex/AGENTS.md，等于在本项目内屏蔽全局指令)。
  不加则用普通 AGENTS.md(与全局指令叠加)。

.PARAMETER Mcp
  显式指定档位②里要保留的 MCP server(逗号分隔)，给了就完全按这个来，其余全部裁掉。
  例：-Mcp memory,sequential-thinking,context7

.PARAMETER KeepMcp
  档位②保留「全部」MCP server，不做任何裁剪。

.PARAMETER KeepPlaywright
  自动裁剪模式下，额外保留 playwright(默认会被裁掉，因为它走浏览器扩展、较重)。

.PARAMETER Path
  目标项目根目录。默认 = 当前目录。

.PARAMETER EccRepo
  ECC 仓库根。默认 = 本脚本上一级里的 ECC 文件夹(即 ..\ECC)。

.PARAMETER DryRun
  只打印将要执行的计划与 MCP 裁剪决策，不实际写入任何文件。

.EXAMPLE
  # 在某项目里，Claude+Codex 一起启用(Codex 走轻量档位①)
  cd D:\my\project ;  E:\Work2\AI_Work\tool\ECC\ECC局部启用工具\ecc-on.ps1

.EXAMPLE
  # 只启用 Claude，规模用 full，并带上中文规则
  ecc-on.ps1 -Harness claude -Profile full -Rules common,zh

.EXAMPLE
  # 只启用 Codex，走完整档位②，并自动裁剪 MCP(只留有 key / 无需 key 的)
  ecc-on.ps1 -Harness codex -CodexFull

.EXAMPLE
  # 先看计划、不动文件
  ecc-on.ps1 -CodexFull -DryRun
#>
[CmdletBinding()]
param(
  [ValidateSet('both', 'claude', 'codex')]
  [string]$Harness = 'both',

  [ValidateSet('minimal', 'core', 'full')]
  [string]$Profile = 'core',

  [string[]]$Rules = @('common'),

  [switch]$CodexFull,
  [switch]$CodexOverride,

  [string[]]$Mcp,
  [switch]$KeepMcp,
  [switch]$KeepPlaywright,

  [string]$Path = (Get-Location).Path,
  [string]$EccRepo,

  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# ---------- 小工具：彩色日志 ----------
function Info($m) { Write-Host "[ECC] $m" -ForegroundColor Cyan }
function Good($m) { Write-Host "[ECC] $m" -ForegroundColor Green }
function Note($m) { Write-Host "[ECC] $m" -ForegroundColor Yellow }
function Bad($m)  { Write-Host "[ECC] $m" -ForegroundColor Red }

# ---------- 解析关键路径 ----------
if (-not $EccRepo) { $EccRepo = Join-Path (Split-Path $PSScriptRoot -Parent) 'ECC' }
$installPs1 = Join-Path $EccRepo 'install.ps1'
if (-not (Test-Path $installPs1)) {
  Bad "找不到 ECC 仓库的 install.ps1：$installPs1"
  Bad "请用 -EccRepo 指定 ECC 仓库根目录(里面应有 install.ps1 / .codex / rules)。"
  exit 1
}
if (-not (Test-Path $Path)) { Bad "目标项目目录不存在：$Path"; exit 1 }
$Path = (Resolve-Path $Path).Path

$doClaude = $Harness -in @('both', 'claude')
$doCodex  = $Harness -in @('both', 'codex')

$manifestPath = Join-Path $Path '.ecc-local.json'
$prev = $null
if (Test-Path $manifestPath) {
  try { $prev = Get-Content $manifestPath -Raw | ConvertFrom-Json } catch { $prev = $null }
}
# 判定某路径是否「由本工具创建」(供卸载时安全删除)。existsNow 在创建前采样。
function Test-Ours($existsNow, $prevFlag) { if (-not $existsNow) { return $true } ; return [bool]$prevFlag }

# ---------- MCP 裁剪决策(自动模式) ----------
function Resolve-McpKeep {
  $known = @('github', 'context7', 'exa', 'memory', 'playwright', 'sequential-thinking')
  $reason = [ordered]@{}

  if ($KeepMcp) {
    foreach ($n in $known) { $reason[$n] = '保留(-KeepMcp 全保留)' }
    return @{ Keep = $known; Reason = $reason; Known = $known }
  }
  if ($Mcp) {
    $want = $Mcp | ForEach-Object { $_.Trim() }
    $keep = @()
    foreach ($n in $known) {
      if ($want -contains $n) { $keep += $n; $reason[$n] = '保留(-Mcp 显式指定)' }
      else { $reason[$n] = '移除(不在 -Mcp 列表)' }
    }
    return @{ Keep = $keep; Reason = $reason; Known = $known }
  }

  # 自动：无需 key 的保留；需要 key 的，检测到环境变量才保留；playwright 默认裁掉。
  $keep = @()
  foreach ($n in @('sequential-thinking', 'memory', 'context7')) { $keep += $n; $reason[$n] = '保留(无需 API key)' }

  if ($env:GITHUB_PERSONAL_ACCESS_TOKEN -or $env:GITHUB_TOKEN -or $env:GH_TOKEN) {
    $keep += 'github'; $reason['github'] = '保留(检测到 GitHub token)'
  } else {
    $reason['github'] = '移除(未检测到 GITHUB_PERSONAL_ACCESS_TOKEN / GITHUB_TOKEN / GH_TOKEN)'
  }
  if ($env:EXA_API_KEY) {
    $keep += 'exa'; $reason['exa'] = '保留(检测到 EXA_API_KEY)'
  } else {
    $reason['exa'] = '移除(未检测到 EXA_API_KEY)'
  }
  if ($KeepPlaywright) { $keep += 'playwright'; $reason['playwright'] = '保留(-KeepPlaywright)' }
  else { $reason['playwright'] = '移除(默认；走浏览器扩展、较重，需要时加 -KeepPlaywright)' }

  return @{ Keep = $keep; Reason = $reason; Known = $known }
}

# ---------- 改写项目内 .codex\config.toml：裁剪 MCP + (Windows)注释 notify ----------
function Edit-CodexConfig {
  param([string]$ConfigPath, [string[]]$KeepServers)
  $lines = Get-Content -LiteralPath $ConfigPath
  $out = New-Object System.Collections.Generic.List[string]
  $removeBlock = $false      # 当前是否处在「要删除的 mcp_servers 块」中
  $inNotify = $false         # 当前是否处在 notify 多行数组中
  $winNotify = [bool]$IsWindows

  foreach ($line in $lines) {
    $t = $line.TrimStart()

    # notify 依赖 macOS 的 terminal-notifier，Windows 下整段注释掉
    if ($winNotify -and -not $inNotify -and ($t -match '^notify\s*=\s*\[')) {
      $out.Add('# [ECC-LOCAL] 以下 notify 依赖 macOS 的 terminal-notifier，Windows 下已自动注释')
      $out.Add('# ' + $line)
      if ($t -match '\]\s*$') { $inNotify = $false } else { $inNotify = $true }
      continue
    }
    if ($inNotify) {
      $out.Add('# ' + $line)
      if ($line.TrimEnd().EndsWith(']')) { $inNotify = $false }
      continue
    }

    # 段头 [mcp_servers.<name>] 或其子表 [mcp_servers.<name>.xxx]
    if ($t -match '^\[mcp_servers\.([^.\]]+)') {
      $name = $Matches[1]
      if ($KeepServers -contains $name) { $removeBlock = $false; $out.Add($line) }
      else { $removeBlock = $true }   # 跳过该段头及其内容
      continue
    }
    # 其它任何段头([features] / [profiles.x] / [agents] ...) → 结束删除状态并保留
    elseif ($t -match '^\[') {
      $removeBlock = $false
      $out.Add($line)
      continue
    }

    if (-not $removeBlock) { $out.Add($line) }
  }

  Set-Content -LiteralPath $ConfigPath -Value $out -Encoding utf8
}

# ===================== 计划摘要 =====================
Info "ECC 仓库   : $EccRepo"
Info "目标项目   : $Path"
Info "启用对象   : $Harness   (Claude=$doClaude, Codex=$doCodex)"
if ($doClaude) { Info "Claude     : profile=$Profile, rules=$($Rules -join ',')" }
if ($doCodex) {
  if ($CodexFull) {
    $codexMode = '档位②(整个 .codex\)'
    $agentsDesc = if ($CodexOverride) { '.codex\AGENTS.md + 根级 AGENTS.override.md' } else { '.codex\AGENTS.md' }
  } else {
    $codexMode = '档位①(仅指令)'
    $agentsDesc = if ($CodexOverride) { '根级 AGENTS.override.md' } else { '根级 AGENTS.md' }
  }
  Info "Codex      : $codexMode, 指令=$agentsDesc"
}

$mcpPlan = $null
if ($doCodex -and $CodexFull) {
  $mcpPlan = Resolve-McpKeep
  Info "Codex MCP 裁剪决策："
  foreach ($k in $mcpPlan.Reason.Keys) { Write-Host ("        - {0,-20} {1}" -f $k, $mcpPlan.Reason[$k]) }
  Info ("Codex MCP 最终保留：" + (($mcpPlan.Keep | Sort-Object) -join ', '))
}

if ($DryRun) { Note 'DryRun：以上为计划，未写入任何文件。'; exit 0 }

# ===================== 执行：Claude =====================
$mClaude = $null
if ($doClaude) {
  $claudeDir = Join-Path $Path '.claude'
  $claudeOurs = Test-Ours (Test-Path $claudeDir) $prev.claude.createdByUs

  Info '启用 Claude：调用 install.ps1 --target claude-project ...'
  Push-Location $Path
  try {
    # 用独立的 pwsh 进程跑 install.ps1，避免它内部的 exit 终止本脚本。cwd=项目根→写入 .\.claude
    & pwsh -NoProfile -File $installPs1 --target claude-project --profile $Profile
    $code = $LASTEXITCODE
  } finally { Pop-Location }
  if ($code -ne 0) { Bad "install.ps1 退出码 $code，Claude 安装可能未完成。" }

  # 复制 rules(插件/安装器都不会自动分发 rules)
  $rulesDest = Join-Path $Path '.claude\rules\ecc'
  New-Item -ItemType Directory -Force $rulesDest | Out-Null
  foreach ($r in $Rules) {
    $src = Join-Path $EccRepo "rules\$r"
    if (Test-Path $src) {
      $dst = Join-Path $rulesDest $r
      if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
      Copy-Item -Recurse $src $dst
      Good "  rules\$r → .claude\rules\ecc\$r"
    } else { Note "  rules\$r 不存在，已跳过" }
  }
  Good 'Claude 启用完成。'
  $mClaude = [ordered]@{ enabled = $true; profile = $Profile; rules = $Rules; createdByUs = $claudeOurs }
}

# ===================== 执行：Codex =====================
$mCodex = $null
if ($doCodex) {
  if ($CodexFull) {
    # 档位②：复制整个 .codex\ 内容(含 config.toml / agents / AGENTS.md)
    $codexDst = Join-Path $Path '.codex'
    $codexOurs = Test-Ours (Test-Path $codexDst) $prev.codex.codexCreatedByUs
    New-Item -ItemType Directory -Force $codexDst | Out-Null
    Copy-Item -Recurse -Force (Join-Path $EccRepo '.codex\*') $codexDst
    Good '  复制 .codex\ (config.toml + agents + AGENTS.md)'

    # 自动裁剪 MCP + Windows 注释 notify
    if (-not $mcpPlan) { $mcpPlan = Resolve-McpKeep }
    $cfg = Join-Path $codexDst 'config.toml'
    Edit-CodexConfig -ConfigPath $cfg -KeepServers $mcpPlan.Keep
    $removed = $mcpPlan.Known | Where-Object { $mcpPlan.Keep -notcontains $_ }
    Good ("  config.toml 裁剪完成 → 保留:[" + (($mcpPlan.Keep | Sort-Object) -join ',') + "]  移除:[" + (($removed | Sort-Object) -join ',') + "]")
    if ($IsWindows) { Good '  已在 config.toml 注释掉 macOS 专用的 notify' }

    # 档位②的指令默认来自 .codex\AGENTS.md(已随上面复制，删 .codex\ 时一并清理)。
    # 仅当 -CodexOverride 时，额外放一份根级 AGENTS.override.md 以屏蔽全局指令。
    $agFile = $null; $agOurs = $false
    if ($CodexOverride) {
      $agFile = 'AGENTS.override.md'
      $agDst = Join-Path $Path $agFile
      $agOurs = Test-Ours (Test-Path $agDst) $prev.codex.agentsCreatedByUs
      Copy-Item -Force (Join-Path $EccRepo 'AGENTS.md') $agDst
      Good "  指令(override) → $agFile"
    }

    $mCodex = [ordered]@{
      enabled = $true; mode = 'full'; override = [bool]$CodexOverride
      agentsFile = $agFile; agentsCreatedByUs = $agOurs
      codexCreatedByUs = $codexOurs
      mcpKept = @($mcpPlan.Keep); mcpRemoved = @($removed)
    }
  }
  else {
    # 档位①：只放根级指令文件
    $agFile = if ($CodexOverride) { 'AGENTS.override.md' } else { 'AGENTS.md' }
    $agDst = Join-Path $Path $agFile
    $agOurs = Test-Ours (Test-Path $agDst) $prev.codex.agentsCreatedByUs
    Copy-Item -Force (Join-Path $EccRepo 'AGENTS.md') $agDst
    Good "  指令 → $agFile"
    $mCodex = [ordered]@{
      enabled = $true; mode = 'light'; override = [bool]$CodexOverride
      agentsFile = $agFile; agentsCreatedByUs = $agOurs
      codexCreatedByUs = $false; mcpKept = @(); mcpRemoved = @()
    }
  }
  Good 'Codex 启用完成。'
}

# ===================== 写清单 =====================
$manifest = [ordered]@{
  tool      = 'ecc-local'
  version   = 1
  enabledAt = (Get-Date).ToString('s')
  eccRepo   = $EccRepo
  harness   = $Harness
}
# 合并保留另一 harness 的旧记录(本次没动它)
if ($mClaude) { $manifest.claude = $mClaude } elseif ($prev.claude) { $manifest.claude = $prev.claude }
if ($mCodex)  { $manifest.codex  = $mCodex }  elseif ($prev.codex)  { $manifest.codex  = $prev.codex }
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Good "清单已写入：.ecc-local.json"

# ===================== 收尾提示 =====================
Write-Host ''
Good '完成。后续使用：'
if ($doClaude) { Write-Host '  · Claude Code：在本项目打开，输入 / 可见 ECC 命令/技能；首次可能提示信任项目 hooks，同意即可。' }
if ($doCodex)  {
  Write-Host '  · Codex：在本项目目录运行 codex；【首次务必"信任该项目"】，否则项目级 .codex\config.toml 不生效。'
  if ($CodexFull) { Write-Host '          运行时可用 codex -p strict / codex -p yolo 切换 ECC 预设 profile。' }
}
Write-Host '  · 停用：在本项目目录运行 ecc-off.ps1 (可加 -Harness claude|codex 单独停)。'
Write-Host '  · 建议把 .ecc-local.json / .claude/ / .codex/ / AGENTS*.md 加入 .gitignore(若不想提交)。'
