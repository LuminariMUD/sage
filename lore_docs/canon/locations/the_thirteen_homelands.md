# The Thirteen Homelands

- **Canon status:** [ESTABLISHED]
- **Canon version:** `homelands-1.0.0`
- **Approved use:** Public character creation, player help, onboarding media,
  regional hooks, and source-data implementation
- **Spoiler level:** Player-safe

_Compiled by Edda Vey, Keeper of the Harbor Book, from birth rolls, road
canticles, tax maps, refugee testimony, and the sort of tavern argument that
only becomes history because nobody leaves before dawn._

## The Meaning of Homeland

A nation is a border drawn by a ruler. A birthplace is a room remembered by a
mother. A homeland is the place that taught you what the world sounds like.

For character creation, **Homeland** means a formative origin jurisdiction: the
city, region, or cultural march whose customs and Heart Tongue shaped a
character before play. The thirteen choices are therefore not thirteen
sovereign nations and are not required to be the same kind of place. Ashenport
and Sanctus are charter cities. Onduis and Axtros are broad littoral regions.
Hir is an inland basin. The Ubdinas are two provinces of one divided land.

All thirteen sit within, beside, or beneath the influence of Lumia's Five
Nations. Choosing one establishes public cultural knowledge and a Heart Tongue.
It does not restrict race, class, alignment, faction, faith, or present
residence. Lumia has always moved people faster than maps can contain them.

The selection answers one useful question:

> When your character says _home_, what place answers?

## Canonical Crosswalk

The runtime value is legacy save data and must remain stable unless a deliberate
migration is shipped. Stable IDs and canonical names are the content contract.

| Runtime value | Runtime constant     | Stable ID              | Display name | Place kind                 | Geographic parent | Political sphere      | Heart Tongue |
| ------------- | -------------------- | ---------------------- | ------------ | -------------------------- | ----------------- | --------------------- | ------------ |
| 1             | `REGION_ASHENPORT`   | `homeland/ashenport`   | Ashenport    | Charter city               | Onduis            | Free Cities of Kohn   | Ashen Cant   |
| 2             | `REGION_SANCTUS`     | `homeland/sanctus`     | Sanctus      | Charter city and diaspora  | Axtros            | Free Cities of Kohn   | Sanctine     |
| 3             | `REGION_ONDUIS`      | `homeland/onduis`      | Onduis       | Littoral region            | —                 | Free Cities of Kohn   | Onduic       |
| 4             | `REGION_SELERISH`    | `homeland/selerish`    | Selerish     | Coastal scholarly province | —                 | Magocracy of Chulan   | Seleric      |
| 5             | `REGION_CARSTAN`     | `homeland/carstan`     | Carstan      | Glass-coast province       | —                 | Magocracy of Chulan   | Carstani     |
| 6             | `REGION_AXTROS`      | `homeland/axtros`      | Axtros       | Eastern maritime march     | —                 | Free Cities of Kohn   | Axtrosi      |
| 7             | `REGION_HIR`         | `homeland/hir`         | Hir          | Inland river basin         | —                 | Empire of New Anteria | Hiri         |
| 8             | `REGION_QUECHIAN`    | `homeland/quechian`    | Quechian     | Twilight-forest province   | —                 | Mosswood Federation   | Quechian     |
| 9             | `REGION_VAILAND`     | `homeland/vailand`     | Vailand      | Lake-and-heath march       | —                 | Mosswood Federation   | Vailic       |
| 10            | `REGION_OORPII`      | `homeland/oorpii`      | Oorpii       | Northern island league     | —                 | Free Cities of Kohn   | Oorpic       |
| 11            | `REGION_KELLUST`     | `homeland/kellust`     | Kellust      | Highland reach             | —                 | Crystal Reaches       | Tal          |
| 12            | `REGION_EAST_UBDINA` | `homeland/east-ubdina` | East Ubdina  | River-and-forest province  | Ubdina            | Empire of New Anteria | Ubdinic      |
| 13            | `REGION_WEST_UBDINA` | `homeland/west-ubdina` | West Ubdina  | Frost-and-marsh province   | Ubdina            | Empire of New Anteria | Ubdinic      |

### Binding identity decisions

- **Onduis is the canonical spelling.** `Ondius` is a deprecated dockmaster's
  spelling retained only as a legacy alias for transport data and search.
- **Ashenport is a city within Onduis.** It has its own Free City charter and
  may be chosen separately because an Ashenporter's civic identity is more
  specific than the wider Onduic coast.
- **Sanctus is a city within Axtros.** Sanctus proper is under the Silence. Its
  outer harbor, caravan court, and service wards remain physically accessible
  as the Pilgrim's Ring. A Sanctus Homeland now represents a pre-Silence
  citizen, a person raised in the Ring, or a member of the Sanctine diaspora.
- **Hir is not Ashenport.** Pesh is an old market city and river district
  within Hir. `Hir/Pesh` is valid shorthand for the basin and its principal
  market road. A draft that called Ashenport an alias of Hir/Pesh conflated two
  quest revisions and is explicitly rejected.
- **East and West Ubdina are distinct Homelands within one historic land.**
  They share Ubdinic but maintain different accents, customs, terrain, and
  political grievances.
- The five political spheres are parent affiliations, not replacements for
  the thirteen choices. They answer _who claims or protects this place_; the
  Homeland answers _what place formed this character_.

## Hometown Crosswalk

Homeland and Hometown answer different questions. Homeland is formative culture
and grants a Heart Tongue. Hometown is a mechanical home base that controls
recall, donation services, and some hometown-dependent abilities.

The default campaign currently offers one selectable Hometown:

| Runtime value | Runtime stable ID | Display name | Canon record         | Card summary                                      |
| ------------- | ----------------- | ------------ | -------------------- | ------------------------------------------------- |
| 1             | `hometown/1`      | Ashenport    | `homeland/ashenport` | Lumia's Great Port and principal adventuring hub. |

**Hometown detail:** Ashenport is a diverse harbor city at the mouth of the
River Veyr, governed by a mayor and the Republic of Nine. It is Lumia's
principal trade and adventuring hub, with a major Swiftpath, broad services,
and roads into the low- and mid-level quest regions of Onduis. Choosing it as
Hometown makes the city your practical point of return; choosing Ashenport as
Homeland separately means its civic culture formed your character.

`CITY_SANCTUS` remains defined in source data but is not selectable in the
default campaign. It must not become a Hometown option merely because a city
record exists. If it is enabled later, the design must decide whether recall
lands in the accessible Pilgrim's Ring and must never place a character inside
Sanctus proper while the Silence remains canon.

## Ashenport

- **Stable ID:** `homeland/ashenport`
- **Kind:** Charter city within Onduis
- **Political sphere:** Free Cities of Kohn
- **Heart Tongue:** Ashen Cant

### Card summary

The Great Port where every road becomes a bargain and every bargain becomes a
story.

### Player-facing lore

Ashenport stands where the River Veyr loosens its fist and gives itself to the
Shallow Sea. Its roofs are red tile, green copper, patched sailcloth, and the
occasional inverted hull of a ship that found a second career as a tavern.
Seven old quays divide the harbor, though any dockhand will swear there are
nine and accuse the tax office of losing the other two.

The city calls itself the Phoenix Crown because its founding marks the modern
human calendar: Year One of the New Calendar began when refugees kindled a
signal fire in the ash of the Last War and ships answered from three horizons.
That fire has never been allowed to die. It burns today in the Harbor House,
watched by a noble, a commoner, and a child chosen by lot.

Ashenport is governed twice. A mayor and appointed judges keep the streets,
while the Republic of Nine bargains for the waters and lands beyond the walls.
Four seats belong to old houses, five to elected wards, and the Field Marshal
breaks a tie only after publicly naming the cost of doing so. It is a system
built to irritate everyone equally, which Ashenporters consider the nearest
politics comes to justice.

Here the Swiftpath hums beneath gull cries. Here the Jade Jug keeps lamps for
travelers who have nowhere else to be. Here one may buy a crystal memory, a
forged genealogy, an honest meal, or a dishonest map—sometimes from the same
stall.

### What growing up here teaches

Ashenport teaches that strangers are unfinished opportunities, that a promise
needs witnesses, and that civilization is not clean. It is the daily labor of
keeping ten thousand hungers from becoming one riot.

Choose Ashenport for a character shaped by crowds, commerce, rumor, civic
pride, quick friendship, and quicker suspicion.

### Cultural anchors

- **Greeting:** Show an empty palm, then turn it upward: “Nothing hidden;
  something offered.”
- **Keepsake:** A pierced quay-token, invalid as money but treasured as proof
  that one belongs.
- **Common virtue:** Resourcefulness.
- **Common failing:** Treating every kindness as the opening move of a trade.
- **Public concern:** Roads beyond the walls grow dangerous as Darkling-touched
  creatures press toward the port.

### Media anchors

Show a lived-in harbor metropolis: layered quays, the river mouth, copper and
tile roofs, mixed peoples, cranes and sails, and a distant crystalline
Swiftpath glow. Do not depict Ashenport as a desert city, a pristine royal
capital, or Hir/Pesh.

### Provenance

Ashenport's role as Great Port, civilizational center, calendar anchor, and
Swiftpath hub is established in `lore_docs/canon/timeline/timeline.md`,
`lore_docs/canon/timeline/ages.md`, and
`lore_docs/canon/locations/the_swiftpaths.md`. Runtime geography places the
city and its low-level quest network inside legacy `Ondius` at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:98-110` and its sea
port at `/home/aiwithapex/projects/Luminari-Source/src/transport.c:148-151`.
The dual government and named streets are promoted from the Ashenport quest
archive after rejecting its Hir/Pesh alias.

## Sanctus

- **Stable ID:** `homeland/sanctus`
- **Kind:** Charter city and living diaspora within Axtros
- **Political sphere:** Free Cities of Kohn
- **Heart Tongue:** Sanctine

### Card summary

The Silent City whose bells no longer ring—and whose scattered people refuse
to forget their sound.

### Player-facing lore

Sanctus was built in concentric circles around a bell that had no clapper.
According to its oldest charter, a city devoted to free thought should never
be summoned by force. The bell would ring only when every citizen wished it.
It never rang, but generations learned to hear the promise inside its silence.

Before the Incident, Sanctus served as High Mediator among the Free Cities of
Kohn. Its courts were famous for the Hour of Listening, during which advocates
had to restate an opponent's case so faithfully that the opponent accepted the
summary. Its crafters worked in open arcades. Its player-owned stalls, shrine
services, and eastern goods made the city a destination rather than merely a
capital.

Three months ago, Sanctus proper went quiet. No lawful road enters the inner
rings. Birds turn aside. Divinations return the face of the questioner. Voices
occasionally speak from behind the pale boundary with perfect courtesy and no
breath between words.

The contradiction seen on common maps is real but not impossible: the
**Pilgrim's Ring** lies outside the sealed city. This outer harbor and service
ward remains open under Axtrosi quarantine. Ships dock, caravaners trade,
craftspeople work, and former Sanctine officials stamp documents beneath the
shadow of gates they cannot cross. Travelers who say they “went to Sanctus”
usually mean the Ring. Those born inside the Silence, those raised in the Ring,
and the refugees now scattered across Lumia all remain Sanctine.

### What growing up here teaches

Sanctus teaches the difference between silence and consent. Its people listen
closely, choose words carefully, and distrust any harmony that requires every
voice to become the same voice.

Choose Sanctus for a mediator, refugee, artisan, investigator, survivor, or
anyone carrying a home that can be remembered but not reached.

### Cultural anchors

- **Greeting:** Pause for one heartbeat before giving your name.
- **Keepsake:** A small bell with the clapper removed.
- **Common virtue:** Deliberation.
- **Common failing:** Withholding truth until its moment has passed.
- **Public concern:** Loved ones may remain beyond the Silence, while messages
  from within cannot be trusted.

### Media anchors

Show pale concentric walls, silent bell towers, an unreachable luminous core,
and a busy outer harbor under watch. The image must contain both absence and
life. Do not portray the whole Axtrosi coast as abandoned, nor show ordinary
crowds inside Sanctus proper.

### Provenance

Sanctus as a Free City, High Mediator, and Silent City is established in
`lore_docs/canon/locations/the_five_nations.md` and
`lore_docs/canon/factions/the_villian_hierarchy.md`. Its accessible services
and Axtros placement are live runtime evidence at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:166-169` and
`/home/aiwithapex/projects/Luminari-Source/src/act.other.c:9267-9271`.
The Pilgrim's Ring is newly established here to reconcile those truths without
erasing either.

## Onduis

- **Stable ID:** `homeland/onduis`
- **Kind:** Littoral region
- **Political sphere:** Free Cities of Kohn
- **Heart Tongue:** Onduic
- **Legacy alias:** `Ondius`

### Card summary

A many-roaded coast of green lowlands, old ruins, and towns that survive by
helping one another.

### Player-facing lore

Onduis curves around the middle Shallow Sea like a hand held beneath a falling
cup. Rivers, roads, and old war routes all gather there. Ashenport crowns its
central estuary, but the region is larger than its famous city: Mosswood
Village keeps the northern green; Graven Hollow watches a wounded valley;
farms lean against old forts; and harmless-looking hills conceal places that
remember the Last War too well.

No single ruler owns Onduis. The Republic of Nine claims the roads nearest
Ashenport, village councils hold the interior, and the Free Cities maintain
harbor law along the coast. When these authorities disagree, which is often,
the people rely on the **Lantern Compact**: any settlement that lights three
blue lamps may ask food, shelter, or defense from its neighbors until the
danger passes. The Compact has no army and has outlived four armies.

Onduic identity is practical rather than grand. People mend what they have,
mark safe wells, and leave chalk signs where monsters have moved. They are
accustomed to heroes passing through on important business and unimpressed by
importance that cannot stack firewood.

### What growing up here teaches

Onduis teaches that roads are promises between strangers. A character from
here may be a village guide, caravan guard, hedge scholar, ruin scavenger,
militia runner, or ordinary person who learned early that ordinary people keep
the world alive.

### Cultural anchors

- **Greeting:** “How is the road behind you?”
- **Keepsake:** A blue-glass lantern bead.
- **Common virtue:** Mutual aid.
- **Common failing:** Suspicion of plans too elegant to repair with rope.
- **Public concern:** The old quest roads are becoming active again as
  Darklings seek forgotten artifacts.

### Media anchors

Show a temperate coast joined to inland roads, farms, forest margins, blue
warning lanterns, and half-buried ruins. Ashenport may appear on the horizon
but must not consume the scene.

### Provenance

The region's city, village, forest, ruin, cave, and quest topology is grounded
in `/home/aiwithapex/projects/Luminari-Source/src/transport.c:98-110`,
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:148-159`, and the
approved Ashenport/Mosswood timeline. This document establishes `Onduis` as the
canonical spelling and treats `Ondius` as a migration alias.

## Selerish

- **Stable ID:** `homeland/selerish`
- **Kind:** Coastal scholarly province
- **Political sphere:** Magocracy of Chulan
- **Heart Tongue:** Seleric

### Card summary

A rain-bright coast where arguments are archived, storms are named, and magic
must survive peer review.

### Player-facing lore

Selerish occupies a long southeastern shelf where warm sea air strikes black
cliffs and becomes rain. Its harbors smell of wet slate, ink, and citrus peel.
The province entered Chulan's sphere not by conquest but by examination: its
three coastal colleges challenged the Council of Nine to prove that rule by
magic was better than rule by evidence. Chulan answered with a decade of
debates. Nobody agrees who won, so both sides claim the result.

Every Selerish town keeps a **Book of Disagreements** in its public hall.
Citizens may record a claim, a counterclaim, and the evidence that would change
their mind. Children learn to sign their first page before they learn formal
spellcraft. The practice has made Selerish excellent at navigation, weather
prediction, and finding polite ways to call an archmage wrong.

Corm Orp is the best-known port, though Selerish people insist it is neither
the oldest nor the most beautiful. Inland, rain terraces carry orchards and
herbs used by healers across Lumia. Along the cliff road stand abandoned
observatories whose brass roofs still turn toward stars no current chart
contains.

### What growing up here teaches

Selerish teaches that changing one's mind is a discipline, not a defeat.
Choose it for a skeptic, weather-worker, healer, navigator, apprentice mage,
archivist, or curious soul who would rather ask a dangerous question than
inherit a comfortable lie.

### Cultural anchors

- **Greeting:** Offer a claim and its exception: “The day is fair, unless the
  west wind has news.”
- **Keepsake:** A slate token bearing the first question one remembers asking.
- **Common virtue:** Intellectual honesty.
- **Common failing:** Turning grief, love, and danger into debates.
- **Public concern:** Chulan's Reality Revision experiments have caused
  impossible weather along the southern capes.

### Media anchors

Show black sea cliffs, rain silvering slate roofs, orchard terraces,
observatories, and restrained arcane instruments. Avoid generic wizard towers
floating in empty sky; Selerish magic is empirical, coastal, and inhabited.

### Provenance

The Corm Orp and seaport anchors come from
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:114-115` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:155-157`. Its
relationship to Chulan, civic customs, and scholarly identity are newly
established to connect the runtime region to the approved Magocracy.

## Carstan

- **Stable ID:** `homeland/carstan`
- **Kind:** Glass-coast province
- **Political sphere:** Magocracy of Chulan
- **Heart Tongue:** Carstani

### Card summary

A sun-struck coast of glassworks, hard bargains, and towers that remember
lightning.

### Player-facing lore

Carstan is where Lumia's eastern stone meets a sea so bright that sailors wrap
dark cloth around their eyes at noon. Long ago, a storm of magical fire melted
whole beaches into green-black glass. Carstani builders learned to cut those
sheets without waking the sparks trapped inside. Their windows hold dawn for
hours. Their lenses can find flaws in gems, armor, and occasionally arguments.

The Glass Tower rises above the inner coast, part observatory, part lightning
archive. Every storm that strikes its crown leaves a branching white memory in
the walls. Chulan's scholars study the marks as records of the Loom under
stress. The fishing and smuggling town of Hardbuckler distrusts this
interpretation and maintains that lightning simply has terrible handwriting.

Carstan joined Chulan after bargaining for the **Right of Refusal**: no
provincial household may be compelled to participate in an experimental spell.
This right is fiercely guarded, frequently litigated, and sometimes sold for
an alarming sum.

### What growing up here teaches

Carstan teaches that beauty can be dangerous long after the fire is gone.
Choose it for a glassworker, storm-reader, smuggler, advocate, artificer,
fisher, or anyone who has learned to look through a thing without mistaking
clarity for truth.

### Cultural anchors

- **Greeting:** Hold a hand to the light so the other person can see it is
  empty.
- **Keepsake:** A piece of harmless stormglass wrapped in wire.
- **Common virtue:** Precision.
- **Common failing:** Testing people to destruction to learn how they break.
- **Public concern:** New lightning marks in the Glass Tower form the same
  pattern as cracks around Chulan's revised histories.

### Media anchors

Show luminous glass beaches, working furnaces, a storm-marked tower, bright
sea, and practical port life. The glass must look crafted and weathered, not
like a pristine crystal-dwarf cavern.

### Provenance

The Glass Tower, Hardbuckler, and east/west ports are runtime anchors at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:122-123` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:159-161`. Their
meanings, Carstan's charter rights, and its relationship to Chulan are newly
established.

## Axtros

- **Stable ID:** `homeland/axtros`
- **Kind:** Eastern maritime march
- **Political sphere:** Free Cities of Kohn
- **Heart Tongue:** Axtrosi

### Card summary

An eastern road-and-sea march that keeps trading while the Silent City watches
from behind pale walls.

### Player-facing lore

Axtros stretches along Lumia's eastern sea-lanes, a country of dry headlands,
red grass, salt vineyards, and roads built broad enough for two caravans to
pass without either admitting fear. Sanctus stands within it but never ruled
it. The region is a braid of independent port councils, caravan families, and
the old **March Wardens**, who maintain wells and warning towers in exchange
for hospitality rather than taxes.

Since the Silence, Axtros has become the hinge on which half the eastern world
turns. The Pilgrim's Ring receives Sanctine refugees and contains the trade
that once crossed Sanctus proper. Quarantine lanterns burn violet along the
roads. Every inn keeps a mirror by the door—not for vanity, but because people
returning from the Silent boundary sometimes forget to cast reflections in
the same direction as everyone else.

Axtrosi culture prizes motion with memory. Caravan families carry household
shrines on wagons. Vintners bury one bottle from every harvest beside a road
marker, “so the land may taste what it gave.” Children learn the routes by
song, and a missed verse can put a traveler a hundred miles wrong.

### What growing up here teaches

Axtros teaches hospitality with boundaries. Choose it for a caravaner, scout,
vintner, border guard, refugee worker, road-priest, or someone who knows that
an open door and an unwatched door are not the same thing.

### Cultural anchors

- **Greeting:** “Water first, questions after.”
- **Keepsake:** A violet-glass road lantern or a knotted route cord.
- **Common virtue:** Prepared generosity.
- **Common failing:** Measuring every newcomer as a possible danger.
- **Public concern:** The Silence tests quarantine, trade, and trust every day.

### Media anchors

Show red-grass headlands, caravan roads, salt vineyards, violet warning
lanterns, and Sanctus's pale distant rings. Do not make Axtros synonymous with
the Silent City.

### Provenance

Sanctus and multiple ports place the eastern runtime network within Axtros at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:166-175`. The
Silence derives from established Sanctus canon. Axtros's land, culture, and
March Warden tradition are newly established.

## Hir

- **Stable ID:** `homeland/hir`
- **Kind:** Inland river basin
- **Political sphere:** Empire of New Anteria
- **Heart Tongue:** Hiri
- **Contained place:** Pesh

### Card summary

A broad river basin where the living bargain with inherited duty and every old
road seems to remember a war.

### Player-facing lore

Hir is a basin of long rivers and low brown hills west of Onduis. Pesh, its
oldest market city, sits where three stone roads meet a ford that no flood has
managed to move. This is why travelers say **Hir/Pesh** when they mean the
region's commercial heart, much as sailors may use a harbor's name for the
whole coast.

The Empire of New Anteria claims Hir through inheritance tablets recovered
after the fall of Old Anteria. Hir accepts the claim with qualifications,
footnotes, and several armed tollhouses. Its villages send grain and recruits
to the Empire; in return, New Anteria's Registered Dead maintain ancient
causeways and remember where plague pits must never be opened.

Hiri households keep a **Second Chair** at important meals. It may honor an
ancestor, an absent traveler, or the person one has not forgiven yet. No one
sits there. To remove it is to declare that the past has no claim on the
present, a statement considered either monstrous or brave.

Grunwald guards the western road, while Pesh's traders carry news between
Onduis, the Ubdinas, and the Anterean interior. Old quest records place
Darkling agents, half-orc camps, and the earliest resistance routes across
this basin. The locals do not call that history. They call it directions.

### What growing up here teaches

Hir teaches that inheritance can be shelter, debt, or both. Choose it for a
road warden, farmer, ancestor-keeper, dissident, half-orc veteran, merchant, or
someone deciding which obligations deserve to survive them.

### Cultural anchors

- **Greeting:** Touch the nearest doorframe and say, “May what follows enter
  honestly.”
- **Keepsake:** A river-smoothed stone marked with a household name.
- **Common virtue:** Loyalty across generations.
- **Common failing:** Allowing old duties to make new choices impossible.
- **Public concern:** Darkling routes thought broken after the old wars are
  being walked again.

### Media anchors

Show river roads, low hills, grain fields, old Anterean causeways, mixed living
and Registered Dead labor, and distant Pesh market roofs. Do not reuse
Ashenport's harbor skyline.

### Provenance

Runtime places Grunwald in Hir at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:125-126` and
separately locates Pesh. The archived Hir/Pesh quest treats the basin as a
distinct route and market region. This record promotes that distinction,
rejects the erroneous Ashenport alias, and newly establishes Hir's qualified
relationship with New Anteria.

## Quechian

- **Stable ID:** `homeland/quechian`
- **Kind:** Twilight-forest province
- **Political sphere:** Mosswood Federation
- **Heart Tongue:** Quechian

### Card summary

A deep western forest where paths are agreements and no tree is assumed to be
merely scenery.

### Player-facing lore

Quechian lies beneath a canopy so old that noon arrives green and quiet. Its
settlements occupy clearings negotiated with the forest rather than cut from
it. A house may stand for thirty years, then be dismantled because the roots
beneath it have asked for darkness. The request is delivered by druids,
wood-elves, awakened birds, or mushrooms whose legal testimony remains
controversial everywhere except Mosswood.

The province joined the Mosswood Federation by the **Covenant of Shade**. In
return for a voice in the Federation, Quechian protects the old twilight
pools, the Reaching Woods, and the enormous darkwood trees whose roots touch
places not entirely inside the waking world.

Quechian culture distinguishes ownership from stewardship. One may own an axe,
but never the tree it cuts; own a bow, but never the path of the arrow; own a
memory, but not another person's telling of it. Visitors find this poetic until
the first property dispute is adjudicated by a jury of squirrels.

### What growing up here teaches

Quechian teaches attention to lives that cannot speak in familiar ways. Choose
it for a ranger, druid, herbalist, dreamer, patient hunter, seasonal diplomat,
or anyone who suspects every landscape has an opinion.

### Cultural anchors

- **Greeting:** Touch a living leaf, then one's own chest: “We share the
  weather.”
- **Keepsake:** A seed carried in a small cage, planted only when it “chooses”
  a place.
- **Common virtue:** Reverence.
- **Common failing:** Letting deliberation become paralysis.
- **Public concern:** Something in the Giant Darkwood Tree is dreaming with
  another creature's memories.

### Media anchors

Show layered twilight forest, inhabited clearings, living bridges, pools that
reflect unfamiliar skies, and diverse forest peoples. Avoid a generic elven
palace or an untouched wilderness with no evidence of daily life.

### Provenance

Evereska, the Reaching Woods, and Giant Darkwood Tree are runtime anchors at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:116-117` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:179-184`.
Quechian's Federation relationship extends the approved Mosswood principle of
citizenship for all life.

## Vailand

- **Stable ID:** `homeland/vailand`
- **Kind:** Lake-and-heath march
- **Political sphere:** Mosswood Federation
- **Heart Tongue:** Vailic

### Card summary

A western country of windy heaths and wandering lakes, where communities
follow water rather than walls.

### Player-facing lore

Vailand begins where Quechian's trees loosen into heather and high grass. Its
four great lakes do not always remain in the same basins. During certain moon
phases, one will drain without mud or flood and rise days later many miles
away. Villages travel after them on broad wooden runners, leaving stone hearths
for whoever inherits the empty shore.

The Mosswood Federation recognizes Vailand's lakes as voting citizens. Their
voices are interpreted by **mere-listeners**, people trained to read shoreline
changes, fish migrations, and the dreams of those sleeping nearest the water.
Critics say this gives enormous power to a priestly class. Vailanders reply
that the critics have never heard a lake say no.

The region's south road passes old towers and shadowed valleys; its northern
waters reach stranger ruins. Vailanders therefore value portable traditions.
Their law is sung, their family histories are woven into tent bands, and their
dead are remembered with cups of water poured onto whatever ground the
household presently calls home.

### What growing up here teaches

Vailand teaches that leaving a place need not mean abandoning it. Choose it
for a wanderer, fisher, horse-herder, lake mystic, scout, portable artisan, or
someone who believes belonging can move without becoming shallow.

### Cultural anchors

- **Greeting:** Share the direction of the nearest water, whether seen or not.
- **Keepsake:** A cup carved from driftwood of a vanished shore.
- **Common virtue:** Adaptability.
- **Common failing:** Departing before a difficult root can take hold.
- **Public concern:** One wandering lake returned carrying a drowned tower no
  Vailic song remembers.

### Media anchors

Show windswept heaths, a migrating lakeside settlement, runner-built homes,
horses, reeds, and an impossible distant shoreline. Do not depict dense
Quechian forest or a fixed feudal castle as the dominant identity.

### Provenance

Vailand's four runtime seaports and scattered neighboring zones are recorded at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:187-193`. Its
wandering waters, culture, and relationship with Mosswood are newly
established, connected to the approved Wandering Isle and Lumia's unstable
geography.

## Oorpii

- **Stable ID:** `homeland/oorpii`
- **Kind:** Northern island league
- **Political sphere:** Free Cities of Kohn
- **Heart Tongue:** Oorpic

### Card summary

A cold island league of rope bridges, elected harbor-mothers, and ships built
to survive the sea changing its mind.

### Player-facing lore

Oorpii is not one island but a chain of basalt backs rising from the northern
sea. Rope bridges join the nearest cliffs; boats join everything else. In
winter, spray freezes sideways and whole villages glitter like chandeliers
until sunrise.

Each island governs itself, but the league chooses a **Harbor-Mother** whenever
storm season begins. The title is not hereditary and need not belong to a
woman. It goes to the person trusted to decide which ships may sail, which must
stay, and which stranded strangers will be fed first. The Harbor-Mother's word
is absolute until the first calm week, after which the office dissolves and
its holder is expected to return every borrowed privilege.

Oorpii joined the Free Cities through a charter written on sailcloth so no
capital could lock it in a vault. Its pilots are prized wherever reefs,
Swiftpath tides, or political tempers make a straight route dangerous. Its
storykeepers carve records into whalebone replicas rather than the bones of
whales; Oorpii law forbids claiming another creature's death as one's own
memory.

### What growing up here teaches

Oorpii teaches that authority is a tool for a storm, not a chair for a
lifetime. Choose it for a pilot, fisher, bridge-runner, storm priest,
shipwright, temporary leader, or someone who knows when survival requires
obedience and when survival requires taking the keys back.

### Cultural anchors

- **Greeting:** Grip forearms and test footing before exchanging names.
- **Keepsake:** A three-knot cord: harbor, vessel, home.
- **Common virtue:** Crisis discipline.
- **Common failing:** Distrusting leadership even when the storm is not over.
- **Public concern:** Northern currents carry warm water and fragments of
  architecture from a coast that should not exist.

### Media anchors

Show basalt islands, rope bridges, steep harbors, ice-bright spray, resilient
wooden buildings, and working vessels. Avoid tropical pirate imagery.

### Provenance

Oorpii's north, east, west, and northwest sea connections appear at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:195-200`.
The island-league government and culture are newly established within the
approved Free Cities framework.

## Kellust

- **Stable ID:** `homeland/kellust`
- **Kind:** Highland reach
- **Political sphere:** Crystal Reaches
- **Heart Tongue:** Tal

### Card summary

A high country where stone sings beneath the snow and every bridge is tuned
before it bears weight.

### Player-facing lore

Kellust occupies the northern heights above the Crystal Reaches. Its valleys
belong to surface farmers, dwarven halls, monastery mines, and Crystal Dwarf
listening posts built where Arcanite veins hum close to the air. Mithril Hall
is its best-known gate, but the Reach extends through seven passes and more
than seven hundred named echoes.

People in Kellust test a structure by song. A mason strikes a bridge and
listens for fear. A miner hums into a wall and waits for the mountain's refusal.
A family settling an argument may ask each person to sustain a note until the
discord resolves—not because agreement is always possible, but because hidden
strain should be heard before it becomes fracture.

Surface Kellustans and Crystal Dwarves do not pretend to be one people. They
share roads, trade, and the Heart Tongue Tal, while disagreeing over mining,
memory, caste, and who is entitled to call a mountain an ancestor. The
Arcanite crisis has sharpened every disagreement. Still, when an avalanche
falls, all voices join the same rescue chord.

### What growing up here teaches

Kellust teaches that strength is not silence; sound reveals where strength
fails. Choose it for a miner, mason, resonator, mountain guide, archivist,
craftsperson, or someone caught between inherited communities.

### Cultural anchors

- **Greeting:** Tap stone, wood, or metal once and listen before speaking.
- **Keepsake:** A tuning shard matched to one's birth hall or valley.
- **Common virtue:** Structural honesty.
- **Common failing:** Confusing measurable purity with moral worth.
- **Public concern:** Several deep veins have gone silent, an omen Crystal
  Dwarves fear more than collapse.

### Media anchors

Show high snowy passes, inhabited stone valleys, subtle Arcanite light,
Mithril Hall approaches, resonant bridges, and both organic and Crystal Dwarf
communities. Do not make every inhabitant crystalline.

### Provenance

Mithril Hall, Dwarven Mines, and Kellust's seven ports are runtime anchors at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:127-128` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:202-213`. The
Crystal Reaches, Tal, harmonic culture, and Arcanite crisis are established in
`lore_docs/canon/locations/the_five_nations.md`,
`lore_docs/canon/cultures/races_of_lumia.md`, and the Lumia timeline.

## East Ubdina

- **Stable ID:** `homeland/east-ubdina`
- **Kind:** River-and-forest province
- **Geographic parent:** Ubdina
- **Political sphere:** Empire of New Anteria
- **Heart Tongue:** Ubdinic, eastern register

### Card summary

The greener half of a divided southern land, where forest roads and ancestor
bridges carry both trade and old resentment.

### Player-facing lore

Ubdina was one province before the Ash Years broke its central river into two
channels and its surviving councils into two certainties. East Ubdina took the
forests, broad water, and the old imperial road toward New Anteria. West Ubdina
took the frost basins, marsh coast, and most of the province's grief.

East Ubdina is a land of red-barked forests and deep rivers crossed by
**ancestor bridges**. The Empire's Registered Dead tend these bridges, not as
slaves but as officeholders whose terms continue until a named repair is
finished. Some have served for a century because their descendants keep
finding new cracks.

Villages hold **two-name markets**. Sellers display a public price and a
remembered price: what the item cost before the division. No one must honor
the old price, but refusing to show it is considered a claim that history does
not matter. The custom causes excellent arguments and terrible accounting.

### What growing up here teaches

East Ubdina teaches the uses and dangers of continuity. Choose it for a
forester, river trader, bridge keeper, imperial clerk, skeptic of empire,
explorer, or someone trying to repair an inheritance without becoming trapped
inside it.

### Cultural anchors

- **Greeting:** Give both family name and chosen name, if they differ.
- **Keepsake:** A copper bridge nail stamped with a predecessor's initials.
- **Common virtue:** Stewardship.
- **Common failing:** Repairing a system long after it should be replaced.
- **Public concern:** Bloodfist raiders and strange wyrms have made the
  southern roads unreliable.

### Media anchors

Show broad rivers, red-barked forest, long stone-and-wood bridges, active
villages, and respectful cooperation between living and Registered Dead.
Avoid frozen terrain as the dominant feature.

### Provenance

Bloodfist Caverns and East Ubdina's forest, settlement, and southern sea
routes are runtime anchors at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:112-113` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:215-222`. The
division of Ubdina and its Anterean relationship are newly established.

## West Ubdina

- **Stable ID:** `homeland/west-ubdina`
- **Kind:** Frost-and-marsh province
- **Geographic parent:** Ubdina
- **Political sphere:** Empire of New Anteria
- **Heart Tongue:** Ubdinic, western register

### Card summary

The colder half of Ubdina, where marsh lights, frost keeps, and stubborn
villages outlast every map drawn over them.

### Player-facing lore

West Ubdina lies below long winter skies. Its northwestern heights carry the
Frozen Castle; its coast descends through reed marsh and black water toward
old keeps, grave roads, and villages built on pilings. Winter comes early, fog
comes whenever it pleases, and the lights walking over the marsh are not
always lanterns.

After Ubdina divided, the west refused to move its provincial dead to New
Anteria's registries. Instead, communities maintain local **Hearth Rolls**:
lists of the living, the dead, the missing, and those whose state is presently
under dispute. New Anterian law recognizes three categories. West Ubdina
recognizes that the world is rarely so tidy.

The province is famous for **thaw feasts**. When the first river ice breaks,
neighbors carry preserved food into the road and feed whoever arrives,
including rivals. A feud may resume at sunset, but no hunger is allowed to
cross the thaw. West Ubdinans say civilization is proven by what it postpones
for mercy.

### What growing up here teaches

West Ubdina teaches endurance without romance. Choose it for a marsh guide,
grave tender, hunter, keep survivor, herbalist, local patriot, or anyone who
knows that stubbornness can be both shield and prison.

### Cultural anchors

- **Greeting:** “Is your hearth named?”—a question of shelter, not ownership.
- **Keepsake:** A reed ring sealed in winter wax.
- **Common virtue:** Endurance.
- **Common failing:** Treating help as an attempt to claim authority.
- **Public concern:** Marsh paths change overnight, and the Frozen Castle has
  begun showing fire in windows long thought empty.

### Media anchors

Show cold marsh, reed-built settlements, distant frostbound heights, warm
hearth light, and grave-road markers. Avoid making the region a featureless
snowfield.

### Provenance

The Frozen Castle, Lizard Marsh, graveyard, trail, and five coastal routes are
runtime anchors at
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:119-120` and
`/home/aiwithapex/projects/Luminari-Source/src/transport.c:224-232`. West
Ubdina's culture and relationship to East Ubdina and New Anteria are newly
established.

## Homeland Data Contract

Every implementation record derived from this canon must carry:

- legacy runtime value;
- stable Homeland ID;
- display name;
- place kind;
- geographic parent, when applicable;
- political sphere;
- short card summary;
- full player-facing lore;
- Heart Tongue stable ID and display name;
- gameplay-facing cultural hook;
- current public concern;
- canon version;
- approval status;
- source references;
- legacy aliases;
- media anchors and explicit anti-anchors.

`homelands-1.0.0` is the first complete approved set. Draft geography may
inspire later revisions, but no draft may override these records without a
canon-version change and review.

The selectable Hometown record must carry its runtime stable ID, city name,
card summary, detail text, mechanical-purpose summary, media key, and the stable
Homeland record it reuses for city lore.

## Canon and Runtime Boundaries

- This document establishes public identity, culture, geography, and language.
  It does not assign numeric language enums or alter saved region values.
- Runtime mechanics remain authoritative for what a language proficiency
  enables. Each Homeland must grant its listed Heart Tongue in addition to
  universal Common; returning `LANG_COMMON` for every region does not satisfy
  this canon.
- Dynamic wilderness `region_data` remains a separate spatial system unless a
  future mapping explicitly binds a polygon to a stable Homeland ID.
- Imported zone names may remain as production identifiers while their
  player-facing presentation is adapted. They are evidence of topology, not
  automatic canon.
- Region-specific media must follow the anchors above. When an image cannot be
  reconciled, the neutral region fallback is more truthful than beautiful
  invention.

## Source Ledger

### Approved Lore Sage foundations

- `lore_docs/canon/locations/the_five_nations.md`
- `lore_docs/canon/locations/the_swiftpaths.md`
- `lore_docs/canon/cultures/races_of_lumia.md`
- `lore_docs/canon/timeline/timeline.md`
- `lore_docs/canon/timeline/ages.md`
- `lore_docs/canon/factions/the_villian_hierarchy.md`

### Runtime topology consulted

- `/home/aiwithapex/projects/Luminari-Source/src/constants.c:4715-4719`
- `/home/aiwithapex/projects/Luminari-Source/src/structs.h:1053-1066`
- `/home/aiwithapex/projects/Luminari-Source/src/transport.c:98-232`
- `/home/aiwithapex/projects/Luminari-Source/src/race.c:6267-6426`

### Draft evidence adjudicated

- `lore_docs/drafts/locations/LEGENDARY_LOCATIONS.md`
- `lore_docs/drafts/locations/Hir_Pesh Region Main Quest (Darkling).md`
- `lore_docs/drafts/locations/Ashenport Region Main Quest.md`
- `lore_docs/drafts/cultures/CULTURES_OF_LUMIA.md`

Draft material was treated as testimony, not authority. Its useful particulars
were promoted only where this document resolves their contradictions.

---

_A map is a promise that a place will stay put. A Homeland is what remains
when it doesn't._
