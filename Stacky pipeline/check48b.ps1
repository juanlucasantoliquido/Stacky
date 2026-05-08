$j = Get-Content "N:\GIT\RS\RSPacifico\Tools\Stacky\auth\ado_auth.json" | ConvertFrom-Json
$pat = $j.pat
$url = "https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_apis/wit/workitems/48?api-version=7.1"
$h = @{ Authorization = "Basic $pat" }
$r = Invoke-RestMethod -Uri $url -Headers $h -Method Get
Write-Host "Titulo: $($r.fields.'System.Title')"
Write-Host "Estado: $($r.fields.'System.State')"
Write-Host "Tipo: $($r.fields.'System.WorkItemType')"
Write-Host "Asignado: $($r.fields.'System.AssignedTo')"
Write-Host "Tags: $($r.fields.'System.Tags')"
Write-Host "URL: https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/48"
