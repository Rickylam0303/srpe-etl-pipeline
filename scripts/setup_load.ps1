# Setup Load layer: create .env, database, schema, and load data
# Run from project root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_load.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$pip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

if (-not (Test-Path $python)) {
  Write-Error ".venv not found. Create the virtual environment and install requirements.txt first."
}

Write-Host "==> Installing python-dotenv..."
& $pip install python-dotenv -q

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "==> Created .env from .env.example"
  $password = Read-Host "Enter PostgreSQL password for user postgres"
  (Get-Content ".env" -Raw) -replace "your_password_here", $password | Set-Content ".env" -NoNewline
  Write-Host "==> Saved password to .env"
} else {
  Write-Host "==> Using existing .env"
  $envLines = Get-Content ".env"
  $passwordLine = $envLines | Where-Object { $_ -match '^SRPE_DB_PASSWORD=' } | Select-Object -First 1
  $currentPassword = if ($passwordLine) { ($passwordLine -split '=', 2)[1] } else { "" }
  if ([string]::IsNullOrWhiteSpace($currentPassword) -or $currentPassword -eq "your_password_here") {
    Write-Host "==> .env has no PostgreSQL password yet"
    $password = Read-Host "Enter PostgreSQL password for user postgres"
    $updated = $envLines | ForEach-Object {
      if ($_ -match '^SRPE_DB_PASSWORD=') { "SRPE_DB_PASSWORD=$password" } else { $_ }
    }
    $updated | Set-Content ".env" -Encoding utf8
    Write-Host "==> Saved password to .env"
  }
}

Write-Host "==> Creating database, initializing schema, loading data..."
& $python run_load.py --create-db --init-db

Write-Host ""
Write-Host "Done. Connect to database srpe_etl via pgAdmin or Excel Power Query."

#region agent log
$logPath = Join-Path $ProjectRoot "debug-6c9edf.log"
$logEntry = @{
  sessionId = "6c9edf"
  runId = "setup-load"
  hypothesisId = "A"
  location = "scripts/setup_load.ps1:end"
  message = "setup_load.ps1 parsed and completed"
  data = @{ projectRoot = $ProjectRoot }
  timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
} | ConvertTo-Json -Compress
Add-Content -Path $logPath -Value $logEntry -Encoding utf8
#endregion
