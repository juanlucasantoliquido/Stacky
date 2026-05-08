$j = Get-Content "N:\GIT\RS\RSPacifico\Tools\Stacky\auth\ado_auth.json" | ConvertFrom-Json
$pat = $j.pat
$headers = @{
    Authorization = "Basic $pat"
    "Content-Type" = "application/json-patch+json"
}

foreach ($id in @(46, 48)) {
    $url = "https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_apis/wit/workitems/$($id)?api-version=7.1"
    $body = '[{"op":"add","path":"/fields/System.State","value":"Doing"}]'
    try {
        $r = Invoke-RestMethod -Uri $url -Headers $headers -Method Patch -Body $body -ErrorAction Stop
        Write-Host "OK  $id -> $($r.fields.'System.State') | $($r.fields.'System.Title')"
    } catch {
        Write-Host "ERR $id | $($_.Exception.Message)"
    }
}
