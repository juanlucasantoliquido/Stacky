$ErrorActionPreference = "Stop"
$secrets = "N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\.secrets"
Get-Content "$secrets\agenda_web.env" | ForEach-Object { 
    if ($_ -match '^([^#=][^=]*)=(.+)$') { 
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process') 
    } 
}
Get-Content "$secrets\qa_db.env" | ForEach-Object { 
    if ($_ -match '^([^#=][^=]*)=(.+)$') { 
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process') 
    } 
}
[System.Environment]::SetEnvironmentVariable('AGENDA_WEB_BASE_URL', 'http://localhost:35017/AgendaWeb/', 'Process')
[System.Environment]::SetEnvironmentVariable('AGENDA_WEB_USER', 'PACIFICO', 'Process')
[System.Environment]::SetEnvironmentVariable('AGENDA_WEB_PASS', 'PACIFICO', 'Process')
[System.Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')
Write-Host "ENV LOADED: URL=$env:AGENDA_WEB_BASE_URL USER=$env:AGENDA_WEB_USER"
Set-Location "N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\QA UAT Agent"
$ADO = "N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky\Stacky tools\ADO Manager\ado.py"
Write-Host "=== RUNNING QA pipeline ADO-116 / User: PACIFICO ==="
python qa_uat_pipeline.py --ticket 116 --ado-path $ADO --mode dry-run --headed 2>&1
Write-Host "=== EXIT CODE: $LASTEXITCODE ==="
