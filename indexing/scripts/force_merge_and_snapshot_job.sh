#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=a145
#SBATCH --time=11:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --job-name=merge-snapshot

# Runs after ES cluster restarts:
#   1. Wait for cluster to be healthy
#   2. Delete any partial snapshot
#   3. Force merge to 1 segment per shard
#   4. Start a new snapshot (incremental — reuses already-uploaded segment files)

set -euo pipefail

SCRATCH="/iopsstor/scratch/cscs/${USER}"
VENV="${SCRATCH}/indexer-venv/bin/python3"
INFO_FILE="${SCRATCH}/es-cluster-${INDEX_NAME}.info"
REPO_NAME="capstor-a145"
SNAPSHOT_NAME="snapshot-$(date +%Y%m%d-%H%M%S)"

# ── Wait for cluster ──────────────────────────────────────────────────────────
echo "[merge-snapshot] Waiting for ES cluster info file ..."
for i in $(seq 1 120); do
    [[ -f "$INFO_FILE" ]] && break
    sleep 10
done
[[ -f "$INFO_FILE" ]] || { echo "ERROR: cluster info file never appeared"; exit 1; }

ES_HOST=$(grep ^ES_HOST "$INFO_FILE" | cut -d= -f2)
ES_PORT=$(grep ^ES_PORT "$INFO_FILE" | cut -d= -f2)
ES_BASE="http://${ES_HOST}:${ES_PORT}"

echo "[merge-snapshot] ES: ${ES_BASE}  index=${INDEX_NAME}"
echo "[merge-snapshot] Waiting for green/yellow health ..."
for i in $(seq 1 60); do
    STATUS=$(curl -sf "${ES_BASE}/_cluster/health?timeout=5s" 2>/dev/null \
             | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','red'))" 2>/dev/null || echo red)
    [[ "$STATUS" != "red" ]] && { echo "[merge-snapshot] Cluster ${STATUS}"; break; }
    sleep 10
done

# ── Delete partial snapshot if present ───────────────────────────────────────
echo ""
echo "[merge-snapshot] Checking for partial snapshots ..."
"$VENV" - <<PYEOF
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

base = "${ES_BASE}"
repo = "${REPO_NAME}"

data = json.load(urlopen(f"{base}/_snapshot/{repo}/_all"))
for s in data.get("snapshots", []):
    name = s["snapshot"]
    state = s["state"]
    if state in ("PARTIAL", "FAILED", "IN_PROGRESS"):
        print(f"  Deleting {state} snapshot: {name}")
        req = Request(f"{base}/_snapshot/{repo}/{name}", method="DELETE")
        try:
            urlopen(req)
            print(f"  Deleted: {name}")
        except HTTPError as e:
            print(f"  Warning: {e}")
    else:
        print(f"  Keeping {state} snapshot: {name}")
PYEOF

# ── Force merge ───────────────────────────────────────────────────────────────
echo ""
echo "[merge-snapshot] Starting force merge to 1 segment per shard ..."

# Bump merge threads for speed
curl -sf -X PUT "${ES_BASE}/${INDEX_NAME}/_settings" \
    -H "Content-Type: application/json" \
    -d '{"index.merge.scheduler.max_thread_count": 8}' \
    | python3 -c "import json,sys; print('merge threads set:', json.load(sys.stdin))"

# Submit async, poll segment count until it reaches ~850 (1 per shard)
"$VENV" - <<PYEOF
import json, time
from urllib.request import urlopen, Request
from urllib.error import URLError

base = "${ES_BASE}"
index = "${INDEX_NAME}"

# Fire and forget — force merge is async at the HTTP level anyway for large indices
req = Request(f"{base}/{index}/_forcemerge?max_num_segments=5", method="POST")
req.add_header("Content-Type", "application/json")
try:
    urlopen(req, timeout=30)
except Exception:
    pass  # expected to time out on HTTP; merge continues on ES side

print("Force merge submitted. Polling segment counts ...", flush=True)
start = time.time()
prev_segs = None

while True:
    try:
        d = json.load(urlopen(f"{base}/{index}/_stats/segments", timeout=30))
        segs = d["_all"]["primaries"]["segments"]["count"]
        size_gb = d["_all"]["primaries"]["segments"]["memory_in_bytes"] / 1e9

        # Check active merges via _cat/thread_pool
        tp = urlopen(f"{base}/_cat/thread_pool/merge?h=active,queue&format=json", timeout=10).read()
        tp_data = json.loads(tp)
        active_merges = sum(int(n.get("active", 0)) for n in tp_data)
        queued_merges = sum(int(n.get("queue", 0)) for n in tp_data)

        elapsed = int(time.time() - start)
        print(
            f"  [{elapsed//3600:02d}h{(elapsed%3600)//60:02d}m] "
            f"segments: {segs:,}  merge_active/queued: {active_merges}/{queued_merges}",
            flush=True,
        )

        # Done when segments ≈ number of primary shards and no active merges
        if segs <= 1000 and active_merges == 0 and queued_merges == 0 and prev_segs == segs:
            print(f"Force merge complete: {segs} segments remaining", flush=True)
            break
        prev_segs = segs
    except Exception as e:
        print(f"  (poll error: {e})", flush=True)

    time.sleep(60)
PYEOF

echo "[merge-snapshot] Force merge done at $(date)"
sleep 10

# ── New snapshot ──────────────────────────────────────────────────────────────
echo ""
echo "[merge-snapshot] Starting snapshot: ${SNAPSHOT_NAME}"
"$VENV" - <<PYEOF
import json, time
from urllib.request import urlopen, Request

base = "${ES_BASE}"
repo = "${REPO_NAME}"
snap = "${SNAPSHOT_NAME}"
index = "${INDEX_NAME}"

# Start snapshot
req = Request(
    f"{base}/_snapshot/{repo}/{snap}?wait_for_completion=false",
    data=json.dumps({"indices": index, "include_global_state": False}).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
resp = json.load(urlopen(req))
print(f"Snapshot started: {resp}")

# Poll
while True:
    d = json.load(urlopen(f"{base}/_snapshot/{repo}/{snap}"))
    s = d["snapshots"][0]
    state = s["state"]
    shards = s.get("shards", {})
    done = shards.get("successful", 0)
    total = shards.get("total", 0)
    failed = shards.get("failed", 0)
    print(f"  [{time.strftime('%H:%M:%S')}] {state}  shards: {done}/{total}  in-progress: {failed}", flush=True)
    if state in ("SUCCESS", "FAILED", "PARTIAL"):
        print(f"Snapshot finished: {state}")
        break
    time.sleep(60)
PYEOF

echo ""
echo "[merge-snapshot] Done at $(date)"
