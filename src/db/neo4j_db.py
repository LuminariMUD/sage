"""Neo4j graph database connection manager."""

import os
import re
from typing import Any

from dotenv import load_dotenv
from neo4j import AsyncDriver, AsyncGraphDatabase

load_dotenv()

_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Neo4jDB:
    """Neo4j graph database manager with async support."""

    def __init__(self):
        self.driver: AsyncDriver | None = None
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")

        # Validate required credentials - no defaults for security
        self.user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")

        if not self.user:
            raise ValueError(
                "NEO4J_USER environment variable is required. "
                "Set it in your .env file or environment."
            )
        if not password:
            raise ValueError(
                "NEO4J_PASSWORD environment variable is required. "
                "Set it in your .env file or environment."
            )

    @staticmethod
    def _validate_identifier(value: str, kind: str) -> str:
        """Validate labels, relationship types, and property names used in Cypher."""
        if not _CYPHER_IDENTIFIER.fullmatch(value):
            raise ValueError(f"Invalid {kind}")
        return value

    async def connect(self) -> None:
        """Create Neo4j driver connection."""
        if not self.driver:
            password = os.getenv("NEO4J_PASSWORD")
            if not password:
                raise ValueError("NEO4J_PASSWORD environment variable is required")
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60,
            )
            # Verify connectivity
            await self.driver.verify_connectivity()

    async def disconnect(self) -> None:
        """Close Neo4j driver connection."""
        if self.driver:
            await self.driver.close()
            self.driver = None

    async def execute_query(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results."""
        if not self.driver:
            await self.connect()

        async with self.driver.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def create_node(self, labels: list[str], properties: dict[str, Any]) -> dict[str, Any]:
        """Create a node with given labels and properties."""
        labels_str = ":".join(self._validate_identifier(label, "node label") for label in labels)
        query = f"""
            CREATE (n:{labels_str} $props)
            RETURN n
        """
        result = await self.execute_query(query, {"props": properties})
        return result[0]["n"] if result else {}

    async def create_relationship(
        self, from_id: str, to_id: str, rel_type: str, properties: dict[str, Any] | None = None
    ) -> bool:
        """Create a relationship between two nodes."""
        safe_rel_type = self._validate_identifier(rel_type, "relationship type")
        query = f"""
            MATCH (a {{stable_id: $from_id}})
            MATCH (b {{stable_id: $to_id}})
            CREATE (a)-[r:{safe_rel_type} $props]->(b)
            RETURN r
        """
        result = await self.execute_query(
            query, {"from_id": from_id, "to_id": to_id, "props": properties or {}}
        )
        return bool(result)

    async def find_node(
        self,
        stable_id: str | None = None,
        labels: list[str] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Find a node by ID, labels, or properties."""
        conditions = []
        params = {}

        if stable_id:
            conditions.append("n.stable_id = $stable_id")
            params["stable_id"] = stable_id

        if labels:
            label_str = ":".join(self._validate_identifier(label, "node label") for label in labels)
            query_start = f"MATCH (n:{label_str})"
        else:
            query_start = "MATCH (n)"

        if properties:
            for key, value in properties.items():
                safe_key = self._validate_identifier(key, "property name")
                conditions.append(f"n.{safe_key} = ${safe_key}")
                params[safe_key] = value

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"{query_start}{where_clause} RETURN n LIMIT 1"

        result = await self.execute_query(query, params)
        return result[0]["n"] if result else None

    async def get_relationships(
        self, node_id: str, rel_type: str | None = None, direction: str = "both"
    ) -> list[dict[str, Any]]:
        """Get relationships for a node."""
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("Invalid relationship direction")
        safe_rel_type = (
            self._validate_identifier(rel_type, "relationship type") if rel_type else None
        )
        if direction == "outgoing":
            pattern = f"(n)-[r{':' + safe_rel_type if safe_rel_type else ''}]->(m)"
        elif direction == "incoming":
            pattern = f"(n)<-[r{':' + safe_rel_type if safe_rel_type else ''}]-(m)"
        else:  # both
            pattern = f"(n)-[r{':' + safe_rel_type if safe_rel_type else ''}]-(m)"

        query = f"""
            MATCH {pattern}
            WHERE n.stable_id = $node_id
            RETURN r, m
        """

        return await self.execute_query(query, {"node_id": node_id})

    async def init_schema(self, schema_file: str) -> None:
        """Initialize Neo4j schema from Cypher file."""
        with open(schema_file) as f:
            schema_cypher = f.read()

        # Split by semicolons and execute each statement
        statements = [s.strip() for s in schema_cypher.split(";") if s.strip()]
        for statement in statements:
            if statement and not statement.startswith("//"):
                await self.execute_query(statement)

    async def clear_database(self) -> None:
        """Clear all nodes and relationships (use with caution!)."""
        await self.execute_query("MATCH (n) DETACH DELETE n")

    async def get_relationship_full_data(self, relationship_id: str) -> dict[str, Any] | None:
        """Get complete relationship data including all properties for backup."""
        query = """
        MATCH (source)-[r]->(target)
        WHERE elementId(r) = $rel_id
        RETURN elementId(r) as id,
               type(r) as type,
               properties(r) as properties,
               elementId(source) as source_id,
               source.name as source_name,
               labels(source) as source_labels,
               elementId(target) as target_id,
               target.name as target_name,
               labels(target) as target_labels
        """

        result = await self.execute_query(query, {"rel_id": relationship_id})
        return result[0] if result else None

    async def delete_relationship_by_id(self, relationship_id: str) -> bool:
        """Delete relationship by element ID."""
        query = "MATCH ()-[r]->() WHERE elementId(r) = $id DELETE r RETURN count(r) as deleted"
        result = await self.execute_query(query, {"id": relationship_id})
        return result[0]["deleted"] > 0 if result else False

    async def update_relationship_property(
        self, relationship_id: str, property_name: str, property_value: Any
    ) -> bool:
        """Update a single property of a relationship."""
        safe_property_name = self._validate_identifier(property_name, "property name")
        query = f"""
        MATCH ()-[r]->()
        WHERE elementId(r) = $rel_id
        SET r.{safe_property_name} = $value
        RETURN count(r) as updated
        """

        result = await self.execute_query(
            query, {"rel_id": relationship_id, "value": property_value}
        )
        return result[0]["updated"] > 0 if result else False

    async def restore_relationship(
        self, source_id: str, target_id: str, rel_type: str, properties: dict[str, Any]
    ) -> bool:
        """Restore a relationship with all its original properties."""
        safe_rel_type = self._validate_identifier(rel_type, "relationship type")
        query = f"""
        MATCH (source), (target)
        WHERE elementId(source) = $source_id AND elementId(target) = $target_id
        CREATE (source)-[r:{safe_rel_type}]->(target)
        SET r += $props
        RETURN r
        """

        result = await self.execute_query(
            query, {"source_id": source_id, "target_id": target_id, "props": properties}
        )
        return bool(result)

    async def bulk_update_relationship_properties(self, updates: list[dict[str, Any]]) -> int:
        """Bulk update relationship properties for efficiency."""
        if not updates:
            return 0

        updated_count = 0
        for update in updates:
            success = await self.update_relationship_property(
                update["relationship_id"], update["property_name"], update["property_value"]
            )
            if success:
                updated_count += 1

        return updated_count


# Global database instance
_neo4j_db: Neo4jDB | None = None


async def get_neo4j_db() -> Neo4jDB:
    """Get or create the global Neo4j database instance."""
    global _neo4j_db
    if _neo4j_db is None:
        _neo4j_db = Neo4jDB()
        await _neo4j_db.connect()
    return _neo4j_db


async def close_neo4j_db() -> None:
    """Close the global Neo4j database connection."""
    global _neo4j_db
    if _neo4j_db:
        await _neo4j_db.disconnect()
        _neo4j_db = None
