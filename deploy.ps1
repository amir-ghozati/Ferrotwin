<#
  FerroTwin — full cloud deployment (PowerShell).

  Deploys the Function App + hosts the dashboard, reusing the existing
  Azure Digital Twins instance and storage account. Event Grid stays disabled
  (the app processes telemetry/inspection directly) to keep the deploy simple.

  PREREQUISITES (install once):
    - Azure CLI            https://aka.ms/installazurecli
    - Azure Functions Core Tools v4   npm i -g azure-functions-core-tools@4
    - Python 3.11+ with this repo's requirements installed (for the twin bootstrap)
    - You are logged in:   az login    (and az account set --subscription "<name>")
    - Run from the repo root:   .\deploy.ps1

  Edit the CONFIG block below if your names differ, then run.
#>

$ErrorActionPreference = "Stop"

# ============================ CONFIG ============================
$AdtName    = "ferrotwin-adt"          # existing Azure Digital Twins instance
$Storage    = "ferrotwinst001"         # existing storage account
$FuncApp    = "ferrotwin-func-$((Get-Random -Maximum 9999))"  # must be globally unique
$PyVersion  = "3.11"
# ===============================================================

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Step "1/11  Ensure the az digital-twins (dt) extension is present"
az extension add --name azure-iot --only-show-errors 2>$null
az extension update --name azure-iot --only-show-errors 2>$null

Step "2/11  Locate the existing ADT instance ($AdtName)"
$adtJson = az dt show -n $AdtName -o json 2>$null
if (-not $adtJson) { throw "ADT instance '$AdtName' not found. Check the name / your subscription." }
$adt      = $adtJson | ConvertFrom-Json
$RG       = $adt.resourceGroup
$Location = $adt.location
$AdtHost  = "https://$($adt.hostName)"
Write-Host "  Resource group : $RG"
Write-Host "  Location       : $Location"
Write-Host "  ADT host       : $AdtHost"

Step "3/11  Upload DTDL models + create the twin graph (idempotent)"
$env:ADT_HOST = $AdtHost
python scripts/upload_models.py
python scripts/create_twins.py
Write-Host "  Twin graph ready."

Step "4/11  Create the Function App ($FuncApp) on Linux Consumption, Python $PyVersion"
az functionapp create `
  --name $FuncApp --resource-group $RG `
  --storage-account $Storage `
  --consumption-plan-location $Location `
  --runtime python --runtime-version $PyVersion `
  --functions-version 4 --os-type Linux `
  --assign-identity "[system]" `
  --only-show-errors | Out-Null
Write-Host "  Function App created."

Step "5/11  Read the Function App's managed-identity principal id"
$PrincipalId = az functionapp identity show -n $FuncApp -g $RG --query principalId -o tsv
Write-Host "  Managed identity: $PrincipalId"

Step "6/11  Grant the identity 'Azure Digital Twins Data Owner' on the ADT instance"
az dt role-assignment create --dt-name $AdtName `
  --assignee $PrincipalId `
  --role "Azure Digital Twins Data Owner" --only-show-errors | Out-Null
Write-Host "  Role assigned (propagation can take a few minutes)."

Step "7/11  Apply application settings"
az functionapp config appsettings set -n $FuncApp -g $RG --only-show-errors --settings `
  "ADT_HOST=$AdtHost" `
  "STORAGE_ACCOUNT_NAME=$Storage" `
  "INSPECTION_BLOB_CONTAINER=inspections" `
  "EVENT_GRID_ENABLED=false" `
  "TEMPERATURE_ALERT_THRESHOLD=900" `
  "REPEATED_DEFECT_COUNT=3" `
  "REPEATED_DEFECT_WINDOW_MINUTES=30" | Out-Null
Write-Host "  App settings applied."

Step "8/11  Enable the storage static website and upload the dashboard"
$Key = az storage account keys list -n $Storage -g $RG --query "[0].value" -o tsv
az storage blob service-properties update --account-name $Storage --account-key $Key `
  --static-website --index-document index.html --404-document index.html --only-show-errors | Out-Null
az storage blob upload-batch --account-name $Storage --account-key $Key `
  -s dashboard -d '$web' --overwrite --only-show-errors | Out-Null
$DashUrl = az storage account show -n $Storage -g $RG --query "primaryEndpoints.web" -o tsv
Write-Host "  Dashboard hosted at: $DashUrl"

Step "9/11  Configure CORS so the dashboard can call the API"
az functionapp cors add -n $FuncApp -g $RG --allowed-origins $DashUrl.TrimEnd('/') "http://localhost:8080" --only-show-errors | Out-Null
Write-Host "  CORS allows the static site + localhost:8080."

Step "10/11  Publish the function code (remote build installs deps on Linux)"
func azure functionapp publish $FuncApp --build remote

Step "11/11  Retrieve the Function key and print the summary"
Start-Sleep -Seconds 5
$FuncKey = az functionapp keys list -n $FuncApp -g $RG --query "functionKeys.default" -o tsv
$ApiBase = "https://$FuncApp.azurewebsites.net/api"

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Dashboard URL : $DashUrl"
Write-Host " API base URL  : $ApiBase"
Write-Host " Function key  : $FuncKey"
Write-Host ""
Write-Host " Next:"
Write-Host "  1. Open the Dashboard URL, click 'Connect API', paste the two values above."
Write-Host "  2. Generate live data from another terminal (repo root):"
Write-Host "       `$env:FERROTWIN_FUNCTION_URL='$ApiBase'"
Write-Host "       `$env:FERROTWIN_FUNCTION_KEY='$FuncKey'"
Write-Host "       python scripts/demo_stream.py"
Write-Host "  3. Quick health check:"
Write-Host "       curl $ApiBase/health"
Write-Host "============================================================" -ForegroundColor Green
