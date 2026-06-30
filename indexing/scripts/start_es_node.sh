#!/bin/bash
# Called via: srun --ntasks=N --ntasks-per-node=1 start_es_node.sh
# Starts one Elasticsearch node per SLURM task.
#
# SLURM sets per-task:
#   SLURM_PROCID    - 0-based node index
#   SLURMD_NODENAME - hostname of this physical node
#
# Required env (set by start_es_cluster.sh before srun):
#   ES_BASE_DATA        - shared base path; node data → $ES_BASE_DATA/node-$SLURM_PROCID
#   ES_BASE_LOGS        - shared base path; node logs → $ES_BASE_LOGS/node-$SLURM_PROCID
#   ES_SEED_HOSTS       - transport addresses: "nodeA:9300,nodeB:9300,..."
#   ES_MASTER_NAME      - ES node.name eligible to bootstrap the cluster (es-node-0)
#   ES_PORT             - HTTP port (default: 9200)
#   ES_HEAP             - JVM heap flags (default: -Xms200g -Xmx200g)
#   CLUSTER_NAME        - ES cluster name (must be identical on all nodes)
#
# Optional env:
#   SNAPSHOT_REPO_PATH  - filesystem path registered as ES snapshot repository
#                         (default: /capstor/store/cscs/swissai/a145/es_indices_2026/snapshots)

set -euo pipefail

NODE_ID="${SLURM_PROCID:?}"
NODE_NAME="${SLURMD_NODENAME:?}"
DATA_PATH="${ES_BASE_DATA:?}/node-${NODE_ID}"
LOGS_PATH="${ES_BASE_LOGS:?}/node-${NODE_ID}"
PORT="${ES_PORT:-9200}"
HEAP="${ES_HEAP:--Xms200g -Xmx200g}"
CLUSTER="${CLUSTER_NAME:-fw-es-cluster}"
ES_NODE_NAME="es-node-${NODE_ID}"
SNAPSHOT_REPO_PATH="${SNAPSHOT_REPO_PATH:-/capstor/store/cscs/swissai/a145/es_indices_2026/snapshots}"

mkdir -p "$DATA_PATH" "$LOGS_PATH"
echo "[ES node-${NODE_ID}] hostname=${NODE_NAME}  data=${DATA_PATH}"

unset JAVA_HOME
export ES_JAVA_HOME="/usr/share/elasticsearch/jdk"

"$ES_JAVA_HOME/bin/java" -version 2>&1 | head -1 || { echo "[ES node-${NODE_ID}] ERROR: Java not found"; exit 1; }

ES_NUM_NODES="${ES_NUM_NODES:-1}"

if [[ "$ES_NUM_NODES" -eq 1 ]]; then
    DISCOVERY_ARGS=(
        -E "discovery.type=single-node"
        -E "network.host=0.0.0.0"
        -E "http.host=0.0.0.0"
    )
else
    DISCOVERY_ARGS=(
        -E "cluster.name=${CLUSTER}"
        -E "discovery.seed_hosts=${ES_SEED_HOSTS:?}"
        -E "cluster.initial_master_nodes=${ES_MASTER_NAME:?}"
        -E "network.bind_host=0.0.0.0"
        -E "network.publish_host=${NODE_NAME}"
        -E "http.host=${NODE_NAME}"
    )
fi

export ES_JAVA_OPTS="${HEAP} -XX:MaxGCPauseMillis=200"
exec /usr/share/elasticsearch/bin/elasticsearch \
    -E "node.name=${ES_NODE_NAME}" \
    -E "path.data=${DATA_PATH}" \
    -E "path.logs=${LOGS_PATH}" \
    -E "path.repo=${SNAPSHOT_REPO_PATH}" \
    -E "http.port=${PORT}" \
    -E "xpack.security.enabled=false" \
    -E "node.store.allow_mmap=false" \
    -E "cluster.routing.allocation.disk.watermark.low=85%" \
    -E "cluster.routing.allocation.disk.watermark.high=90%" \
    -E "cluster.routing.allocation.disk.watermark.flood_stage=95%" \
    -E "bootstrap.memory_lock=false" \
    -E "http.max_content_length=200mb" \
    -E "thread_pool.write.queue_size=2000" \
    -E "thread_pool.write.size=16" \
    -E "indices.memory.index_buffer_size=20%" \
    "${DISCOVERY_ARGS[@]}"
