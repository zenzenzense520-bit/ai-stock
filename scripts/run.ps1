# Run & Debug 入口（PowerShell 版，供无 Git Bash 环境使用）
# 用法: powershell -File scripts\run.ps1 -PoolSize 8 -Years 5
param(
    [int]$PoolSize = 8,
    [int]$Years = 5,
    [string]$Strategies = "ma_cross,momentum,bollinger",
    [string]$PoolFile = "",
    [string]$UniverseFile = "",
    [double]$MaxPosition = 0.8,
    [double]$StopLoss = 0.08,
    [double]$TakeProfit = 0.2,
    [double]$MaxDrawdown = 0.2,
    [int]$FactorTopN = 3,
    [int]$FactorTrainDays = 252,
    [int]$FactorTestDays = 63,
    [int]$FactorRebalanceDays = 20
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# 修改说明：兼容入口同步传递四项基础风控参数。
$args = @(
    "--pool-size", $PoolSize,
    "--years", $Years,
    "--strategies", $Strategies,
    "--max-position", $MaxPosition,
    "--stop-loss", $StopLoss,
    "--take-profit", $TakeProfit,
    "--max-drawdown", $MaxDrawdown,
    "--factor-top-n", $FactorTopN,
    "--factor-train-days", $FactorTrainDays,
    "--factor-test-days", $FactorTestDays,
    "--factor-rebalance-days", $FactorRebalanceDays
)
if ($PoolFile) { $args += @("--pool-file", $PoolFile) }
if ($UniverseFile) { $args += @("--universe-file", $UniverseFile) }

if (-not (Test-Path ".venv")) { uv sync }

# 修改说明：PowerShell 兼容入口与 Bash 主入口保持参数一致。
uv run ai-stock @args
