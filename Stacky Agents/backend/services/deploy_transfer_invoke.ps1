# Plan 120 — invocador de transferencia WinRM. Copia un archivo al servidor
# por PSSession (WinRM 5985). Credencial SOLO por env del proceso (nunca argv/disk),
# mismo riel que remote_exec_invoke.ps1 (Plan 105, §3.1).
$ErrorActionPreference = 'Stop'
try {
    $sec  = ConvertTo-SecureString $env:SR_PASS -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($env:SR_USER, $sec)
    $s = New-PSSession -ComputerName $env:SR_HOST -Credential $cred -ErrorAction Stop
    try {
        Copy-Item -LiteralPath $env:SR_LOCAL_ZIP -Destination $env:SR_REMOTE_ZIP -ToSession $s -Force -ErrorAction Stop
    } finally {
        Remove-PSSession $s
    }
    exit 0
} catch {
    # El mensaje puede contener host/usuario pero NUNCA el password (no se interpola).
    Write-Error ($_.Exception.Message)
    exit 1
}
