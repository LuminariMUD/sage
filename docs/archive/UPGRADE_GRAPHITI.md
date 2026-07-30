# Upgrading Graphiti-Core for Rich Relationships

## What Changed
- Updated `requirements-core.txt` to pin graphiti-core to version **0.19.0rc3** (latest release candidate)
- Fixed tenacity dependency conflict (updated to >=9.0.0 to match graphiti-core requirements)
- This version supports custom edge types and entity types for rich relationship extraction

## Required Steps

### 1. Rebuild Docker Image
Since graphiti-core is installed during Docker build, you must rebuild the API container:

```bash
# Stop the current containers
GITHUB_REPOSITORY=luminarimud/sage GRAFANA_PASSWORD=test docker compose -f docker-compose.prod.yml down

# Rebuild the API container with new graphiti-core version
GITHUB_REPOSITORY=luminarimud/sage GRAFANA_PASSWORD=test docker compose -f docker-compose.prod.yml build api --no-cache

# Start the containers again
GITHUB_REPOSITORY=luminarimud/sage GRAFANA_PASSWORD=test docker compose -f docker-compose.prod.yml up -d
```

### 2. Reset Documents for Processing
Reset all documents to process them with rich relationship types:

```bash
GITHUB_REPOSITORY=luminarimud/sage GRAFANA_PASSWORD=test docker compose -f docker-compose.prod.yml exec postgres psql -U luminari -d luminari_sage -c "UPDATE lore_documents SET graphiti_status = 'pending', graphiti_processed_at = NULL;"
```

### 3. Run Entity Extraction
Process documents with rich relationship extraction:

```bash
GITHUB_REPOSITORY=luminarimud/sage GRAFANA_PASSWORD=test docker compose -f docker-compose.prod.yml exec api python3 scripts/extract_entities.py
```

## Expected Results

With graphiti-core 0.19.0rc3, you should get specific relationship types like:

- **OpposedTo** instead of RELATES_TO for divine conflicts
- **PatronOf** for deity-organization relationships  
- **AlliedWith** for cooperative relationships
- **SiblingOf** for divine family relationships
- **WorksWith** for collaboration
- And 35+ other specific relationship types

## Verification

Check what relationship types were extracted:

```cypher
MATCH ()-[r]->() 
RETURN DISTINCT type(r) as RelationshipType, COUNT(r) as Count 
ORDER BY Count DESC;
```

You should see many specific relationship types instead of just RELATES_TO and MENTIONS.

## Troubleshooting

If you still get "unexpected keyword argument 'edge_types'" errors:
1. Verify the Docker rebuild completed successfully
2. Check logs: `docker compose -f docker-compose.prod.yml logs api | grep graphiti`
3. Try the release candidate: Change to `graphiti-core==0.19.0rc3` in requirements
