# Luminari GraphRAG Demo Guide

## Overview
This demo showcases a **Hybrid Graph RAG system** that combines:
- **Semantic Search** (PostgreSQL + pgvector) for text similarity
- **Knowledge Graph Traversal** (Neo4j) for entity relationships
- **LLM-powered Entity Extraction** (Graphiti) for automated knowledge building

## Demo Setup
1. Import `Luminari_GraphRAG_Demo.postman_collection.json` into Postman
2. The collection contains 9 pre-configured requests demonstrating key capabilities including the new thin relationships architecture
3. All requests point to `https://luminarimud.com/sage/mcp/tools/call`

## System Scale (Current)
- **Documents:** 4 canonical lore files
- **Episodes:** 172 text chunks (avg. 492 chars with overlap)  
- **Knowledge Graph:** 200 entities, 1,376 relationships
- **Entity Types:** Locations, Persons, Organizations, Events, Concepts, Artifacts

## Demo Flow & Talking Points

### 1. **GraphRAG Query - Void's Wake** 
*"Let me show you how our hybrid system works..."*

**What happens:**
- Semantic search finds relevant text chunks about Void's Wake
- Graph traversal discovers related entities automatically
- Returns rich context: direct text + entity relationships + 2-hop connections

**Key points:**
- Shows **207 total connections** (11 direct + 196 indirect 2-hop)
- Demonstrates how graph expansion enriches semantic search results
- Notice the **similarity scores** (0.680, 0.673, etc.) from vector search

### 2. **Entity Search - Find Void Witch**
*"Now let's explore the knowledge graph directly..."*

**What happens:**
- Direct entity search in the Neo4j knowledge graph
- Returns structured entity data with IDs for further exploration

**Key points:**
- Shows different entity types: Person, Location, Organization, Event
- Each entity has a unique UUID for relationship traversal

### 3. **Entity Details - Void's Wake Location**
*"Let's get comprehensive details about this location..."*

**What happens:**
- Retrieves full entity profile including summary, properties, metadata
- Shows how the system automatically categorizes and describes entities

**Key points:**
- **LLM-generated summary** from multiple text sources
- **Structured metadata** (Region: Salandrian, Location Type, etc.)
- **Automatic categorization** and labeling

### 4. **Entity Relationships - Void's Wake (Thin List)** 
*"Here's where our scalable architecture really shines..."*

**What happens:**
- Lists **82 relationships** for Void's Wake (previously would crash!)
- Shows lightweight view: relationship IDs, types, connected entity names
- No heavy property loading - fast and reliable

**Key points:**
- **Scalable architecture:** Handles entities with 100+ relationships
- **Progressive enhancement:** List first, then drill down for details
- **Relationship directions:** Shows both outgoing (→) and incoming (←) connections
- **Performance:** Loads instantly despite high relationship count

### 5. **Relationship Details - Deep Dive**
*"Now let's get the full details for a specific relationship..."*

**What happens:**
- Uses relationship ID from the list to get comprehensive details
- Shows full properties, timestamps, episodes, and metadata
- Demonstrates the two-step progressive enhancement pattern

**Key points:**
- **Rich properties:** Episodes, creation dates, facts, embeddings
- **Source & target details:** Full entity information
- **On-demand loading:** Only fetch details when needed
- **Same pattern as episodes:** List → details when interested

### 6. **Advanced GraphRAG - Timeline Query**
*"Let's query historical timeline data..."*

**What happens:**
- Semantic search across timeline/historical content
- Graph traversal finds related historical entities and events
- Demonstrates domain-specific knowledge retrieval

**Key points:**
- Shows how the system handles different content types (timeline vs. narrative)
- Discovers connections between historical events and entities
- Maintains coherent world-building across different document types

### 6. **System Stats**
*"Here's the scale we're working with..."*

**What happens:**
- Shows current system metrics and knowledge base size
- Demonstrates system health and capabilities

**Key points:**
- Built from just **4 canonical documents** 
- Generated **172 episodic chunks** with intelligent overlap
- Extracted **200 entities** and **1,376 relationships** automatically
- Shows how much knowledge can be extracted from limited source material

## Technical Architecture Highlights

### **Hybrid Approach Benefits:**
- **Semantic Search:** Finds relevant content by meaning, not just keywords
- **Graph Traversal:** Discovers indirect connections and broader context  
- **Combined Power:** More comprehensive results than either approach alone

### **Pipeline Intelligence:**
- **Smart Chunking:** 450-character episodes with 75-character overlap
- **Automatic Entity Extraction:** LLM identifies entities, relationships, and types
- **Episode Linking:** Neo4j entities link back to PostgreSQL text chunks via UUIDs

### **Production Features:**
- **Error Handling:** Graceful failures, continues processing despite individual errors
- **Thin Architecture:** Progressive enhancement pattern prevents buffer overflows
- **Scalability:** Handles entities with 100+ relationships without performance issues

### **Thin Relationships Architecture:**
- **List First:** Lightweight endpoint returns relationship IDs and basic info only
- **Details On Demand:** Separate endpoint for full relationship properties when needed
- **No Serialization Crashes:** Heavy properties loaded only when requested
- **Same Pattern:** Mirrors episode architecture (list → details when interested)

## Demo Questions to Address

**Q: "How accurate is the entity extraction?"**
A: Show entity details - LLM-generated summaries are quite sophisticated, properly identifying roles, relationships, and context.

**Q: "How does this compare to traditional RAG?"**  
A: Traditional RAG only finds similar text. Our system also discovers *why* things are related through the knowledge graph.

**Q: "What about hallucinations?"**
A: All responses are grounded in source text chunks. The graph relationships are extracted from actual document content, not generated.

**Q: "How does it scale?"**
A: Currently 4 documents → 200 entities. Each document exponentially increases the knowledge graph density.

**Q: "What about entities with many relationships?"**
A: Our thin architecture handles this perfectly - Void's Wake has 82 relationships and loads instantly. We list relationships first, then get details on demand.

## Key Demo Success Metrics
- ✅ Rich, contextual responses with entity relationships
- ✅ Accurate entity extraction and categorization  
- ✅ Stable performance with complex queries
- ✅ Graceful handling of edge cases (large relationship sets)
- ✅ Demonstrable knowledge graph connections

## Follow-up Opportunities
- **Expansion:** Adding more canonical documents exponentially increases graph density
- **Query Complexity:** Multi-hop reasoning across entity relationships
- **Domain Expertise:** Specialized knowledge extraction for world-building
- **Integration:** MCP protocol enables Claude Code integration