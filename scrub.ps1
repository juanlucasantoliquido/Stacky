param(
    [string]$Root = (Get-Location).Path,
    [switch]$InPlace
)

$ErrorActionPreference = "Stop"

function Write-Info($message) {
    Write-Host "[scrub] $message"
}

function Clear-JsonSecrets {
    param(
        [string]$Path,
        [string[]]$SecretKeys
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($key in $SecretKeys) {
        if ($null -ne $json.$key) {
            $json.$key = ""
        }
        $formatKey = "${key}_format"
        if ($null -ne $json.$formatKey) {
            $json.$formatKey = "dpapi"
        }
    }

    if ($InPlace) {
        $json | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
        Write-Info "Secretos limpiados en $Path"
    } else {
        Write-Info "Detectado archivo a limpiar: $Path"
    }
}

$backendRoot = Join-Path $Root "Stacky Agents\backend"
$envExample = Join-Path $backendRoot ".env.example"
$envPath = Join-Path $backendRoot ".env"

if (Test-Path -LiteralPath $envPath) {
    if ($InPlace) {
        if (Test-Path -LiteralPath $envExample) {
            Copy-Item -LiteralPath $envExample -Destination $envPath -Force
            Write-Info "Reemplazado backend/.env por la plantilla segura."
        } else {
            Set-Content -LiteralPath $envPath -Value "" -Encoding UTF8
            Write-Info "Vaciado backend/.env."
        }
    } else {
        Write-Info "Detectado backend/.env con posible configuración sensible."
    }
}

$authFiles = @(
    Get-ChildItem -Path (Join-Path $backendRoot "projects") -Recurse -File -Filter "ado_auth.json" -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Join-Path $backendRoot "projects") -Recurse -File -Filter "jira_auth.json" -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Join-Path $backendRoot "projects") -Recurse -File -Filter "mantis_auth.json" -ErrorAction SilentlyContinue
)

foreach ($file in $authFiles) {
    switch -Wildcard ($file.Name) {
        "ado_auth.json"    { Clear-JsonSecrets -Path $file.FullName -SecretKeys @("pat") }
        "jira_auth.json"   { Clear-JsonSecrets -Path $file.FullName -SecretKeys @("token", "password") }
        "mantis_auth.json" { Clear-JsonSecrets -Path $file.FullName -SecretKeys @("token", "password") }
    }
}

if (-not $InPlace) {
    Write-Info "Dry-run completado. Ejecutá '.\\scrub.ps1 -InPlace' sobre una copia de staging antes de empaquetar."
}
