# Ferrotwin Digital Twin — Corrected Implementation Roadmap

Companion to `inspection-station-digital-twin-proposal.md`. This document assumes the proposal as baseline and only restates what changes, plus the precise implementation detail the proposal left unspecified. Structure: the seven corrections in full, the corrected big picture, then ten implementation phases mapped onto a revised 14-day timeline.

Assumption stated up front: you already have a working Azure subscription with the $200 credit and can provision resources normally. If that is not settled, settle it before Day 1 — it gates everything.

---

## Part 1 — Corrections in Full

### C1. Upstream query direction

The relationship is defined on `ProcessStage` as source: `ProcessStage --feedsInto--> InspectionStation`. In the ADT query language, `JOIN X RELATED Y.relName` traverses relationships *outgoing from* collection `Y`. `InspectionStation.feedsInto` does not exist, and because ADT queries return empty (no error) on wrong names, the proposal's query fails silently.

Three working options — pick per context:

**Option A — JOIN filtered on the target's `$dtId`** (docs explicitly allow filtering on source *or* target). Use this for the interview demo, it proves graph literacy:

```sql
SELECT stage
FROM DIGITALTWINS stage
JOIN station RELATED stage.feedsInto
WHERE station.$dtId = 'station-line1-a'
```

**Option B — incoming-relationships API** (simplest inside the Recommender; no query units, no query syntax):

```python
def get_upstream_stage_ids(client, station_id: str) -> list[str]:
    return [
        r.source_id
        for r in client.list_incoming_relationships(station_id)
        if r.relationship_name == "feedsInto"
    ]
```

**Option C — MATCH clause** (mention in interview as the "variable-hop" tool; requires `$dtId` on at least one twin). **CORRECTED after external review + doc verification.** The MATCH reference documents a limitation: "`$dtId` filters on any twin other than the starting twin for the MATCH traversal may show empty results," and the docs' own left-to-right example flags a `$dtId` filter on the *target* twin as exactly this case. A directed form `MATCH (stage)-[:feedsInto]->(station) WHERE station.$dtId = ...` anchors the target and is therefore the documented-unreliable shape — the same silent-empty failure class as the original proposal's JOIN bug. Since our task fixes the *target* (known station, unknown upstream stage), no direction-specified MATCH is doc-safe for it. The doc-consistent form is **non-directional**, which is semantically equivalent here because only ProcessStage defines `feedsInto`:

```sql
SELECT stage
FROM DIGITALTWINS
MATCH (station)-[:feedsInto]-(stage)
WHERE station.$dtId = 'station-line1-a'
```

(Non-directional MATCH is documented as costlier to process — irrelevant at this scale — and MUST still be tested against the live instance before any demo use; "starting twin" is not formally defined in the docs.)

Important boundary: this MATCH limitation does **not** apply to Option A. The JOIN clause explicitly supports filtering on either the source or the target twin's `$dtId` — the docs even say "if your scenario requires you to use `$dtId` on other twins, consider using the JOIN clause instead." Do not let the MATCH caveat shake confidence in A.

Use B in the Recommender (fewer failure modes), A in the demo script and README, C only if asked about variable-hop queries — and only after live-testing it.

### C2. Recommender self-trigger loop

Twin-update events fire on *every* property patch, including the Recommender's own writes of `lastRecommendation` / `lastRecommendationSeverity`. Without a guard: inspection patch → event → recommender → recommendation patch → event → recommender → … Each cycle is a Function invocation and an ADT operation; at best noise, at worst runaway.

Guard at the top of the Event Grid handler by inspecting the JSON Patch in the event body:

```python
RECO_PATHS = ("/lastRecommendation", "/lastRecommendationSeverity")

def main(event: func.EventGridEvent):
    body = event.get_json()
    paths = [op.get("path", "") for op in body.get("data", {}).get("patch", body.get("patch", []))]
    if paths and all(p.startswith(RECO_PATHS) for p in paths):
        return  # our own write — do not recurse
    if not any(p.startswith(("/totalInspected", "/lastDefectType", "/rollingDefectRate")) for p in paths):
        return  # not an inspection-driven update
    ...
```

(Exact payload nesting differs slightly by Event Grid schema version — log one raw event on Day 3 and pin the parsing to what you actually receive. Do not trust any doc or this file over the logged payload.)

Alternative that eliminates the class of bug entirely: run the Recommender on a 60-second timer instead of Event Grid. You lose the "event-driven" resume phrase but gain determinism. Recommended compromise: Event Grid trigger with the guard, plus debounce (skip if a recommendation for this station was written < 60 s ago — one Postgres lookup).

### C3. Reproducibility: Bicep covers control plane only

ARM/Bicep can create: the ADT instance, the Event Grid topic, the ADT *endpoint* resource, Function Apps, Container Apps, Postgres, role assignments. ARM/Bicep can NOT create: DTDL model uploads, twins, relationships, or ADT *event routes* — those are data-plane API calls.

Correct split:

```
deploy.sh
├── az deployment sub create ... main.bicep      # all control-plane resources + RBAC
└── python bootstrap/setup_dataplane.py          # idempotent:
      1. upload dtdl/*.json models (skip if same version exists)
      2. create twins + relationships from graph.yaml
      3. create event route  (filter: type = 'Microsoft.DigitalTwins.Twin.Update')
      4. smoke test: run the Option-A query, assert non-empty
```

Idempotency matters because you will re-run this constantly. Model uploads with an existing `@id`+version fail — catch and skip. Twin creation: use upsert (`upsert_digital_twin` is create-or-replace by design). Success criterion becomes: "environment stands up from a single `./deploy.sh`."

### C4. Latency criterion vs. scale-to-zero

Cold start on Container Apps Consumption = provision + image pull + uvicorn boot + ONNX session load. Tens of seconds, not < 2 s. Fixes, in combination:

1. Redefine the success criterion: *warm-path* p50/p95 latency < 2 s, measured over the soak run and reported honestly ("p95 warm-path 640 ms; cold start 18 s, mitigated by min-replica pinning during operation").
2. During soak/demo sessions set `minReplicas: 1` (a few cents/day at 0.25 vCPU / 0.5 GiB); set back to 0 between sessions. One `az containerapp update` each way — put both in a `Makefile`.
3. Keep the image small: `python:3.12-slim`, `onnxruntime` CPU wheel, no torch in the serving image. Target < 400 MB.

### C5. Honest correlation detection (the centerpiece fix)

Problem restated: the proposal *claims* the Recommender "detects the correlation statistically — it isn't told the mapping in advance," but the pseudocode hardcodes temperature, uses two independent thresholds, and calls co-occurrence correlation. A tension-driven drift is invisible to it; a coincidental defect bump during any temperature wobble produces a confident false attribution. An interviewer who reads the code sees the gap immediately.

The honest version is barely harder. Full algorithm in Phase 7; the shape:

1. **Drift score per parameter** — for each of {temperature, tension, speed}: z-score of the last 10-minute mean against a trailing reference window (e.g., 2–6 h ago). Drift = |z| above threshold. No parameter is privileged.
2. **Per-class lift** — split inspections into drift window vs. reference window. For each defect class c: `lift(c) = rate_drift(c) / max(rate_ref(c), ε)`, gated on minimum sample counts (n_drift ≥ 20, class count ≥ 5) and a two-proportion z-test (or, simpler and defensible at this n, lift ≥ 2 with the count gates — state the tradeoff in the README).
3. **Recommendation = argmax pair** (drifting parameter, lifted class) with the numbers in the message. The parameter→class affinity map lives *only* in the simulator; the Recommender genuinely discovers which pair lights up.

This also fixes the demo-metric weakness: log ground truth (`drift_active`, `drift_param`) in Postgres from the simulator, and after the soak run compute **recommender precision/recall over ≥ 5 injected drifts**. "Detected 5/5 injected drifts with 1 false positive, correct parameter attribution in 5/5" is a dramatically better resume line than "3 scenarios produced recommendations."

Frame it in interviews as a lightweight SPC (statistical process control) analog — the proposal's instinct there was right; now the code matches the framing.

### C6. Inverted risk model → inverted timeline

NEU-CLS with ResNet18/MobileNetV2 transfer learning sits at 98–99.5% in the literature and in practice; the classes are visually very distinct at 200×200. Your ≥ 90% target is a floor you would have to work to miss, so Days 2–3 carry almost no risk — while ADT RBAC, managed identities, the endpoint→topic→subscription chain, and event payload parsing (the actual documented first-timer pain, which the proposal itself flags) sit untested until Day 6–9 with no slack behind them.

Consequences:

- **Walking skeleton first.** Days 1–3 build the entire pipe end-to-end with a *stub* classifier (returns a random class + fake confidence). Every integration risk is burned down by Day 3; the real model is then a drop-in container swap. This also means you have something demoable from Day 3 onward.
- **Raise the model bar**: target ≥ 97% accuracy and report macro-F1 + per-class confusion matrix. On this dataset, 90% signals a broken pipeline, not a trained model.
- Keep the Day-3 fallback-dataset rule, but its trigger is now "pipeline blocked," not "accuracy low" — accuracy will not be the problem.

### C7. DTDL v2, not v3

Your validation/debug workflow leans on ADT Explorer, which is still in public preview with only limited DTDL v3 support (v3 models generally need to be handled via code). Nothing in the four models uses a v3 feature. Change every `@context` to `"dtmi:dtdl:context;2"` and keep the Explorer-centric workflow. The models are otherwise valid as written (`double`, `integer`, `string`, `dateTime` are all v2 primitives; relationships need no `@id`).

Two model nits while you are in there: (a) `lastUpdated` duplicates ADT's built-in per-property `$metadata.$lastUpdateTime` — harmless, keep it for query convenience, but know the built-in exists for the interview; (b) consider `Enum` schema for `status` and `lastRecommendationSeverity` instead of free strings — one line each, and it shows DTDL fluency.

### Smaller corrections folded into the phases below

- **Image supply chain** (unspecified in proposal): the held-out test split goes to Blob Storage under `pool/<class>/*.jpg`; the inspection simulator samples *only* from this pool. Never let training images into the live pool — that is data leakage in your demo story, and "the live stream only ever sees images the model never trained on" is a sentence worth saying out loud.
- **Dashboard transport** (unspecified): poll every 3 s from a small read-only backend. SignalR stays a stretch goal.
- **Region**: ADT exists only in a subset of regions, and the supported list changes over time — trust no static list (including any in this document). Check the live region dropdown / supported-regions page during Phase 0, pick one region, put *everything* in it, hardcode it in Bicep params.
- **Postgres stop/start**: compute billing stops, storage keeps billing, and a stopped Flexible Server **auto-restarts after 7 days** — set a calendar reminder or you will silently burn credit in week 2 of any pause.
- **Timeline duplication**: Day 1 provisions ADT via Bicep; Day 6 says "provision ADT instance" again. Resolved by the phase plan below (provision once, Day 1).

---

## Part 2 — Corrected Big Picture

One paragraph you should be able to say from memory: *Two simulators generate the world. The drift simulator random-walks three process parameters per stage, occasionally injecting an out-of-band drift window, patching the ProcessStage twin and logging every reading (plus ground-truth drift flags) to Postgres. The inspection simulator samples a held-out defect image from Blob — with class probabilities biased by whatever the upstream stage is currently doing — sends it to a FastAPI/ONNX classifier on Container Apps, patches the InspectionStation twin with the result, and logs the event to Postgres. Twin patches flow through an ADT event route → Event Grid topic → Recommender Function, which guards against its own writes, scores parameter drift and per-class defect lift from Postgres history, resolves the upstream stage through the ADT graph, and writes an explainable recommendation back onto the station twin. A Next.js dashboard polls a thin read-only API over both ADT (current state) and Postgres (history) every 3 seconds. Bicep builds the control plane; one bootstrap script builds the data plane; one `deploy.sh` runs both.*

Data-flow deltas vs. the proposal's mermaid diagram: add `Blob (image pool) → IE`, add the loop-guard on REC, add `ground truth drift flags → PG` from PS, and note the Event Grid hop is really three resources (ADT endpoint → EG topic → EG subscription → Function).

---

## Part 3 — Implementation Phases

### Phase 0 — Prerequisites (half of Day 1)

Local tooling: Azure CLI (`az`) + `az extension add --name dt` (or `azure-iot`, whichever currently carries the `az dt` commands — check `az dt -h`), Azure Functions Core Tools v4, Docker, Python 3.12, Node 20+, Bicep CLI (`az bicep install`). Azure: verify you can create a resource group and that ADT is creatable in your chosen region (portal → Create → Digital Twins → check region dropdown *before* writing Bicep). Create the Kaggle account / download path for NEU-CLS now so the dataset is local before Day 4.

Repo: initialize the structure from proposal §8 unchanged, plus `bootstrap/` and `Makefile`.

### Phase 1 — Control plane + RBAC (rest of Day 1)

`infra/main.bicep` provisions, in one region:

| Resource | SKU / config |
|---|---|
| Resource group | — |
| Azure Digital Twins instance | default |
| Event Grid topic | Basic |
| ADT endpoint → that topic | key-based auth (simplest) |
| Storage account | Standard LRS; container `pool` |
| Function App (Consumption, Python) ×1 (three functions inside) | system-assigned managed identity ON |
| Container Apps environment + app `inference` | 0.25 vCPU / 0.5 GiB, minReplicas 0, external ingress |
| Container App `dash-api` (added Phase 8, stub now optional) | same size |
| Postgres Flexible Server | Burstable B1ms, 32 GB, public access + firewall to your IP and Azure services |
| Application Insights | workspace-based |

RBAC (also in Bicep — `Microsoft.Authorization/roleAssignments`):

| Principal | Role | Scope |
|---|---|---|
| Your user | **Azure Digital Twins Data Owner** | ADT instance |
| Function App managed identity | **Azure Digital Twins Data Owner** | ADT instance |
| dash-api managed identity | **Azure Digital Twins Data Reader** | ADT instance |
| Function App + dash-api identities | **Storage Blob Data Reader** | storage account |

The single most common ADT first-timer failure: having Owner/Contributor on the *subscription* and assuming that grants data-plane access. It does not. ADT Explorer shows an empty instance or 403s until the explicit **Data Owner** data-plane role lands (and role propagation can take a few minutes). The inference Container App needs no ADT access at all — it only classifies.

Secrets: Postgres connection string and inference URL go into Function App settings via Bicep. Key Vault stays a stretch goal, as proposed.

**Exit test:** `az dt twin query -n <instance> -q "SELECT COUNT() FROM DIGITALTWINS"` returns 0 without a permissions error.

### Phase 2 — Twin graph as code (Day 2)

1. Rewrite the four DTDL files with `dtmi:dtdl:context;2` (+ optional Enum nits from C7). Validate locally — DTDL parser libraries exist for .NET; the pragmatic Python-side check is simply attempting the upload and reading the error, which is precise about what it dislikes.
2. `bootstrap/graph.yaml` — declarative twin list: 1 Factory, 2 Lines, 4 ProcessStages, 3 InspectionStations, and the relationships including `feedsInto` per stage→station pair.
3. `bootstrap/setup_dataplane.py` (azure-digitaltwins-core + DefaultAzureCredential): upload models (skip-if-exists), upsert twins, upsert relationships, create the event route with filter `type = 'Microsoft.DigitalTwins.Twin.Update'`, then run the Option-A query and assert it returns the expected stage.

**Exit test:** graph visible in ADT Explorer; the C1 Option-A query returns the correct upstream stage for every station, from the CLI, with zero application code involved. This *is* the "graph correctness" success criterion — bank it on Day 2.

### Phase 3 — Walking skeleton (Day 3) ← the de-risking move

Goal: every integration seam exercised once, with a fake brain.

1. **Stub inference service**: FastAPI `POST /classify` accepting multipart image bytes, returning `{"predicted_class": random.choice(CLASSES + ["ok"]), "confidence": round(random.uniform(0.7, 0.99), 3), "model_version": "stub-0"}`. Dockerize, push to a registry (GitHub Container Registry keeps ACR off the bill; Container Apps can pull public GHCR images), deploy.
2. **Inspection simulator v0** (timer trigger, every 15 s): pick any image from Blob, call inference, patch the station twin (`totalInspected`, `lastDefectType`, `lastUpdated`). No Postgres yet.
3. **Recommender v0** (Event Grid trigger): log the raw event JSON, apply the C2 loop-guard, patch `lastRecommendation = "skeleton OK <timestamp>"` once per N events.
4. Pin the event-payload parsing to the logged reality (C2 caveat).

**Exit test:** watch `lastRecommendation` change in ADT Explorer with zero manual steps in the loop. End-to-end proven on Day 3. Everything after this is substitution, not integration.

### Phase 4 — Real vision model (Days 4–5)

**Dataset.** NEU-CLS: 6 classes × 300 images, 200×200 grayscale — crazing, inclusion, patches, pitted_surface, rolled-in_scale, scratches. Source via the Kaggle mirror ("NEU Surface Defect Database"); the original university links rot regularly. Academic-use dataset; fine for a portfolio, cite it in the README.

**Split protocol (this doubles as the demo-integrity story).** Stratified 70/15/15 with a fixed seed. The 15% test split serves two roles: metrics, and the *entire* live simulation pool uploaded to Blob under `pool/<class>/`. Add ~50 "ok" images (defect-free steel surface crops — NEU-CLS has no OK class; simplest honest options: source OK-surface images from a companion steel dataset, or train 6-class and let the simulator emit "ok" events without an image at a fixed base rate, clearly documented. The second is less pretty but zero-risk; decide Day 4, don't burn hours on it).

**Training recipe (Colab or local, never Azure):**

- Preprocess: grayscale→3-channel replicate, resize 224, ImageNet normalization. Put this in a single `transforms.py` imported by BOTH the training code and the FastAPI service. Duplicated preprocessing is the classic parity killer — more so than the ONNX export itself.
- Augmentation (train only): h/v flip, 90° rotations, mild brightness/contrast. Orientation-invariance claim in the proposal is correct for these classes.
- Model: MobileNetV2 (smaller image, faster CPU inference) or ResNet18. Freeze backbone for 3 epochs (head lr 3e-4, AdamW), then unfreeze last block (backbone lr 3e-5), cosine decay, batch 32, ≤ 25 epochs, early stop on val macro-F1.
- Expect 98%+. If you are under 95%, suspect the pipeline (label mapping, normalization, leakage) before the model.

**Export + parity:** `torch.onnx.export(..., opset_version=17, dynamic_axes={'input': {0: 'batch'}})`. Parity gate: over ≥ 50 val images, `max |logit_pytorch − logit_onnx| < 1e-3` and 100% argmax agreement. Commit the parity script; mention the gate in the README.

**Serving:** swap the stub — same endpoint contract, now loading `model.onnx` with onnxruntime (CPU EP, `intra_op_num_threads=1` is fine at this size). Add `GET /healthz` (Container Apps probes) and return `model_version` from a build arg. Image target < 400 MB: `python:3.12-slim`, no torch.

**Exit test:** deployed endpoint classifies a known crazing image correctly in < 300 ms warm; confusion matrix + macro-F1 artifact committed to `docs/`.

### Phase 5 — History layer (Day 6, morning)

Postgres DDL (three tables; `drift_active`/`drift_param` are simulator ground truth used ONLY for post-hoc evaluation — the Recommender never reads them, say so in a comment and in the interview):

```sql
CREATE TABLE inspection_events (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  station_id TEXT NOT NULL,
  image_key TEXT,
  predicted_class TEXT NOT NULL,
  confidence REAL NOT NULL,
  is_defect BOOLEAN NOT NULL,
  latency_ms INTEGER
);
CREATE INDEX ix_ie_station_ts ON inspection_events (station_id, ts DESC);

CREATE TABLE stage_readings (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  stage_id TEXT NOT NULL,
  temperature REAL NOT NULL,
  tension REAL NOT NULL,
  speed REAL NOT NULL,
  drift_active BOOLEAN NOT NULL DEFAULT FALSE,  -- ground truth, evaluation only
  drift_param TEXT                               -- ground truth, evaluation only
);
CREATE INDEX ix_sr_stage_ts ON stage_readings (stage_id, ts DESC);

CREATE TABLE recommendations (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  station_id TEXT NOT NULL,
  stage_id TEXT,
  parameter TEXT,
  defect_class TEXT,
  drift_z REAL,
  lift REAL,
  severity TEXT,
  message TEXT NOT NULL
);
```

Both simulators gain their Postgres writes here. Connection handling in Functions: one connection per invocation is fine at this volume; skip pooling complexity.

### Phase 6 — Simulators, full version (Day 6 afternoon – Day 8)

**Drift simulator** (timer, every 20 s, per stage): mean-reverting random walk per parameter — `x += θ·(μ − x) + σ·N(0,1)` with per-parameter (μ, σ, band). A drift injector: with small probability per tick (or on a schedule you control for the demo), pick one parameter, shift its μ out of band for 10–20 min, set `drift_active/drift_param`, then revert. Patch the ProcessStage twin and insert into `stage_readings` every tick.

**Inspection simulator** (timer, every 10–15 s, per station): read the upstream stage's current parameters (from its own last patch or a shared config — reading the twin back costs an operation; cheaper to read from Postgres). Sampling weights: baseline `P0(class)` ≈ 25% defect total spread over 6 classes + 75% ok; if a parameter is out-of-band, multiply the weights of `AFFINITY[param]` classes by k=4 and renormalize. AFFINITY (simulator-only, from domain literature): temperature→{rolled-in_scale, patches}; tension→{crazing, scratches}; speed→{inclusion, pitted_surface}. Sample an image key from `pool/<class>/`, call inference, patch station twin (counters + rolling rate over last 50), insert into `inspection_events`.

Note the honest wrinkle: what the twin records is the *model's prediction*, not the sampled label — with a 98% model these coincide almost always, and the residual gap is exactly the "real inference in the loop" claim. Log both (`image_key` encodes true class) so you can show live accuracy on the dashboard as a bonus.

**Exit test (Day 8):** during a forced temperature drift, the class mix in `inspection_events` visibly shifts toward rolled-in_scale/patches within ~5 min; outside drift it does not. One SQL query proves it; screenshot it for `docs/`.

### Phase 7 — Recommender, honest version (Day 9)

Trigger: Event Grid with C2 guard + 60 s debounce. Logic per invocation:

```python
def evaluate(station_id):
    stage_ids = get_upstream_stage_ids(adt, station_id)       # C1 option B
    now = utcnow()
    drift, ref = window(now, minutes=15), window(now - 2h, hours=2)

    for stage_id in stage_ids:
        # 1. parameter drift scores (NO parameter privileged)
        zs = {}
        for p in ("temperature", "tension", "speed"):
            cur  = pg.mean(stage_readings, stage_id, p, drift)
            base = pg.mean_std(stage_readings, stage_id, p, ref)
            zs[p] = (cur - base.mean) / max(base.std, 1e-6)
        p_star, z_star = max(zs.items(), key=lambda kv: abs(kv[1]))
        if abs(z_star) < 3.0:
            continue

        # 2. per-class lift, gated
        d = pg.class_counts(inspection_events, station_id, drift)   # n_d, counts
        r = pg.class_counts(inspection_events, station_id, ref)
        if d.total < 20:
            continue
        best = None
        for c in DEFECT_CLASSES:
            rate_d = d[c] / d.total
            rate_r = max(r[c] / max(r.total, 1), 1/max(r.total,1))  # ε floor
            lift = rate_d / rate_r
            if d[c] >= 5 and lift >= 2.0 and two_prop_ztest(d, r, c) < 0.05:
                best = max(best, (lift, c), key=lambda t: t[0] if t else 0)
        if not best:
            continue

        lift, c = best
        write_recommendation(station_id, stage_id, p_star, c, z_star, lift,
            severity="high" if lift >= 4 else "medium",
            message=(f"{c} rate {lift:.1f}x baseline over last 15 min at {station_id}; "
                     f"upstream {stage_id} {p_star} drifting ({z_star:+.1f}σ). "
                     f"Inspect {p_star} control on {stage_id}."))
        patch_station_twin(station_id, message, severity)
```

The two-proportion z-test is ~10 lines with scipy or by hand; if you'd rather not defend p-values at n≈30, drop it and keep lift ≥ 2 with count gates — but then say exactly that in the README ("count-gated lift heuristic; z-test noted as the rigorous upgrade"). Either is honest; silent thresholds pretending to be statistics are not.

**Sparse-baseline guard (added after external review).** The gates above are not sufficient after a data gap (Postgres stopped overnight, simulators paused). Two failure paths: (a) a reference window with only a handful of `stage_readings` rows yields a degenerate std → inflated z-scores; (b) a sparse-but-nonzero inspection reference (e.g., `r.total = 10`, `r[c] = 1` → floor rate 0.1) lets an ordinary 30% drift-window rate register as lift 3.0 and pass every gate — a **false positive**, not the silent skip you might assume. Add two hard gates: `ref stage_readings count ≥ 60` and `r.total ≥ 100`, and when any gate blocks, **log the skip with its reason** (`insufficient_baseline`, `low_drift_z`, `no_significant_lift`) instead of a bare `continue`. Silent skips and false alarms look identical to "the recommender is broken" from the outside; logged reasons make the system diagnosable and give you an extra observability talking point.

Unit-test this against canned Postgres fixtures (one true drift, one quiet period, one drift-without-defect-shift) *before* wiring it live — this function is the only nontrivial logic in the system and the only one worth real tests.

**Exit test:** injected temperature drift → recommendation naming temperature and a plausible class, with numbers, on the twin and in Postgres; quiet hour → zero recommendations.

### Phase 8 — Dashboard (Days 11–12)

Thin read-only FastAPI (`dash-api`, Data Reader on ADT + Postgres read): `GET /overview` (query ADT for all stations + stages, one query, current state), `GET /stations/{id}/history?minutes=60` (Postgres), `GET /stages/{id}/readings?minutes=60`, `GET /recommendations?limit=20`, `GET /live-accuracy` (prediction vs. image_key class, Phase 6 bonus). Next.js on Static Web Apps free tier, polling every 3 s: hierarchy panel, per-station cards (rolling rate, last class, last recommendation with severity color), stacked defect-mix chart, parameter trend chart with drift windows shaded (ground truth — label it as such), recommendation feed. No SignalR, no auth (dashboard API is read-only demo data; note it as a deliberate scope cut).

### Phase 9 — Reproducibility (Day 13)

Consolidate to the C3 shape: `deploy.sh` = Bicep + bootstrap. Then the real test: delete the resource group, run `./deploy.sh`, republish the two container images, `func azure functionapp publish`, and confirm the walking-skeleton exit test passes within ~30 min. Document every manual step you couldn't automate — the honest list is itself interview material. `teardown.sh`: stop Postgres, minReplicas 0, or full `az group delete`.

### Phase 10 — Soak, evaluation, demo (Days 10 & 14)

Soak (Day 10, pulled earlier than polish on purpose): 4–6 h run with 5+ scheduled drift injections across parameters and stations. Then compute from Postgres: recommender precision/recall vs. ground truth, parameter-attribution accuracy, warm-path latency p50/p95 (inference `latency_ms`), and end-to-end lag (inspection ts → twin `lastUpdated`). These four numbers + the confusion matrix are the demo's spine. Add one runtime invariant to the soak: recommendation-write volume must stay a small bounded fraction of inspection-event volume (e.g., recs ≤ 2% of inspections over any hour) — it's the cheap tripwire that catches any residual C2-style feedback or an over-eager recommender, and "silent failures need explicit invariants, not clean logs" is itself an interview line.

Demo script (proposal §12 stands, two upgrades): replace criterion "3 scenarios fire" with the precision/recall table; add 30 seconds showing the C2 loop-guard and explaining why it must exist — nothing signals production instinct like a bug you prevented.

---

## Part 4 — Revised 14-Day Timeline

| Day | Focus | Exit test |
|---|---|---|
| 1 | Phase 0 + 1: tooling, region check, Bicep control plane, RBAC | `az dt twin query` COUNT works, no 403 |
| 2 | Phase 2: DTDL v2, bootstrap script, graph up | Upstream query (C1-A) correct from CLI |
| 3 | Phase 3: stub inference deployed, sim v0, Event Grid chain, loop guard | `lastRecommendation` updates hands-free |
| 4 | Phase 4: dataset, training run, ≥ 97% val | Confusion matrix in hand |
| 5 | Phase 4: ONNX + parity gate, swap stub, Blob pool upload | Real classifications end-to-end |
| 6 | Phase 5 + 6 start: Postgres schema, history writes, drift sim skeleton | Rows landing in both tables |
| 7 | Phase 6: drift injector + ground truth, full drift sim | Drift windows visible in stage_readings |
| 8 | Phase 6: biased sampling wired | Class-mix shift under drift (SQL proof) |
| 9 | Phase 7: recommender + unit tests | Correct rec on injected drift; silence when quiet |
| 10 | Phase 10a: soak + metrics extraction | Precision/recall + latency numbers |
| 11–12 | Phase 8: dashboard | Live demo-able UI |
| 13 | Phase 9: deploy.sh, from-scratch rebuild | Fresh env passes Day-3 exit test |
| 14 | Demo video, README, resume bullets, teardown | Portfolio complete |

Slack analysis: the old plan's risk (Days 6–9 plumbing, no slack) now burns down by Day 3; the model days (4–5) are the low-variance ones; Days 11–12 remain the compressible buffer (a plainer dashboard is an acceptable loss, a broken event chain is not).

## Part 5 — Budget deltas only

**Operational-continuity rule (added after external review — the stop/start advice below conflicts with Phase 7's data needs if applied naively).** The Recommender's reference window spans roughly t−4h to t−2h; stopping Postgres overnight leaves that window empty or sparse for hours after resume, and per the Phase 7 sparse-baseline guard, sparse baselines can produce false positives, not just silence. Also note the timer Functions keep firing while Postgres is down — failed inserts, noisy logs, twins drifting on stale context. So pause the world **atomically**: `make world-down` = disable both timer functions → stop Postgres → minReplicas 0; `make world-up` = reverse order. Budget **≥ 6 contiguous hours of world-up** before trusting any recommendation output, and do not world-down the night before the Day 10 soak.

Proposal §10 numbers verified and stand. Adjustments: min-replicas 1 during work sessions adds cents/day (still ~$0–3 total for Container Apps); GHCR instead of ACR keeps registry at $0; Postgres storage bills even while stopped and the server auto-restarts after 7 days — set the $25 budget alert on Day 1, not Day 13.

## Part 6 — Interview-prep additions

Beyond proposal §12's "what I'd change at scale" list, be ready for: (1) *"Why not Fabric?"* — Microsoft now also ships digital-twin capability inside Fabric (digital twin builder); ADT remains the standalone PaaS with the graph/DTDL/event-route model this project exercises — knowing the newer sibling exists and why you chose classic ADT for an event-driven demo is a strong answer. (2) *"Why is the correlation not hardcoded?"* — the AFFINITY map lives only in the simulator; walk them through Phase 7's lift computation and the precision/recall table. (3) *"What broke?"* — the self-trigger loop and the query-direction trap (silent empty results from case-sensitive names) are exactly the war stories interviewers want; you now get to have found them at design time.

## Resume bullets (corrected drafts)

- Designed and deployed an end-to-end computer-vision digital twin on Azure Digital Twins: DTDL-modeled multi-line factory, event routes through Event Grid to Python Azure Functions, current-state graph + Postgres history split per ADT's documented pattern, reproducible via Bicep + data-plane bootstrap from a single deploy script.
- Trained an ONNX-exported CNN (transfer learning) to [98–99]% test accuracy / [X] macro-F1 on 6-class steel surface-defect classification (NEU-CLS), with an automated PyTorch↔ONNX parity gate, served at [X] ms p95 warm latency via FastAPI/onnxruntime on Azure Container Apps.
- Built a statistical drift-attribution engine (per-parameter z-scores + count-gated defect-class lift) over ADT graph traversals, detecting [5/5] injected process drifts with [X] precision and correct root-cause parameter attribution, surfaced as explainable recommendations on the twin graph.

Numbers in brackets get filled from the Day-10 soak. Do not ship a bullet with a claim the repo can't back — that discipline is the whole point of the corrections above.
