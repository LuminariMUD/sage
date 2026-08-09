# Lumia Lore Repository

This tree contains the approved narrative foundation for Lumia.

## Authority

1. **`canon/` is binding lore.** New work may extend its gaps, introduce
   explicitly attributed disagreement, or clarify an old account. It may not
   silently replace an established fact.
2. **More specific concordances interpret broad chronicles.** For example,
   `timeline/the_shattered_truth.md` establishes the Five Locks as Memory,
   Identity, Time, Space, and Will. An older chronicle's “hidden keys” is
   testimony about how people described the Locks, not authority to turn them
   into five lootable objects.
3. **Attributed belief is canon as belief.** A culture may truly teach something
   that is not objectively true. Documents must make that distinction legible.
4. **`meta/STYLE.md` governs narrative voice.** Metadata, implementation
   contracts, and audits should favor precision over ornament.

## Current Structure

### Characters

- `canon/characters/the_black_bitch_of_voids_wake.md` — the captain at the
  center of the Forgotten Tide.

### Cultures and Peoples

- `canon/cultures/races_of_lumia.md` — racial origins and transformed states.
- `canon/cultures/the_crystal_dwarves_of_nagburim.md` — Nagburim's foundational
  account.
- `canon/cultures/the_trelux.md` — Lumia's ancient collective consciousness.
- `canon/cultures/the_courts_of_hunger.md` — vampire culture and the Five
  Farewells.
- `canon/cultures/living_customs_of_lumia.md` — cross-border practices,
  observances, goods, and cultural disputes.
- `canon/cultures/tales_told_against_the_dark.md` — established folklore whose
  internal claims may remain unreliable.
- `canon/cultures/languages_of_the_homelands.md` — stable Heart Tongues.
- `canon/cultures/the_characters_compass.md` — character identity and background
  guidance.

### Factions, Gods, and Orders

- `canon/factions/DEITIES.md` — the Forty recognized Woven Gods.
- `canon/factions/THE_TWO_ORDERS_OF_DIVINITY.md` — Woven Gods, Deep Titans, and
  their distinct roads of power.
- `canon/factions/KNIGHTS.md` and
  `canon/factions/divine_knight_concordance.md` — the six Knight Orders, lost
  seventh, and divine relationships.
- `canon/factions/the_forgotten_tide.md` — the pirate federation.
- `canon/factions/the_three_embers.md` — the Freehands, Civic Guard, and Lantern
  Atlas along the Ashenport road.
- `canon/factions/the_villian_hierarchy.md` — present threat taxonomy. The
  historical filename is retained despite its spelling.

### Locations and Political Geography

- `canon/locations/the_five_nations.md` — current political powers.
- `canon/locations/the_thirteen_homelands.md` — stable character-origin
  geography and public regional identities.
- `canon/locations/the_swiftpaths.md` — the approved transit mystery.
- `canon/locations/the_ashenport_road.md` — the Lenadrian regional adventure
  framework and reconciled legendary sites.

### History and Metaphysics

- `canon/timeline/timeline.md` — chronological spine.
- `canon/timeline/ages.md` — cultural and metaphysical age structure.
- `canon/timeline/the_shattered_truth.md` — restricted interpretation of the
  Luminari, Prisoner, Arcanite, and Five Locks.

### World Systems

- `canon/world/the_roads_of_magic.md` — Arcane, Woven, Deep, Primal, and
  Psionic practice.
- `canon/world/relics_and_the_art_of_making.md` — relics, artifacts, Arcanite
  craft, and the three schools of making.
- `canon/world/the_feyveil_and_the_otherworld.md` — Otherworld, Feyveil, Pools
  of Twilight, and thin places.

## Non-Negotiable Cross-Document Facts

- The world is **Lumia**.
- The Loom's three forces are **Memory, Will, and Possibility**.
- The Five Locks are **Memory, Identity, Time, Space, and Will**.
- Arcanite is crystallized Aeonic residue and part of the Prison.
- **Serane** is the last Luminari.
- Woven Gods and Deep Titans are different orders of divinity.
- The Shadowmoon's observed effects are canon; its body, conventional orbit,
  and origin are not settled.
- Ashenport is a charter city within Onduis and is not Hir/Pesh.
- Runtime topology and imported production names are evidence, not automatic
  player-facing canon.

## Writing New Canon

Before adding a record:

1. Read the relevant foundation and `meta/STYLE.md`.
2. State whether the record is objective concordance, public belief, restricted
   truth, proposal, or unresolved testimony.
3. Connect the material to at least two established elements without collapsing
   a deliberate mystery.
4. Keep mechanics at the boundary: lore may guide an implementation, but levels,
   vnums, stat bonuses, admin process, and engine commands are not truths about
   the world.
5. Name costs and consequences. Magic, immortality, artifacts, government, and
   memory all leave someone carrying weight.
6. Add a provenance section when reconciling prior or imported material.

## Draft Policy

The 2026-08-10 canonization retired the entire historical draft backlog. The
`lore_docs/drafts` directory is intentionally absent.

New unapproved work should not accumulate as an untracked second canon. Use a
short-lived review branch or an explicitly marked proposal, adjudicate it against
the foundation, and either promote it promptly or remove it.

The complete disposition of the retired backlog is recorded in
`meta/LORE_AUDIT.md`. Historical actions are recorded in `meta/CHANGELOG.md`.

---

_The Loom is not kept by never changing a thread._

_It is kept by knowing which knot the thread was holding before you move it._
