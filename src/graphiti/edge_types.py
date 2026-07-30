"""Relationship (edge) type definitions for the Luminari Sage knowledge graph.

Each edge model captures a single semantic relationship direction (A -> B).
Field descriptions focus on meaning + short example values. Multi-value fields
use comma + space separation. Exclude instructions prevent spillover between
dimensions (e.g., putting causes into conflict_type). If unknown: leave blank.

Keep examples concise: use existing canon terms (orders, races, deities,
locations, events) without extra narrative prose.

Reserved field notice: the attribute name `fact` is reserved by the upstream
graph ingestion / reasoning layer and has been deliberately removed from all
edge schemas. Do not reintroduce it in edge or entity models.
"""

from pydantic import BaseModel, Field

# Existing edge types (enhanced)


class OpposedTo(BaseModel):
    """Antagonistic / conflict relationship (enmity, rivalry, war, ideological clash).

    Examples: Crimson Loom -> Darklings; Zorren -> Void Crown; Ember Throne -> Shattered Mirror.
    Narrative utility: threat mapping, quest tension surfacing, escalation chains.
    """

    conflict_type: str | None = Field(
        None,
        description="Type of opposition (single). Examples: war, rivalry, ideological, personal, divine, cosmic. Exclude: intensity, status.",
    )
    intensity: str | None = Field(
        None,
        description="Intensity level. Examples: mild, moderate, severe, escalating, eternal, legendary. Exclude: cause.",
    )
    reason: str | None = Field(
        None,
        description="Root cause / origin phrase. Examples: oath breach, domain overlap, succession claim, doctrinal schism, resource control, prophecy divergence.",
    )
    status: str | None = Field(
        None,
        description="Current status. Examples: active, dormant, resolved, escalating, stalemated.",
    )


class Influences(BaseModel):
    """Mentorship / guidance / inspiration / manipulation relationship.

    Examples: Serane -> Marked; Phoenix Smith -> Ember apprentice.
    """

    influence_type: str | None = Field(
        None,
        description="Type of influence. Examples: mentorship, counsel, inspiration, corruption, guidance, manipulation.",
    )
    direction: str | None = Field(
        None, description="Moral direction. Examples: positive, negative, neutral, mixed."
    )
    domain: str | None = Field(
        None,
        description="Domain focus. Examples: political, spiritual, magical, personal, military, scholarly.",
    )
    strength: str | None = Field(
        None, description="Strength. Examples: weak, moderate, strong, overwhelming, absolute."
    )


class Protects(BaseModel):
    """Guardian / defensive relationship.

    Examples: Order of the Crimson Loom -> Crimson Spindle; Howling Moon -> Moonweald.
    """

    protection_type: str | None = Field(
        None,
        description="Type. Examples: physical, spiritual, magical, political, divine, ancestral.",
    )
    scope: str | None = Field(
        None, description="Scope. Examples: individual, group, site, city, realm, race, planar."
    )
    method: str | None = Field(
        None,
        description="Method. Examples: warding rites, oath lattice, patrols, barrier forge, lunar hunt perimeter.",
    )
    dedication: str | None = Field(
        None,
        description="Dedication level. Examples: casual, committed, sworn, eternal, sacrificial.",
    )


class Embodies(BaseModel):
    """Embodiment of concept / aspect / avatar manifestation.

    Examples: Seraphine -> Radiance; Nyxara -> Void; Zorren -> Wild Hunt.
    """

    embodiment_type: str | None = Field(
        None,
        description="Type. Examples: aspect, avatar, symbol, manifestation, incarnation, representation.",
    )
    completeness: str | None = Field(
        None,
        description="Completeness. Examples: partial, full, primary, secondary, fractional, perfect.",
    )
    cosmic_role: str | None = Field(
        None,
        description="Cosmic role phrase. Examples: balance anchor, cycle initiator, boundary keeper, fate moderator.",
    )
    permanence: str | None = Field(
        None, description="Permanence. Examples: temporary, cyclical, eternal, conditional."
    )


# New edge types for comprehensive lore coverage


class Commands(BaseModel):
    """Leadership / authority chain.

    Examples: The Unbroken -> Crimson Loom knights; Phoenix Smith master -> forge cell.
    """

    command_type: str | None = Field(
        None, description="Type. Examples: military, religious, political, organizational, magical."
    )
    authority_source: str | None = Field(
        None,
        description="Authority source. Examples: divine right, election, conquest, inheritance, appointment, seniority.",
    )
    scope: str | None = Field(
        None, description="Scope. Examples: individual, unit, order, multi‑order, realm, race."
    )
    obedience: str | None = Field(
        None,
        description="Expected obedience. Examples: absolute, strong, conditional, contested, fragile.",
    )


class ServesUnder(BaseModel):
    """Service / subordination / sworn loyalty.

    Examples: Knight initiate -> Crimson Loom; Apprentice -> Phoenix Smith.
    """

    service_type: str | None = Field(
        None,
        description="Type. Examples: military, religious, personal, voluntary, indentured, magical.",
    )
    loyalty_level: str | None = Field(
        None, description="Loyalty level. Examples: absolute, strong, moderate, tenuous, forced."
    )
    duration: str | None = Field(
        None,
        description="Duration. Examples: lifelong, contractual, temporary, until death, probationary.",
    )
    compensation: str | None = Field(
        None, description="Compensation. Examples: payment, protection, knowledge, power, status."
    )


class AlliedWith(BaseModel):
    """Alliance / cooperation / treaty / pact.

    Examples: Ember Throne -> Crimson Loom (forge supply); Howling Moon -> Pale Throne (ritual cycle).
    """

    alliance_type: str | None = Field(
        None,
        description="Type. Examples: military, political, trade, ritual, marriage, magical, divine.",
    )
    strength: str | None = Field(
        None, description="Strength. Examples: unbreakable, strong, moderate, fragile, nominal."
    )
    terms: str | None = Field(
        None,
        description="Key terms (comma + space separated). Examples: shared patrols, forge exchange, oath witness, lunar rites access.",
    )
    duration: str | None = Field(
        None,
        description="Expected duration. Examples: eternal, until goal achieved, seasonal, conditional, provisional.",
    )


class DescendedFrom(BaseModel):
    """Lineage / ancestry / heritage.

    Examples: Modern Crystal Dwarves -> sealed progenitors; Vampire bloodline -> original sire.
    """

    lineage_type: str | None = Field(
        None, description="Type. Examples: blood, spiritual, cultural, magical, adoptive."
    )
    generations: str | None = Field(
        None, description="Generational distance. Examples: direct, recent, ancient, distant."
    )
    purity: str | None = Field(
        None, description="Purity. Examples: pure, diluted, mixed, contested, lost."
    )
    inheritance: str | None = Field(
        None,
        description="Inherited elements (comma + space separated). Examples: traits, powers, titles, curses, responsibilities.",
    )


class CreatedBy(BaseModel):
    """Creation / origination / forging / crafting.

    Examples: Arcana Golem -> Arcanite Engineers; Oath Blade -> Oath Weavers.
    """

    creation_type: str | None = Field(
        None,
        description="Type. Examples: divine, magical, technological, natural, artistic, hybrid.",
    )
    purpose: str | None = Field(
        None,
        description="Original purpose. Examples: oath channeling, sealing, memory preservation, ascension trial.",
    )
    method: str | None = Field(
        None,
        description="Method. Examples: forge ritual, crystallization, binding, harmonic weaving, soul graft.",
    )
    cost: str | None = Field(
        None,
        description="Creation cost (comma + space separated or single). Examples: time, power, life, sanity, identity loss.",
    )


class TransformedInto(BaseModel):
    """Transformation / evolution / metamorphosis / corruption.

    Examples: Mortal -> Lich; Dwarf -> Crystal Dwarf; Knight -> Death‑Tempered Knight.
    """

    transformation_type: str | None = Field(
        None,
        description="Type. Examples: physical, spiritual, magical, corrupted, evolved, synthesis.",
    )
    reversibility: str | None = Field(
        None, description="Reversibility. Examples: yes, no, conditional, partial."
    )
    catalyst: str | None = Field(
        None,
        description="Catalyst. Examples: curse, blessing, choice, accident, ritual, environmental.",
    )
    completeness: str | None = Field(
        None, description="Completeness. Examples: total, partial, ongoing, failed, stalled."
    )


class BoundTo(BaseModel):
    """Binding / oath / contract / magical tether.

    Examples: Knight -> Oath Thread; Lich -> Phylactery; Spirit -> Anchor Relic.
    """

    binding_type: str | None = Field(
        None, description="Type. Examples: oath, curse, contract, magical, soul, divine."
    )
    strength: str | None = Field(
        None, description="Strength. Examples: unbreakable, strong, moderate, weak, failing."
    )
    conditions: str | None = Field(
        None,
        description="Conditions (comma + space separated). Examples: vow renewal, lunar phase, dual witness, sacrifice.",
    )
    consequences: str | None = Field(
        None,
        description="Consequences. Examples: soul shatter, oath backlash, release, corruption spread.",
    )


class Corrupts(BaseModel):
    """Taint / corruption / degradation / moral or metaphysical erosion.

    Examples: Void Influence -> Order; Curse Artifact -> Bearer.
    """

    corruption_type: str | None = Field(
        None, description="Type. Examples: moral, physical, spiritual, magical, mental, identity."
    )
    method: str | None = Field(
        None,
        description="Method. Examples: gradual influence, sudden curse, willing embrace, parasitic resonance.",
    )
    resistance: str | None = Field(
        None, description="Resistance. Examples: yes, no, conditional, temporary."
    )
    progression: str | None = Field(
        None, description="Progression. Examples: slow, rapid, cyclical, triggered, cascading."
    )


class TeachesTo(BaseModel):
    """Teaching / training / knowledge transfer.

    Examples: Phoenix Smith -> Apprentice; Death Warden -> Novice.
    """

    teaching_type: str | None = Field(
        None, description="Type. Examples: martial, magical, spiritual, scholarly, artistic."
    )
    knowledge_domain: str | None = Field(
        None,
        description="Knowledge domain. Examples: oath weaving, flame forging, dual-soul balance, death rites.",
    )
    mastery_level: str | None = Field(
        None, description="Level. Examples: basic, intermediate, advanced, master, secret."
    )
    method: str | None = Field(
        None,
        description="Method. Examples: formal instruction, apprenticeship, trial, revelation, mnemonic ritual.",
    )


# Additional edge types for temporal, magical, and geographic relationships


class Precedes(BaseModel):
    """Temporal ordering (A occurs before B). Not inherently causal.

    Examples: The Last War -> Convergence Prophecy Carving; Vigil Age -> Marking Age.
    """

    time_gap: str | None = Field(
        None, description="Time gap. Examples: immediate, short, long, generations, eras."
    )
    causality: str | None = Field(
        None, description="Causality implication. Examples: direct, indirect, none."
    )
    sequence_type: str | None = Field(
        None,
        description="Sequence type. Examples: chronological, prophetic, cyclical, conditional.",
    )


class Causes(BaseModel):
    """Causal relationship (A produces B). Distinct from Precedes.

    Examples: Crystal Sealing -> Magical Diminution; Prophecy Convergence -> Order Reformations.
    """

    causation_type: str | None = Field(
        None, description="Type. Examples: direct, indirect, necessary, sufficient, contributing."
    )
    mechanism: str | None = Field(
        None,
        description="Mechanism phrase. Examples: energy depletion, oath overload, resonance collapse, lineage loss.",
    )
    inevitability: str | None = Field(
        None, description="Inevitability. Examples: certain, probable, possible, accidental."
    )


class Fulfills(BaseModel):
    """Fulfillment of prophecy / oath / destiny / curse / blessing.

    Examples: Serane -> Convergence Prophecy (partial); Order -> Oath Cycle.
    """

    fulfillment_type: str | None = Field(
        None, description="Type. Examples: prophecy, oath, destiny, curse, blessing."
    )
    completeness: str | None = Field(
        None, description="Completeness. Examples: partial, full, exceeded, failed, in-progress."
    )
    method: str | None = Field(
        None,
        description="Method. Examples: ritual enactment, oath completion, sacrificial act, ascension event.",
    )


class Channels(BaseModel):
    """Magical energy channeling (intermediary / conduit). A channels B's power.

    Examples: Oath Loom -> Knight; Forge Flame -> Phoenix Smith.
    """

    magic_type: str | None = Field(
        None, description="Magic type. Examples: arcane, divine, primal, psionic, hybrid."
    )
    efficiency: str | None = Field(
        None, description="Efficiency. Examples: perfect, high, moderate, poor, corrupted."
    )
    capacity: str | None = Field(
        None, description="Capacity. Examples: unlimited, high, limited, depleting."
    )


class Amplifies(BaseModel):
    """Amplification (A boosts B's effect / power).

    Examples: Forge Flame -> Oath Blade; Lunar Cycle -> Hunt Rite.
    """

    amplification_type: str | None = Field(
        None, description="Type. Examples: magical, physical, mental, spiritual, emotional."
    )
    multiplier: str | None = Field(
        None,
        description="Strength. Examples: slight, moderate, significant, exponential, unstable spike.",
    )
    stability: str | None = Field(
        None, description="Stability. Examples: stable, fluctuating, unstable, dangerous."
    )


class Counters(BaseModel):
    """Counter / neutralization / suppression.

    Examples: Death Rite -> Corruption Spread; Mirror Shard -> Illusion Veil.
    """

    counter_type: str | None = Field(
        None, description="Type. Examples: magical, elemental, conceptual, physical."
    )
    effectiveness: str | None = Field(
        None, description="Effectiveness. Examples: complete, partial, situational, ineffective."
    )
    method: str | None = Field(
        None,
        description="Method. Examples: cleansing rite, resonance dampening, oath nullification, pattern inversion.",
    )


class Borders(BaseModel):
    """Geographic or metaphysical boundary adjacency.

    Examples: Moonweald -> Twilight Boundary; Ossuary Eternal -> Death Threshold.
    """

    border_type: str | None = Field(
        None, description="Type. Examples: natural, political, magical, disputed, liminal."
    )
    permeability: str | None = Field(
        None, description="Permeability. Examples: open, restricted, closed, unstable, phased."
    )
    significance: str | None = Field(
        None,
        description="Significance. Examples: patrol chokepoint, ritual threshold, resource barrier, corruption buffer.",
    )


class Contains(BaseModel):
    """Geographic / structural containment.

    Examples: Threshold Citadel -> Inner Vault; Crimson Spindle -> Oath Archives.
    """

    containment_type: str | None = Field(
        None,
        description="Type. Examples: physical, political, magical, dimensional, administrative.",
    )
    hierarchy_level: str | None = Field(
        None,
        description="Hierarchy expression. Examples: continent>region>city, city>district>hall, fortress>wing>vault.",
    )
    control: str | None = Field(
        None, description="Control. Examples: absolute, partial, contested, nominal."
    )


class ConnectsTo(BaseModel):
    """Path / route / portal / conduit connection.

    Examples: Moonweald -> Paradox Palace (phase path); Everforge Citadel -> Crimson Spindle (forge road).
    """

    connection_type: str | None = Field(
        None, description="Type. Examples: road, river, portal, magical, telepathic, phase path."
    )
    distance: str | None = Field(
        None,
        description="Effective distance. Examples: nearby, distant, instant, variable, phased.",
    )
    accessibility: str | None = Field(
        None,
        description="Accessibility. Examples: public, restricted, secret, conditional, seasonal.",
    )


# Complete edge type mapping for import
EDGE_TYPES = {
    "OpposedTo": OpposedTo,
    "Influences": Influences,
    "Protects": Protects,
    "Embodies": Embodies,
    "Commands": Commands,
    "ServesUnder": ServesUnder,
    "AlliedWith": AlliedWith,
    "DescendedFrom": DescendedFrom,
    "CreatedBy": CreatedBy,
    "TransformedInto": TransformedInto,
    "BoundTo": BoundTo,
    "Corrupts": Corrupts,
    "TeachesTo": TeachesTo,
    "Precedes": Precedes,
    "Causes": Causes,
    "Fulfills": Fulfills,
    "Channels": Channels,
    "Amplifies": Amplifies,
    "Counters": Counters,
    "Borders": Borders,
    "Contains": Contains,
    "ConnectsTo": ConnectsTo,
}
