# Validation System Documentation

**Version**: 0.7.0  
**Status**: Production Ready  
**Last Updated**: 2025-11-12

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Validation Rules](#validation-rules)
5. [Validation Workflow](#validation-workflow)
6. [Confidence Scoring](#confidence-scoring)
7. [Storage & Audit Trail](#storage--audit-trail)
8. [API Integration](#api-integration)
9. [LLM-Enhanced Analysis](#llm-enhanced-analysis)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Luminari Sage validation system is a comprehensive framework for analyzing and validating knowledge graph relationships. It combines rule-based validation with LLM-enhanced semantic analysis to identify inconsistencies, missing relationships, and logical contradictions in the Neo4j graph database.

### Key Features

- **Multi-Layer Validation**: Rule-based checks + LLM semantic analysis
- **Comprehensive Audit Trail**: Complete finding history with confidence scores
- **Human Review Workflow**: Mark findings as reviewed with actions
- **Non-Destructive**: Validation never modifies data automatically
- **Production Ready**: Full PostgreSQL storage with rollback capability
- **GraphRAG Optimized**: Focuses on relationship semantics for hybrid RAG

### Design Philosophy

1. **Never Auto-Modify**: All validations produce findings for human review
2. **Confidence-Based**: Every finding includes confidence score and explanation
3. **Complete Audit Trail**: All findings stored in PostgreSQL for tracking
4. **LLM-Enhanced**: Uses GPT-4o-mini for semantic understanding
5. **GraphRAG-Aware**: Optimizes for hybrid vector + graph retrieval

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Validation System                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────┐      ┌──────────────┐      ┌─────────┐ │
│  │   Rule-Based  │      │     LLM      │      │  Human  │ │
│  │  Validators   │─────▶│   Enhanced   │─────▶│ Review  │ │
│  │   (5 types)   │      │   Analysis   │      │Workflow │ │
│  └───────────────┘      └──────────────┘      └─────────┘ │
│         │                      │                     │      │
│         └──────────────────────┴─────────────────────┘      │
│                            │                                 │
│                            ▼                                 │
│                ┌────────────────────────┐                   │
│                │  ValidationReport      │                   │
│                │  - Findings            │                   │
│                │  - Confidence Scores   │                   │
│                │  - Evidence            │                   │
│                │  - Suggested Actions   │                   │
│                └────────────────────────┘                   │
│                            │                                 │
│                            ▼                                 │
│                ┌────────────────────────┐                   │
│                │  PostgreSQL Storage    │                   │
│                │  - validation_reports  │                   │
│                │  - validation_findings │                   │
│                └────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Neo4j Graph Data
   │
   ├─▶ Fetch entities & relationships
   │   (filtered by entity_limit/relationship_limit)
   │
2. Rule-Based Validation
   │
   ├─▶ Check Bidirectional Consistency
   ├─▶ Check Mutual Exclusivity
   ├─▶ Check Hierarchical Consistency
   ├─▶ Check Semantic Consistency
   ├─▶ Check for Orphaned Entities
   └─▶ Check for Duplicate Relationships
   │
3. LLM-Enhanced Analysis (optional)
   │
   ├─▶ Semantic Appropriateness Analysis
   ├─▶ RELATES_TO Semantic Clarity
   └─▶ MENTIONS Classification Optimization
   │
4. ValidationReport Generation
   │
   ├─▶ Consolidate findings
   ├─▶ Calculate statistics
   └─▶ Generate markdown report
   │
5. Storage & Review
   │
   ├─▶ Store in PostgreSQL
   └─▶ Enable human review workflow
```

---

## Components

### 1. BaseValidator

**Location**: `src/agents/base_validator.py`

**Purpose**: Foundation class for all validation agents with audit trail capabilities.

**Key Classes**:

```python
class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class ValidationFinding(BaseModel):
    finding_id: str
    agent_id: str
    timestamp: datetime
    severity: ValidationSeverity
    category: str
    title: str
    description: str
    evidence: List[str]
    affected_entities: List[str]
    affected_relationships: List[str]
    confidence_score: float
    confidence_explanation: str
    suggested_action: str
    priority: int
    reviewed: bool
    reviewer: Optional[str]
    review_timestamp: Optional[datetime]
    review_action: Optional[str]
    review_notes: Optional[str]
    metadata: Dict[str, Any]

class ValidationReport(BaseModel):
    report_id: str
    agent_id: str
    validation_type: str
    timestamp: datetime
    scope_description: str
    total_items_checked: int
    findings: List[ValidationFinding]
    execution_time_seconds: float
    success: bool
    error_message: Optional[str]
    metadata: Optional[Dict[str, Any]]
```

**System Prompt Pattern**:

```python
def _get_system_prompt(self) -> str:
    return f"""You are a validation agent for the Luminari Sage knowledge graph system.

AGENT IDENTIFICATION: {self.agent_id}

CRITICAL REQUIREMENTS:
1. Every finding MUST include your agent ID
2. Every finding MUST include a confidence score (0.0-1.0) with explanation
3. Every finding MUST be labeled for human review
4. You CANNOT make automatic changes - only suggest actions
5. Provide specific evidence for all findings
6. Be thorough but not overly verbose

CONFIDENCE SCORING GUIDELINES:
- 0.9-1.0: Very high confidence (clear logical contradiction)
- 0.7-0.8: High confidence (strong pattern match)
- 0.5-0.6: Medium confidence (possible issue)
- 0.3-0.4: Low confidence (speculation)
- 0.1-0.2: Very low confidence (weak signals)

Focus on actionable findings that improve data quality."""
```

### 2. RelationshipValidator

**Location**: `src/agents/relationship_validator.py`

**Purpose**: Validates entity relationships in the Neo4j graph, focusing on RELATES_TO and MENTIONS edges.

**Agent ID**: `relationship_validator_v1_llm`

**Capabilities**:
- Bidirectional consistency checking
- Mutual exclusivity validation
- Hierarchical relationship verification
- Semantic property consistency
- Orphaned entity detection
- Duplicate relationship detection
- LLM-enhanced semantic analysis

**Configuration**:

```python
async def validate(
    entity_limit: int = 1000,
    relationship_limit: int = 5000,
    check_bidirectional: bool = True,
    check_mutual_exclusivity: bool = True,
    check_hierarchies: bool = True,
    check_semantic_consistency: bool = True,
    enable_llm_analysis: bool = True
) -> ValidationReport
```

### 3. ValidationStorageService

**Location**: `src/agents/validation_storage.py`

**Purpose**: Manages PostgreSQL storage of validation reports and findings.

**Key Methods**:

```python
class ValidationStorageService:
    @staticmethod
    async def store_report(report: ValidationReport) -> bool
    
    @staticmethod
    async def get_report(report_id: str) -> Optional[ValidationReport]
    
    @staticmethod
    async def list_reports(limit: int = 50) -> List[Dict[str, Any]]
    
    @staticmethod
    async def get_findings_for_report(report_id: str) -> List[ValidationFinding]
    
    @staticmethod
    async def get_unreviewed_findings(
        severity: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[ValidationFinding]
    
    @staticmethod
    async def mark_finding_reviewed(
        finding_id: str,
        reviewer: str,
        action: str,
        notes: str = ""
    ) -> bool
```

**Database Schema**:

```sql
CREATE TABLE validation_reports (
    report_id UUID PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    validation_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    scope_description TEXT,
    total_items_checked INTEGER,
    execution_time_seconds FLOAT,
    success BOOLEAN,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE validation_findings (
    finding_id UUID PRIMARY KEY,
    report_id UUID REFERENCES validation_reports(report_id),
    agent_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    severity VARCHAR(20) NOT NULL,
    category VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence TEXT[],
    affected_entities TEXT[],
    affected_relationships TEXT[],
    confidence_score FLOAT NOT NULL,
    confidence_explanation TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    priority INTEGER NOT NULL,
    reviewed BOOLEAN DEFAULT FALSE,
    reviewer VARCHAR(100),
    review_timestamp TIMESTAMPTZ,
    review_action VARCHAR(50),
    review_notes TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Validation Rules

### 1. Bidirectional Consistency

**Purpose**: Ensure naturally bidirectional relationships exist in both directions.

**Business Rules**:
- Only applies to RELATES_TO relationships
- MENTIONS relationships are unidirectional (episode → entity)
- Focuses on semantic appropriateness, not just missing reverse edges

**Bidirectional Relationship Types**:
```python
{
    "allied_with", "opposed_to", "related_to", "connected_to",
    "married_to", "sibling_of", "friend_of", "enemy_of"
}
```

**Example Finding**:
```
Title: Potentially missing bidirectional RELATES_TO: allied_with
Description: Found RELATES_TO allied_with from Paladine to Kiri-Jolith, 
             which typically should be bidirectional.
Severity: INFO
Confidence: 0.6 (Medium - semantic context matters)
Suggested Action: Review if reverse allied_with relationship should exist
```

**LLM Enhancement**: Uses GPT-4o-mini to analyze semantic appropriateness and suggest better relationship types.

### 2. Mutual Exclusivity

**Purpose**: Identify logically contradictory relationships between the same entities.

**Business Rules**:
- Only checks RELATES_TO relationships
- MENTIONS relationships don't have mutual exclusivity constraints

**Mutually Exclusive Pairs**:
```python
{
    ("allied_with", "opposed_to"),
    ("friend_of", "enemy_of"),
    ("protects", "threatens"),
    ("supports", "opposes")
}
```

**Example Finding**:
```
Title: Mutually exclusive RELATES_TO: allied_with vs opposed_to
Description: Paladine and Takhisis have both allied_with and opposed_to 
             relationships, which are mutually exclusive.
Severity: ERROR
Confidence: 0.9 (Very high - logically contradictory)
Suggested Action: Remove one of the conflicting relationships
Evidence:
  - RELATES_TO Relationship 1: allied_with (ID: 4:abc:123)
  - RELATES_TO Relationship 2: opposed_to (ID: 4:def:456)
```

### 3. Hierarchical Consistency

**Purpose**: Validate hierarchical relationships have inverse counterparts.

**Hierarchical Pairs**:
```python
{
    "commands": "serves_under",
    "rules": "governed_by",
    "created_by": "creation_of",
    "parent_of": "child_of",
    "teaches": "student_of"
}
```

**Example Finding**:
```
Title: Missing hierarchical counterpart: commands → serves_under
Description: Found 'commands' from Astinus to Aesthetics, but missing 
             'serves_under' in reverse.
Severity: INFO
Confidence: 0.7 (High - hierarchical relationships typically paired)
Suggested Action: Consider adding serves_under from Aesthetics to Astinus
```

### 4. Semantic Consistency

**Purpose**: Ensure relationships have appropriate semantic properties for GraphRAG.

**Business Rules**:

**For RELATES_TO**:
- MUST have semantic type information (stored in `name` property)
- Semantic type helps LLMs understand relationship meaning
- Used for graph traversal and reasoning

**For MENTIONS**:
- Simple episode-to-entity links
- Should NOT have complex semantic attributes
- Rich semantics may indicate better fit as RELATES_TO

**Example Findings**:

```
# Missing semantic type
Title: RELATES_TO lacks semantic clarity for LLM reasoning
Description: RELATES_TO between Paladine and Solamnia lacks semantic type 
             information needed for hybrid GraphRAG.
Severity: WARNING
Confidence: 0.8 (High - LLMs need semantic context)
Suggested Action: Add semantic type (e.g., 'protects', 'allied_with')

# Rich MENTIONS
Title: MENTIONS may have rich semantics suitable for RELATES_TO
Description: MENTIONS between episode and entity has semantic type 'commands'. 
             This semantic richness might provide more value as RELATES_TO.
Severity: INFO
Confidence: 0.6 (Medium - rich semantics may indicate RELATES_TO)
Suggested Action: Consider converting to RELATES_TO for LLM graph traversal
```

### 5. Orphaned Entity Detection

**Purpose**: Find entities with no incoming or outgoing relationships.

**Example Finding**:
```
Title: Orphaned entity with no relationships
Description: Entity 'Abandoned Shrine' has no relationships, which may 
             indicate incomplete data extraction.
Severity: INFO
Confidence: 0.4 (Low - some entities may legitimately be isolated)
Suggested Action: Review entity to determine if relationships are missing
```

### 6. Duplicate Relationship Detection

**Purpose**: Identify duplicate relationships between the same entities with the same semantic type.

**Grouping Key**: `(source_id, target_id, semantic_type)`

**Example Finding**:
```
Title: Duplicate relationships: allied_with
Description: Found 3 duplicate 'allied_with' relationships between 
             Paladine and Kiri-Jolith.
Severity: WARNING
Confidence: 0.9 (Very high - identical relationships are duplicates)
Suggested Action: Remove 2 duplicate relationships, keeping the most complete one
Evidence:
  - Number of duplicates: 3
  - Relationship IDs: 4:abc:123, 4:def:456, 4:ghi:789
```

---

## Validation Workflow

### Basic Workflow

```python
from src.agents.relationship_validator import RelationshipValidator
import os

# 1. Initialize validator
validator = RelationshipValidator(
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# 2. Run validation
report = await validator.validate(
    entity_limit=1000,
    relationship_limit=5000,
    check_bidirectional=True,
    check_mutual_exclusivity=True,
    check_hierarchies=True,
    check_semantic_consistency=True,
    enable_llm_analysis=True
)

# 3. Review findings
print(f"Total findings: {len(report.findings)}")
for finding in report.findings:
    if finding.severity in ["error", "critical"]:
        print(f"{finding.severity.upper()}: {finding.title}")
        print(f"Confidence: {finding.confidence_score}")
        print(f"Action: {finding.suggested_action}\n")

# 4. Generate markdown report
markdown = report.to_markdown()
with open("validation_report.md", "w") as f:
    f.write(markdown)
```

### API Workflow

**Step 1: Run Validation**

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
    "enable_llm_analysis": true
  }'
```

**Response**:
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_id": "relationship_validator_v1_llm",
  "validation_type": "Entity Relationship Validation",
  "total_items_checked": 2500,
  "findings_count": 42,
  "severity_breakdown": {
    "critical": 0,
    "error": 3,
    "warning": 15,
    "info": 24
  },
  "execution_time_seconds": 45.2,
  "success": true,
  "timestamp": "2025-11-12T10:30:00Z"
}
```

**Step 2: Get Detailed Report**

```bash
curl https://luminarimud.com/sage/api/v1/validate/report/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: YOUR_API_KEY"
```

**Step 3: Filter Unreviewed Findings**

```bash
# Get all error-level unreviewed findings
curl "https://luminarimud.com/sage/api/v1/validate/findings/unreviewed?severity=error" \
  -H "X-API-Key: YOUR_API_KEY"
```

**Step 4: Mark Finding as Reviewed**

```bash
curl -X POST https://luminarimud.com/sage/api/v1/validate/findings/{finding_id}/review \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "reviewer": "admin",
    "action": "fixed",
    "notes": "Removed duplicate relationship manually"
  }'
```

**Review Actions**:
- `fixed`: Issue has been resolved
- `false_positive`: Agent was wrong, no issue exists
- `acknowledged`: Valid finding, will fix later
- `wont_fix`: Issue exists but intentional
- `needs_investigation`: Requires further analysis

---

## Confidence Scoring

### Confidence Scale

| Range | Level | Description | Use Case |
|-------|-------|-------------|----------|
| 0.9-1.0 | Very High | Clear logical contradiction, missing required data | Auto-correction candidates |
| 0.7-0.8 | High | Strong pattern match, multiple supporting evidence | High priority review |
| 0.5-0.6 | Medium | Possible issue, limited evidence | Medium priority review |
| 0.3-0.4 | Low | Speculation, unclear patterns | Low priority, context-dependent |
| 0.1-0.2 | Very Low | Weak signals, requires human judgment | Information only |

### Confidence Explanation Requirements

Every finding must include a clear explanation of why the confidence score was assigned:

```python
finding = self.create_finding(
    confidence_score=0.9,
    confidence_explanation="Very high confidence - these RELATES_TO relationship "
                         "types are logically contradictory. MENTIONS relationships "
                         "don't have mutual exclusivity issues."
)
```

### LLM Confidence Mapping

When using LLM analysis, map LLM confidence to numeric scores:

```python
confidence_map = {
    "HIGH": 0.8,
    "MEDIUM": 0.6,
    "LOW": 0.4
}
```

---

## Storage & Audit Trail

### Complete Audit Trail

Every validation creates a complete audit trail:

1. **Validation Report**: Stored in `validation_reports` table
2. **Individual Findings**: Stored in `validation_findings` table
3. **Review History**: Tracked in findings with reviewer, action, notes
4. **Metadata**: Extensible JSON fields for additional context

### Query Patterns

**Get validation statistics**:

```sql
SELECT 
    agent_id,
    COUNT(*) as total_validations,
    AVG(execution_time_seconds) as avg_execution_time,
    SUM(total_items_checked) as total_items_analyzed
FROM validation_reports
WHERE success = true
GROUP BY agent_id;
```

**Get unresolved high-priority findings**:

```sql
SELECT * FROM validation_findings
WHERE reviewed = false
  AND severity IN ('error', 'critical')
  AND confidence_score > 0.7
ORDER BY priority ASC, confidence_score DESC;
```

**Get review statistics by reviewer**:

```sql
SELECT 
    reviewer,
    review_action,
    COUNT(*) as count
FROM validation_findings
WHERE reviewed = true
GROUP BY reviewer, review_action;
```

---

## API Integration

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/validate/relationships` | POST | Run relationship validation |
| `/api/v1/validate/history` | GET | List validation reports |
| `/api/v1/validate/report/{report_id}` | GET | Get specific report |
| `/api/v1/validate/findings/unreviewed` | GET | Get unreviewed findings |
| `/api/v1/validate/findings/{finding_id}/review` | POST | Mark finding reviewed |
| `/api/v1/validate/stats` | GET | Get validation statistics |

See [API_REFERENCE.md](API_REFERENCE.md) for complete API documentation.

---

## LLM-Enhanced Analysis

### Semantic Appropriateness Analysis

Uses GPT-4o-mini to analyze whether relationship types make semantic sense between entity types.

**LLM Prompt Pattern**:

```python
prompt = f"""Analyze these RELATES_TO relationships for semantic appropriateness.

RELATIONSHIPS TO ANALYZE:
1. Crystal Dwarves --commands--> Mithril Ore
   Relationship ID: 4:abc:123
   
For each relationship, analyze:
1. SEMANTIC_APPROPRIATENESS: APPROPRIATE | QUESTIONABLE | INAPPROPRIATE
2. ENTITY_TYPE_ANALYSIS: What types of entities are these?
3. SUGGESTED_IMPROVEMENT: What would be better?
4. BIDIRECTIONAL_ASSESSMENT: Should this be bidirectional?

Examples of common issues to flag:
- Factions "commanding" materials (should be "uses")
- People "allied with" concepts (should be "believes_in")
- Places "married to" people (should be "inhabited_by")
"""
```

**Structured Output**:

```python
class SemanticAnalysis(BaseModel):
    relationship_id: str
    semantic_appropriateness: Literal["APPROPRIATE", "QUESTIONABLE", "INAPPROPRIATE"]
    source_entity_type: str
    target_entity_type: str
    current_relationship: str
    suggested_relationship: str
    suggested_reverse_relationship: Optional[str]
    bidirectional_assessment: Literal["NATURALLY_BIDIRECTIONAL", "NATURALLY_UNIDIRECTIONAL", "CONTEXT_DEPENDENT"]
    reasoning: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
```

### RELATES_TO Semantic Clarity

Analyzes RELATES_TO relationships missing semantic type information for GraphRAG optimization.

**Focus**: Will an LLM understand this relationship's meaning for graph traversal?

**LLM Output**:

```python
class RelatesToAnalysis(BaseModel):
    relationship_id: str
    semantic_clarity: Literal["CLEAR", "UNCLEAR", "MISSING"]
    suggested_semantic_type: str
    graphrag_impact: Literal["HIGH", "MEDIUM", "LOW"]
    llm_reasoning: str
```

### MENTIONS Classification Optimization

Analyzes whether MENTIONS relationships with rich semantics would be better classified as RELATES_TO.

**Focus**: Does this semantic richness provide value for LLM graph reasoning?

**LLM Output**:

```python
class MentionsAnalysis(BaseModel):
    relationship_id: str
    optimal_type: Literal["MENTIONS", "RELATES_TO"]
    graphrag_benefit: Literal["CLEAR_SEPARATION", "IMPROVED_REASONING", "NEUTRAL"]
    semantic_richness: Literal["HIGH_VALUE", "SOME_VALUE", "MINIMAL_VALUE"]
    llm_strategy: str
```

---

## Best Practices

### 1. Validation Frequency

- **Post-Ingestion**: Run after adding new lore documents
- **Pre-Release**: Full validation before major deployments
- **Regular Schedule**: Weekly or bi-weekly for ongoing monitoring
- **Debug**: Focused validation when investigating specific issues

### 2. Configuration Guidelines

**Small Datasets** (< 500 entities):
```python
entity_limit=500
relationship_limit=2000
enable_llm_analysis=True  # LLM analysis manageable
```

**Medium Datasets** (500-2000 entities):
```python
entity_limit=1000
relationship_limit=5000
enable_llm_analysis=True  # May take longer
```

**Large Datasets** (> 2000 entities):
```python
entity_limit=2000
relationship_limit=10000
enable_llm_analysis=False  # Skip LLM for faster validation
# Or enable LLM but expect longer execution times
```

### 3. Priority-Based Review

1. **Critical/Error** with **High Confidence (> 0.7)**: Immediate review
2. **Warning** with **High Confidence**: Next priority
3. **Info** with **Medium/High Confidence**: Backlog review
4. **Low Confidence (< 0.5)**: Context-dependent, may defer

### 4. Batch Processing

For large graphs, validate in batches:

```python
# Validate in chunks
async def validate_in_batches(total_entities: int, batch_size: int = 1000):
    reports = []
    for offset in range(0, total_entities, batch_size):
        report = await validator.validate(
            entity_limit=batch_size,
            # Use Neo4j SKIP/LIMIT to offset batches
        )
        reports.append(report)
    return reports
```

### 5. Review Workflow

```python
# 1. Get unreviewed high-priority findings
high_priority = await ValidationStorageService.get_unreviewed_findings(
    severity="error"
)

# 2. Group by category for efficient review
by_category = {}
for finding in high_priority:
    if finding.category not in by_category:
        by_category[finding.category] = []
    by_category[finding.category].append(finding)

# 3. Review systematically
for category, findings in by_category.items():
    print(f"\nReviewing {category}:")
    for finding in findings:
        # Present finding to reviewer
        # Get review decision
        await ValidationStorageService.mark_finding_reviewed(
            finding_id=finding.finding_id,
            reviewer="admin",
            action="fixed",  # or other action
            notes="Details of fix"
        )
```

---

## Troubleshooting

### Common Issues

#### 1. Timeout Errors

**Symptom**: Validation times out or takes too long

**Solutions**:
- Reduce `entity_limit` and `relationship_limit`
- Disable `enable_llm_analysis` for faster validation
- Validate in smaller batches
- Check Neo4j query performance

```python
# Fast validation for debugging
report = await validator.validate(
    entity_limit=100,
    relationship_limit=500,
    enable_llm_analysis=False
)
```

#### 2. Empty Results

**Symptom**: Validation returns no findings on known problematic data

**Possible Causes**:
- Database not connected
- Entity/relationship limits too small
- Validation checks disabled
- Data doesn't match validation rules

**Debug**:
```python
# Check what's being validated
print(f"Entities analyzed: {len(entities)}")
print(f"Relationships analyzed: {len(relationships)}")
print(f"Entity types: {set(e.get('labels', []) for e in entities)}")
print(f"Relationship types: {set(r.get('type') for r in relationships)}")
```

#### 3. LLM Analysis Failures

**Symptom**: LLM analysis fails or returns errors

**Solutions**:
- Check OpenAI API key is valid
- Verify API key has sufficient credits
- Reduce batch size for LLM analysis
- Disable LLM analysis if not needed

```python
# Validate without LLM if API issues
report = await validator.validate(
    enable_llm_analysis=False
)
```

#### 4. Storage Errors

**Symptom**: Validation runs but storage fails

**Solutions**:
- Check PostgreSQL connection
- Verify database schema is up to date
- Check disk space
- Review PostgreSQL logs

```bash
# Check PostgreSQL connection
docker exec luminari-postgres psql -U luminari -d luminari_sage -c "SELECT 1;"

# Check validation tables exist
docker exec luminari-postgres psql -U luminari -d luminari_sage -c "\dt validation_*"
```

### Performance Optimization

#### 1. Index Optimization

Ensure PostgreSQL indexes exist:

```sql
CREATE INDEX idx_findings_reviewed ON validation_findings(reviewed);
CREATE INDEX idx_findings_severity ON validation_findings(severity);
CREATE INDEX idx_findings_confidence ON validation_findings(confidence_score);
CREATE INDEX idx_reports_timestamp ON validation_reports(timestamp);
```

#### 2. Neo4j Query Optimization

Ensure Neo4j indexes exist:

```cypher
CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name);
CREATE INDEX episodic_stable_id IF NOT EXISTS FOR (n:Episodic) ON (n.stable_id);
```

#### 3. Batch LLM Calls

The validator already batches LLM calls (10 relationships per call). Adjust if needed:

```python
# In relationship_validator.py
batch_size = 10  # Adjust based on LLM rate limits
for i in range(0, len(relationships), batch_size):
    batch = relationships[i:i+batch_size]
    # Process batch...
```

---

## Related Documentation

- [CORRECTION_SYSTEM.md](CORRECTION_SYSTEM.md) - Autonomous correction system
- [API_REFERENCE.md](API_REFERENCE.md) - API endpoint details
- [VALIDATION_AGENT_GUIDE.md](VALIDATION_AGENT_GUIDE.md) - Practical testing guide
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Developer integration guide

---

**Last Updated**: 2025-11-12  
**Version**: 0.7.0  
**Status**: Production Ready

