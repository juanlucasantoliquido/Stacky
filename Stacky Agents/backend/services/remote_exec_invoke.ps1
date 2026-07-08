# Plan 105 — invocador WinRM. Credencial SOLO por env del proceso (nunca argv/disk).
$ErrorActionPreference = 'Stop'
try {
    $sec  = ConvertTo-SecureString $env:SR_PASS -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($env:SR_USER, $sec)
    $sb   = [scriptblock]::Create($env:SR_CMD)
    $out  = Invoke-Command -ComputerName $env:SR_HOST -Credential $cred -ScriptBlock $sb |
            Out-String -Width 500
    Write-Output $out
    exit 0
} catch {
    # El mensaje puede contener host/usuario pero NUNCA el password (no se interpola).
    Write-Error ($_.Exception.Message)
    exit 1
}
