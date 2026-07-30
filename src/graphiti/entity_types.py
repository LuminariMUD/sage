"""Entity (node) type definitions for the Luminari Sage knowledge graph.

These Pydantic models describe the ontological surface that Graphiti will
use when transforming semantic "episodes" (chunked lore text) into a
validated graph. Descriptions give plain meaning plus concrete examples
drawn from `canon/` lore. Each field description uses the pattern:

<meaning / scope>. Examples: <example>, <example>, ...

Formatting constraints are intentionally minimal—focus on accurate capture
of the source lore; free-form text or lists are acceptable where helpful.
"""

from pydantic import BaseModel, Field


class Deity(BaseModel):
    """Divine or quasi‑divine entity with thematic domains and mortal anchors.

    Use for named powers (paired, merged, or triadic aspects included) that exert
    metaphysical influence and drive narrative stakes (vows, blessings, taboos,
    ascension arcs). Examples: Kordran; Aethyra; Seraphine; Nyxara; Pyrion;
    Calystral; Borhild; Nethris; Zorren.

    Narrative utility: grounding divine conflicts, quest patron motives, domain
    tension, and relic provenance.
    """

    portfolio: str | None = Field(
        None,
        description="Domains or aspects associated with the deity (comma + space separated; single value allowed). Exclude: follower groups, relic names, historical events. Examples: War, Duty; Magic, Oaths; Passion, Art; Death, Fate; Wild Hunt; Law, Truth",
    )
    alignment: str | None = Field(
        None,
        description="Moral tenor or metaphysical orientation. Examples: lawful duty-bound; paradoxical duality; radiant balanced; shadow-embracing; primal untamed; patient inevitable",
    )
    symbol: str | None = Field(
        None,
        description="Holy symbol or recurring visual motif (concise). Exclude: domains, follower groups. Examples: crimson oath threads; twin dawn–shadow shrine; eternal forge flame; shattered mirror facet; meteoric ice crown",
    )
    worshippers: str | None = Field(
        None,
        description="Principal follower groups, orders, or ancestries (comma + space separated). Exclude: domains, relics. Examples: Crimson Loom knights; Sundered Dawn initiates; Ember Throne warrior‑artists; Pale Throne death‑priests; Howling Moon pack; Shattered Mirror adepts",
    )
    divine_realm: str | None = Field(
        None,
        description="Named metaphysical seat, sanctum, or realm anchor. Examples: Crimson Spindle; Threshold Citadel; Everforge Citadel; Ossuary Eternal; Paradox Palace",
    )


class Organization(BaseModel):
    """Formal or semi‑formal collective: order, concordance, guild, cult, council.

    Examples: Divine Knight Concordance; Order of the Crimson Loom; Order of the
    Sundered Dawn; Ember Throne; Howling Moon; Shattered Mirror; Pale Throne; Void Crown.

    Narrative utility: factional allegiance, quest giver structure, political or
    ritual authority, multi‑order convergence tracking.
    """

    organization_type: str | None = Field(
        None,
        description="Organizational classification (choose most specific). Examples: knightly order; divine concordance; shadow order; warrior‑artist order; paradox order; death order; lost order",
    )
    leader: str | None = Field(
        None,
        description="Current apex authority (individual or council). Examples: The Unbroken; The Sevenfold; Phoenix Smiths; Faceless Court; Thrice‑Crowned",
    )
    headquarters: str | None = Field(
        None,
        description="Primary stronghold or anchor site. Examples: Crimson Spindle; Threshold Citadel; Everforge Citadel; Moonweald; Paradox Palace; Ossuary Eternal",
    )
    founding: str | None = Field(
        None,
        description="Origin era or catalyst. Examples: Age of Woven Crowns; post‑Schism consolidation; after Last War reconstruction; pre‑Convergence vigilance",
    )
    membership: str | None = Field(
        None,
        description="Composition descriptor (single or comma + space separated). Exclude: goals, territory. Examples: oath‑bound knights; dual‑soul initiates; warrior‑poet forgesworn; primal hunt packs; fractured identity adepts; death‑tempered revenant knights",
    )


class Person(BaseModel):
    """Named individual (mortal, transformed, or ascendant) with roles or ties.

    Examples: Serane; The Black Bitch; Borhild (as a mortal reference if used);
    a Phoenix Smith master; a Sundered Dawn veteran; a Pale Throne champion.

    Narrative utility: anchors for personal arcs, relationship edges, prophecy
    fulfillment candidates, relic wielders.
    """

    title: str | None = Field(
        None,
        description="Formal or bestowed rank or honorific. Examples: Thread‑Bound; Oath Weaver; Loom Guard; Eclipse Knight; Phoenix Smith; Alpha Hunter; Truth Thief; Thrice‑Crowned",
    )
    occupation: str | None = Field(
        None,
        description="Primary functional role. Examples: oath enforcer; balance arbiter; warrior‑poet; primal hunter; paradox infiltrator; death adjudicator; Arcanite scholar",
    )
    race: str | None = Field(
        None,
        description="Species or lineage. Examples: Human; Crystal Dwarf; Elf; Arcana Golem; Half‑Orc; Vampire; Lich; Changeling",
    )
    affiliation: str | None = Field(
        None,
        description="Associated organizations or factions (comma + space separated). Exclude: titles, artifacts. Examples: Crimson Loom; Sundered Dawn; Ember Throne; Howling Moon; Shattered Mirror; Pale Throne; Divine Knight Concordance",
    )
    status: str | None = Field(
        None,
        description="Current existential or narrative state. Examples: living; missing; once‑dead returned; void‑scarred; oath‑fractured; death‑tempered; ascension‑pending",
    )


class Location(BaseModel):
    """Physical or quasi‑physical site: settlement, fortress, node, or liminal zone.

    Examples: Crimson Spindle; Threshold Citadel; Everforge Citadel; Moonweald;
    Paradox Palace; Ossuary Eternal.

    Narrative utility: quest hubs, traversal gates, ritual sites, escalation or
    convergence staging grounds.
    """

    location_type: str | None = Field(
        None,
        description="Category of place (single noun/compound). Examples: citadel; tower; forge‑citadel; shifting forest; paradox palace; ossuary stronghold",
    )
    region: str | None = Field(
        None,
        description="Broader geographic or metaphysical region. Examples: boundary of day and night; dream interface; death threshold; oath resonance locus",
    )
    ruler: str | None = Field(
        None,
        description="Controlling order, council, or notable absence. Examples: Crimson Loom guardians; dual‑soul wardens; forge council; pack alphas; faceless court; death wardens",
    )
    significance: str | None = Field(
        None,
        description="Strategic, magical, or spiritual importance (single or comma + space separated clauses). Exclude: access requirements, rulers. Examples: binds fulfilled oaths; stabilizes liminal light/shadow; fuels creative ascension; channels primal hunt; fractures truth; anchors death passage",
    )
    access: str | None = Field(
        None,
        description="Entry requirement or gating condition. Examples: sworn oath resonance; twilight alignment; forge initiation; lunar phase attunement; identity fragmentation; death rite passage",
    )


class Concept(BaseModel):
    """Abstract metaphysical force, doctrine, pattern, or ontological principle.

    Examples: Loom of Aether; Oath Binding; Dual‑Soul Balance; Death Mastery;
    Creative Forging; Fragmentary Perception; Primal Resonance; Convergence.

    Narrative utility: thematic scaffolding for magic systems, cosmological
    debates, prophecy interpretation, and edge semantics.
    """

    concept_type: str | None = Field(
        None,
        description="Subtype classification. Examples: metaphysical pattern; divine synergy; ontic duality; post‑mortem transition; creative synthesis; identity fragmentation; primal consciousness",
    )
    manifestation: str | None = Field(
        None,
        description="Observable form or phenomenon (single or list). Exclude: philosophical interpretation. Examples: visible crimson threads; twin dawn–shadow shrines; forging transmutation heat; lunar hunt transformation; mirror shatter vision; cold death stillness",
    )
    adherents: str | None = Field(
        None,
        description="Groups or entities embodying it. Examples: oath knights; dual‑soul initiates; Ember forge adepts; hunt packs; mirror fragments; death wardens",
    )


class Artifact(BaseModel):
    """Discrete object of enduring mystical, symbolic, or catalytic potency.

    Examples: Mercy's Edge; Necessity's Bite; an Oath Blade; a Phoenix Forge Blade;
    an Arcanite Core; a Lich Phylactery; a Mirror Shard.

    Narrative utility: quest objectives, power progression anchors, catalyst for
    faction conflict, divine domain leverage.
    """

    artifact_type: str | None = Field(
        None,
        description="Item category. Examples: oath blade; twin ritual blade; forge‑relic; meteoric ice weapon; Arcanite core; phylactery; mirror shard",
    )
    power: str | None = Field(
        None,
        description="Primary function or magical effect (single or comma + space separated). Exclude: creator, location, curse. Examples: binds fulfilled vows; dual light–shadow strike; ignites creative resonance; severs life thread; sustains crystalline life; anchors lich soul",
    )
    creator: str | None = Field(
        None,
        description="Maker or forging agency. Examples: oath weavers; dual‑soul artisans; Phoenix Smiths; death forgemasters; Arcanite engineers; ascendant mage",
    )
    location: str | None = Field(
        None,
        description="Current or last known placement. Examples: Crimson Spindle vault; Threshold Citadel armory; Everforge sanctum; Ossuary Eternal reliquary; Moonweald ritual grove",
    )
    curse: str | None = Field(
        None,
        description="Negative cost, drawback, or corruptive trait. Examples: oath‑scar backlash; identity bifurcation strain; soul‑ember burnout; frost of unlife leech; fragmentation madness risk",
    )


class Event(BaseModel):
    """Singular or bounded historical occurrence altering state or trajectory.

    Examples: The Last War; Crystal Dwarves Sealing; Re‑Emergence of Crystal Dwarves;
    Vigil to Marking Transition; Convergence Prophecy Carving; Founding of the Orders;
    Void Crown Fall.

    Narrative utility: timeline anchoring, causal chain analysis, flashback
    structuring, prophecy milestone detection.
    """

    event_type: str | None = Field(
        None,
        description="Classification. Examples: war; cataclysm; founding; reemergence; sealing; prophecy inscription; order collapse",
    )
    when: str | None = Field(
        None,
        description="Temporal marker. Accepted patterns: Age of <Name>; <ordinal> Year of <Name>; pre-<Event>; post-<Event>. Avoid vague phrases like 'long ago'. Examples: Age of Ash; 80th Year of Revelation; pre-Last War; post-Sealing; Age of Woven Crowns",
    )
    participants: str | None = Field(
        None,
        description="Key involved factions or entities (comma + space separated). Exclude: outcomes, motivations. Examples: Arcana Golem factions; Crystal Dwarves; Marked heroes; knight orders; Darklings; Luminari remnant",
    )
    outcome: str | None = Field(
        None,
        description="Immediate resolution or result. Examples: world devastation; prison stabilization; knowledge concealment; order restructuring; partial sealing success",
    )
    significance: str | None = Field(
        None,
        description="Long-term impact or shift. Examples: magic diminution; rediscovery surge; oath system formalization; death mastery emergence; convergence risk escalation",
    )


class Race(BaseModel):
    """Distinct lineage or form with shared origin narrative and physiological traits.

    Examples: Crystal Dwarves; Elves; Humans; Half‑Orcs; Arcana Golems; Vampires;
    Liches; Changelings; Genasi; Halflings.

    Narrative utility: mechanical differentiation, cultural tension sources,
    transformation arcs, origin mystery resolution.
    """

    race_type: str | None = Field(
        None,
        description="High-level classification. Examples: humanoid; crystalline lineage; adaptive mortal; construct‑ensouled; hybrid forged; undead transcendence; potential shifter; elemental manifestation",
    )
    origin: str | None = Field(
        None,
        description="Creation or emergence summary. Examples: Arcanite isolation metamorphosis; dream memory emergence; consciousness fragments coalescence; divine forge ritual; soul binding in constructs; death refusal transformation",
    )
    homeland: str | None = Field(
        None,
        description="Primary locus or formative environment. Examples: sealed crystal caverns; Pools of Twilight thresholds; adaptive borderlands; Apparatus planned construct city; battlefield forges; lunar shadow sites",
    )
    lifespan: str | None = Field(
        None,
        description="Longevity pattern or conditional immortality. Examples: ageless until Arcanite field loss; memory fading–return cycle; rapid adaptive generations; potentially immortal with recharge; conditionally immortal hunger; phylactery anchored existence",
    )
    culture: str | None = Field(
        None,
        description="Social pattern or philosophical core. Examples: crystal purity caste; collective memory synchronization; contradictory origin multiplicity; Rage Meditation lodges; Iteration reconstruction ethos; hunger courts",
    )
    abilities: str | None = Field(
        None,
        description="Innate capacities or resistances (comma + space separated or single). Exclude: cultural practices, artifact effects. Examples: harmonic Arcanite attunement; partial physics detachment; multi‑path adaptability; dual heart resilience; modular body iteration; prophecy resistance; probability manipulation",
    )


class Faction(BaseModel):
    """Collective with strategic motive (can overlap with Organization but broader).

    Examples: Divine Knight Concordance; Void Crown; Darklings; Arcana Golem
    Blocs; Pattern Seekers; Titan Loyalists.

    Narrative utility: antagonistic pressure, alliance dynamics, resource control
    mapping, ideological conflict graph expansion.
    """

    faction_type: str | None = Field(
        None,
        description="Category of influence. Examples: military order network; metaphysical corruption; construct ideology; prophetic cult; titan allegiance",
    )
    goals: str | None = Field(
        None,
        description="Stated or implied objectives (comma + space separated). Exclude: specific methods, territories. Examples: maintain oath lattice; balance revelation/secrecy; forge convergence readiness; awaken planetary consciousness; harvest forbidden truth; stabilize death threshold",
    )
    methods: str | None = Field(
        None,
        description="Operational approaches (comma + space separated). Exclude: goals, assets. Examples: oath enforcement; dual ritual trials; inspirational forging rites; predatory hunt cycles; perception fragmentation; death ordeal initiations",
    )
    territory: str | None = Field(
        None,
        description="Physical or conceptual zone of control. Examples: oath citadels; twilight boundaries; forge districts; lunar forests; reflected realities; death ossuaries",
    )
    resources: str | None = Field(
        None,
        description="Key assets (comma + space separated). Exclude: goals, methods. Examples: fulfilled oath power; dual‑soul resonance; eternal forge flame; hunt pack ferality; mirror shard intelligence; death energy reserves",
    )


class Creature(BaseModel):
    """Non-humanoid entity (natural, constructed, or metaphysically emergent).

    Examples: Dragon; Dire Beast; Death Apparition; Elemental; Void‑Touched Predator.

    Narrative utility: encounter theming, environmental hazard modeling, hunt or
    taming quest hooks.
    """

    creature_type: str | None = Field(
        None,
        description="Classification. Examples: dragon; dire beast; elemental manifestation; void predator; death apparition",
    )
    habitat: str | None = Field(
        None,
        description="Primary environment or planar adjacency. Examples: probability‑warped lairs; lunar phase forests; Arcanite caverns; death threshold regions; twilight pools",
    )
    intelligence: str | None = Field(
        None,
        description="Cognitive tier. Examples: bestial cunning; fragmentary sentience; strategic sapience; alien conceptual; instinct‑bound",
    )
    threat_level: str | None = Field(
        None,
        description="Relative danger. Examples: existential age‑shaping; region destabilizing; order‑testing; hunt pack lethal; low ambient",
    )
    abilities: str | None = Field(
        None,
        description="Distinct powers or defenses (comma + space separated). Exclude: habitat, intelligence. Examples: probability breath; lunar phase shapeshift; Arcanite resonance pulse; death drain aura; void phase step",
    )


class Magic(BaseModel):
    """Defined magical paradigm, channel, technique, or structured effect system.

    Examples: Oath Weaving; Dual Light‑Shadow Smiting; Phoenix Forging; Primal Hunt
    Resonance; Mirror Fragmentation; Death Channeling; Arcanite Harmonics.

    Narrative utility: power source justification, mechanic gating, ritual and
    edge type inference, counter‑magic reasoning.
    """

    magic_type: str | None = Field(
        None,
        description="Source lineage or channel origin. Examples: arcane; divine; primal; psionic; hybrid oath; negative channel; Arcanite harmonic",
    )
    school: str | None = Field(
        None,
        description="Formal school or functional grouping. Examples: evocation flame forging; divination paradox insight; necromancy death channel; transmutation oath crystallization; illusion fragment splitting",
    )
    practitioners: str | None = Field(
        None,
        description="Primary users. Examples: oath knights; dual‑soul initiates; Ember forge adepts; hunt packs; mirror adepts; death wardens; Arcanite engineers",
    )
    components: str | None = Field(
        None,
        description="Required catalysts, materials, or ritual conditions (comma + space separated). Exclude: effects, users. Examples: sworn vow phrases; simultaneous light–shadow invocation; forge flame resonance; lunar phase alignment; mirror shard focus; death rite sequence",
    )
    restrictions: str | None = Field(
        None,
        description="Costs or limiting factors (comma + space separated). Exclude: required components. Examples: oath scar backlash risk; identity bifurcation strain; passion burnout; feral loss of self; perception fragmentation; life force drain; Arcanite depletion dependence",
    )


class Prophecy(BaseModel):
    """Foretelling inscription, vision fragment, convergence verse, or fate pattern.

    Examples: Convergence Prophecy; Prophecy of Forms; Void Crown Paradox.

    Narrative utility: foreshadow anchors, branching quest condition checks,
    convergence risk assessment.
    """

    prophecy_type: str | None = Field(
        None,
        description="Category. Examples: convergence verse; form transformation sequence; sealing paradox; age transition omen",
    )
    source: str | None = Field(
        None,
        description="Origin or medium. Examples: Void Crown Sanctum negative space carving; ancient pre‑race inscription; oath loom resonance; death ossuary echo",
    )
    subject: str | None = Field(
        None,
        description="Targeted entities or processes. Examples: seven orders convergence; racial metamorphoses; prison stability; convergence of knight threads",
    )
    interpretation: str | None = Field(
        None,
        description="Current inferred meaning (implication). Exclude: fulfillment status. Examples: apotheosis risk; liberation threat; pattern unweaving warning; unified resonance potential",
    )
    fulfillment: str | None = Field(
        None,
        description="Status of realization (progress only; do not restate interpretation). Examples: partial activation; conditions emerging; unfulfilled; speculative alignment in progress",
    )


class Realm(BaseModel):
    """Plane, liminal substrate, metaphysical enclosure, or patterned other‑space.

    Examples: Loom of Aether; Arcanite Prison; Twilight Boundary; Death Threshold;
    Dream Interface (Pools of Twilight).

    Narrative utility: planar traversal logic, metaphysical barrier reasoning,
    temporal or memory distortion framing.
    """

    realm_type: str | None = Field(
        None,
        description="Classification. Examples: metaphysical weave layer; prison substrate; liminal boundary; death transition plane; dream leakage zone",
    )
    access: str | None = Field(
        None,
        description="Access mechanism. Examples: oath weaving attunement; Arcanite resonance key; twilight phase alignment; death rite passage; dream pool immersion",
    )
    inhabitants: str | None = Field(
        None,
        description="Resident entities or patterns. Examples: oath thread echoes; sealing custodians; dual‑soul reflections; death memories; pre‑formed consciousness fragments",
    )
    properties: str | None = Field(
        None,
        description="Defining environmental laws or effects. Examples: thread visibility; probability dampening; light–shadow simultaneity; entropy suspension; memory diffusion",
    )
    purpose: str | None = Field(
        None,
        description="Function or originating intent. Examples: bind divine/mortal threads; contain imprisoned power; stabilize duality; process post‑life transition; gestate emergent forms",
    )


# Complete entity type mapping for import
ENTITY_TYPES = {
    "Deity": Deity,
    "Organization": Organization,
    "Person": Person,
    "Location": Location,
    "Concept": Concept,
    "Artifact": Artifact,
    "Event": Event,
    "Race": Race,
    "Faction": Faction,
    "Creature": Creature,
    "Magic": Magic,
    "Prophecy": Prophecy,
    "Realm": Realm,
}
