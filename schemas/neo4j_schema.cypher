// Neo4j Schema for Luminari Sage
// Native graph database for entities and relationships

// ============================================
// CONSTRAINTS & INDEXES
// ============================================

// Unique constraints ensure data integrity
CREATE CONSTRAINT entity_stable_id IF NOT EXISTS
FOR (e:Entity) REQUIRE e.stable_id IS UNIQUE;

CREATE CONSTRAINT deity_name IF NOT EXISTS
FOR (d:Deity) REQUIRE d.name IS UNIQUE;

CREATE CONSTRAINT location_name IF NOT EXISTS
FOR (l:Location) REQUIRE l.name IS UNIQUE;

CREATE CONSTRAINT faction_name IF NOT EXISTS
FOR (f:Faction) REQUIRE f.name IS UNIQUE;

// Indexes for performance
CREATE INDEX entity_type IF NOT EXISTS
FOR (e:Entity) ON (e.type);

CREATE INDEX entity_name IF NOT EXISTS
FOR (e:Entity) ON (e.name);

CREATE INDEX event_date IF NOT EXISTS
FOR (e:Event) ON (e.date);

CREATE INDEX lore_canonical IF NOT EXISTS
FOR (l:LoreNode) ON (l.canonical);

// Full-text search indexes
CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
FOR (e:Entity) ON EACH [e.name, e.description, e.aliases];

CREATE FULLTEXT INDEX lore_search IF NOT EXISTS
FOR (l:LoreNode) ON EACH [l.title, l.summary];

// ============================================
// NODE LABELS & PROPERTIES
// ============================================

// Base Entity (inherited by all entity types)
// :Entity {
//   stable_id: String!        // ULID/KSUID
//   name: String!
//   aliases: [String]
//   description: String
//   created_at: DateTime!
//   updated_at: DateTime!
//   confidence: Float         // 0-100 confidence score
//   canonical: Boolean
//   attrs: Map                // Flexible attributes
// }

// Specific Entity Types (inherit from Entity)
// :Deity:Entity
// :Location:Entity
// :Faction:Entity
// :Character:Entity
// :Item:Entity
// :Race:Entity
// :Concept:Entity

// Deity-specific properties
// :Deity {
//   portfolio: [String]       // Domains of influence
//   alignment: String
//   symbol: String
//   realm: String
// }

// Location-specific properties
// :Location {
//   coordinates: Point
//   region: String
//   terrain_type: String
//   population: Integer
// }

// Event nodes for timeline
// :Event {
//   id: String!
//   name: String!
//   date: String!            // In-world date
//   age: String              // Age/Era name
//   description: String
//   impact: String           // major|moderate|minor
//   canonical: Boolean
// }

// Lore document nodes
// :LoreNode {
//   id: String!
//   title: String!
//   summary: String
//   source_file: String!     // Original markdown file
//   canonical: Boolean
//   created_at: DateTime!
//   updated_at: DateTime!
//   word_count: Integer
//   chunk_ids: [String]      // References to PostgreSQL chunks
// }

// ============================================
// RELATIONSHIP TYPES
// ============================================

// Religious/Divine Relations
// (:Character)-[:WORSHIPS]->(:Deity)
// (:Faction)-[:PATRON_DEITY]->(:Deity)
// (:Deity)-[:ALLIED_WITH]->(:Deity)
// (:Deity)-[:OPPOSED_TO]->(:Deity)

// Organizational Relations
// (:Character)-[:MEMBER_OF]->(:Faction)
// (:Character)-[:LEADS]->(:Faction)
// (:Faction)-[:ALLIED_WITH]->(:Faction)
// (:Faction)-[:AT_WAR_WITH]->(:Faction)
// (:Faction)-[:SUBSIDIARY_OF]->(:Faction)

// Geographic Relations
// (:Entity)-[:LOCATED_IN]->(:Location)
// (:Location)-[:PART_OF]->(:Location)
// (:Location)-[:CONNECTED_TO {distance: Float, travel_time: String}]->(:Location)
// (:Location)-[:BORDERS]->(:Location)

// Temporal Relations
// (:Event)-[:PRECEDED_BY]->(:Event)
// (:Event)-[:CAUSED]->(:Event)
// (:Entity)-[:PARTICIPATED_IN]->(:Event)
// (:Event)-[:OCCURRED_AT]->(:Location)

// Item Relations
// (:Character)-[:POSSESSES]->(:Item)
// (:Item)-[:CREATED_BY]->(:Entity)
// (:Item)-[:ENCHANTED_BY]->(:Deity)
// (:Location)-[:CONTAINS]->(:Item)

// Knowledge Relations
// (:Entity)-[:MENTIONED_IN {confidence: Float, span: String}]->(:LoreNode)
// (:Entity)-[:RELATED_TO {relation_type: String}]->(:Entity)
// (:LoreNode)-[:REFERENCES]->(:LoreNode)
// (:LoreNode)-[:CONTRADICTS]->(:LoreNode)

// Meta Relations (for knowledge graph management)
// (:Entity)-[:SAME_AS {confidence: Float}]->(:Entity)  // Entity resolution
// (:Entity)-[:VARIANT_OF]->(:Entity)  // Name variants
// (:Entity)-[:SUPERSEDED_BY]->(:Entity)  // Version tracking

// ============================================
// EXAMPLE QUERIES
// ============================================

// Find all deities and their followers
// MATCH (c:Character)-[:WORSHIPS]->(d:Deity)
// RETURN d.name, collect(c.name) as followers

// Get entity with all relationships
// MATCH (e:Entity {stable_id: $id})
// OPTIONAL MATCH (e)-[r]-(connected)
// RETURN e, collect({type: type(r), node: connected}) as relationships

// Find lore contradictions
// MATCH (l1:LoreNode)-[:CONTRADICTS]-(l2:LoreNode)
// WHERE l1.canonical = true
// RETURN l1.title, l2.title, l1.source_file, l2.source_file

// Timeline traversal
// MATCH path = (e1:Event)-[:PRECEDED_BY*1..5]->(e2:Event)
// WHERE e1.age = 'Age of Mortals'
// RETURN path

// Geographic pathfinding
// MATCH path = shortestPath(
//   (start:Location {name: 'Ashenport'})-[:CONNECTED_TO*]-(end:Location {name: 'Hir-Pesh'})
// )
// RETURN path, reduce(dist = 0, r IN relationships(path) | dist + r.distance) as total_distance

// Entity resolution check
// MATCH (e1:Entity)-[:SAME_AS]-(e2:Entity)
// WHERE e1.confidence < 80
// RETURN e1.name, e2.name, e1.confidence

// ============================================
// GRAPHITI INTEGRATION SUPPORT
// ============================================

// Graphiti-specific properties for episodic memory
// :Episode {
//   id: String!
//   timestamp: DateTime!
//   content: String!
//   entities: [String]       // Entity IDs involved
//   embeddings_ref: String   // Reference to PostgreSQL
// }

// (:Episode)-[:CONTAINS]->(:Entity)
// (:Episode)-[:PREVIOUS]->(:Episode)
// (:Episode)-[:DERIVED_FROM]->(:LoreNode)
