#Requires -Version 5.1
<#
.SYNOPSIS
    Wrapper de Windows para el CLI del migrador Mantis -> GitLab (Plan 217).
.DESCRIPTION
    Resuelve el venv del backend (Stacky Agents/backend/.venv) y ejecuta
    "python -m tools.migrar_mantis_gitlab" con el cwd puesto en backend/,
    pasando todos los argumentos recibidos tal cual (subcomando + flags).
.EXAMPLE
    .\migrar_mantis_gitlab.ps1 validate --config migration_config_ripley.json
.EXAMPLE
    .\migrar_mantis_gitlab.ps1 plan --config migration_config_ripley.json
.EXAMPLE
    .\migrar_mantis_gitlab.ps1 execute --config migration_config_ripley.json --dry-run
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RestArgs
)

$ErrorActionPreference = "Stop"

$deploymentDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($deploymentDir)) {
    $deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$backendDir = Join-Path $deploymentDir "..\backend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[migrar_mantis_gitlab] ERROR: no se encontro el venv del backend en:" -ForegroundColor Red
    Write-Host "  $venvPython" -ForegroundColor Red
    Write-Host "Corre la instalacion de dependencias del backend primero (ver deployment/Install-Dependencies.ps1)." -ForegroundColor Yellow
    exit 1
}

if (-not $RestArgs -or $RestArgs.Count -eq 0) {
    Write-Host "[migrar_mantis_gitlab] Uso: migrar_mantis_gitlab.ps1 <validate|plan|execute|resume|verify|report> --config <archivo> [flags]" -ForegroundColor Yellow
    Write-Host "[migrar_mantis_gitlab] AVISO: 'execute --confirmed' escribe de verdad en GitLab. Un scheduler/cron NUNCA debe invocar 'execute --confirmed' desatendido (HITL, Plan 217 seccion 13)." -ForegroundColor Yellow
    exit 2
}

Push-Location $backendDir
try {
    & $venvPython -m tools.migrar_mantis_gitlab @RestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
