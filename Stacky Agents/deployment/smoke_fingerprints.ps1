#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke NEGATIVO de huellas de regresion (Plan 163 F5).
.DESCRIPTION
    Lee docs/sistema/error_fingerprints.json y, por cada huella resolved+log_guarded,
    grepea el log objetivo. Si ENCUENTRA alguna, FALLA (exit 1): una clase de error
    ya resuelta reaparecio. Corre desde el repo; -LogPath apunta al log fresco del deploy.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$CatalogPath = ""
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot es fiable en el CUERPO (no siempre en el default del param bajo
# PS 5.1 con [CmdletBinding()]+comment-help): resolver el catalogo aca.
if ([string]::IsNullOrEmpty($CatalogPath)) {
    $CatalogPath = Join-Path $PSScriptRoot "..\docs\sistema\error_fingerprints.json"
}

if (-not (Test-Path $LogPath)) { throw "No existe el log objetivo: $LogPath" }
if (-not (Test-Path $CatalogPath)) { throw "No existe el catalogo: $CatalogPath" }

$catalog = Get-Content -Raw -Path $CatalogPath | ConvertFrom-Json
$guarded = $catalog.fingerprints | Where-Object { $_.status -eq "resolved" -and $_.log_guarded -eq $true }

$found = @()
foreach ($fp in $guarded) {
    # C8: SIN -ErrorAction SilentlyContinue - un regex invalido para .NET debe
    # REVENTAR con el id del patron ofensor, jamas degradar a falso verde.
    try {
        $hit = Select-String -Path $LogPath -Pattern $fp.log_pattern -List
    } catch {
        throw ("Patron invalido para .NET en la huella '{0}': {1}" -f $fp.id, $_.Exception.Message)
    }
    if ($null -ne $hit) {
        $found += $fp
        Write-Host ("[REGRESION] {0} ({1}) - matada por {2}" -f $fp.id, $fp.title, $fp.killed_by) -ForegroundColor Red
    }
}

if ($found.Count -gt 0) {
    Write-Host ("Smoke de huellas FALLO: {0} clase(s) de error resuelta(s) reaparecieron en {1}" -f $found.Count, $LogPath) -ForegroundColor Red
    exit 1
}

Write-Host ("Smoke de huellas OK: ninguna clase resuelta reaparecio en {0}" -f $LogPath) -ForegroundColor Green
exit 0
