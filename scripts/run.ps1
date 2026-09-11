# Run & Debug 入口（PowerShell 版，供无 Git Bash 环境使用）
# 用法: powershell -File scripts\run.ps1 -PoolSize 8 -Years 5
param(
    [int]$PoolSize = 8,
    [int]$Years = 5,
    [string]$Strategies = "ma_cross,momentum,bollinger",
    [string]$PoolFile = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$args = @("--pool-size", $PoolSize, "--years", $Years, "--strategies", $Strategies)
if ($PoolFile) { $args += @("--pool-file", $PoolFile) }

if (-not (Test-Path ".venv")) { uv sync }

# 修改说明：PowerShell 兼容入口与 Bash 主入口保持参数一致。
uv run ai-stock @args
