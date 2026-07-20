# FerroTwin — Full Cloud Deployment (1-day trial)

Deploys the Function API to Azure and hosts the dashboard on Azure Storage,
**reusing your existing `ferrotwin-adt` instance and `ferrotwinst001` storage
account**. Event Grid stays disabled — the app processes telemetry and
inspections directly, which behaves identically for the demo and removes the
single biggest source of first-time deployment pain.

Everything provisioned here fits comfortably inside the free trial credit.

---

## 0. Prerequisites (install once)

- **Azure CLI** — https://aka.ms/installazurecli
- **Azure Functions Core Tools v4** — `npm i -g azure-functions-core-tools@4`
- **Python 3.11+** with this repo's packages: `pip install -r requirements.txt`
- Log in and select the right subscription:

  ```powershell
  az login
  az account set --subscription "<your-subscription-name>"
  ```

- You must hold **Azure Digital Twins Data Owner** on `ferrotwin-adt`
  (you created it, so you likely do). If step 3 fails with 403, see Troubleshooting.

---

## 1. One command

From the repo root (`D:\ADT`):

```powershell
.\deploy.ps1
```

It discovers the ADT's resource group and region, uploads models, builds the
twin graph, creates the Function App with a managed identity, grants that
identity ADT Data Owner, applies app settings, hosts the dashboard, configures
CORS, publishes the code, and prints the **Dashboard URL + API base URL +
Function key** at the end.

Then open the Dashboard URL → **Connect API** → paste the API base URL and key.

To bring the line alive, in a second terminal (repo root):

```powershell
$env:FERROTWIN_FUNCTION_URL="https://<yourfunc>.azurewebsites.net/api"
$env:FERROTWIN_FUNCTION_KEY="<function-key>"
python scripts/demo_stream.py
```

Within a few seconds the KPI cards, temperature chart, defect distribution,
inspection history, and (about every 2 minutes) a critical heat alarm appear.

---

## 2. Manual steps (if you'd rather run each yourself, or the script stops midway)

```powershell
# --- names ---
$Adt="ferrotwin-adt"; $Storage="ferrotwinst001"; $Func="ferrotwin-func-1234"  # make Func globally unique

# discover RG / region / host from the existing ADT
$adt = az dt show -n $Adt -o json | ConvertFrom-Json
$RG=$adt.resourceGroup; $Loc=$adt.location; $AdtHost="https://$($adt.hostName)"

# models + twins (idempotent)
$env:ADT_HOST=$AdtHost
python scripts/upload_models.py
python scripts/create_twins.py

# function app (Linux Consumption, Python 3.11, system identity)
az functionapp create -n $Func -g $RG --storage-account $Storage `
  --consumption-plan-location $Loc --runtime python --runtime-version 3.11 `
  --functions-version 4 --os-type Linux --assign-identity "[system]"

# grant the identity data-plane access to ADT (THE step first-timers miss)
$pid = az functionapp identity show -n $Func -g $RG --query principalId -o tsv
az dt role-assignment create --dt-name $Adt --assignee $pid --role "Azure Digital Twins Data Owner"

# app settings
az functionapp config appsettings set -n $Func -g $RG --settings `
  "ADT_HOST=$AdtHost" "STORAGE_ACCOUNT_NAME=$Storage" "INSPECTION_BLOB_CONTAINER=inspections" `
  "EVENT_GRID_ENABLED=false" "TEMPERATURE_ALERT_THRESHOLD=900" `
  "REPEATED_DEFECT_COUNT=3" "REPEATED_DEFECT_WINDOW_MINUTES=30"

# host the dashboard on the storage static website
$Key = az storage account keys list -n $Storage -g $RG --query "[0].value" -o tsv
az storage blob service-properties update --account-name $Storage --account-key $Key `
  --static-website --index-document index.html --404-document index.html
az storage blob upload-batch --account-name $Storage --account-key $Key -s dashboard -d '$web' --overwrite
$Dash = az storage account show -n $Storage -g $RG --query "primaryEndpoints.web" -o tsv

# CORS + publish
az functionapp cors add -n $Func -g $RG --allowed-origins $Dash.TrimEnd('/') "http://localhost:8080"
func azure functionapp publish $Func --build remote

# grab the key
az functionapp keys list -n $Func -g $RG --query "functionKeys.default" -o tsv
```

---

## 3. Verify

```powershell
curl https://<yourfunc>.azurewebsites.net/api/health
# -> {"status":"ok","adtConnected":true,"factory":"Factory 01",...,"eventGridEnabled":false}
```

`/health` and `/ping` are anonymous. Everything else needs the `x-functions-key`
header (the dashboard sends it for you once you click **Connect API**).

---

## 4. Troubleshooting (the ones that actually happen)

- **`create_twins.py` returns 403 / "Forbidden"** — you have subscription
  Owner/Contributor but not the ADT *data-plane* role. Grant yourself:
  ```powershell
  $me = az ad signed-in-user show --query id -o tsv
  az dt role-assignment create --dt-name ferrotwin-adt --assignee $me --role "Azure Digital Twins Data Owner"
  ```
  Wait a few minutes for propagation, then re-run.

- **Function `/health` returns 503 after publish** — the managed-identity ADT
  role hasn't propagated yet (up to ~10 min), or the role wasn't assigned. Re-check
  step 6, wait, retry.

- **Dashboard shows "Connection failed" / CORS error in the browser console** —
  the dashboard origin isn't in the Function App CORS list. Re-run the
  `az functionapp cors add` line with your exact static-site URL (trailing slash
  removed).

- **First request is slow (10–30 s)** — Consumption plan cold start (loads the
  ONNX model). Normal; subsequent requests are fast. Keep `demo_stream.py`
  running and it stays warm.

- **`func publish` fails on package size or a torch wheel** — make sure you're on
  the fixed `requirements.txt` (no torch/torchvision) and `.funcignore` excludes
  `Neu-CLS`, `ml`, and `data`. Confirm with `git status`.

- **First inspection image doesn't render** — the blob container is created on
  the first inspection write. Post one inspection (or let `demo_stream.py` run a
  minute), then refresh.

---

## 4b. Optional — switch to the event-driven (Event Grid) architecture

Only after the direct path works. Set `$FuncApp` in `deploy-eventgrid.ps1` to the
Function App name printed above, then:

```powershell
.\deploy-eventgrid.ps1
```

It creates a custom Event Grid topic, subscribes the `process_event` function to
it, and sets `EVENT_GRID_ENABLED=true`. `POST /telemetry` and `/inspection` then
return `202` and are processed asynchronously. Revert anytime with:

```powershell
az functionapp config appsettings set -n <func> -g <rg> --settings EVENT_GRID_ENABLED=false
```

## 5. Save your trial credit when you stop

```powershell
# cheapest: stop the function app (ADT + storage cost almost nothing idle)
az functionapp stop -n <yourfunc> -g <rg>

# or delete everything you added (leaves ADT + storage intact):
az functionapp delete -n <yourfunc> -g <rg>
```

The ADT instance and storage account bill negligibly at idle, so you don't need
to tear those down between sessions.
