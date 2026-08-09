# Draft Lore-Value Review

| Field           | Value                                           |
| --------------- | ----------------------------------------------- |
| Status          | Active review of the retained draft corpus      |
| Reviewed        | 2026-08-09                                      |
| Scope           | All 14 files remaining under `lore_docs/drafts` |
| Standard        | In-world lore only                              |
| Canon authority | `lore_docs/canon`                               |

## Executive finding

The retained corpus contains **10 files with genuine source-lore value**: five
primary sources and five mixed documents from which lore should be extracted.
The other four files contain potentially useful ideas, but they are later
syntheses rather than trustworthy lore sources.

| Verdict                   | Files | Meaning                                                                                                                    |
| ------------------------- | ----: | -------------------------------------------------------------------------------------------------------------------------- |
| **KEEP — primary lore**   |     5 | Authored/source material with substantial setting value. Preserve with provenance; this verdict does not make it canon.    |
| **EXTRACT — mixed**       |     5 | Genuine lore exists, but it must be separated from mechanics, external-IP residue, obsolete claims, or quest instructions. |
| **CANDIDATE — synthetic** |     4 | Lore-shaped material worth retaining as an idea pool pending human approval. Do not promote wholesale.                     |

This review treats lore as in-world history, cosmology, peoples, characters,
places, institutions, beliefs, customs, artifacts, and events. Game statistics,
commands, balance, code, zone administration, staff history, development
metaphors, templates, and generic design material do not qualify.

The classification used three repository signals: comparison with the approved
canon corpus, source provenance recorded in conversion headers and
`lore_docs/meta/CHANGELOG.md`, and claim-level comparison between parallel drafts.
Writing polish was not treated as evidence of authority. A later synthetic
document can be more complete and readable than an older converted source while
still being less reliable as lore evidence.

`factions/DEITIES.md` and `factions/THE_TWO_ORDERS_OF_DIVINITY.md` were removed
from this draft corpus after explicit approval and promoted to
`lore_docs/canon/factions` on 2026-08-09. Their former verdicts no longer
contribute to the retained-draft totals.

Files deleted from `lore_docs/drafts` are outside this retained-corpus review and
are not preserved as historical rows here.

## Highest-value source material

These five files are the primary-source core of the draft tree:

| File                                           | Lore value                                                                                                            | Qualification                                                                             |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `factions/Faction Overview.md`                 | Original Mosswood Bandits, Ashenport Guards, Explorer's League, leaders, motives, and post-war context.               | Events and reputation mechanics still require separation.                                 |
| `locations/Worldbuilding.md`                   | Foundational Lumia source: moons, peoples, planes, Swiftpaths, Mosswood, Ashenport, and Lenadrian family biographies. | Contains old spellings and several models superseded by canon.                            |
| `timeline/Luminari Back story.md`              | Foundational narrative of the Luminari, Last War, Mark, Arcana Golems, Darklings, Serane, and Crystal Dwarves.        | Its earliest cosmology is not automatically current canon.                                |
| `timeline/luminari-aeon-and-prisoner-lore.txt` | Compact primary seed for Aeon Luminous, the Prisoner, arcanite, and the Last War.                                     | Much is already elaborated in canon, but the source provenance is valuable.               |
| `world/Magic in Lumia.md`                      | Original two-source magic model: Arcane power from the Primal Realm and Divine power from Titan planes.               | Treat this as the surviving draft authority unless a future canon decision supersedes it. |

The largest high-priority extraction is
`locations/Ashenport Region Main Quest.md`. It preserves major characters,
Darkling types, named sites, quest objects, and the original five-key narrative,
but those facts are embedded in commands, combat design, external setting names,
and obsolete geography. It should be mined, not canonized as a document.

## Material conflicts that require a decision

| Subject                 | Competing draft claims                                                                                      | Current handling                                                                                                                      |
| ----------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Ashenport and Hir/Pesh  | Retained quest/synthesis material contains traces of treating Ashenport as Hir/Pesh.                        | Canon `the_thirteen_homelands.md` explicitly separates them. Reject the conflation.                                                   |
| Cultures and states     | `CULTURES_OF_LUMIA.md` compresses the world into five cultural spheres closely tied to five powers.         | This does not align cleanly with the approved Thirteen Homelands and twelve Heart Tongues. Individual customs may still be harvested. |
| The Prisoner's location | Some retained quest/synthesis material places the prison in Avernus; current canon places it beneath Lumia. | Treat Avernus as legacy external-IP contamination, not Lumia lore.                                                                    |

The former gods-and-Titans conflict is resolved by the approved
`lore_docs/canon/factions/THE_TWO_ORDERS_OF_DIVINITY.md` and
`lore_docs/canon/factions/DEITIES.md`.

Several mixed files contain recognizable legacy setting/game material such as
Neverwinter, Avernus, and Pathfinder content. Names, places, creatures, spells,
domains, and mechanics from those sources are not evidence for Lumia lore and
must not survive extraction merely because they appear beside original material.

## Recommended disposition

1. Put the five **KEEP** files in a read-only, provenance-preserving source
   archive. Do not feed them to production lore retrieval as canon.
2. Create small, subject-specific extraction notes for the five **EXTRACT** files.
   Every extracted claim should retain its source path and record any canon
   conflict.
3. Quarantine the four **CANDIDATE** files as unapproved concepts. They should not
   be used to answer factual lore questions.
4. Promote only narrowly reviewed claims into `lore_docs/canon`; never promote
   another mixed or synthetic file wholesale.

## Retained file review

### `cultures` — 2 files

| File                            | Verdict       | Lore-only finding                                                                                                                                                                                              |
| ------------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cultures/CULTURES_OF_LUMIA.md` | **CANDIDATE** | Rich five-sphere synthesis with customs, festivals, economies, and languages. Unique but unapproved and structurally at odds with the Thirteen Homelands/twelve-tongue canon. Harvest individual customs only. |
| `cultures/Vampire Race!.md`     | **EXTRACT**   | A real story seed survives: a restrained deposed vampire, a slaughter survivor, worthiness trials, lost family, and a final sunrise. Remove race mechanics, commands, vnums, and borrowed geography.           |

### `factions` — 1 file

| File                           | Verdict  | Lore-only finding                                                                                                    |
| ------------------------------ | -------- | -------------------------------------------------------------------------------------------------------------------- |
| `factions/Faction Overview.md` | **KEEP** | Primary faction and character lore for the Mosswood Bandits, Ashenport Guards, Explorer's League, and their leaders. |

### `locations` — 5 files

| File                                       | Verdict       | Lore-only finding                                                                                                                                                                                                     |
| ------------------------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `locations/02_10_2021  Notes.md`           | **EXTRACT**   | Mixed notes with genuine kernels: Pools of Twilight rites, maritime halfling life, Sanctus/dragon history, Crystal Dwarf customs, and Trelux traits. Much is already canon; extract only unique supported details.    |
| `locations/Ashenport Region Main Quest.md` | **EXTRACT**   | High-value primary quest archive containing the Lenadrians, five-key arc, Darkling types, Lady Raven, named sites, and artifacts. Heavy mechanics, obsolete geography, and external-IP residue prevent wholesale use. |
| `locations/LEGENDARY_LOCATIONS.md`         | **CANDIDATE** | Useful synthetic index of quest sites, but it repeats the Ashenport/Hir-Pesh error, includes legacy cosmology, and labels unapproved claims as established. Validate each site against primary sources.               |
| `locations/TREASURES.md`                   | **CANDIDATE** | Synthetic crafting/artifact consolidation with some useful traditions, but also formulas, invented schools, unapproved artifacts, and a mistaken treatment of the Five Locks as items.                                |
| `locations/Worldbuilding.md`               | **KEEP**      | Major foundational source for Lumia's moons, peoples, planes, Swiftpaths, Mosswood, Ashenport, and named characters. Preserve with explicit flags for superseded claims.                                              |

### `timeline` — 3 files

| File                                                                                   | Verdict     | Lore-only finding                                                                                                                                                                 |
| -------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timeline/Luminari Back story.md`                                                      | **KEEP**    | Foundational primary narrative for the Luminari, Last War, Mark, Arcana Golems, Darklings, Serane, and Crystal Dwarves.                                                           |
| `timeline/The Secret History + Storbuilding Questbuilding GameDesign Brainstorming.md` | **EXTRACT** | High-value attributed creation-history source is mixed with generic game-design brainstorming and mechanics. Preserve the Aeon/Khadhu Coshek/Prisoner section and its provenance. |
| `timeline/luminari-aeon-and-prisoner-lore.txt`                                         | **KEEP**    | Concise primary lore seed for Aeon Luminous, the Prisoner, arcanite, and the Last War.                                                                                            |

### `world` — 3 files

| File                               | Verdict       | Lore-only finding                                                                                                                                                         |
| ---------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `world/How artifacts will work.md` | **EXTRACT**   | Small setting concepts—unique/possessive artifacts, Titan bestowal, cyclical ownership, destructive bearers, and player legacies—embedded in mechanics and staff process. |
| `world/Magic in Lumia.md`          | **KEEP**      | Primary Arcane/Divine source model and dual-caster premise.                                                                                                               |
| `world/TALES_AND_LEGENDS.md`       | **CANDIDATE** | Synthetic folklore collection with useful cultural texture, quests, and artifacts, but extensive unapproved invention. Treat each tale as a proposal.                     |

## Audit boundary

This document remains a disposition review of the retained drafts. The two
approved divine documents left the corpus through an explicit canonization pass,
and later deletions are omitted entirely. No verdict on any retained draft was
changed. A later extraction pass should operate only on the remaining **KEEP**
and **EXTRACT** sets and should present conflicts for explicit human approval.
