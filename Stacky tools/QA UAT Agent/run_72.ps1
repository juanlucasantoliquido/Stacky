$ErrorActionPreference = "Stop"
$secrets = "N:\GIT\RS\RSPacifico\Tools\Stacky\.secrets"
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
[System.Environment]::SetEnvironmentVariable('AGENDA_WEB_BASE_URL', 'http://localhost:35019/AgendaWebRIPLEYCHI/', 'Process')
Write-Host "ENV LOADED: URL=$env:AGENDA_WEB_BASE_URL USER=$env:AGENDA_WEB_USER"
Set-Location "N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\QA UAT Agent"
$ADO = "N:\GIT\RS\RSPacifico\Tools\Stacky\Stacky tools\ADO Manager\ado.py"
Write-Host "=== RUNNING pipeline from runner stage ==="
python qa_uat_pipeline.py --ticket 72 --ado-path $ADO --skip-to runner --mode dry-run --verbose 2>&1
Write-Host "=== EXIT CODE: $LASTEXITCODE ==="
