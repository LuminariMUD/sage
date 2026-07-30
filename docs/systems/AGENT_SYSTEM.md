# Agent System Documentation

## Overview

The Luminari Sage agent system consists of multiple specialized AI agents that work independently or collaboratively to handle various tasks. Each agent has specific capabilities, input/output schemas, and can be orchestrated for complex multi-step operations.

## Agent Types

### 1. Chat Agent (PydanticAI)

**Purpose**: Provide conversational interface for lore queries with streaming responses.

**Model**: GPT-4o

**Location**: `src/agents/lore_chat_agent_streaming.py`

**Capabilities**:
- Natural language understanding
- Context-aware responses
- Tool calling (search_lore)
- Streaming token generation
- Conversation memory

**System Prompt**:
```
You are the Sage of Luminari, a keeper of ancient knowledge and lore.
You have access to a vast repository of information about the world.
Always ground your responses in the search results.
Be helpful, accurate, and engaging.
```

**Tools**:
- `search_lore(query: str)`: Search the knowledge base

**Usage Example**:
```python
agent = StreamingLoreChatAgent(api_key)
async for event in agent.stream_chat("Tell me about the Sundering"):
    if event["type"] == "token":
        print(event["content"], end="")
```

---

### 2. Story Development Agent

**Purpose**: Create new non-canon stories, characters, and locations while respecting established lore.

**Model**: GPT-4o-mini

**Location**: `src/agents/langchain/chains/story_development.py`

**Capabilities**:
- Create new characters, locations, events
- Mark non-canon elements with [STORY] tags
- Maintain story continuity
- Reference canonical lore
- Track story-specific elements

**Output Schema**:
```python
{
    "canon_foundation": ["Referenced lore elements"],
    "new_elements": [
        {
            "name": "Character Name",
            "type": "character",
            "description": "Description",
            "canon_references": ["Thrain", "Ashenport"],
            "is_canon": false
        }
    ],
    "story_content": "The narrative text...",
    "continuity_notes": "How this fits the broader story",
    "story_id": "unique-story-identifier"
}
```

**Example Prompt**:
```
Create a story about a Crystal Dwarf craftsman in Ashenport 
who is secretly building an Arcana Golem.
```

---

### 3. Quest Planner Agent

**Purpose**: Generate structured quests with phases, objectives, and key entities.

**Model**: GPT-4o-mini

**Location**: `src/agents/langchain/chains/quest_planner.py`

**Capabilities**:
- Create multi-phase quest structures
- Include objectives and risks
- Reference entities from context
- Adapt to story contexts
- Generate quest titles and premises

**Output Schema**:
```json
{
    "title": "The Craftsman's Vision",
    "objective": "Help complete the Arcana Golem",
    "premise": "A Crystal Dwarf needs rare materials...",
    "phases": [
        {
            "phase": "Hook",
            "description": "Discover the hidden workshop",
            "key_entities": ["Crystal Dwarf", "Ashenport"],
            "risks": ["Discovery by authorities"]
        },
        {
            "phase": "Escalation",
            "description": "Gather rare components",
            "key_entities": ["Arcane Crystals"],
            "risks": ["Rival collectors"]
        }
    ],
    "unresolved_threads": ["The craftsman's true motivation"]
}
```

**Phase Structure**:
1. **Hook**: Initial engagement
2. **Escalation**: Rising action
3. **Complication**: Unexpected challenges
4. **Climax**: Peak conflict
5. **Resolution**: Conclusion

---

### 4. Narrative Generator Agent

**Purpose**: Write atmospheric prose and scenes based on canonical lore.

**Model**: GPT-4o-mini

**Location**: `src/agents/langchain/chains/narrative.py`

**Capabilities**:
- Generate 150-220 word scenes
- Create narrative outlines (3-7 beats)
- Track creative embellishments
- Maintain canon adherence
- Write dramatic prose

**Output Schema**:
```json
{
    "outline": [
        {
            "beat": 1,
            "title": "The Awakening",
            "purpose": "Set the scene"
        },
        {
            "beat": 2,
            "title": "First Light",
            "purpose": "Show the transformation"
        }
    ],
    "scene": "The cavern trembled as ancient crystals began to pulse...",
    "embellishment_note": "Added sensory details about crystal resonance"
}
```

**Trigger Words**:
- "write a scene"
- "describe"
- "narrate"
- "create prose"

---

### 5. Direct Answer Agent

**Purpose**: Provide comprehensive, conversational answers about lore.

**Model**: GPT-4o-mini

**Location**: `src/agents/langchain/chains/direct_answer.py`

**Capabilities**:
- Answer factual questions
- Provide detailed explanations
- Connect related concepts
- Maintain conversation continuity
- Cite sources from context

**Personality Traits**:
- Warm and conversational
- Enthusiastic about lore
- Professional yet approachable
- Occasionally mystical

**Example Response Style**:
```
Ah, the Crystal Dwarves! One of Luminari's most fascinating races. 
These silicon-based beings emerged during the Age of Crystal, when 
the deep caverns resonated with primordial energies...
```

---

### 6. Retrieval Chain

**Purpose**: Perform semantic search and context retrieval using hybrid RAG.

**Model**: N/A (retrieval only, uses embedding models)

**Location**: `src/agents/langchain/chains/retrieval.py`

**Capabilities**:
- Vector similarity search (pgvector)
- Full-text search (PostgreSQL FTS)
- Graph entity expansion (Neo4j)
- Reciprocal rank fusion
- Context formatting for LLMs
- Metadata extraction

**Search Process**:
1. Query embedding generation
2. Vector search in pgvector (episode embeddings)
3. Full-text search in PostgreSQL
4. Reciprocal rank fusion to combine results
5. Graph expansion in Neo4j (entity context)
6. Context assembly with structured blocks

**Usage**:
```python
from src.agents.langchain.chains.retrieval import RetrievalChain

retrieval = RetrievalChain()
result = await retrieval.ainvoke({"query": "Tell me about Crystal Dwarves"})

# Returns structured context blocks
context_blocks = result.get("context_blocks", [])
entities = result.get("raw", {}).get("entities", [])
chunks = result.get("raw", {}).get("chunks", [])
```

---

### 7. Direct Answer Agent

**Purpose**: Provide comprehensive, grounded answers to lore questions using retrieved context.

**Model**: GPT-4.1 (default) or configurable

**Location**: `src/agents/langchain/chains/direct_answer.py`

**Capabilities**:
- Two-stage answer generation (digest → compose)
- Context prioritization (prose > entity summaries > graph)
- Block citation for fact tracing
- Gap identification (what archives don't cover)
- Offline fallback for testing

**Answer Pipeline**:

1. **Digest Stage**: Analyze context blocks with structured JSON output
   - Extract direct answers with block citations
   - Identify supporting facts
   - Note related details
   - Flag gaps in knowledge

2. **Compose Stage**: Generate comprehensive response
   - Begin with direct answer summary
   - Provide canonical details
   - List key entities and roles
   - Include notable connections
   - Reference blocks inline [Block X]
   - List source blocks with previews

**Context Block Types** (in priority order):

1. **Plain Prose**: Canonical episode text (highest authority)
2. **Entity Summaries**: Curated entity facts from graph (lines prefixed "ENTITY ...")
3. **Graph Data**: Supporting notes from Neo4j (prefixed "GRAPH ENTITY"/"GRAPH RELATIONSHIP")

**System Prompt Highlights**:
```
You are an archivist distilling canonical knowledge of Lumia.

Always ground direct conclusions in the prose passages first.
Use entity summaries to reinforce or extend the prose when sparse.
Use graph information only to corroborate or extend what the prose establishes.
If graph details contradict the prose or entity summary, trust the canon sources.
```

**Usage**:
```python
from src.agents.langchain.chains.direct_answer import DirectAnswerChain

direct_answer = DirectAnswerChain(
    model_name="gpt-4.1",
    temperature=0.0
)

result = direct_answer.invoke({
    "query": "Who are the Crystal Dwarves?",
    "context_blocks": context_blocks
})

answer = result.get("answer")
```

**Output Structure**:
```markdown
## Direct Answer
[Core response summary]

## Canonical Details
[Every supporting fact from context]

## Key Entities & Roles
[Important entities and their roles]

## Notable Connections
[Key relationships from graph]

## Additional Insights
[Related tangential information]

## Source Blocks
- Block 1: [Preview of first 100 chars...]
- Block 2: [Preview of first 100 chars...]
```

---

### 8. Agent Orchestrator

**Purpose**: Coordinate multiple agents for complex multi-step operations.

**Model**: GPT-4o-mini (for planning)

**Location**: `src/agents/langchain/chains/agent_orchestrator.py`

**Capabilities**:
- Analyze complex requests
- Create execution plans
- Execute agents sequentially
- Pass context between steps
- Assemble combined responses

**Planning Process**:
```python
{
    "user_intent": "Create story and quest about Crystal Dwarf",
    "needs_orchestration": true,
    "execution_plan": [
        {
            "step": 1,
            "tool": "search_lore",
            "description": "Search for Crystal Dwarf lore",
            "input": {"query": "Crystal Dwarves Ashenport"},
            "output_key": "lore_context"
        },
        {
            "step": 2,
            "tool": "develop_story",
            "description": "Create the story",
            "input": {
                "prompt": "Crystal Dwarf craftsman story",
                "previous_context": "{{lore_context}}"
            },
            "output_key": "story"
        },
        {
            "step": 3,
            "tool": "plan_quest",
            "description": "Create quest based on story",
            "input": {
                "premise": "Help complete the Arcana Golem",
                "previous_context": "{{story}}"
            },
            "output_key": "quest"
        }
    ]
}
```

**Available Tools**:
- `search_lore`: Search canonical information
- `develop_story`: Create non-canon stories
- `plan_quest`: Generate quest structures
- `generate_narrative`: Write prose scenes
- `answer_lore`: Direct Q&A about lore

---

## Validation and Correction Agents

The validation and correction system provides autonomous graph quality assurance with complete audit trails and rollback capabilities. See [VALIDATION_SYSTEM.md](VALIDATION_SYSTEM.md) and [CORRECTION_SYSTEM.md](CORRECTION_SYSTEM.md) for comprehensive documentation.

### 1. Relationship Validator

**Purpose**: Validate entity relationships in the Neo4j knowledge graph with LLM-enhanced semantic analysis.

**Model**: GPT-4o-mini (for semantic analysis)

**Agent ID**: `relationship_validator_v1_llm`

**Location**: `src/agents/relationship_validator.py`

**Capabilities**:
- **Rule-Based Validation**: 6 validation types with deterministic checks
- **LLM-Enhanced Analysis**: Semantic appropriateness and GraphRAG optimization
- **Complete Audit Trail**: All findings stored in PostgreSQL
- **Human Review Workflow**: Mark findings as reviewed with actions
- **Confidence Scoring**: Every finding includes confidence (0.0-1.0) with explanation
- **Non-Destructive**: Never modifies data automatically

**Validation Types**:

1. **Bidirectional Consistency**: Missing reverse relationships
   - Checks RELATES_TO relationships for semantic appropriateness
   - LLM analyzes if relationship types make sense between entity types
   - Example: Faction "commanding" Material → should be "uses"

2. **Mutual Exclusivity**: Contradictory relationships
   - Detects logically exclusive pairs (allied_with vs opposed_to)
   - High confidence (0.9) for clear contradictions
   - Only applies to RELATES_TO relationships

3. **Hierarchical Consistency**: Missing inverse relationships
   - Validates hierarchical pairs (commands ↔ serves_under)
   - Ensures parent/child relationship consistency
   - Medium-high confidence (0.7)

4. **Semantic Consistency**: GraphRAG optimization
   - RELATES_TO must have semantic type for LLM understanding
   - MENTIONS should be simple (no complex semantics)
   - Optimizes for hybrid vector + graph retrieval

5. **Orphaned Entities**: Entities with no relationships
   - Identifies isolated entities
   - Low confidence (0.4) - may be intentional
   - Informational severity

6. **Duplicate Relationships**: Identical relationships
   - Same source, target, semantic type
   - Very high confidence (0.9)
   - Warning severity

**LLM-Enhanced Analysis** (optional, `enable_llm_analysis=True`):

- **Semantic Appropriateness**: Does relationship type make sense for these entity types?
- **RELATES_TO Clarity**: Does semantic type help LLM understand for graph traversal?
- **MENTIONS Classification**: Should rich MENTIONS semantics be RELATES_TO instead?

**Configuration**:
```python
report = await validator.validate(
    entity_limit=1000,              # Max entities to analyze
    relationship_limit=5000,        # Max relationships to check
    check_bidirectional=True,       # Missing reverse relationships
    check_mutual_exclusivity=True,  # Contradictory relationships
    check_hierarchies=True,         # Command/serve consistency
    check_semantic_consistency=True,# GraphRAG optimization
    enable_llm_analysis=True        # LLM semantic analysis
)
```

**Output Schema**:
```python
class ValidationReport(BaseModel):
    report_id: str
    agent_id: str
    validation_type: str
    timestamp: datetime
    total_items_checked: int
    findings: List[ValidationFinding]
    execution_time_seconds: float
    success: bool
    
class ValidationFinding(BaseModel):
    finding_id: str
    severity: ValidationSeverity  # INFO, WARNING, ERROR, CRITICAL
    category: str
    title: str
    description: str
    evidence: List[str]
    affected_entities: List[str]
    affected_relationships: List[str]
    confidence_score: float  # 0.0-1.0
    confidence_explanation: str
    suggested_action: str
    priority: int  # 1-5
    reviewed: bool
    reviewer: Optional[str]
    review_action: Optional[str]
    review_notes: Optional[str]
```

**Business Rules**:
- **Never validates MENTIONS bidirectionality**: MENTIONS are unidirectional episode→entity links
- **GraphRAG-aware**: RELATES_TO needs semantics for LLM reasoning, MENTIONS should be simple
- **Confidence-based**: High confidence (>0.85) suitable for autonomous correction

---

### 2. Base Validator

**Purpose**: Foundation class for all validation agents with comprehensive audit trails.

**Location**: `src/agents/base_validator.py`

**Features**:
- **Standardized Finding Structure**: ValidationFinding and ValidationReport models
- **Confidence Scoring Guidelines**: 0.9-1.0 (very high) to 0.1-0.2 (very low)
- **Human Review Tracking**: Reviewer, action, timestamp, notes
- **Agent Identification**: Every finding tagged with agent ID
- **Evidence Collection**: List of supporting evidence for each finding
- **Priority System**: 1 (highest) to 5 (lowest)

**System Prompt Template**:
```python
You are a validation agent for the Luminari Sage knowledge graph system.

AGENT IDENTIFICATION: {agent_id}

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
```

**Severity Levels**:
- **CRITICAL**: Data corruption, major inconsistencies requiring immediate action
- **ERROR**: Clear logical problems needing fixes
- **WARNING**: Potential issues worth investigating
- **INFO**: Suggestions for improvement

**Helper Methods**:
```python
def create_finding(...) -> ValidationFinding
def create_report(...) -> ValidationReport
```

---

### 3. Relationship Corrector

**Purpose**: Autonomous agent for safe relationship corrections with complete rollback capability.

**Agent ID**: `relationship_corrector_v1`

**Location**: `src/agents/relationship_corrector.py`

**Capabilities**:
- **Deduplication**: Remove duplicate RELATES_TO relationships (confidence: 0.95)
- **Semantic Standardization**: Normalize to SCREAMING_SNAKE_CASE (confidence: 0.90)
- **Complete Backup**: Store full relationship data before modification
- **Batch Processing**: Group corrections for atomic rollback
- **Dry-Run Mode**: Preview corrections without applying
- **MENTIONS Protection**: Never modifies MENTIONS relationships

**Correction Types**:

1. **Deduplication** (`DEDUPLICATION`):
   - Detects duplicate RELATES_TO relationships (same source, target, semantic type)
   - Scores duplicates by data completeness (embeddings, properties, episodes)
   - Keeps highest-scoring duplicate
   - Deletes inferior duplicates with full backup
   - Action: DELETE

2. **Semantic Standardization** (`SEMANTIC_STANDARDIZATION`):
   - Normalizes semantic types to consistent format
   - Converts "allied with" → "ALLIED_WITH"
   - Updates `name` property in Neo4j
   - Preserves semantic meaning
   - Action: UPDATE

**Scoring Algorithm** (for duplicate selection):
```python
def score_relationship(rel):
    score = 0
    if "fact_embedding" in props: score += 100
    if "name_embedding" in props: score += 100
    if "name" in props: score += 50
    if "fact" in props: score += 30
    if "episodes" in props: score += min(len(episodes) * 5, 50)
    if "created_at" in props: score += 10
    score += len(props)  # Property count
    return score
```

**Configuration**:
```python
corrections = await corrector.apply_corrections(
    relationships=relationships,
    correct_duplicates=True,         # Remove duplicates
    standardize_semantics=True,      # Standardize formats
    confidence_threshold=0.85,       # High confidence only
    max_corrections=100,             # Limit corrections
    dry_run=True                     # Preview only (default)
)
```

**Safety Mechanisms**:
1. **Dry-run by default**: Must explicitly set `dry_run=False`
2. **Confidence threshold**: Only high-confidence corrections (≥0.85)
3. **Max corrections limit**: Prevents runaway corrections
4. **MENTIONS protection**: Business rule - never modifies MENTIONS
5. **Complete backup**: Full relationship data stored before changes
6. **Batch tracking**: All corrections share correction_batch_id

**Correction Record**:
```python
class CorrectionRecord(BaseModel):
    correction_id: str
    correction_type: str  # DEDUPLICATION or SEMANTIC_STANDARDIZATION
    relationship_id: str
    action: str  # DELETE or UPDATE
    confidence_score: float
    reasoning: str
    original_semantic_type: Optional[str]
    new_semantic_type: Optional[str]
    duplicate_count: Optional[int]
    metadata: Dict  # Includes backup_data
```

---

### 4. Rollback Manager

**Purpose**: High-level interface for rolling back corrections and restoring original state.

**Location**: `src/agents/rollback_manager.py`

**Capabilities**:
- **Single Correction Rollback**: Restore one specific correction
- **Batch Rollback**: Atomically rollback all corrections in a batch
- **Rollback Preview**: Preview what would be rolled back
- **Statistics**: Track rollback metrics and patterns
- **Safety Validation**: Check if correction can be rolled back

**Key Methods**:
```python
async def rollback_correction(
    correction_id: str,
    rollback_by: str,
    rollback_reason: str
) -> Dict[str, Any]

async def rollback_batch(
    correction_batch_id: str,
    rollback_by: str,
    rollback_reason: str
) -> Dict[str, Any]

async def preview_rollback_batch(
    correction_batch_id: str
) -> Dict[str, Any]

async def get_rollback_statistics(
    days: int = 30
) -> Dict[str, Any]
```

**Rollback Process**:
1. **Validate**: Check if correction can be rolled back (not already rolled back)
2. **Retrieve**: Get complete backup data from PostgreSQL
3. **Restore**: Apply inverse operation to Neo4j
   - DELETE → Recreate relationship with all original properties
   - UPDATE → Restore original property values (including embeddings)
4. **Mark**: Update correction record as rolled_back in PostgreSQL
5. **Audit**: Log rollback with user, timestamp, and reason

**Batch Rollback**: Processes corrections in reverse order (most recent first) to handle dependencies.

---

### 5. Validation Storage

**Purpose**: Persist validation reports and findings with complete audit trail.

**Location**: `src/agents/validation_storage.py`

**Key Methods**:
```python
async def store_report(report: ValidationReport) -> bool
async def get_report(report_id: str) -> Optional[ValidationReport]
async def list_reports(limit: int = 50) -> List[Dict[str, Any]]
async def get_findings_for_report(report_id: str) -> List[ValidationFinding]
async def get_unreviewed_findings(
    severity: Optional[str] = None,
    category: Optional[str] = None
) -> List[ValidationFinding]
async def mark_finding_reviewed(
    finding_id: str,
    reviewer: str,
    action: str,
    notes: str = ""
) -> bool
async def get_validation_statistics() -> Dict[str, Any]
```

**Features**:
- **PostgreSQL Storage**: Durable storage with indexes
- **Report Versioning**: Track all validation runs
- **Finding Tracking**: Individual finding records with review status
- **Review Workflow**: Complete review lifecycle (unreviewed → reviewed)
- **Statistics Aggregation**: Validation metrics over time
- **Query Filters**: By severity, category, agent ID, reviewed status

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

**Review Actions**:
- `fixed`: Issue has been resolved
- `false_positive`: Agent was wrong, no issue exists
- `acknowledged`: Valid finding, will fix later
- `wont_fix`: Issue exists but intentional
- `needs_investigation`: Requires further analysis

---

### 6. Correction Storage

**Purpose**: Track correction history and maintain complete rollback data.

**Location**: `src/agents/correction_storage.py`

**Key Methods**:
```python
async def store_correction(
    correction_id: str,
    validation_report_id: Optional[str],
    correction_batch_id: str,
    correction_type: str,
    action: str,
    confidence_score: float,
    agent_reasoning: str,
    relationship_data: Dict[str, Any],  # Complete backup
    ...
) -> bool

async def get_correction(correction_id: str) -> Optional[Dict[str, Any]]
async def get_corrections_for_batch(batch_id: str) -> List[Dict[str, Any]]
async def get_corrections_for_report(report_id: str) -> List[Dict[str, Any]]
async def can_rollback_correction(correction_id: str) -> bool
async def get_correction_batch_summary(batch_id: str) -> Dict[str, Any]
async def list_recent_corrections(limit: int = 100) -> List[Dict[str, Any]]
```

**Features**:
- **Complete Backup**: Stores entire relationship including embeddings
- **Batch Management**: Group related corrections
- **Rollback Data**: Everything needed to restore exact original state
- **Status Tracking**: Applied vs rolled back
- **Audit Logging**: Who, when, why for every correction and rollback
- **Linked to Validation**: Connects corrections to originating validation reports

**Database Schema**:
```sql
CREATE TABLE relationship_corrections (
    correction_id UUID PRIMARY KEY,
    validation_report_id UUID REFERENCES validation_reports(report_id),
    correction_batch_id UUID NOT NULL,
    
    -- Correction details
    correction_type VARCHAR(50) NOT NULL,  -- DEDUPLICATION, SEMANTIC_STANDARDIZATION
    action VARCHAR(20) NOT NULL,           -- DELETE, UPDATE
    confidence_score FLOAT NOT NULL,
    agent_reasoning TEXT NOT NULL,
    
    -- Relationship backup (complete data for rollback)
    relationship_id TEXT NOT NULL,
    relationship_type VARCHAR(50) NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_node_name TEXT,
    target_node_name TEXT,
    source_node_labels TEXT[],
    target_node_labels TEXT[],
    original_properties JSONB NOT NULL,  -- Full backup including embeddings
    new_properties JSONB,                -- For UPDATE actions
    
    -- Type-specific details
    original_semantic_type TEXT,
    new_semantic_type TEXT,
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
```

**Correction States**:
- **Applied**: Successfully applied to Neo4j (`rolled_back=false`)
- **Rolled Back**: Reverted to original state (`rolled_back=true`)

**Critical Feature**: `original_properties` JSONB stores complete Neo4j relationship data including embeddings, enabling exact restoration.

---

## Classification System

### LLM-Based Classification

**Model**: GPT-4o-mini

**Location**: `src/agents/langchain/util/classifier.py`

**Routes**:
1. **lore_query**: Factual questions
2. **quest_planning**: Quest creation
3. **narrative_generation**: Prose writing
4. **story_development**: New non-canon content
5. **orchestrated**: Multi-step operations
6. **meta_help**: System capabilities

**Classification Process**:
```python
async def llm_classify(message, conversation_history):
    # Considers conversation context
    # Returns (route, confidence)
    return ("story_development", 0.95)
```

### Heuristic Fallback

Pattern-based classification when LLM unavailable:
- Quest patterns: "quest", "adventure", "mission"
- Story patterns: "create", "develop", "new character"
- Narrative patterns: "write", "describe", "scene"
- Orchestration patterns: "then", "after that", "based on"

---

## Conversation Management

### Storage Service

**Location**: `src/agents/conversation_storage.py`

**Features**:
- PostgreSQL-backed persistence
- Session management
- Message threading
- Metadata storage
- Streaming state tracking

**Schema**:
```sql
conversations (
    id UUID PRIMARY KEY,
    user_id TEXT,
    created_at TIMESTAMP,
    metadata JSONB
)

conversation_messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations,
    message_type TEXT,  -- 'user' or 'assistant'
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMP
)
```

---

## Streaming Architecture

### SSE (Server-Sent Events)

**Event Types**:
```javascript
// Route selection
{"type": "route", "route": "lore_query", "confidence": 0.95}

// Token streaming
{"type": "token", "content": "The"}

// Tool calls
{"type": "tool_call", "tool": "search_lore", "query": "Crystal Dwarves"}

// Tool results
{"type": "tool_result", "tool": "search_lore", "results": [...]}

// Execution plan (orchestrated)
{"type": "plan", "plan": {...}}

// Final response
{"type": "final", "answer": "Complete response"}

// Error
{"type": "error", "content": "Error message"}
```

### Stream Session Management

**Session Creation**:
1. User sends message
2. Create stream session with TTL
3. Return stream URL
4. Client connects to SSE endpoint

**Session State**:
- `pending`: Awaiting processing
- `processing`: Currently generating
- `completed`: Successfully finished
- `error`: Failed with error

---

## Error Handling

### Retry Mechanisms

**LLM Failures**:
1. First retry: Provide error feedback
2. Second retry: Give concrete template
3. Fallback: Use default response

**Example Retry Logic**:
```python
if not valid_response:
    # First retry with feedback
    retry_prompt = "Your JSON was invalid. Expected format: ..."
    
    if still_invalid:
        # Second retry with template
        template_prompt = "Fill in this exact template: ..."
        
        if still_invalid:
            # Use fallback
            return FALLBACK_RESPONSE
```

### Validation Layers

1. **Input Validation**: Pydantic models
2. **Output Validation**: Schema checking
3. **Context Validation**: Ensure references exist
4. **Semantic Validation**: Check logical consistency

---

## Agent Customization

### Creating New Agents

**Base Template**:
```python
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

class CustomAgent(Runnable):
    def __init__(self, model="gpt-4o-mini", temperature=0.7):
        self.llm = ChatOpenAI(model=model, temperature=temperature)
    
    def invoke(self, input: Dict[str, Any]) -> Dict[str, Any]:
        # Process input
        # Call LLM
        # Return structured output
        pass
```

### Adding to Orchestrator

1. Define tool in `AVAILABLE_TOOLS`
2. Map to chain in `tool_chain_map`
3. Add to service initialization
4. Update classifier if needed

---

## Performance Optimization

### Token Management
- Streaming for long responses
- Chunked processing for large contexts
- Token counting with tiktoken

### Caching Strategy
- Embedding cache (15 minutes)
- Query result cache
- Conversation context cache

### Parallel Processing
- Concurrent tool calls
- Batch embedding generation
- Async database queries

---

## Testing Agents

### Unit Testing
```python
async def test_story_agent():
    agent = StoryDevelopmentChain()
    result = agent.invoke({
        "query": "Create a story about a Crystal Dwarf",
        "context_blocks": ["lore context"]
    })
    assert "story_content" in result["story_development"]
```

### Integration Testing
```python
async def test_orchestration():
    service = LangChainChatService()
    result = await service.chat(
        "Create a story then a quest",
        conversation_history=[]
    )
    assert result["route"] == "orchestrated"
```

### Load Testing
```bash
# Using locust or similar
locust -f tests/load_test.py --host=http://localhost:8003
```

---

## Best Practices

### Prompt Engineering
1. Be explicit about output format
2. Provide examples when possible
3. Use temperature appropriate to task
4. Include validation instructions

### Context Management
1. Limit context to relevant information
2. Use semantic chunking
3. Preserve conversation flow
4. Clean up old sessions

### Error Recovery
1. Always have fallbacks
2. Log failures for debugging
3. Provide meaningful error messages
4. Retry with different strategies

---

## Future Enhancements

### Planned Features
1. **Multi-modal agents**: Image and map understanding
2. **Collaborative agents**: Multi-agent debate
3. **Learning agents**: Fine-tuning on feedback
4. **Specialized agents**: Combat, crafting, trading

### Research Areas
1. **Chain-of-thought prompting**
2. **Self-consistency checking**
3. **Retrieval-augmented generation improvements**
4. **Agent communication protocols**

## Context Management Strategy

### Problem Statement
As conversations grow with multi-step tasks (questlines, connected stories), context accumulation becomes critical:
- 4-quest questline can exceed 5000+ tokens
- Tool results add 1000+ tokens per complex operation
- Conversation history grows linearly
- Risk of hitting token limits or degraded performance

### Proposed Solution: Intelligent Context Compression

#### 1. Sliding Window with Task Preservation
```python
class ContextWindow:
    full_detail_turns: int = 2      # Last 2 turns keep full detail
    summary_turns: int = 3           # Next 3 turns compressed to summaries
    active_task_context: Any        # Always preserved regardless of age
```

**Implementation**:
- Keep recent messages in full detail
- Compress older messages to summaries
- ALWAYS preserve "active task" context (current questline, pending stories)
- Never compress incomplete multi-step operations

#### 2. Semantic Compression Strategies

**Tool Result Compression**:
```python
# Original (1000+ tokens):
{
    "tool": "create_quest",
    "result": {
        "title": "The Crystal Memory",
        "phases": [/* 5 detailed phases */],
        "npcs": [/* detailed NPC list */],
        ...
    }
}

# Compressed (50 tokens):
{
    "tool": "create_quest",
    "summary": "Created 'The Crystal Memory' (Quest 2/4)",
    "key_points": ["Silicon awakening theme", "Elder Thrain NPC", "Crystal Caverns location"],
    "continuity": ["unresolved: memory fragments"]
}
```

**Conversation Compression**:
- Merge adjacent user messages
- Combine tool calls of same type
- Extract and preserve key decisions/choices
- Remove redundant confirmations

#### 3. Task-Aware Context Structure
```python
class TaskAwareContext:
    # Always preserved
    active_questline: Optional[QuestlineState]  
    pending_stories: List[StoryThread]
    unresolved_threads: List[str]
    
    # Compressed after completion
    completed_quests: List[QuestSummary]  # Just titles and connections
    tool_history: ToolHistorySummary      # Aggregated by type
    
    # Recent context
    recent_messages: List[Message]        # Last 3-5 turns
    current_entities: Set[str]            # Active NPCs/locations
```

#### 4. Progressive Detail Reduction

| Age | Detail Level | Example |
|-----|-------------|---------|
| Current turn | Full | Complete tool results, all text |
| 1 turn ago | Full | Complete tool results, all text |
| 2-4 turns ago | Moderate | Key results, main points |
| 5-10 turns ago | Summary | One-line summaries |
| 10+ turns ago | Minimal | Only if task-relevant |

#### 5. Smart Compression Triggers

**Automatic Compression When**:
- Context exceeds 50% of model limit
- Major task completes (questline finished)
- Topic shift detected
- User explicitly starts new task

**Never Compress**:
- Active multi-step operations
- Unresolved story threads  
- Recent tool failures needing retry
- Explicit user references to past content

#### 6. Implementation Approach

```python
class ContextManager:
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.compression_threshold = max_tokens * 0.5
        
    async def manage_context(
        self, 
        messages: List[Message],
        active_tasks: List[Task]
    ) -> List[Message]:
        """Intelligently compress context while preserving continuity."""
        
        # Calculate current token usage
        current_tokens = self.count_tokens(messages)
        
        if current_tokens < self.compression_threshold:
            return messages  # No compression needed
            
        # Identify what must be preserved
        preserve_ids = self.identify_critical_messages(messages, active_tasks)
        
        # Apply progressive compression
        compressed = []
        for msg in messages:
            if msg.id in preserve_ids:
                compressed.append(msg)  # Keep full detail
            elif msg.age < 2:
                compressed.append(msg)  # Recent: keep full
            elif msg.age < 5:
                compressed.append(self.moderate_compress(msg))
            else:
                summary = self.semantic_compress(msg)
                if summary:  # Only include if still relevant
                    compressed.append(summary)
                    
        return compressed
```

### When to Implement

**Phase 1** (Current): Monitor token usage in production
- Log warnings when context > 4000 tokens
- Track which operations cause most growth
- Identify compression candidates

**Phase 2** (When needed): Implement basic compression
- Start with tool result compression
- Add conversation summarization
- Preserve task continuity

**Phase 3** (Future): Advanced features
- Semantic importance scoring
- Dynamic compression thresholds
- User-controllable detail levels

### Success Metrics
- No loss of task continuity
- Maintain conversation coherence
- Support 10+ turn questline generation
- Handle 20+ turn conversations
- Reduce context by 60-70% when compressed

---

*For API integration, see the [API Reference](./API_REFERENCE.md).*
*For development setup, see the [Developer Guide](./DEVELOPER_GUIDE.md).*