# Production zones with explicit Forgotten Realms lore

This inventory retains named Forgotten Realms locations and child zones that
carry those names. Generic fantasy areas, shared D&D planes and creatures,
staff zones, and already-renamed Luminari locations are omitted.

World files checked:
`/home/aiwithapex/projects/Luminari-Source/lib/world`

## Evaluation method

Candidates were drawn from all documents under `lore_docs/canon/`, then checked
against the live `.zon` header, representative room names in each listed `.wld`
file, and the existing-zone registers in
`lore_docs/drafts/working_copy_zone_sheet/`. A name already assigned to a
production zone is ineligible for reuse, including aliases, subareas, and new
compounds built from that name. Closeness measures how much of the zone's present
terrain, physical form, and gameplay role can survive a lore reskin:

- **High**: same place type and strong terrain or functional overlap.
- **Medium**: useful structural or thematic overlap, but a substantial lore pass
  would still be required.
- **Low**: the canon offers only a weak anchor, or the production zone contains
  too little evidence to assess reliably.

An unmarked proposal is a name or named place already present in canon and not
assigned to another production zone in the available registers. A name marked
**†** is a new working label assembled from established canon geography,
institutions, or imagery plus the zone's generic function; it must be reviewed
and promoted before being treated as canon.

These are replacement candidates, not a final geographic crosswalk. Every
proposal is unique in this inventory. Related labels are used only where the
existing zone sheet already records a parent/child or route relationship.

| VNum | Zone name | Proposed replacement name | Closeness to match |
| ---: | --- | --- | --- |
| 1018 | Dawn Pass & Lonely Moor | Hir's Western Road† | **High** — Hir canon gives a western road, rivers, low hills, old war routes, and Darkling traffic; the live zone is a forest-to-moor caravan route with a river ford. |
| 1020 | Delimiyr Route | Lanternwood Road† | **High** — the narrow forest route and warning markers fit Onduis's blue-lantern road culture without borrowing the name of an existing settlement. |
| 1024 | Skull Gorge | The Crimson Spindle | **Medium** — the live content is chiefly a tall, room-dense forsaken tower rather than a gorge; the oath-tower supplies a unique canonical structure but needs a complete faction rewrite. |
| 1040 | The Coast Way | Onduis Coast Way† | **High** — a coastal road, river crossing, ferry, and bunkhouse fit many-roaded littoral Onduis. |
| 1047 | Bargewright Inn | Violet Lantern Stockade† | **High** — the gated inn, trader pavilion, camp, and stock pens fit Axtrosi caravan culture and its violet warning lanterns. |
| 1049 | Amphail | Vailand Horsefair† | **High** — a horse-centered village and trade stop fit Vailand's mobile settlements and horse-herders. |
| 1050 | Corm Orp | Selerish Slateharbor† | **Medium** — Selerish canon makes this slot its best-known port, but the live rooms read as an inland farming town; the replacement needs coastal dressing as well as text swaps. |
| 1052 | Corm Orp Caverns | Selerish Undercliff Caverns† | **High** — worked tunnels, tombs, a bridge, and an underground river fit the caverns beneath Selerish's black cliffs. |
| 1053 | The Way Inn | The Orchard Gate Inn† | **High** — a major walled road inn with yards, orchards, gardens, lodging, and traveler services; the new label does not reuse the existing Ashenport tavern. |
| 1054 | Eveningstar | Blue Lantern Village† | **High** — farms, mill, market, trails, and modest village scale fit Onduis's Lantern Compact without taking the name of the existing Mosswood settlement. |
| 1066 | Red Larch | Briarwatch† | **High** — a defended town amid rolling hills with a nearby monster warren supports a new compact frontier-village identity. |
| 1068 | Longsaddle | Stormglass Academy† | **Medium** — the magical manor and training functions fit Carstani stormglass and Chulani instruction, but the live zone also contains a wider roadside settlement. |
| 1072 | The Trade Way II | Lantern Compact Road† | **High** — a major trade road linking bridges, fields, and stockaded villages fits Onduis's mutual-aid road network. |
| 1075 | Shadowdale | Northroad Cellars† | **Medium** — the settlement, inn, temple, and extensive cellars support a new northern road-town identity, though the surface dale needs a broader rewrite. |
| 1078 | Aumvor's Castle | The Ossuary Eternal | **High** — an undead lord's castle and the death-touched Pale Throne stronghold share form, occupants, and mood. |
| 1081 | Mithril Hall | Nagburim Prime | **High** — both are large subterranean dwarven capitals with mines, gates, markets, residences, and civic interiors; the crystalline culture requires a visual/textual pass. |
| 1086 | The Dusk Road | Phoenix Crown Road† | **High** — the long inter-settlement road, river crossings, side towns, and escalating danger fit the Great Port's road network without reusing Ashenport's zone name. |
| 1088 | The Moonsea Ride | Axtros March Road† | **High** — a long route across stony country, gaps, forests, and foothills fits Axtros's broad caravan roads and warning-tower march. |
| 1089 | The North Ride | Quechian Northroad† | **High** — a forest-edge road with forks, a gap, and a river crossing fits Quechian's negotiated woodland paths. |
| 1090 | The Evermoor Way | Three-Ford Market Road† | **High** — an intercity dirt road with fords, fields, and junctions matches Hir's three-road market culture without reusing its existing market city. |
| 1091 | The Rauvin Ride | Kellust Resonance Road† | **High** — the road climbs from river crossings into mountain trails, matching Kellust's inhabited valleys and seven passes. |
| 1094 | Tesh Trail | Vailand South Road† | **High** — Vailand canon explicitly gives a southern road through grassland toward old towers and shadowed valleys. |
| 1095 | Dagger Falls | The Bone Gardens | **High** — the live zone's lich, undead streets, crypt-like interiors, and grave motifs fit the Vitalist base beneath New Anteria's capital. |
| 1100 | The Tower of Twilight | The Threshold Citadel | **High** — tower, bridge, stables, and a supernatural twilight boundary closely match the Sundered Dawn stronghold. |
| 1101 | Ardeep Forest | The Blueleaf Weald† | **High** — dense forest paths, cave, and old elven remains fit Onduis's green northern country without borrowing another zone's name. |
| 1106 | Lost City of Thunderholme | Shatterdeep Necropolis† | **Medium** — the new name preserves a hostile fallen dwarven city, mines, royal dead, and deep-cavern scale without consuming the separately established Echo Chambers. |
| 1108 | Skull Crag | Kellust Silent Pass† | **High** — steep mountain trail, cliff face, plateau, and caves fit Kellust's passes and newly silent veins. |
| 1110 | Tethyamar Trail | Quechian Covenant Trail† | **High** — river ford, forest paths, dell, and isolated tower fit Quechian's paths and inhabited clearings. |
| 1113 | Tilverton | Memoria | **Medium** — the walled town, bank, university, residences, and civic services can support New Anteria's library city, but its identity needs an undead-memory pass. |
| 1115 | Bleak Palace | The Paradox Palace | **Medium** — the gloomy castle and palace scale align, while the Shattered Mirror stronghold's multiple realities require substantial new room lore. |
| 1123 | Mount Hotenow | Kellust Silent Peak† | **Medium** — the mountain ascent and deep cave fit Kellust, but the live volcanic/fire identity is absent from current Kellust canon. |
| 1126 | Flaming Tower | The Everforge Citadel | **High** — a tower-fortress with temple, barracks, inner halls, and supernatural flame closely fits the Ember Throne stronghold. |
| 1130 | Mantol-Derith | Nightmarket Trench† | **High** — a subterranean caravan market around trenches, streams, and tunnels fits Lumia's deep-road culture under a unique name. |
| 1132 | Mantol-Derith Tunnels | Blackstone Transit Tunnels† | **High** — the new label preserves the zone's direct function as an underground passage link without assigning the whole Underways to one zone. |
| 1134 | Candlekeep Proper | The Floating Library of Chulan | **Medium** — both are major magical scholastic complexes, but floating-city imagery and Chulani reality magic would require extensive dressing changes. |
| 1137 | Ashabenford | Three-Lamp Crossroads† | **High** — a small forest-road settlement with an inn, stable, and clearings fits the Lantern Compact's three-lamp call for aid. |
| 1141 | Soubar Underhalls | The First Temple | **High** — chambers dedicated to many gods closely match the canon's shared, deliberately unlocated convergence temple. |
| 1153 | The Friendly Arm | The Open-Hand Roadhouse† | **High** — a fortified inn with smithy, stables, temple, lodging, and guarded gate fits the road's hospitality themes under a new identity. |
| 1155 | The Rat Hills | Cinderheap Warren† | **High** — the city dump, trash hills, rats, and kobold lairs directly support a unique refuse-district name. |
| 1170 | Dragonspear Castle | Five-Scar Keep† | **High** — a broken castle with dangerous cultic and planar interiors fits the recurring five-fold Darkling imagery under a unique name. |
| 1174 | Grunwald | Lantern Watch† | **High** — canon says this settlement guards Hir's western road; the live forest village and watch structures fit that role. |
| 1177 | Eveningstar Haunted Halls | Echoing Cliffhold† | **High** — cliffside ruined halls, old keep walls, and supernatural occupants support a distinct haunted stronghold name. |
| 1179 | Triel | Lantern Compact Granary† | **High** — the stockaded farm settlement, grain sheds, homes, and road position fit an Onduic Compact village. |
| 1185 | Hardbuckler | Carstan Glassmarket† | **Medium** — a fortified gnome market town fits Carstan's trade and craft culture, but the canon's fishing, smuggling, stormglass, and coast need stronger expression. |
| 1187 | The Lost Vale | Singing Orchard Vale† | **High** — an isolated settled valley with orchard, singing cave, temple, and surrounding hills directly supports the new label. |
| 1189 | Yellow Snake Pass | Axtros Dry Pass† | **High** — a dry mountain pass and desolate plain fit Axtros's dry headlands and long caravan routes. |
| 1191 | Zhentil Keep | — | **N/A** — remove this row from the rename queue: the live `1191.zon` header is already `Llawryn Keep`; FR child content still needs a separate text audit. |
| 1197 | Sewers of CandleKeep | The Inkdrain† | **High** — sewer and drain tunnels beneath a scholarly complex can retain their function without borrowing an existing academy or city-zone name. |
| 1199 | Hardbuckler Caverns | Carstan Smugglers' Underways† | **High** — caverns beneath the town already hold a thieves' guild, a strong match for canon Hardbuckler's smuggling identity. |
| 1200 | Zhent Graveyard | Bone Cathedral Necropolis† | **High** — cemetery, mausoleum, and crypt interiors fit the capital where living and Registered Dead coexist. |
| 1208 | Evereska Way | Quechian Covenant Way† | **High** — a lightly-to-densely forested approach with a cave fits the road into Quechian's twilight forest. |
| 1209 | City of Mirabar | Resonance Forgecity† | **High** — a dense dwarven craft city with workshops, inns, temples, and smithing streets fits Kellust's resonant culture as an independent settlement. |
| 1211 | Dark Dominion | The Wound Beneath Old Anteria | **High** — the live deep shaft and hostile subterranean domain closely match the Darklings' canonical base below the ruined empire. |
| 1214 | Arabel | Kohn Prime | **Medium** — both are major walled trade cities, but canon currently supplies almost no detail for Kohn Prime, so the match is mostly structural. |
| 1217 | Soubar | Violet Lantern Market† | **High** — merchant tents, caravan traffic, guards, and a fortified perimeter closely fit Axtrosi trade culture under a new settlement name. |
| 1218 | Beregost | Three-Road Market† | **High** — a road-centered town with traders, shrines, inns, and smiths fits Hir's market culture without reusing its existing city. |
| 1222 | Luskan Outpost | Alfarth Watch-Fort† | **High** — the stockade, guard posts, gates, and attached village match the Civic Guard's abandoned east-road refuge and training fort. |
| 1250 | Secomber | East Ubdina Bridge Market† | **High** — a marshy river settlement centered on old and new bridges fits East Ubdina's ancestor bridges, river trade, and two-name markets. |
| 1253 | Iron Road | Kellust Stone Road† | **High** — a stone-lined road from river country toward mountain passages fits the highland reach's tuned roads and bridges. |
| 1255 | Darklake | Lockwater Deep† | **High** — underground lake, locks, canals, rivers, and passages directly support a unique deep-water district name. |
| 1260 | High Horn | The Harmonic Gates | **High** — a heavily fortified mountain gateway and garrison is a close functional match for the Crystal Reaches' guarded surface trade posts. |
| 1262 | Misty Forest | Quechian Twilight Forest† | **High** — deep misted forest, groves, shrines, and old paths align strongly with Quechian's layered twilight woods. |
| 1263 | Mithril Hall Palace | Nagburim Prime Palace† | **High** — the palace, audience, residential, and defensive spaces fit the seat of the Transparent Council. |
| 1264 | Roads of Amn | Axtros Caravan Roads† | **High** — mountain pass, river ferry, town approaches, and long trade routes match Axtros's road-and-sea march. |
| 1266 | Trollclaws | Broken Span Road† | **High** — rolling hills, a broken bridge, temple, and troll country directly support the new road name. |
| 1267 | Mere of Dead Men | West Ubdina Grave Marsh† | **High** — cold marsh, black water, ruined keeps, grave roads, and undead danger are central West Ubdina anchors. |
| 1272 | The Reaching Woods | Quechian Covenant Woods† | **High** — ancient trees, riverbank, bridge, druid homes, and woodland paths match Quechian directly. |
| 1275 | Evereska | The Root-Cities of Quechian | **High** — an elven forest city with bridges, gardens, magic, and civic wards is the strongest production shell for Quechian's inhabited darkwood trees. |
| 1280 | The Halfway Inn | The Lantern Cup Inn† | **High** — wagon court, campsite, parade ground, and extensive facilities fit a major road inn under a new identity. |
| 1281 | The Labyrinth | Bonecoil Labyrinth† | **High** — bone-lined tunnels, descents, caverns, and branching subterranean passages directly support the unique label. |
| 1286 | Greycloak Hills Side Path | Hir Low-Hill Side Road† | **High** — caravan trail, bridge, flatlands, hills, and a narrow pass align with Hir's low hills and old causeways. |
| 1292 | The Lurkwood | East Ubdina Timber Road† | **High** — an actively logged forest with roads and camps fits East Ubdina's foresters and red-barked forest routes better than protected Quechian. |
| 1297 | Forest of Wyrms | East Ubdina Wyrmwood† | **High** — East Ubdina canon specifically places strange wyrms on its unreliable forest roads; the logging and hill fissures also fit. |
| 1300 | Undermountain [Level I] | The First Descent† | **High** — a vast first-level dungeon of wells, halls, caverns, camps, and tunnels directly supports the new deep-road name. |
| 1325 | The Serpent Hills | Hir's Brown Hills† | **High** — streams, rolling hills, keeps, mines, and long trails fit Hir's low brown hill country. |
| 1328 | Amiskal's Keep | Void Crown Keep† | **Medium** — the dark fortified complex suits a Void Crown holding, but the Inverse Citadel's negative-space identity is not present in the rooms. |
| 1330 | Settlestone | Kellust Gatehold† | **High** — a dwarven road settlement immediately outside a great hall fits one of Kellust's surface valleys or pass communities. |
| 1332 | Ulcaster's College | The Archive That Defends Itself | **High** — a ruined magical college with library spaces and active arcane hazards closely fits the League's self-rearranging archive. |
| 1335 | Wormwrithings | Wormroad Deeps† | **High** — worm-burrowed granite tunnels and caverns directly support a unique subterranean route name. |
| 1360 | Deep Eveningstar Halls | The Arcanite Workings | **High** — mines, worked passages, cells, fungus caverns, and hostile deep labor spaces fit the reopened Arcanite sites. |
| 1365 | Temple of Ghaundaur | Draven's Chasm† | **High** — slime, poison, a grand chasm, and a subterranean temple align strongly with Draven Coil's serpent-and-poison cult. |
| 1370 | Battle of Bones | The Darkling Wastes | **High** — barren plains, ancient battlefield, bones, undead, and corrupted ruins are a direct terrain and threat match. |
| 1372 | Ch'Chitl | The Echo Chambers | **High** — a hostile deep city organized as connected ring caverns can become the resonant infection's subterranean center. |
| 1375 | Malaugrym Castle | The Inverse Citadel | **High** — a shadow-realm castle reached through distorted forest and planar spaces closely matches the Void Crown's negative-space base. |
| 1380 | The Stonelands | The Crystal Frontier | **High** — rocky disputed trails, caves, ruins, and mineral country fit the contested Arcanite frontier. |
| 1384 | Daurgothoth's Domain | Blackroot Sanctuary† | **High** — ruined temple approaches, cellars, bog forest, lair spaces, and a powerful corrupting presence support a distinct fallen sanctuary. |
| 1387 | Dragon Cult Fortress | Void Crown Fortress† | **Medium** — the temple-fortress structure supports a fallen knight order, but cult identity and planar effects need a full rewrite. |
| 1425 | Daggerford | Cerax | **Low** — `1425.wld` is effectively a one-room placeholder and canon only names Cerax without defining it; there is not enough evidence for a stronger match. |
| 1433 | Thethyr Bandit Castle | Hearthbreak | **High** — a burned-out forest castle occupied by people labeled bandits closely matches the Freehands' reclaimed former-necromancer tower. |
| 1440 | Ardeep Forest | Onduis Oldwood† | **High** — the forest's trails, glen, tomb, shrine, ruined house, and Great Port proximity fit Onduis without borrowing the existing Mosswood zone. |
| 1455 | Sloopdilmonpolop | Deepcurrent Haven† | **High** — a dark cavern city built around water, harvesting pools, tunnels, and specialized craft fits the Forgotten Tide's deep-current imagery under a new name. |
| 1468 | Trollbark Forest | Thornwake Forest† | **High** — thorn forest, trolls, spiders, and dangerous tracks directly support a unique wildwood identity. |
| 1507 | Hulburg Trail | Lenadrian Ruined Trail† | **High** — ruined road, multiple crossroads, gates, and branching routes fit the Lenadrian investigation without reusing an existing city-zone name. |
| 1575 | Luskan Southbank | Phoenix Crown Southbank† | **High** — urban gates, riverbank, streets, guard rooms, docks, shops, and inns fit a new Great Port district label without repeating Ashenport. |
| 1591 | Hulburg | The Green Maw† | **High** — the live content is a green cavern maw, shafts, tunnels, and subterranean structures despite its city label. |
| 1688 | Evermeet Main Rd | Quechian Root-City Road† | **High** — a broad road through vast forest lands fits the main approach to the Root-Cities. |
| 1689 | Evermeet E Coast Rd N | Quechian East Canopy Road† | **High** — a long forest road beneath great trees and gentle rises fits an inhabited Quechian canopy route; coastal wording must be removed. |
| 1690 | Evermeet W Coast Rd N | Quechian West Canopy Road† | **High** — forest, glades, valleys, and curves fit a second Root-City approach; coastal wording must be removed. |
| 1691 | Evermeet Ancient Forest | Quechian Ancient Darkwood† | **High** — ancient trees, game trail, and a root-like underground fissure directly match western Quechian. |
| 1692 | Evermeet Misc Rooms/Mobs | Quechian Outlands† | **Medium** — forest paths, campgrounds, fissures, and wildflower areas fit the region, but this is a miscellaneous support zone rather than one coherent place. |
| 1693 | Evermeet Rd to Elven Settl | Quechian Rootward Road† | **High** — plains giving way to young and then vast forest form a strong approach to the root-cities without reusing the existing Giant Darkwood Tree zone. |
| 1699 | the Vault of Ages | The Memory Vaults | **High** — both are monumental repositories of long-preserved knowledge; the production zone currently contains too little detail to test the material culture. |
| 1800 | MarblePyramid HighForest E | Stilltear Grounds† | **Medium** — undead monument, dark woods, graves, and marshy exterior echo the Pale Throne's crystallized-tear imagery, but the pyramid form is not established in canon. |
| 1803 | MarblePyramid HighForest I | Stilltear Sepulcher† | **Medium** — corpse-lined monumental interiors and undead occupants fit the Pale Throne's crystallized-tear imagery; the pyramid architecture and much of the encounter lore need replacement. |
| 5515 | Delimbiyr Vale | Hir River Vale† | **High** — river, prairie, wildflowers, low hills, and an old road closely match Hir's inland river basin. |
| 5520 | Road West of Secomber | East Ubdina West Road† | **Low** — the live world file contains only a placeholder room, so the regional road name is plausible but likeness cannot be tested. |
| 5521 | Road through Orlbar | Hir River Road† | **High** — grassland trail, river ford, settlement streets, and old road fit Hir's river-and-market network. |
| 5523 | Skullport Port & Island | Forgotten Reach | **High** — a concealed criminal port-and-island complex closely matches the Tide's shipwreck-built capital in a calm pocket of the Void's Wake. |
| 5527 | Skullport Trade Lanes | Wakebound Trade Lanes† | **Low** — the Forgotten Tide theme is a strong match, but this child world's only room is a placeholder, so no finer comparison is possible. |
| 5529 | Skullport Heart | Inkwater | **High** — wet rock tunnels, underground river, trade traffic, and criminal interiors align with the volcanic cave port. |
| 5531 | Pelleor's Prairie | Hir's Old War Prairie† | **High** — battlefield, grassland, copse, crossroads, and burned areas fit Hir's grain country and still-active old war routes. |
| 5536 | Hellgate Keep | Ashfall Gate† | **Medium** — forest approaches, broken ground, crags, and a dangerous fortress fit the ash-and-Darkling setting, but the portal-scale encounter needs dedicated canon. |

## Canon migration required

Six names in this list are currently repeated as public geographic anchors in
`lore_docs/canon/locations/the_thirteen_homelands.md`. Renaming only the world
zones would leave the Forgotten Realms names canonical:

| Existing canon name | Recommended canon-safe anchor |
| --- | --- |
| Corm Orp | Selerish Slateharbor† |
| Hardbuckler | Carstan Glassmarket† |
| Grunwald | Lantern Watch† |
| Mithril Hall | Nagburim Prime for the city; “the tuned gates of Kellust” for generic approach references |
| Evereska | The Root-Cities of Quechian |
| The Reaching Woods | Quechian Covenant Woods† |

`1191.zon` is already headed `Llawryn Keep`, so `Zhentil Keep` should be removed
from any generated zone index. The zone's rooms, mobs, objects, and scripts still
contain Forgotten Realms names and are outside this name-only proposal.

## Principal canon sources

- `lore_docs/canon/locations/the_thirteen_homelands.md` — regional geography,
  settlement roles, terrain, and runtime-to-canon anchors.
- `lore_docs/canon/locations/the_ashenport_road.md` — named roads, settlements,
  ruins, dungeons, and the Underways.
- `lore_docs/canon/locations/the_five_nations.md` — national capitals, the
  Crystal Reaches, contested territories, and named civic sites.
- `lore_docs/canon/factions/KNIGHTS.md` — the six established order
  strongholds.
- `lore_docs/canon/factions/the_three_embers.md` — Hearthbreak, the League
  archive, the Alfarth watch-fort, and the Ember Cache.
- `lore_docs/canon/factions/the_forgotten_tide.md` — Forgotten Reach,
  Inkwater, Port Nowhere, and the Forgotten Wharf.
- `lore_docs/canon/factions/the_villian_hierarchy.md` — the Bone Gardens,
  Inverse Citadel, Wound Beneath Old Anteria, Echo Chambers, and other threat
  bases.
- `lore_docs/canon/world/the_feyveil_and_the_otherworld.md` — Quechian
  root-cities, the Giant Darkwood Tree, twilight pools, and root caverns.
