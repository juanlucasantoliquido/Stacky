$j = Get-Content "N:\GIT\RS\RSPacifico\Tools\Stacky\auth\ado_auth.json" | ConvertFrom-Json
$pat = $j.pat
$url = "https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_apis/wit/workitems/48?api-version=7.1"
$h = @{ Authorization = "Basic $pat" }
try {
    $r = Invoke-RestMethod -Uri $url -Headers $h -Method Get
    Write-Host "EXISTE: $($r.fields.'System.Title')"
} catch {
    Write-Host "NO EXISTE status: $($_.Exception.Response.StatusCode)"
}
