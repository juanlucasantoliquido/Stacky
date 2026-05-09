Set-Location 'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent'
Get-Content 'N:\GIT\RS\RSPACIFICO\Tools\Stacky\.secrets\agenda_web.env' | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}
$env:AGENDA_WEB_USER     = 'PACIFICO'
$env:AGENDA_WEB_PASS     = 'PACIFICO'
$env:AGENDA_WEB_BASE_URL = 'http://localhost:35017/AgendaWeb/'
Write-Host "ENV OK — USER=$env:AGENDA_WEB_USER  URL=$env:AGENDA_WEB_BASE_URL"
& 'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent\node_modules\.bin\playwright' test 116/tests/p01 116/tests/p02 116/tests/p10 --reporter=list