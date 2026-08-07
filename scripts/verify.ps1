<#!
.SYNOPSIS
  Windows equivalent of `make verify`.

  Run from the repository root: `pwsh -File scripts/verify.ps1`.
#>
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

Write-Host '=== Ruff check ==='
& $python -m ruff check .
Write-Host '=== Ruff format check ==='
& $python -m ruff format --check .
Write-Host '=== Size budget ==='
& $python scripts/check_size_budget.py
Write-Host '=== Mypy (informational baseline) ==='
& $python -m mypy api/aigenis scraper/providers scoring portfolio
if ($LASTEXITCODE -ne 0) { Write-Warning 'Mypy has known type debt; see ArchitectureAudit.md A-06.' }
Write-Host '=== Pytest ==='
& $python -m pytest
Write-Host '=== Frontend lint ==='
Push-Location frontend
try {
  npm run lint
  Write-Host '=== Frontend tests ==='
  npm run test -- --run
  Write-Host '=== Frontend build ==='
  npm run build
} finally { Pop-Location }
Write-Host '=== All blocking checks passed ==='
