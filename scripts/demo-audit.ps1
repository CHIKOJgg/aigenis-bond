<#!
.SYNOPSIS
  Reproducible pre-demo audit chain (Windows).

  Chains the full demo audit: fixture consistency (two-copy sync) ->
  optimizer monotonicity -> backend demo tests -> ruff (demo surface) ->
  frontend lint/typecheck/unit tests -> e2e smoke + visual regression ->
  security grep for hardcoded secrets.

  Run from the repository root: `pwsh -File scripts/demo-audit.ps1`
#>
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$root = Resolve-Path (Join-Path $PSScriptRoot '..')

Write-Host '=== 1/8 Fixture consistency (audit_demo: regenerate + two-copy sync) ==='
& $python (Join-Path $root 'audit_demo.py')
if ($LASTEXITCODE -ne 0) { throw 'audit_demo.py failed' }

Write-Host '=== 2/8 Optimizer monotonicity (verify_demo_frontend) ==='
& $python (Join-Path $root 'verify_demo_frontend.py')
if ($LASTEXITCODE -ne 0) { throw 'verify_demo_frontend.py failed' }

Write-Host '=== 3/8 Backend demo tests ==='
& $python -m pytest tests/test_demo_endpoint.py tests/test_demo_components.py tests/test_analytics_http.py -q
if ($LASTEXITCODE -ne 0) { throw 'Backend demo tests failed' }

Write-Host '=== 4/8 Ruff (demo surface) ==='
& $python -m ruff check api/demo.py tests/test_demo_endpoint.py tests/test_demo_components.py tests/test_analytics_http.py audit_demo.py verify_demo_frontend.py
if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }

Write-Host '=== 5/8 Frontend lint + typecheck ==='
Push-Location (Join-Path $root 'frontend')
try {
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed' }
    npx tsc -b
    if ($LASTEXITCODE -ne 0) { throw 'Frontend typecheck failed' }

    Write-Host '=== 6/8 Frontend unit tests ==='
    npm run test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend unit tests failed' }

    Write-Host '=== 7/8 E2E smoke + visual regression + perf ==='
    npm run test:e2e
    if ($LASTEXITCODE -ne 0) { throw 'E2E smoke failed' }
    npm run test:e2e:visual
    if ($LASTEXITCODE -ne 0) { throw 'Visual regression failed' }
    npm run test:e2e:perf
    if ($LASTEXITCODE -ne 0) { throw 'Perf budgets failed' }
} finally { Pop-Location }

Write-Host '=== 8/8 Security grep (hardcoded secrets in demo surface) ==='
$pattern = '(api[_-]?key|apikey|secret|passwd|password|bearer|auth[_-]?token|access[_-]?token)\s*[:=]\s*["' + "'" + '][^"' + "'" + ']{8,}["' + "'" + ']'
$leaks = @(Get-ChildItem -Path (Join-Path $root 'frontend\src\demo'), (Join-Path $root 'api') -Recurse -Include *.ts,*.tsx,*.py |
    Select-String -Pattern $pattern -CaseSensitive:$false |
    Where-Object { $_.Line -notmatch 'do-not-use-in-production' })
if ($leaks.Count -gt 0) {
    $leaks | ForEach-Object { Write-Host "LEAK: $($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    throw 'Security grep found potential hardcoded secrets'
}
Write-Host 'Security grep clean.'

Write-Host '=== Demo audit chain passed ==='