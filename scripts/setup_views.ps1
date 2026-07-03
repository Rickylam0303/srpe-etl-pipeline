# 一鍵建立 Power Query 用嘅 SQL views
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
& ".\.venv\Scripts\python.exe" run_load.py --init-views
