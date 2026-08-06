# Correction System Documentation

**Version**: 0.7.9
**Status**: Production Ready  
**Last Updated**: 2025-11-12

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Correction Types](#correction-types)
5. [Correction Workflow](#correction-workflow)
6. [Rollback System](#rollback-system)
7. [Storage & Audit Trail](#storage--audit-trail)
8. [API Integration](#api-integration)
9. [Safety Mechanisms](#safety-mechanisms)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Luminari Sage correction system provides autonomous graph correction capabilities with complete rollback support. It safely modifies Neo4j relationships while maintaining comprehensive audit trails in PostgreSQL, enabling full recovery to any previous state.

### Key Features

- **Autonomous Corrections**: Agent-driven duplicate removal and semantic standardization
- **Complete Backup**: Every correction stores full relationship data before modification
- **Full Rollback**: Restore exact original state including embeddings
- **Batch Operations**: Group corrections for efficient processing and rollback
- **Audit Trail**: Complete history in PostgreSQL with confidence scores
- **Safety First**: Dry-run mode, confidence thresholds, and manual review gates
- **Never Touches MENTIONS**: Only modifies RELATES_TO relationships

### Design Philosophy

1. **Safety First**: Dry-run by default, explicit opt-in for actual changes
2. **Complete Backup**: Store everything needed for rollback
3. **Batch Tracking**: Group related corrections for atomic rollback
4. **High Confidence**: Only high-confidence corrections (≥0.85) by default
5. **GraphRAG Aware**: Never modify MENTIONS relationships (critical for retrieval)
6. **Reversible**: Every correction can be rolled back exactly

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Correction System                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐      ┌──────────────┐               │
│  │  Relationship    │      │  Correction  │               │
│  │   Validator      │─────▶│   Corrector  │               │
│  │  (finds issues)  │      │(applies fixes)│               │
│  └──────────────────┘      └──────┬───────┘               │
│                                    │                         │
│                                    ▼                         │
│                         ┌─────────────────────┐            │
│                         │   Backup & Store    │            │
│                         │   in PostgreSQL     │            │
│                         └─────────┬───────────┘            │
│                                   │                         │
│                                   ▼                         │
│                         ┌─────────────────────┐            │
│                         │   Apply to Neo4j    │            │
│                         │   (if not dry-run)  │            │
│                         └─────────────────────┘            │
│                                                              │
│  ┌──────────────────┐      ┌──────────────┐               │
│  │  Rollback        │      │  Correction  │               │
│  │   Manager        │◀─────│   Storage    │               │
│  │ (restore state)  │      │  (audit trail)│               │
│  └──────────────────┘      └──────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Validation Identifies Issues
   │
   ├─▶ Duplicate relationships
   ├─▶ Inconsistent semantic formatting
   └─▶ Other correctable problems
   │
2. Correction Analysis
   │
   ├─▶ Analyze duplicates (select best to keep)
   ├─▶ Analyze semantic standardization needs
   └─▶ Generate correction plan
   │
3. Backup Phase (if not dry-run)
   │
   ├─▶ Fetch complete relationship data from Neo4j
   ├─▶ Store in PostgreSQL with correction_id
   └─▶ Store all properties (including embeddings)
   │
4. Apply Phase (if not dry-run)
   │
   ├─▶ DELETE: Remove duplicate relationship
   ├─▶ UPDATE: Modify semantic type property
   └─▶ Record correction in batch
   │
5. Audit Trail
   │
   ├─▶ Link to validation report
   ├─▶ Store agent reasoning
   └─▶ Track confidence scores
   │
6. Rollback (if needed)
   │
   ├─▶ Retrieve backup data
   ├─▶ Restore original state in Neo4j
   └─▶ Mark correction as rolled back
```

---

## Components

### 1. RelationshipCorrector

**Location**: `src/agents/relationship_corrector.py`

**Purpose**: Autonomous agent for applying safe corrections to relationships.

**Agent ID**: `relationship_corrector_v1`

**Configuration**:

```python
async def apply_corrections(
    relationships: List[Dict],
    correct_duplicates: bool = True,
    standardize_semantics: bool = True,
    confidence_threshold: float = 0.85,
    max_corrections: int = 100,
    dry_run: bool = True
) -> List[CorrectionRecord]
```

**Capabilities**:

1. **Deduplication**: Remove duplicate RELATES_TO relationships
   - Selects best duplicate based on data completeness
   - Scores relationships by embeddings, properties, episodes
   - Deletes inferior duplicates
   - Confidence: 0.95

2. **Semantic Standardization**: Normalize semantic types to SCREAMING_SNAKE_CASE
   - Converts any format to consistent style
   - Updates `name` property in Neo4j
   - Preserves semantic meaning
   - Confidence: 0.90

**Business Rules**:

- **Never modifies MENTIONS**: Only works on RELATES_TO relationships
- **GraphRAG Safety**: MENTIONS are critical for document retrieval
- **Complete Backup**: Stores full relationship data before modification
- **Reversible**: All operations can be rolled back exactly

**Example Usage**:

```python
from src.agents.relationship_corrector import RelationshipCorrector

corrector = RelationshipCorrector(openai_api_key=os.getenv("OPENAI_API_KEY"))

# Dry-run mode (preview only)
corrections = await corrector.apply_corrections(
    relationships=relationships,
    correct_duplicates=True,
    standardize_semantics=True,
    confidence_threshold=0.85,
    max_corrections=100,
    dry_run=True  # No actual changes
)

print(f"Would apply {len(corrections)} corrections")

# Apply corrections (actual changes)
corrections = await corrector.apply_corrections(
    relationships=relationships,
    dry_run=False  # Make actual changes
)
```

### 2. CorrectionStorageService

**Location**: `src/agents/correction_storage.py`

**Purpose**: Manage PostgreSQL storage of corrections and audit trail.

**Key Methods**:

```python
class CorrectionStorageService:
    @staticmethod
    async def store_correction(
        correction_id: str,
        validation_report_id: Optional[str],
        correction_batch_id: str,
        correction_type: str,
        action: str,
        confidence_score: float,
        agent_reasoning: str,
        relationship_data: Dict[str, Any],
        ...
    ) -> bool
    
    @staticmethod
    async def get_correction(correction_id: str) -> Optional[Dict[str, Any]]
    
    @staticmethod
    async def get_corrections_for_batch(batch_id: str) -> List[Dict[str, Any]]
    
    @staticmethod
    async def rollback_correction(
        correction_id: str,
        rollback_by: str,
        rollback_reason: str
    ) -> bool
    
    @staticmethod
    async def rollback_batch(
        correction_batch_id: str,
        rollback_by: str,
        rollback_reason: str
    ) -> Dict[str, int]
    
    @staticmethod
    async def can_rollback_correction(correction_id: str) -> bool
```

**Database Schema**:

```sql
CREATE TABLE relationship_corrections (
    correction_id UUID PRIMARY KEY,
    validation_report_id UUID REFERENCES validation_reports(report_id),
    correction_batch_id UUID NOT NULL,
    
    -- Correction details
    correction_type VARCHAR(50) NOT NULL,  -- 'DEDUPLICATION' or 'SEMANTIC_STANDARDIZATION'
    action VARCHAR(20) NOT NULL,           -- 'DELETE' or 'UPDATE'
    confidence_score FLOAT NOT NULL,
    agent_reasoning TEXT NOT NULL,
    
    -- Relationship backup data
    relationship_id TEXT NOT NULL,         -- Neo4j element ID
    relationship_type VARCHAR(50) NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_node_name TEXT,
    target_node_name TEXT,
    source_node_labels TEXT[],
    target_node_labels TEXT[],
    original_properties JSONB NOT NULL,    -- Complete backup
    new_properties JSONB,                  -- For UPDATE actions
    
    -- Semantic standardization details
    original_semantic_type TEXT,
    new_semantic_type TEXT,
    
    -- Deduplication details
    duplicate_count INTEGER,
    
    -- Rollback tracking
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    rolled_back BOOLEAN DEFAULT FALSE,
    rollback_at TIMESTAMPTZ,
    rollback_by VARCHAR(100),
    rollback_reason TEXT,
    
    -- Additional metadata
    metadata JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX idx_corrections_batch_id ON relationship_corrections(correction_batch_id);
CREATE INDEX idx_corrections_report_id ON relationship_corrections(validation_report_id);
CREATE INDEX idx_corrections_rolled_back ON relationship_corrections(rolled_back);
CREATE INDEX idx_corrections_type ON relationship_corrections(correction_type);
```

### 3. RollbackManager

**Location**: `src/agents/rollback_manager.py`

**Purpose**: High-level interface for rolling back corrections.

**Key Methods**:

```python
class RollbackManager:
    @staticmethod
    async def rollback_correction(
        correction_id: str,
        rollback_by: str,
        rollback_reason: str = "Manual rollback requested"
    ) -> Dict[str, Any]
    
    @staticmethod
    async def rollback_batch(
        correction_batch_id: str,
        rollback_by: str,
        rollback_reason: str = "Batch rollback requested"
    ) -> Dict[str, Any]
    
    @staticmethod
    async def preview_rollback_batch(
        correction_batch_id: str
    ) -> Dict[str, Any]
    
    @staticmethod
    async def get_rollback_statistics(days: int = 30) -> Dict[str, Any]
```

**Rollback Process**:

1. **Validate**: Check if correction can be rolled back
2. **Retrieve**: Get backup data from PostgreSQL
3. **Restore**: Apply inverse operation to Neo4j
   - DELETE → Recreate relationship with all properties
   - UPDATE → Restore original property values
4. **Mark**: Update correction record as rolled back
5. **Audit**: Log rollback action with timestamp, user, reason

---

## Correction Types

### 1. Deduplication

**Purpose**: Remove duplicate RELATES_TO relationships between the same entities.

**Detection Criteria**:
- Same source node
- Same target node  
- Same semantic type (case-insensitive)

**Selection Algorithm**:

Scores each duplicate relationship based on:

```python
def score_relationship(rel: Dict) -> int:
    score = 0
    
    # Has embeddings (most important)
    if "fact_embedding" in props: score += 100
    if "name_embedding" in props: score += 100
    
    # Has semantic type
    if "name" in props and props["name"]: score += 50
    
    # Has fact content
    if "fact" in props and props["fact"]: score += 30
    
    # Has episodes list
    episode_count = len(props.get("episodes", []))
    score += min(episode_count * 5, 50)  # Cap at 50
    
    # Has creation timestamp
    if "created_at" in props: score += 10
    
    # Total property count
    score += len(props)
    
    return score
```

**Keeps**: Highest-scoring relationship (most complete data)  
**Deletes**: All lower-scoring duplicates

**Example**:

```python
# Before correction
Paladine --allied_with--> Kiri-Jolith (ID: rel1, score: 150)
Paladine --allied_with--> Kiri-Jolith (ID: rel2, score: 75)
Paladine --allied_with--> Kiri-Jolith (ID: rel3, score: 100)

# After correction
Paladine --allied_with--> Kiri-Jolith (ID: rel1, kept)
# rel2 and rel3 deleted with full backup
```

**Correction Record**:

```python
CorrectionRecord(
    correction_id="uuid",
    correction_type="DEDUPLICATION",
    relationship_id="rel2",  # The one deleted
    action="DELETE",
    confidence_score=0.95,
    reasoning="Duplicate relationship removed. Kept the more complete version (ID: rel1)",
    duplicate_count=3,
    metadata={"backup_data": {...}}  # Full relationship data
)
```

### 2. Semantic Standardization

**Purpose**: Normalize semantic type formatting to SCREAMING_SNAKE_CASE.

**Standardization Rules**:

1. Replace spaces, hyphens, dots with underscores
2. Remove special characters (except underscores)
3. Convert to uppercase
4. Remove multiple consecutive underscores
5. Strip leading/trailing underscores

**Examples**:

```python
# Before → After
"allied with"       → "ALLIED_WITH"
"Allied-With"       → "ALLIED_WITH"
"allied.with"       → "ALLIED_WITH"
"ALLIED_WITH"       → "ALLIED_WITH"  (no change)
"opposed to"        → "OPPOSED_TO"
"commands"          → "COMMANDS"
"serves under"      → "SERVES_UNDER"
```

**Why Standardize?**:

- Consistent format for GraphRAG queries
- Easier pattern matching
- Cleaner visualization
- Better LLM understanding

**Note**: The LLM can understand any format, but standardization improves consistency and debugging.

**Correction Record**:

```python
CorrectionRecord(
    correction_id="uuid",
    correction_type="SEMANTIC_STANDARDIZATION",
    relationship_id="rel_id",
    action="UPDATE",
    confidence_score=0.90,
    reasoning="Standardized semantic type from 'allied with' to 'ALLIED_WITH'",
    original_semantic_type="allied with",
    new_semantic_type="ALLIED_WITH",
    metadata={"backup_data": {...}}
)
```

---

## Correction Workflow

### Integrated Validation + Correction

The most common workflow integrates validation with optional autonomous correction:

```python
from src.agents.relationship_validator import RelationshipValidator

validator = RelationshipValidator(openai_api_key=os.getenv("OPENAI_API_KEY"))

# Validation with autonomous correction
report = await validator.validate(
    entity_limit=1000,
    relationship_limit=5000,
    
    # Standard validation checks
    check_bidirectional=True,
    check_mutual_exclusivity=True,
    check_hierarchies=True,
    check_semantic_consistency=True,
    enable_llm_analysis=True,
    
    # Autonomous correction parameters
    auto_correct=True,               # Enable corrections
    correct_duplicates=True,         # Remove duplicates
    standardize_semantics=True,      # Standardize formats
    confidence_threshold=0.85,       # High confidence only
    max_corrections=100,             # Limit corrections
    dry_run=False                    # Actually apply changes
)

# Review correction results
print(f"Corrections applied: {report.metadata['corrections_applied']}")
print(f"Duplicates removed: {report.metadata['duplicates_removed']}")
print(f"Semantics standardized: {report.metadata['semantics_standardized']}")
print(f"Batch ID: {report.metadata['correction_batch_id']}")
```

### Standalone Correction

You can also run corrections independently:

```python
from src.agents.relationship_corrector import RelationshipCorrector
from src.db import get_neo4j_db

# Fetch relationships
neo4j_db = await get_neo4j_db()
result = await neo4j_db.execute_query("""
    MATCH (a)-[r:RELATES_TO]->(b)
    RETURN elementId(r) as id, type(r) as type, properties(r) as props,
           elementId(a) as source_id, elementId(b) as target_id,
           a.name as source_name, b.name as target_name
    LIMIT 5000
""")

# Apply corrections
corrector = RelationshipCorrector(openai_api_key=os.getenv("OPENAI_API_KEY"))

corrections = await corrector.apply_corrections(
    relationships=result,
    correct_duplicates=True,
    standardize_semantics=True,
    dry_run=False
)

print(f"Applied {len(corrections)} corrections")
```

### API Workflow

**Step 1: Run validation with corrections**

```bash
curl -X POST https://luminarimud.com/sage/api/v1/validate/relationships \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "entity_limit": 1000,
    "relationship_limit": 5000,
    "check_bidirectional": true,
    "check_mutual_exclusivity": true,
    "check_hierarchies": true,
    "check_semantic_consistency": true,
    "enable_llm_analysis": true,
    "auto_correct": true,
    "correct_duplicates": true,
    "standardize_semantics": true,
    "confidence_threshold": 0.85,
    "max_corrections": 100,
    "dry_run": false
  }'
```

**Response**:

```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_items_checked": 2500,
  "findings_count": 42,
  "execution_time_seconds": 45.2,
  "metadata": {
    "auto_correction_enabled": true,
    "corrections_applied": 23,
    "correction_batch_id": "batch-uuid",
    "duplicates_removed": 15,
    "semantics_standardized": 8,
    "dry_run": false
  }
}
```

**Step 2: Get correction details**

```bash
curl https://luminarimud.com/sage/api/v1/corrections/history?limit=50 \
  -H "X-API-Key: YOUR_API_KEY"
```

**Step 3: Preview rollback (if needed)**

```bash
curl https://luminarimud.com/sage/api/v1/corrections/batch/{batch_id}/preview \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Rollback System

### Single Correction Rollback

Roll back a specific correction to restore the original state.

**API Example**:

```bash
curl -X POST https://luminarimud.com/sage/api/v1/corrections/{correction_id}/rollback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "rollback_by": "admin",
    "rollback_reason": "Incorrect duplicate selection"
  }'
```

**Response**:

```json
{
  "success": true,
  "message": "Correction rolled back successfully",
  "rollback_by": "admin",
  "rollback_reason": "Incorrect duplicate selection",
  "rollback_timestamp": "2025-11-12T14:30:00Z"
}
```

**What Happens**:

1. Retrieves correction record from PostgreSQL
2. Checks if already rolled back
3. Applies inverse operation:
   - **DELETE** → Recreates relationship with all original properties
   - **UPDATE** → Restores original property values
4. Marks correction as rolled back in PostgreSQL
5. Logs rollback action with user and reason

### Batch Rollback

Roll back all corrections in a batch atomically.

**API Example**:

```bash
curl -X POST https://luminarimud.com/sage/api/v1/corrections/batch/{batch_id}/rollback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "rollback_by": "admin",
    "rollback_reason": "Validation run contained errors"
  }'
```

**Response**:

```json
{
  "success": true,
  "message": "Batch rollback completed",
  "rollback_by": "admin",
  "rollback_reason": "Validation run contained errors",
  "rollback_timestamp": "2025-11-12T14:35:00Z",
  "statistics": {
    "total": 23,
    "successful": 23,
    "failed": 0,
    "already_rolled_back": 0
  }
}
```

**Processing Order**: Most recent corrections first (reverse order) to handle dependencies.

### Rollback Preview

Preview what would be rolled back without making changes.

**API Example**:

```bash
curl https://luminarimud.com/sage/api/v1/corrections/batch/{batch_id}/preview \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response**:

```json
{
  "success": true,
  "batch_id": "batch-uuid",
  "total_corrections": 23,
  "corrections": [
    {
      "correction_id": "uuid1",
      "correction_type": "DEDUPLICATION",
      "action": "DELETE",
      "relationship_id": "4:abc:123",
      "source_name": "Paladine",
      "target_name": "Kiri-Jolith",
      "original_semantic_type": "allied_with",
      "rolled_back": false,
      "can_rollback": true
    },
    {
      "correction_id": "uuid2",
      "correction_type": "SEMANTIC_STANDARDIZATION",
      "action": "UPDATE",
      "relationship_id": "4:def:456",
      "source_name": "Astinus",
      "target_name": "Gilean",
      "original_semantic_type": "serves under",
      "new_semantic_type": "SERVES_UNDER",
      "rolled_back": false,
      "can_rollback": true
    }
  ]
}
```

### Rollback Statistics

Get correction and rollback statistics for monitoring.

**API Example**:

```bash
curl "https://luminarimud.com/sage/api/v1/corrections/stats?days=30" \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response**:

```json
{
  "period_days": 30,
  "total_corrections": 156,
  "corrections_by_type": {
    "DEDUPLICATION": 98,
    "SEMANTIC_STANDARDIZATION": 58
  },
  "total_rollbacks": 12,
  "rollback_rate": 0.077,
  "corrections_by_day": [...],
  "average_confidence_score": 0.92
}
```

---

## Storage & Audit Trail

### Complete Relationship Backup

Every correction stores complete relationship data:

```python
{
    "id": "4:abc:123",
    "type": "RELATES_TO",
    "source_id": "4:xyz:789",
    "target_id": "4:uvw:456",
    "source_name": "Paladine",
    "target_name": "Kiri-Jolith",
    "source_labels": ["Entity"],
    "target_labels": ["Entity"],
    "properties": {
        "name": "allied_with",
        "fact": "Paladine is allied with Kiri-Jolith",
        "fact_embedding": [...],  # Full embedding vector
        "name_embedding": [...],  # Full embedding vector
        "episodes": ["episode1", "episode2"],
        "created_at": "2025-01-15T10:00:00Z",
        "source_type": "PERSON",
        "target_type": "PERSON"
        # ... all other properties
    }
}
```

### Audit Trail Queries

**Get all corrections for a validation report**:

```sql
SELECT * FROM relationship_corrections
WHERE validation_report_id = $1
ORDER BY applied_at ASC;
```

**Get unrolled corrections by type**:

```sql
SELECT 
    correction_type,
    COUNT(*) as count,
    AVG(confidence_score) as avg_confidence
FROM relationship_corrections
WHERE rolled_back = false
GROUP BY correction_type;
```

**Get recent rollbacks**:

```sql
SELECT 
    correction_id,
    correction_type,
    rollback_by,
    rollback_reason,
    rollback_at
FROM relationship_corrections
WHERE rolled_back = true
ORDER BY rollback_at DESC
LIMIT 50;
```

**Find corrections that affected specific entities**:

```sql
SELECT * FROM relationship_corrections
WHERE source_node_name = 'Paladine'
   OR target_node_name = 'Paladine'
ORDER BY applied_at DESC;
```

---

## API Integration

### Correction Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/validate/relationships` | POST | Run validation with optional corrections |
| `/api/v1/corrections/{correction_id}/rollback` | POST | Rollback single correction |
| `/api/v1/corrections/batch/{batch_id}/rollback` | POST | Rollback entire batch |
| `/api/v1/corrections/batch/{batch_id}/preview` | GET | Preview batch rollback |
| `/api/v1/corrections/history` | GET | Get correction history |
| `/api/v1/corrections/stats` | GET | Get correction statistics |
| `/api/v1/corrections/{correction_id}` | GET | Get specific correction |
| `/api/v1/corrections/batch/{batch_id}/summary` | GET | Get batch summary |

See [API_REFERENCE.md](API_REFERENCE.md) for complete API documentation.

---

## Safety Mechanisms

### 1. Dry-Run Mode

**Default**: `dry_run=True` (safe mode)

```python
# Preview corrections without applying
corrections = await corrector.apply_corrections(
    relationships=relationships,
    dry_run=True  # No changes to Neo4j
)

# Review the preview
for correction in corrections:
    print(f"{correction.correction_type}: {correction.reasoning}")

# Apply if satisfied
corrections = await corrector.apply_corrections(
    relationships=relationships,
    dry_run=False  # Actually apply
)
```

### 2. Confidence Threshold

Only apply corrections meeting minimum confidence:

```python
corrections = await corrector.apply_corrections(
    relationships=relationships,
    confidence_threshold=0.85,  # High confidence only
    dry_run=False
)
```

**Default Confidence Scores**:
- Deduplication: 0.95 (very high confidence)
- Semantic Standardization: 0.90 (high confidence)

### 3. Max Corrections Limit

Prevent runaway corrections:

```python
corrections = await corrector.apply_corrections(
    relationships=relationships,
    max_corrections=100,  # Stop after 100 corrections
    dry_run=False
)
```

### 4. MENTIONS Protection

**Critical Safety**: MENTIONS relationships are NEVER modified.

```python
# In RelationshipCorrector
for rel in relationships:
    if rel["type"] != "RELATES_TO":
        continue  # Skip MENTIONS completely
```

**Why?**: MENTIONS relationships are critical for GraphRAG document retrieval. Modifying them could break the hybrid RAG system.

### 5. Complete Backup Before Modification

Every correction backs up complete relationship data BEFORE modification:

```python
# 1. Backup
backup_data = await self.get_relationship_full_data(neo4j_db, relationship_id)

# 2. Modify
await neo4j_db.execute_query(delete_query, {"id": relationship_id})

# 3. Store backup with correction
correction.metadata = {"backup_data": backup_data}
```

### 6. Batch Tracking

All corrections in a validation run share a `correction_batch_id`:

- Enables atomic rollback of entire batch
- Groups related corrections
- Simplifies audit trail

---

## Best Practices

### 1. Always Start with Dry-Run

```python
# 1. Preview corrections
report = await validator.validate(
    auto_correct=True,
    dry_run=True  # Preview only
)

# 2. Review results
print(f"Would apply {report.metadata['corrections_applied']} corrections")

# 3. Apply if satisfied
report = await validator.validate(
    auto_correct=True,
    dry_run=False  # Actually apply
)
```

### 2. Use Preview Before Batch Rollback

```bash
# 1. Preview what would be rolled back
curl https://luminarimud.com/sage/api/v1/corrections/batch/{batch_id}/preview \
  -H "X-API-Key: YOUR_API_KEY"

# 2. Review the preview

# 3. Rollback if confirmed
curl -X POST https://luminarimud.com/sage/api/v1/corrections/batch/{batch_id}/rollback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"rollback_by": "admin", "rollback_reason": "Confirmed with preview"}'
```

### 3. Monitor Correction Statistics

Regularly check correction statistics to identify patterns:

```bash
curl "https://luminarimud.com/sage/api/v1/corrections/stats?days=30" \
  -H "X-API-Key: YOUR_API_KEY"
```

High rollback rates may indicate:
- Incorrect duplicate selection logic
- Too aggressive semantic standardization
- Confidence threshold too low

### 4. Incremental Corrections

For large graphs, apply corrections in batches:

```python
# Process 1000 relationships at a time
batch_size = 1000
for offset in range(0, total_relationships, batch_size):
    # Fetch batch
    relationships = await fetch_relationships(offset, batch_size)
    
    # Apply corrections with limit
    corrections = await corrector.apply_corrections(
        relationships=relationships,
        max_corrections=50,  # Limit per batch
        dry_run=False
    )
    
    # Review each batch before continuing
    print(f"Batch {offset//batch_size}: {len(corrections)} corrections")
```

### 5. Document Rollback Reasons

Always provide clear rollback reasons for audit trail:

```python
await RollbackManager.rollback_correction(
    correction_id=correction_id,
    rollback_by="admin",
    rollback_reason="Duplicate selection logic incorrectly prioritized older relationships. "
                   "The newer relationship had better semantic context."
)
```

---

## Troubleshooting

### Common Issues

#### 1. Correction Fails to Apply

**Symptom**: Corrections return empty or fail to apply

**Possible Causes**:
- `dry_run=True` (preview mode)
- Confidence threshold too high
- No correctable issues found
- Neo4j connection issues

**Debug**:

```python
# Check dry-run mode
print(f"Dry run: {dry_run}")

# Check confidence threshold
print(f"Confidence threshold: {confidence_threshold}")

# Check what was analyzed
duplicates = await corrector.analyze_duplicates(relationships)
print(f"Found {len(duplicates)} duplicate groups")

standardizations = await corrector.analyze_semantic_standardization(relationships)
print(f"Found {len(standardizations)} standardization needs")
```

#### 2. Rollback Fails

**Symptom**: Rollback returns error or fails

**Possible Causes**:
- Correction already rolled back
- Correction not found
- Neo4j nodes no longer exist
- Insufficient permissions

**Debug**:

```python
# Check if can rollback
can_rollback = await CorrectionStorageService.can_rollback_correction(correction_id)
print(f"Can rollback: {can_rollback}")

# Get correction details
correction = await CorrectionStorageService.get_correction(correction_id)
print(f"Correction: {correction}")
print(f"Already rolled back: {correction.get('rolled_back')}")
```

#### 3. Embeddings Lost After Correction

**Symptom**: Relationship embeddings missing after correction/rollback

**Cause**: Backup or restore didn't include embedding vectors

**Solution**: The system stores embeddings in backup data. Check storage:

```python
correction = await CorrectionStorageService.get_correction(correction_id)
original_props = json.loads(correction["original_properties"])
print(f"Has fact_embedding: {'fact_embedding' in original_props}")
print(f"Has name_embedding: {'name_embedding' in original_props}")
```

If embeddings are in backup but not restored, check Neo4j restore logic.

#### 4. Duplicate Selection Wrong

**Symptom**: Corrector kept the wrong duplicate

**Cause**: Scoring algorithm may not match your data quality criteria

**Solution**: Adjust scoring weights in `select_best_duplicate()`:

```python
# In RelationshipCorrector.select_best_duplicate()
def score_relationship(rel: Dict) -> int:
    score = 0
    props = rel.get("props", {})
    
    # Increase embedding importance
    if "fact_embedding" in props: score += 200  # Was 100
    if "name_embedding" in props: score += 200  # Was 100
    
    # Adjust other weights...
```

Or manually rollback and keep the preferred duplicate.

---

## Related Documentation

- [VALIDATION_SYSTEM.md](VALIDATION_SYSTEM.md) - Validation architecture
- [API_REFERENCE.md](API_REFERENCE.md) - API endpoint details
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Developer integration
- [AGENT_SYSTEM.md](AGENT_SYSTEM.md) - Complete agent system

---

**Last Updated**: 2025-11-12  
**Version**: 0.7.9
**Status**: Production Ready
