#!/usr/bin/env bash
# Benchmark Graphiti entity extraction performance.

set -Eeuo pipefail

: "${NEO4J_PASSWORD:?Error: NEO4J_PASSWORD not set}"
export NEO4J_USERNAME=${NEO4J_USER:-neo4j}

neo4j_shell() {
    docker exec \
        -e NEO4J_USERNAME \
        -e NEO4J_PASSWORD \
        luminari-neo4j \
        cypher-shell --format plain "$@"
}

echo "🧪 Benchmarking Graphiti entity extraction..."
echo ""

provider=${1:-ollama}
echo "Provider: $provider"
echo ""

unprocessed=$(
    docker exec luminari-postgres \
        psql -U luminari -d luminari_sage -t -c \
        "SELECT COUNT(*) FROM episodes WHERE graphiti_synced = false AND length(text) > 50;"
)
unprocessed=${unprocessed//[[:space:]]/}

if [[ "$unprocessed" -eq 0 ]]; then
    echo "⚠️  No unprocessed episodes found. Resetting some episodes for benchmarking..."
    docker exec luminari-postgres psql -U luminari -d luminari_sage -c \
        "UPDATE episodes SET graphiti_synced = false WHERE id IN (
            SELECT id FROM episodes WHERE length(text) > 50 LIMIT 20
        );"
    unprocessed=20
fi

echo "📊 Episodes to process: $unprocessed"
echo ""

echo "📈 Baseline Neo4j stats:"
baseline_entities=$(
    neo4j_shell "MATCH (e:Entity) RETURN count(e) as count;" | tail -n 1
)
baseline_relationships=$(
    neo4j_shell "MATCH ()-[r]->() RETURN count(r) as count;" | tail -n 1
)

echo "  Entities: $baseline_entities"
echo "  Relationships: $baseline_relationships"
echo ""

echo "⏱️  Starting extraction..."
start_time=$(date +%s)

docker exec -e GRAPHITI_PROVIDER="$provider" luminari-api \
    python src/scripts/extract_entities.py

end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo "⏱️  Time elapsed: ${elapsed}s"
echo ""

speed=""
if [[ "$unprocessed" -gt 0 && "$elapsed" -gt 0 ]]; then
    speed=$(bc <<< "scale=2; $unprocessed / $elapsed")
    echo "📊 Processing speed: ${speed} episodes/second"
    echo ""
fi

echo "📈 Final Neo4j stats:"
final_entities=$(
    neo4j_shell "MATCH (e:Entity) RETURN count(e) as count;" | tail -n 1
)
final_relationships=$(
    neo4j_shell "MATCH ()-[r]->() RETURN count(r) as count;" | tail -n 1
)

echo "  Entities: $final_entities (+$((final_entities - baseline_entities)))"
echo "  Relationships: $final_relationships (+$((final_relationships - baseline_relationships)))"
echo ""

if [[ "$unprocessed" -gt 0 ]]; then
    average_entities=$(
        bc <<< "scale=1; ($final_entities - $baseline_entities) / $unprocessed"
    )
    average_relationships=$(
        bc <<< "scale=1; ($final_relationships - $baseline_relationships) / $unprocessed"
    )

    echo "📊 Averages per episode:"
    echo "  Entities: $average_entities"
    echo "  Relationships: $average_relationships"
    echo ""
fi

echo "📊 Relationship types created:"
neo4j_shell \
    "MATCH ()-[r]->()
     RETURN DISTINCT type(r) as rel_type, COUNT(r) as count
     ORDER BY count DESC
     LIMIT 10;"

echo ""
echo "✅ Benchmark complete!"
echo ""
echo "Summary:"
echo "  Time: ${elapsed}s"
echo "  Episodes: $unprocessed"
if [[ -n "$speed" ]]; then
    echo "  Speed: ${speed} episodes/second"
fi
echo "  Provider: $provider"
