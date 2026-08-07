#!/usr/bin/env bash
# Refuse the legacy benchmark that rewrote synchronization state and wrote Neo4j.

set -Eeuo pipefail

echo "The legacy state-mutating benchmark is disabled." >&2
echo "Use: make benchmark-graphiti CONFIRM_GRAPHITI_BENCHMARK=RUN_GRAPHITI_BENCHMARK" >&2
exit 2
