<#
  FerroTwin — OPTIONAL: switch to the event-driven (Event Grid) architecture.

  Run this AFTER deploy.ps1 has succeeded and the direct path is working.
  It creates a custom Event Grid topic, subscribes the Function's
  `process_event` trigger to it, and flips the app into event-driven mode.

  What changes at runtime:
    - POST /telemetry and POST /inspection publish an event and return 202
      (Accepted) instead of processing inline.
    - The `process_event` Event Grid trigger consumes the event and performs the
      twin update, history write, and alarm evaluation asynchronously.
    - There is NO feedback loop: events originate from our own HTTP handlers, not
      from ADT twin-change routes, so process_event never re-triggers itself.

  To revert to direct processing (no teardown needed):
    az functionapp config appsettings set -n <func> -g <rg> --settings EVENT_GRID_ENABLED=false

  Set $FuncApp below to the name deploy.ps1 printed, then run:  .\deploy-eventgrid.ps1
#>

$ErrorActionPreference = "Stop"

# ============================ CONFIG ============================
$AdtName = "ferrotwin-adt"
$FuncApp = "<your-function-app-name>"     # <-- the name deploy.ps1 printed
$Topic   = "ferrotwin-egt"                 # custom topic name
$SubName = "ferrotwin-eg-sub"
# ===============================================================

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

if ($FuncApp -like "*your-function-app*") { throw "Edit the CONFIG block: set `$FuncApp to your deployed Function App name." }

Step "1/6  Ensure the eventgrid CLI extension is present"
az extension add --name eventgrid --only-show-errors 2>$null

Step "2/6  Resolve resource group + region from the ADT instance"
$adt = az dt show -n $AdtName -o json | ConvertFrom-Json
$RG = $adt.resourceGroup; $Loc = $adt.location
Write-Host "  RG=$RG  Location=$Loc"

Step "3/6  Create the custom Event Grid topic ($Topic)"
az eventgrid topic create -n $Topic -g $RG -l $Loc --only-show-errors | Out-Null
$TopicEndpoint = az eventgrid topic show -n $Topic -g $RG --query endpoint -o tsv
$TopicKey      = az eventgrid topic key list -n $Topic -g $RG --query key1 -o tsv
Write-Host "  Endpoint: $TopicEndpoint"

Step "4/6  Point the Function App at the topic and enable event-driven mode"
az functionapp config appsettings set -n $FuncApp -g $RG --only-show-errors --settings `
  "EVENT_GRID_ENABLED=true" `
  "EVENT_GRID_TOPIC_ENDPOINT=$TopicEndpoint" `
  "EVENT_GRID_TOPIC_KEY=$TopicKey" | Out-Null
Write-Host "  App settings applied (restart + propagation ~1-2 min)."

Step "5/6  Subscribe the process_event function to the topic"
$FuncId  = az functionapp show -n $FuncApp -g $RG --query id -o tsv
$TopicId = az eventgrid topic show -n $Topic -g $RG --query id -o tsv
az eventgrid event-subscription create `
  --name $SubName `
  --source-resource-id $TopicId `
  --endpoint-type azurefunction `
  --endpoint "$FuncId/functions/process_event" `
  --only-show-errors | Out-Null
Write-Host "  Subscription '$SubName' created."

Step "6/6  Done"
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " EVENT-DRIVEN MODE ENABLED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host " POST /telemetry and /inspection now return 202 and are processed async."
Write-Host " Verify: POST a telemetry reading, then GET /history/telemetry a few"
Write-Host " seconds later — the reading should appear once the event is delivered."
Write-Host " Revert anytime: set EVENT_GRID_ENABLED=false on the Function App."
Write-Host "============================================================" -ForegroundColor Green
