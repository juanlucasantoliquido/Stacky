
<#
.SYNOPSIS
Configura WinRM en el servidor para acepar conexiones remotas Invoke-Command.

.DESCRIPTION
Idempotente. Habilita PSRemoting, amplía la regla de firewall para aceptar
cualquier RemoteAddress (no solo subred local), y verifica el listener.
Pensado para ejecución desde Enable-WinRM.bat (sin interactividad).

NOTA: si la red es de dominio, después del Enable-PSRemoting quizás pida
TrustedHosts en el CLIENTE que entra. Ese es un paso del cliente, no del servidor.
#>

param(
    [switch]$NoExitOnSuccess
)

$ErrorActionPreference = 'Stop'

function Write-Info { Write-Host "[INFO] $_" -ForegroundColor Cyan }
function Write-OK { Write-Host "[OK]  $_" -ForegroundColor Green }
function Write-Warn { Write-Host "[WARN] $_" -ForegroundColor Yellow }
function Write-Fail { Write-Host "[FAIL] $_" -ForegroundColor Red }

Write-Info "Iniciando configuracion de WinRM..."

# 1. Verificar que somos admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')
if (-not $isAdmin) {
    Write-Fail "Este script debe ejecutarse como Administrador"
    exit 1
}

# 2. Habilitar PSRemoting (idempotente)
try {
    Write-Info "Habilitando PSRemoting (servicio WinRM + listener HTTP 5985)..."
    Enable-PSRemoting -Force -SkipNetworkProfileCheck -ErrorAction Stop
    Write-OK "PSRemoting habilitado"
} catch {
    Write-Fail "No se pudo habilitar PSRemoting: $_"
    exit 1
}

# 3. Ampliar firewall: la regla WINRM-HTTP-In-TCP que crea Enable-PSRemoting
#    en perfil Público limita el acceso a la subred local. Como quizás entres
#    desde otra subred (VPN), permitís Any.
try {
    Write-Info "Ampliando regla de firewall WINRM-HTTP-In-TCP a RemoteAddress Any..."
    $fwRule = Get-NetFirewallRule -Name "WINRM-HTTP-In-TCP" -ErrorAction SilentlyContinue
    if ($fwRule) {
        Set-NetFirewallRule -Name "WINRM-HTTP-In-TCP" -RemoteAddress Any -ErrorAction Stop
        Write-OK "Regla ampliada"
    } else {
        Write-Warn "Regla WINRM-HTTP-In-TCP no encontrada; quizás ya está abierta por otra regla."
    }
} catch {
    Write-Warn "No se pudo ampliar firewall: $_ (puede que ya esté abierta)"
}

# 4. Verificar que el listener HTTP está en puerto 5985
try {
    Write-Info "Verificando listener WinRM..."
    $listener = winrm enumerate winrm/config/listener 2>&1
    if ($listener -match "5985" -or $listener -match "Port.*5985") {
        Write-OK "Listener HTTP en puerto 5985 activo"
    } else {
        Write-Warn "Listener WinRM detectado; verifica con 'winrm enumerate winrm/config/listener' si el puerto es 5985"
    }
} catch {
    Write-Warn "No se pudo verificar listener: $_"
}

# 5. Verificar connectividad local rápida
try {
    Write-Info "Probando conexion local..."
    $localTest = Test-WSMan -ComputerName localhost -ErrorAction Stop
    Write-OK "Conexion local OK"
} catch {
    Write-Warn "Test-WSMan local falló; WinRM puede estar aún iniciando"
}

Write-OK "======================================"
Write-OK "Configuracion de WinRM completada"
Write-OK "======================================"
Write-Info "El servidor ahora acepta Invoke-Command remoto en el puerto 5985 (HTTP)."
Write-Info "Si entras desde otra red (VPN), tal vez pida TrustedHosts en el CLIENTE."
Write-Info "Pasos finales (desde el cliente, si necesario):"
Write-Info "  Set-Item WSMan:\localhost\Client\TrustedHosts -Value '<host-or-ip>' -Concatenate -Force"
Write-Info "  Test-WSMan -ComputerName <host-or-ip>"

if (-not $NoExitOnSuccess) {
    Write-Info ""
    Write-Info "Presiona una tecla para cerrar..."
    [void][System.Console]::ReadKey($true)
}

exit 0
