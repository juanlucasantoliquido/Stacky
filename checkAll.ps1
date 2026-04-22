$j = Get-Content "N:\GIT\RS\RSPacifico\Tools\Stacky\auth\ado_auth.json" | ConvertFrom-Json
$pat = $j.pat
$ids = @(25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55)

foreach ($id in $ids) {
    $url = "https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_apis/wit/workitems/$($id)?api-version=7.1"
    try {
        $r = Invoke-RestMethod -Uri $url -Headers @{ Authorization = "Basic $pat" } -Method Get -ErrorAction Stop
        Write-Host "OK  $id | $($r.fields.'System.State') | $($r.fields.'System.Title')"
    } catch {
        $code = $_.Exception.Response.StatusCode
        Write-Host "MISS $id | $code"
    }
}
