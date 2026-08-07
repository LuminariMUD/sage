"""Graphiti integration for knowledge graph management."""

import logging
import os
import re
from datetime import datetime
from typing import Any

from rich.console import Console

from src.security import install_sensitive_logging, redact_sensitive_text

# Disable excessive debug logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("graphiti_core").setLevel(logging.WARNING)
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)
console = Console()
_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_cypher_identifier(value: object, kind: str) -> str:
    """Allow only plain identifiers in Cypher positions that cannot be bound."""
    if not isinstance(value, str) or not _CYPHER_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {kind}")
    return value


# Allow network requests for model downloading
# os.environ['HF_HUB_OFFLINE'] = '1'
# os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from src.graphiti.policy_graphiti import PolicyGraphiti

# graphiti-core names the episode node type EpisodicNode (older releases used EpisodeNode)
try:
    from graphiti_core.nodes import EpisodicNode as EpisodeNode
except ImportError:  # pragma: no cover - very old graphiti-core
    from graphiti_core.nodes import EpisodeNode

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


class LuminariGraphiti:
    """Graphiti wrapper for Luminari Sage knowledge graph."""

    def __init__(
        self,
        neo4j_uri: str | None = None,
        neo4j_user: str | None = None,
        neo4j_password: str | None = None,
        llm_client: Any | None = None,
        embedder: Any | None = None,
        verbose: bool = False,
    ):
        """Initialize Graphiti for Luminari Sage."""
        # Get configuration from environment if not provided
        resolved_neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        resolved_neo4j_user = neo4j_user or os.getenv("NEO4J_USER", "neo4j")
        resolved_neo4j_password = neo4j_password or os.getenv("NEO4J_PASSWORD")
        self.verbose = verbose

        # Use provided clients or get from ollama_config
        if embedder is None or llm_client is None:
            from .ollama_config import get_graphiti_config_summary

            # Show configuration summary
            config_summary = get_graphiti_config_summary()
            if verbose:
                console.print("[cyan]🔧 Graphiti Configuration:[/cyan]")
                console.print(f"  Provider: {config_summary['provider']}")
                console.print(f"  Embedding Dimension: {config_summary['embedding_dim']}")

        if embedder is None:
            from .ollama_config import get_graphiti_embedding_client

            embedder = get_graphiti_embedding_client(verbose=verbose)
            logger.info("🚀 Initialized embedding client from ollama_config")

        if llm_client is None:
            from .ollama_config import get_graphiti_llm_client

            llm_client = get_graphiti_llm_client(verbose=verbose)
            logger.info("🚀 Initialized LLM client from ollama_config")

        self.embedder = embedder

        # Set logging to INFO level to reduce noise
        logging.basicConfig(level=logging.INFO)
        install_sensitive_logging()
        openai_logger = logging.getLogger("openai")
        openai_logger.setLevel(logging.WARNING)

        # Initialize Graphiti with configured clients
        self.graphiti = PolicyGraphiti(
            uri=resolved_neo4j_uri,
            user=resolved_neo4j_user,
            password=resolved_neo4j_password,
            embedder=self.embedder,
            llm_client=llm_client,
        )

        # Add LLM logging to see what relationship types are being generated
        original_generate = self.graphiti.llm_client.generate_response
        max_output_tokens = max(
            256,
            int(
                getattr(
                    llm_client,
                    "max_tokens",
                    os.getenv("GRAPHITI_MAX_OUTPUT_TOKENS", "4096"),
                )
            ),
        )

        async def logged_generate_response(*args, **kwargs):
            try:
                # Keep each structured response within the resolved provider budget.
                # Cloud and local routes intentionally resolve different ceilings.
                if len(args) >= 3 and args[2] is not None:
                    args = (*args[:2], min(args[2], max_output_tokens), *args[3:])
                else:
                    requested_tokens = kwargs.get("max_tokens")
                    kwargs["max_tokens"] = (
                        max_output_tokens
                        if requested_tokens is None
                        else min(requested_tokens, max_output_tokens)
                    )

                # Only show debug output in verbose mode
                if self.verbose:
                    # Log the prompt being sent to the LLM
                    prompt_content = ""
                    if args and len(args) > 0:
                        for arg in args:
                            if hasattr(arg, "__iter__") and not isinstance(arg, str):
                                for item in arg:
                                    if hasattr(item, "content"):
                                        prompt_content += str(item.content) + " "

                    # Determine prompt type
                    if "extract entity nodes" in prompt_content or "ENTITY TYPES" in prompt_content:
                        console.print(
                            "[blue]🔍 ENTITY EXTRACTION PROMPT (skipping for brevity)[/blue]"
                        )
                    elif (
                        "relationship" in prompt_content.lower() or "edge" in prompt_content.lower()
                    ):
                        console.print(
                            "[magenta]🔗 Relationship extraction prompt submitted[/magenta]"
                        )
                    else:
                        console.print("[yellow]🤖 LLM prompt submitted[/yellow]")

                response = await original_generate(*args, **kwargs)

                # Only show responses in verbose mode
                if self.verbose:
                    response_str = str(response)

                    # Check if this is an entity extraction response
                    if "extracted_entities" in response_str:
                        console.print("[green]🔍 LLM ENTITY EXTRACTION:[/green]")
                        # Just show count, not full response since it's working
                        import json

                        try:
                            if hasattr(response, "model_dump_json"):
                                resp_dict = json.loads(response.model_dump_json())
                            elif hasattr(response, "dict"):
                                resp_dict = response.dict()
                            else:
                                resp_dict = json.loads(response_str)
                            entity_count = len(resp_dict.get("extracted_entities", []))
                            console.print(f"  Extracted {entity_count} entities")
                        except Exception:
                            console.print("  Entity response received (count unavailable)")

                    # Check if this is a relationship extraction response
                    elif any(
                        keyword in response_str
                        for keyword in [
                            "relationships",
                            "relation_type",
                            "source_entity",
                            "target_entity",
                            "RELATES_TO",
                            "MENTIONS",
                            "OpposedTo",
                            "Influences",
                            "Protects",
                            "Embodies",
                        ]
                    ):
                        console.print("[cyan]🔗 LLM RELATIONSHIP EXTRACTION:[/cyan]")

                        # Count mentions of our 4 custom edge types vs basic types
                        our_edge_types = ["OpposedTo", "Influences", "Protects", "Embodies"]
                        custom_mentions = sum(
                            response_str.count(edge_type) for edge_type in our_edge_types
                        )
                        mentions_count = response_str.count("MENTIONS")
                        relates_count = response_str.count("relates_to") + response_str.count(
                            "RELATES_TO"
                        )

                        console.print(f"  Our 4 custom edge types used: {custom_mentions}")
                        console.print(f"  MENTIONS used: {mentions_count}")
                        console.print(f"  RELATES_TO used: {relates_count}")

                        # Show specific counts for each of our types
                        for edge_type in our_edge_types:
                            count = response_str.count(edge_type)
                            if count > 0:
                                console.print(f"    {edge_type}: {count}")

                return response
            except Exception as e:
                if self.verbose:
                    console.print(f"[red]❌ LLM error type:[/red] {type(e).__name__}")
                raise

        self.graphiti.llm_client.generate_response = logged_generate_response

        # Create separate driver for our own operations
        self.driver = AsyncGraphDatabase.driver(
            resolved_neo4j_uri,
            auth=(resolved_neo4j_user, resolved_neo4j_password),
        )

        logger.info(
            "Initialized Graphiti with Neo4j at %s",
            redact_sensitive_text(resolved_neo4j_uri),
        )

    async def close(self):
        """Close connections."""
        if hasattr(self, "driver"):
            await self.driver.close()
        llm_client = getattr(getattr(self, "graphiti", None), "llm_client", None)
        close = getattr(llm_client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
        else:
            transport = getattr(llm_client, "client", None)
            transport_close = getattr(transport, "close", None)
            if callable(transport_close):
                result = transport_close()
                if hasattr(result, "__await__"):
                    await result

    async def add_episode_with_lore_relationships(
        self,
        content: str,
        source_file: str,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ) -> EpisodeNode:
        """Add an episode with comprehensive fantasy lore relationship types."""
        from graphiti_core.nodes import EpisodeType

        from .edge_types import EDGE_TYPES
        from .entity_types import ENTITY_TYPES

        timestamp = timestamp or datetime.now()

        # Use comprehensive edge types (14 types total)
        edge_types = EDGE_TYPES

        # Use comprehensive entity types (13 types total)
        entity_types = ENTITY_TYPES

        # Define comprehensive edge type map covering all entity type combinations
        # Helper: central rule-based mapping to reduce duplication & fix earlier logical issues
        def build_edge_type_map(entity_names_list):
            edge_map = {}

            command_edges = ["Commands", "ServesUnder"]
            social_edges = ["AlliedWith", "OpposedTo", "Influences"]
            lineage_edges = ["DescendedFrom", "TransformedInto"]
            transformation_edges = ["TransformedInto", "CreatedBy"]
            binding_edges = ["BoundTo", "Protects", "Corrupts"]
            power_flow_edges = ["Channels", "Amplifies", "Counters"]
            teaching_edges = ["TeachesTo", "Influences"]
            representation_edges = ["Embodies"]
            temporal_edges = ["Precedes", "Causes", "Fulfills"]
            geographic_edges = ["Borders", "Contains", "ConnectsTo"]

            for s in entity_names_list:
                for t in entity_names_list:
                    key = (s, t)
                    edges: list[str] = []

                    if s == "Deity":
                        if t == "Deity":
                            edges = (
                                social_edges
                                + binding_edges
                                + representation_edges
                                + power_flow_edges
                            )
                        elif t in ["Person", "Organization", "Faction"]:
                            edges = [
                                "Influences",
                                "Protects",
                                "Commands",
                                "Corrupts",
                                "Channels",
                                "Fulfills",
                            ]
                        elif t in ["Race", "Creature"]:
                            edges = ["CreatedBy", "Influences", "Protects", "Corrupts", "Channels"]
                        elif t in ["Location", "Realm"]:
                            edges = ["Protects", "Embodies", "Channels"]
                        elif t in ["Concept", "Magic"]:
                            edges = ["Embodies", "Influences", "Channels", "Amplifies"]
                        elif t == "Prophecy":
                            edges = ["Embodies", "Influences", "Fulfills"]
                        elif t in ["Artifact", "Event"]:
                            edges = ["CreatedBy", "Influences", "Channels", "Causes", "Fulfills"]

                    elif s == "Person":
                        if t == "Person":
                            edges = social_edges + teaching_edges + ["DescendedFrom"]
                        elif t == "Deity":
                            edges = [
                                "ServesUnder",
                                "OpposedTo",
                                "Influences",
                                "Channels",
                                "Fulfills",
                            ]
                        elif t in ["Organization", "Faction"]:
                            edges = command_edges + social_edges
                        elif t == "Race":
                            edges = ["DescendedFrom", "TransformedInto"]
                        elif t in ["Location", "Realm"]:
                            edges = ["Protects", "ConnectsTo"]
                        elif t == "Artifact":
                            edges = ["CreatedBy", "BoundTo", "Channels"]
                        elif t == "Magic":
                            edges = ["TeachesTo", "Channels", "Amplifies"]
                        elif t == "Creature":
                            edges = ["OpposedTo", "Commands", "Protects"]
                        elif t == "Concept":
                            edges = ["Embodies", "Influences"]
                        elif t == "Prophecy":
                            edges = ["Fulfills", "Influences"]
                        elif t == "Event":
                            edges = ["Causes", "Precedes", "Influences"]

                    elif s == "Organization":
                        if t == "Organization":
                            edges = social_edges
                        elif t in ["Deity", "Person"]:
                            edges = ["ServesUnder", "Influences", "Commands"]
                        elif t == "Faction":
                            edges = [*social_edges, "OpposedTo"]
                        elif t in ["Location", "Artifact"]:
                            edges = ["Protects", "CreatedBy"]
                        elif t == "Magic":
                            edges = ["TeachesTo", "Channels", "Amplifies"]
                        elif t == "Concept":
                            edges = ["Embodies", "Influences"]
                        elif t == "Event":
                            edges = ["Causes", "Precedes", "Influences"]
                        elif t == "Prophecy":
                            edges = ["Fulfills", "Influences"]

                    elif s == "Race":
                        if t == "Race":
                            edges = social_edges + lineage_edges
                        elif t in ["Person", "Creature"]:
                            edges = lineage_edges
                        elif t == "Deity":
                            edges = ["ServesUnder", "Influences"]
                        elif t == "Location":
                            edges = ["Contains", "Protects"]
                        elif t == "Magic":
                            edges = ["Influences", "Embodies"]
                        elif t == "Artifact":
                            edges = ["CreatedBy", "Influences"]
                        elif t == "Event":
                            edges = ["TransformedInto", "Precedes"]

                    elif s == "Faction":
                        if t == "Faction":
                            edges = social_edges
                        elif t in ["Person", "Organization"]:
                            edges = command_edges + social_edges
                        elif t in ["Location", "Artifact"]:
                            edges = ["Protects", "Commands"]
                        elif t == "Event":
                            edges = ["Causes", "Precedes", "Influences"]
                        else:
                            edges = ["Influences", "OpposedTo"]

                    elif s == "Location":
                        if t == "Location":
                            edges = [*geographic_edges, "OpposedTo"]
                        elif t == "Realm":
                            edges = ["ConnectsTo", "Contains"]
                        elif t in ["Artifact", "Creature", "Person", "Organization", "Faction"]:
                            edges = ["Contains", "Protects"]
                        elif t == "Event":
                            edges = ["Precedes", "Influences"]
                        else:
                            edges = ["Influences", "ConnectsTo"]

                    elif s == "Creature":
                        if t == "Creature":
                            edges = social_edges + transformation_edges
                        elif t in ["Person", "Race"]:
                            edges = ["OpposedTo", "TransformedInto"]
                        elif t == "Location":
                            edges = ["Protects", "Contains"]
                        elif t == "Artifact":
                            edges = ["BoundTo", "Influences"]
                        else:
                            edges = ["Embodies", "Influences"]

                    elif s == "Magic":
                        if t == "Magic":
                            edges = ["Amplifies", "Counters", "Influences"]
                        elif t in ["Person", "Creature"]:
                            edges = ["TeachesTo", "Channels", "Amplifies"]
                        elif t == "Artifact":
                            edges = ["Channels", "CreatedBy", "Amplifies"]
                        elif t == "Location":
                            edges = ["Channels", "Influences"]
                        elif t == "Concept":
                            edges = ["Embodies", "Influences", "Amplifies"]
                        elif t == "Prophecy":
                            edges = ["Fulfills", "Influences"]
                        else:
                            edges = ["Influences", "Amplifies"]

                    elif s == "Artifact":
                        if t == "Artifact":
                            edges = [*social_edges, "Amplifies"]
                        elif t in ["Person", "Creature"]:
                            edges = ["BoundTo", "Influences", "Channels"]
                        elif t == "Location":
                            edges = ["Contains", "Protects"]
                        elif t == "Magic":
                            edges = ["Channels", "Amplifies"]
                        elif t == "Event":
                            edges = ["Causes", "Precedes", "Influences"]
                        else:
                            edges = ["Embodies", "Influences"]

                    elif s == "Event":
                        if t == "Event":
                            edges = [*temporal_edges, "OpposedTo"]
                        elif t in ["Person", "Organization", "Faction"]:
                            edges = ["Influences", "Causes", "Precedes"]
                        elif t in ["Location", "Artifact"]:
                            edges = ["Influences", "Precedes", "ConnectsTo"]
                        elif t == "Prophecy":
                            edges = ["Fulfills", "Precedes"]
                        elif t == "Magic":
                            edges = ["Causes", "Influences"]
                        else:
                            edges = ["Influences", "Precedes"]

                    elif s == "Concept":
                        if t == "Concept":
                            edges = social_edges + representation_edges
                        elif t == "Magic":
                            edges = ["Influences", "Embodies", "Amplifies"]
                        elif t in ["Person", "Organization", "Faction"]:
                            edges = ["Influences", "Embodies"]
                        elif t == "Prophecy":
                            edges = ["Fulfills", "Influences"]
                        else:
                            edges = ["Influences", "Embodies"]

                    elif s == "Prophecy":
                        if t == "Event":
                            edges = ["Precedes", "Causes"]
                        elif t in ["Person", "Organization", "Faction", "Deity"]:
                            edges = ["Influences", "Fulfills"]
                        elif t == "Prophecy":
                            edges = ["Precedes", "Influences"]
                        else:
                            edges = ["Influences"]

                    elif s == "Realm":
                        if t == "Realm":
                            edges = [*geographic_edges, "ConnectsTo"]
                        elif t == "Location":
                            edges = geographic_edges
                        elif t in ["Deity", "Concept", "Magic"]:
                            edges = ["Embodies", "Influences", "Channels"]
                        else:
                            edges = ["Contains", "Influences"]

                    # Fallbacks
                    if not edges:
                        edges = ["Influences"]
                    edge_map[key] = edges

            # Generic fallback Entity->Entity includes every custom edge
            edge_map[("Entity", "Entity")] = list(edge_types.keys())
            return edge_map

        # Every extracted node also carries the base ``Entity`` label. A single
        # generic signature therefore enables all custom edge types while keeping
        # Graphiti's prompt small; enumerating all 169 type pairs added thousands
        # of repeated prompt tokens without changing validation behavior.
        edge_type_map = {("Entity", "Entity"): list(edge_types.keys())}

        # Add episode with rich relationship types
        try:
            # Debug: Check Graphiti version and capability (verbose only)
            if self.verbose:
                console.print("[blue]🔍 Graphiti Debug Info:[/blue]")
                console.print(f"  Graphiti object: {type(self.graphiti)}")
                console.print(f"  Has add_episode method: {hasattr(self.graphiti, 'add_episode')}")
                if hasattr(self.graphiti, "add_episode"):
                    import inspect

                    sig = inspect.signature(self.graphiti.add_episode)
                    console.print(f"  add_episode signature: {sig}")

                # Debug: print what we're sending to Graphiti
                console.print("[cyan]📊 Sending to Graphiti:[/cyan]")
                console.print(f"  Entity types: {len(entity_types)} types")
                console.print(f"  Edge types: {len(edge_types)} types")
                console.print(f"  Edge type map: {len(edge_type_map)} mappings")
                console.print(f"  Sample edge types: {list(edge_types.keys())}")
                console.print("  Sample edge_type_map entries:")
                for key, value in list(edge_type_map.items())[:5]:
                    console.print(f"    {key}: {value}")
                console.print("  Edge type classes:")
                for name, cls in edge_types.items():
                    console.print(
                        f"    {name}: {cls.__name__} - {cls.__doc__.strip() if cls.__doc__ else 'No description'}"
                    )

            # Add episode with our custom types
            max_entities = max(1, int(os.getenv("GRAPHITI_MAX_ENTITIES_PER_EPISODE", "25")))
            max_relationships = max(
                1, int(os.getenv("GRAPHITI_MAX_RELATIONSHIPS_PER_EPISODE", "25"))
            )
            extraction_instructions = (
                "Return only the most important facts from this episode. "
                f"Extract at most {max_entities} entities and at most "
                f"{max_relationships} relationships. "
                "Do not repeat equivalent entities or relationships."
            )
            if self.verbose:
                console.print(
                    "[yellow]🔄 Calling graphiti.add_episode with custom types...[/yellow]"
                )
            episode = await self.graphiti.add_episode(
                name=f"episode_{source_file}_{timestamp.isoformat()}",
                episode_body=content,
                source=EpisodeType.text,
                source_description=source_file,
                reference_time=timestamp,
                entity_types=entity_types,
                edge_types=edge_types,
                edge_type_map=edge_type_map,
                custom_extraction_instructions=extraction_instructions,
            )
            console.print("[green]✅ Episode created with custom types![/green]")

            # Debug: Check what relationships were actually created
            console.print("[green]✅ Episode created successfully[/green]")

            # Query Neo4j to see what relationship types were just added
            try:
                async with self.driver.session() as session:
                    # Get recent relationships (last 30 seconds)
                    recent_rels = await session.run("""
                        MATCH ()-[r]->()
                        WHERE r.created_at > datetime() - duration('PT30S')
                        RETURN DISTINCT type(r) as rel_type, COUNT(r) as count
                        ORDER BY count DESC
                        LIMIT 10
                    """)

                    console.print("[cyan]🔗 Recent relationships created:[/cyan]")
                    async for record in recent_rels:
                        rel_type = record["rel_type"]
                        count = record["count"]

                        # Highlight if we see our custom types vs basic types
                        if rel_type in ["RELATES_TO", "MENTIONS"]:
                            console.print(f"  [red]{rel_type}: {count}[/red] (basic type)")
                        elif rel_type in edge_types:
                            console.print(f"  [green]{rel_type}: {count}[/green] (custom type ✓)")
                        else:
                            console.print(f"  [yellow]{rel_type}: {count}[/yellow] (unknown type)")

            except Exception as debug_error:
                console.print(f"[yellow]Debug query failed ({type(debug_error).__name__})[/yellow]")
        except Exception as e:
            # Inspect the error only to preserve the compatibility fallback. Never
            # print the raw message because SDK errors can contain request data.
            error_str = str(e)

            console.print("\n[red]Episode creation failed[/red]")
            console.print(f"[red]Error Type: {type(e).__name__}[/red]")

            # Check if this is an API compatibility issue with custom edge types
            if "unexpected keyword argument" in error_str:
                console.print(
                    "[yellow]📋 API compatibility issue - trying without custom edge types[/yellow]"
                )
                try:
                    episode = await self.graphiti.add_episode(
                        name=f"episode_{source_file}_{timestamp.isoformat()}",
                        episode_body=content,
                        source=EpisodeType.text,
                        source_description=source_file,
                        reference_time=timestamp,
                        entity_types=entity_types,
                        custom_extraction_instructions=extraction_instructions,
                        # Try without edge_types and edge_type_map
                    )
                    console.print("[green]✅ Succeeded with basic configuration[/green]")
                except Exception as e2:
                    console.print(
                        f"[red]❌ Basic configuration also failed ({type(e2).__name__})[/red]"
                    )
                    raise e2
            else:
                raise

        # Set stable_id property for GraphRAG linkage if episode_uuid is provided in metadata
        if metadata and "episode_uuid" in metadata:
            episode_uuid = metadata["episode_uuid"]
            try:
                # Update the Episodic node with stable_id property
                # Try multiple strategies to find the correct episode
                strategies = [
                    # Strategy 1: Match by exact name format
                    f"episode_{source_file}_{timestamp.isoformat()}",
                    # Strategy 2: Match by source_description (exact)
                    source_file,
                    # Strategy 3: Match by source_description pattern (episode_<uuid>)
                    f"episode_{episode_uuid}",
                ]

                # Persist the rest of the caller's metadata alongside stable_id. Graphiti's
                # episode types have no metadata field, so these have to be set on the node.
                extra_props = {
                    k: v
                    for k, v in metadata.items()
                    if k != "episode_uuid" and isinstance(v, (str, int, float, bool))
                }

                updated_count = 0
                for strategy in strategies:
                    # Try to match by name or source_description
                    result = await self.driver.execute_query(
                        """
                        MATCH (ep:Episodic)
                        WHERE (ep.name = $match_value OR ep.source_description = $match_value)
                          AND ep.stable_id IS NULL
                        SET ep.stable_id = $stable_id
                        SET ep += $extra_props
                        RETURN COUNT(ep) as updated_count
                        """,
                        {
                            "match_value": strategy,
                            "stable_id": episode_uuid,
                            "extra_props": extra_props,
                        },
                    )

                    # Extract count based on Neo4j driver version
                    if hasattr(result, "records") and result.records:
                        count = result.records[0]["updated_count"]
                    elif result and len(result) > 0:
                        count = result[0]["updated_count"]
                    else:
                        count = 0

                    updated_count += count
                    if count > 0:
                        break  # Found and updated, no need to try other strategies

                if updated_count > 0:
                    if self.verbose:
                        console.print(
                            f"[cyan]🔗 Set stable_id for {updated_count} episode(s)[/cyan]"
                        )
                else:
                    if self.verbose:
                        console.print("[yellow]⚠️  Could not find episode for stable_id[/yellow]")

            except Exception as e:
                logger.warning("Failed to set stable_id for episode (%s)", type(e).__name__)

        logger.debug("Added episode with lore relationships")
        return episode

    async def add_relationship(
        self,
        source_name: str,
        target_name: str,
        relationship_type: str,
        properties: dict | None = None,
    ):
        """Add a relationship between two entities."""
        # This is a manual relationship addition - we'll use direct Neo4j
        # since Graphiti focuses on episode-based extraction

        properties = properties or {}
        safe_relationship_type = _validate_cypher_identifier(relationship_type, "relationship type")

        # Create relationship via direct Neo4j query
        cypher = (
            """
            MERGE (source:Entity {name: $source_name})
            MERGE (target:Entity {name: $target_name})
            MERGE (source)-[r:"""
            + safe_relationship_type
            + """]->(target)
            SET r += $properties
            RETURN r
        """
        )

        try:
            result = await self.driver.execute_query(
                cypher,
                {"source_name": source_name, "target_name": target_name, "properties": properties},
            )
            logger.debug("Added relationship")
            return result
        except Exception as e:
            logger.error("Failed to add relationship (%s)", type(e).__name__)
            raise


async def initialize_graphiti(
    neo4j_uri: str | None = None,
    neo4j_user: str | None = None,
    neo4j_password: str | None = None,
    verbose: bool = False,
    llm_client: Any | None = None,
    embedder: Any | None = None,
) -> LuminariGraphiti:
    """Initialize and return a configured Graphiti instance."""
    graphiti = LuminariGraphiti(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        verbose=verbose,
    )

    # Initialize Graphiti schema - use manual approach since build_indices_and_constraints is unreliable
    if verbose:
        logger.info("Creating Graphiti schema manually (bypassing build_indices_and_constraints)")
    try:
        async with graphiti.driver.session() as session:
            # Manually create the COMPLETE schema Graphiti expects
            schema_commands = [
                # Entity constraints and indexes
                "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (e:Entity) REQUIRE e.uuid IS UNIQUE",
                "CREATE INDEX entity_group_id IF NOT EXISTS FOR (e:Entity) ON (e.group_id)",
                "CREATE INDEX entity_created_at IF NOT EXISTS FOR (e:Entity) ON (e.created_at)",
                "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
                # Episodic constraints and indexes
                "CREATE CONSTRAINT episodic_uuid IF NOT EXISTS FOR (e:Episodic) REQUIRE e.uuid IS UNIQUE",
                "CREATE INDEX episodic_group_id IF NOT EXISTS FOR (e:Episodic) ON (e.group_id)",
                "CREATE INDEX episodic_valid_at IF NOT EXISTS FOR (e:Episodic) ON (e.valid_at)",
                "CREATE INDEX episodic_created_at IF NOT EXISTS FOR (e:Episodic) ON (e.created_at)",
                # Edge constraints
                "CREATE CONSTRAINT edge_uuid IF NOT EXISTS FOR (e:Edge) REQUIRE e.uuid IS UNIQUE",
                "CREATE CONSTRAINT episodic_edge_uuid IF NOT EXISTS FOR (e:EpisodicEdge) REQUIRE e.uuid IS UNIQUE",
                # Community constraints
                "CREATE CONSTRAINT community_uuid IF NOT EXISTS FOR (c:Community) REQUIRE c.uuid IS UNIQUE",
            ]

            if verbose:
                logger.info("🔧 Creating schema constraints and indexes...")
            for i, cmd in enumerate(schema_commands, 1):
                try:
                    await session.run(cmd)
                    if verbose:
                        logger.info(f"  ✅ [{i}/{len(schema_commands)}] {cmd[:50]}...")
                except Exception as cmd_error:
                    if verbose:
                        logger.warning(
                            "  ❌ [%s/%s] Schema command failed (%s)",
                            i,
                            len(schema_commands),
                            type(cmd_error).__name__,
                        )

            # Create fulltext indexes that Graphiti expects (Neo4j 5.x syntax)
            fulltext_commands = [
                "CREATE FULLTEXT INDEX node_name_and_summary IF NOT EXISTS FOR (n:Entity|Community) ON EACH [n.name, n.summary]",
                "CREATE FULLTEXT INDEX episodic_content IF NOT EXISTS FOR (n:Episodic) ON EACH [n.content]",
                # Relationship fulltext index - correct syntax for relationships
                "CREATE FULLTEXT INDEX edge_name_and_fact IF NOT EXISTS FOR ()-[r:Edge|EpisodicEdge]-() ON EACH [r.name, r.fact]",
            ]

            if verbose:
                logger.info("📝 Creating fulltext indexes...")
            for i, cmd in enumerate(fulltext_commands, 1):
                try:
                    await session.run(cmd)
                    if verbose:
                        logger.info(f"  ✅ [{i}/{len(fulltext_commands)}] Created fulltext index")
                except Exception as cmd_error:
                    if verbose:
                        logger.warning(
                            "  ❌ [%s/%s] Fulltext index failed (%s)",
                            i,
                            len(fulltext_commands),
                            type(cmd_error).__name__,
                        )

            # Schema created successfully - no test entities needed
            if verbose:
                logger.info("✅ Created comprehensive manual Graphiti-compatible schema")

    except Exception as e2:
        logger.error("Failed to create manual schema (%s)", type(e2).__name__)

    # Create indexes and constraints in Neo4j
    async with graphiti.driver.session() as session:
        # Create indexes for better performance
        await session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)")
        await session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.`type`)")
        await session.run(
            "CREATE INDEX entity_stable_id IF NOT EXISTS FOR (n:Entity) ON (n.stable_id)"
        )

        # Create indexes for Episodic nodes (critical for GraphRAG performance)
        await session.run(
            "CREATE INDEX episodic_stable_id IF NOT EXISTS FOR (ep:Episodic) ON (ep.stable_id)"
        )
        await session.run(
            "CREATE INDEX episodic_source_description IF NOT EXISTS FOR (ep:Episodic) ON (ep.source_description)"
        )

        # Create constraint for unique stable_id on entities
        try:
            await session.run(
                "CREATE CONSTRAINT entity_stable_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.stable_id IS UNIQUE"
            )
        except Exception:
            pass  # Constraint might already exist

        # Note: We don't create unique constraint on Episodic.stable_id since multiple episodes
        # might theoretically reference the same PostgreSQL episode in edge cases

    if verbose:
        logger.info("Graphiti initialized with indexes and constraints")
    return graphiti
