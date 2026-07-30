# The Heart Tongues of the Homelands

- **Canon status:** [ESTABLISHED]
- **Canon version:** `homeland-languages-1.0.0`
- **Approved use:** Character creation, language help, regional dialogue,
  onboarding facts, and language-mechanics implementation
- **Spoiler level:** Player-safe

_Set down by Meret-of-Many-Doors, who claimed fluency in twelve languages and
good manners in three. Contemporary witnesses dispute the second figure._

## Trade Tongue and Heart Tongue

Most people in Lumia know **Common**, also called the Trade Tongue. It carries
prices, directions, laws, jokes, threats, and the thousand small necessities
that let strangers share a road. Common is invaluable. It is also deliberately
plain. Generations of merchants have worn away ambiguities until a sentence can
cross three borders without changing shape.

A **Heart Tongue** does the opposite. It carries the things a people refused to
sand smooth: who speaks first at a funeral, whether a promise belongs to the
speaker or the listener, how to address a river in flood, and which silence
means respect rather than fear.

In character creation, every Homeland grants its listed Heart Tongue in
addition to Common. This must be a real language proficiency with a
player-facing name and help entry. Returning Common for all Homelands grants
nothing and is not a valid implementation of this canon.

The tongues below are cultural languages, not biological restrictions.
Migration, education, family, magic, and friendship carry language across every
border.

## Language Registry

| Stable ID             | Display name | Homeland grants             | Family               | Writing system                 |
| --------------------- | ------------ | --------------------------- | -------------------- | ------------------------------ |
| `language/ashen-cant` | Ashen Cant   | Ashenport                   | Shallow Sea Trade    | Quaymarks and Common script    |
| `language/sanctine`   | Sanctine     | Sanctus                     | Kohn Charter         | Bellhand                       |
| `language/onduic`     | Onduic       | Onduis                      | Shallow Sea Trade    | Roadhand                       |
| `language/seleric`    | Seleric      | Selerish                    | Chulani Scholastic   | Slate script                   |
| `language/carstani`   | Carstani     | Carstan                     | Chulani Scholastic   | Faceted script                 |
| `language/axtrosi`    | Axtrosi      | Axtros                      | Eastern Road         | Knot script and Common letters |
| `language/hiri`       | Hiri         | Hir                         | Anterean-Peshic      | Riverhand                      |
| `language/quechian`   | Quechian     | Quechian                    | Verdanian            | Living notches                 |
| `language/vailic`     | Vailic       | Vailand                     | Verdanian            | Woven record                   |
| `language/oorpic`     | Oorpic       | Oorpii                      | Northern Maritime    | Rope-runes                     |
| `language/tal`        | Tal          | Kellust                     | Crystalline Harmonic | Resonance notation             |
| `language/ubdinic`    | Ubdinic      | East Ubdina and West Ubdina | Old Anterean         | Hearth script                  |

Language IDs are stable content identifiers. A source implementation may map
them to numeric skill constants, but must not use display text as identity.

## Ashen Cant

- **Stable ID:** `language/ashen-cant`
- **Pronunciation:** `ASH-en kant`

Ashen Cant began as dock labor made audible. A crane team needed to know
whether _hold_ meant keep the rope or stop the cargo, whether _clear_ meant the
deck or the debt, whether a stranger was lost or merely pretending. The
language grew from shouted verbs, hand signs, tally marks, sailors' curses, and
the private jokes of people carrying another person's fortune over deep water.

Its grammar puts consequence before intention. An Ashen speaker does not say,
“I meant to secure the line.” They say, “The line held; my hand was on it,” or,
if honesty requires, “The line broke; my hand was on it.” This makes the tongue
excellent for contracts and merciless during apologies.

Quaymarks can be scratched with one hand while the other holds a rope. Three
short strokes mean safe water. A hooked stroke warns that a bargain has an
unspoken cost. Children chalk the marks in alleys until every wall looks like a
ship's log arguing with itself.

**Sample expression:** _“Count the hands, then count your fingers.”_ Trust the
crew, but verify the bargain.

**Player help summary:** The fast, consequence-first harbor tongue of
Ashenport's docks, markets, and Republic wards.

## Sanctine

- **Stable ID:** `language/sanctine`
- **Pronunciation:** `SANK-teen`

Sanctine is measured in words and pauses. Its speakers believe meaning includes
the space left for another person to answer. A formal statement is incomplete
until it has been followed by a silence of the proper length: one breath for a
fact, two for a promise, three for grief.

The Bellhand script resembles hanging chimes. Vertical lines mark speakers;
small suspended signs mark how long a reader should wait before continuing.
Court records written in Bellhand can look sparse to outsiders, but a trained
reader sees hesitation, invitation, refusal, and consent made visible.

The recent **Silent Register** is not ordinary Sanctine. It strips emotion,
overlaps voices, and removes the personal pauses that let disagreement exist.
Refugees call it “speech with all the doors bricked shut.” Character creation
grants living Sanctine, never the Silent Register.

**Sample expression:** _“I leave a bell between us.”_ I have spoken; the next
word belongs to you.

**Player help summary:** The deliberate language of Sanctus, where pauses carry
consent, doubt, and respect as clearly as words.

## Onduic

- **Stable ID:** `language/onduic`
- **Pronunciation:** `ON-doo-ik`

Onduic belongs to roads, farms, and neighboring villages. It is rich in words
for distance measured by effort: a _bootmile_ is easy ground, a _wetmile_
crosses water, and a _griefmile_ is any road walked home with bad news. Maps in
Onduic often seem inaccurate because they chart what travel costs rather than
how far it lies.

Its Roadhand writing uses long strokes for routes and short cuts for shelter,
water, danger, and obligation. A message can be read upright on a page or
sideways along a signpost. During the Lantern Compact, three blue marks beside
a settlement's name mean that aid has been requested and no payment may be
demanded before the danger passes.

Onduic speakers often answer a question by naming the road that led to their
answer. This can sound evasive. It is usually an offer of context.

**Sample expression:** _“A straight road still has weather.”_ A simple plan is
not a certain one.

**Player help summary:** The practical road language of Onduis, shaped by
distance, mutual aid, and the changing cost of travel.

## Seleric

- **Stable ID:** `language/seleric`
- **Pronunciation:** `seh-LAIR-ik`

Seleric treats certainty as a temporary office. Every declarative sentence
must indicate how the speaker knows: witnessed, measured, remembered, inferred,
or trusted from another. A sixth marker means “I want this to be true,” a
useful honesty that many political languages lack.

Slate script was designed to be corrected. Its letters leave intentional gaps
where a later hand may add doubt or better evidence. Permanent inscriptions
are considered arrogant unless they describe where to find drinking water.

Selerish weather-workers value the language because it can hold competing
predictions without collapsing them into one answer. Chulani mages value it
because a spell premise written in Seleric reveals exactly where an assumption
entered. Lovers value it because “I trust” and “I have verified” cannot be
confused.

**Sample expression:** _“Measured at noon; ask again by rain.”_ This is true
under the conditions in which I learned it.

**Player help summary:** The evidence-marking language of Selerish scholars,
healers, navigators, and public arguments.

## Carstani

- **Stable ID:** `language/carstani`
- **Pronunciation:** `kar-STAH-nee`

Carstani words are built like cut glass. A root names the thing; a suffix names
the angle from which it is seen. The same storm may be _danger-from-sea_,
_power-in-tower_, _beauty-after-fire_, or _debt-not-yet-paid_. None is treated
as the whole storm.

Faceted script changes meaning when turned. Legal documents are written so
that the promise remains valid from every permitted orientation. Smugglers
have developed contracts that become different contracts when held to a lamp,
a practice the provincial courts admire aesthetically and punish severely.

Carstani contains no neutral word for transparency. One must specify whether
something is visible because it is honest, thin, exposed, or empty.

**Sample expression:** _“Turn the glass.”_ Look again from the side that costs
you something.

**Player help summary:** Carstan's many-angled glass-coast tongue, used by
artisans, advocates, storm-readers, and smugglers.

## Axtrosi

- **Stable ID:** `language/axtrosi`
- **Pronunciation:** `ak-STROH-see`

Axtrosi began in caravan songs whose rhythm matched walking feet. Routes are
verbs: to travel east is not merely movement but _to seek dry wind_; to turn
toward Sanctus is now _to approach the held breath_. A route sung with the
wrong tense can send a listener toward where a road used to be.

Important records are kept as knot script. Fiber identifies the route, knot
shape the event, spacing the time between safe water. A family shrine cord may
contain generations of journeys and can be read in darkness by touch.

Hospitality grammar distinguishes a guest who has been offered water, food,
shelter, confidence, or protection. Each is a separate promise. This precision
lets an Axtrosi host be generous without accidentally declaring a blood feud on
the guest's enemies.

**Sample expression:** _“Water is given; the gate is considered.”_ You are
welcome to recover, but trust has stages.

**Player help summary:** The sung road language of Axtros, preserving routes,
hospitality, and careful boundaries.

## Hiri

- **Stable ID:** `language/hiri`
- **Pronunciation:** `HEER-ee`

Hiri formed where Old Anterean met the market speech of Pesh. Anterean gave it
formal words for duty, office, and inheritance. Pesh gave it quick compounds
for weather, trade, and polite refusal. The result can describe a debt with
terrifying precision and then negotiate three ways not to pay it.

Riverhand runs in parallel lines. The upper line records what was promised;
the lower records what occurred. Space between them is called the **water of
judgment**. A contract with no space is either perfectly kept or suspiciously
edited.

Hiri has separate pronouns for the dead who are remembered, the dead who still
serve, and the dead who should be allowed to rest. Using the wrong one is not
always an insult. Sometimes it is a political declaration.

**Sample expression:** _“The river heard both names.”_ What was promised and
what was done will be remembered together.

**Player help summary:** The river-and-market language of Hir and Pesh, joining
Anterean memory to frontier practicality.

## Quechian

- **Stable ID:** `language/quechian`
- **Pronunciation:** `KWEH-chee-an`

Quechian is a Verdanian language shaped by layered attention. Its verbs specify
whether an action affects the speaker, another person, a community, an animal,
a rooted life, or the place itself. A sentence such as “we built a house” is
grammatically incomplete until the speaker says what the clearing lost and
what the roots gained.

Living notches are cut only into shed bark, fallen wood, or branches freely
offered through druidic rite. The marks deepen as the material dries. A text
therefore changes slowly with age, and readers learn to distinguish what the
writer made from what weather later emphasized.

Quechian names often contain a future clause. A child may be called
Rain-Waits-For-Roots, then shorten or alter the name when its promised meaning
arrives.

**Sample expression:** _“Ask the shade what paid for it.”_ Every shelter has a
cost borne by someone or something.

**Player help summary:** The living forest tongue of Quechian, attentive to the
effects of every choice on people, creatures, and place.

## Vailic

- **Stable ID:** `language/vailic`
- **Pronunciation:** `VAY-lik`

Vailic is Quechian's wind-traveled cousin. It has few fixed directional words.
Instead, a speaker locates something by water, wind, and remembered movement:
_lakeward_, _after-the-geese_, _three camps before thaw_. Outsiders complain
that a Vailic map is a story. Vailanders answer that a map which cannot survive
the lake moving is only a drawing.

Woven records use color for place, knot density for duration, and frayed ends
for uncertainty. Family histories serve as tent bands. Unweaving one is both
historical revision and structural risk, which Vailanders consider an honest
metaphor.

Vailic distinguishes leaving because one chooses, leaving because the land
changes, and leaving so that return remains possible.

**Sample expression:** _“Carry the shore lightly.”_ Belong without demanding
that home stay unchanged.

**Player help summary:** Vailand's mobile lake-and-heath language, woven to
preserve routes and belonging through change.

## Oorpic

- **Stable ID:** `language/oorpic`
- **Pronunciation:** `OR-pik`

Oorpic is spoken through wind. Its vowels are long enough to survive distance,
its consonants sharp enough to cross surf, and many phrases have a whistle
form for use between cliffs or ships. A fluent speaker can give basic harbor
orders without opening their mouth.

Rope-runes are knots whose direction matters. Read from one end, a line may
record departure; from the other, return. Harbor law requires emergency orders
to read the same both ways, preventing an ambitious Harbor-Mother from turning
a temporary power into a permanent one through clever wording.

Oorpic has thirteen ordinary words for storm and one sacred term,
_vaor_, for a storm that changes who returns. The sacred word is never used in
a forecast.

**Sample expression:** _“Untie it in calm.”_ Power granted for danger must end
when danger does.

**Player help summary:** The wind-carrying tongue and tactile rope script of
Oorpii's ships, bridges, and temporary councils.

## Tal

- **Stable ID:** `language/tal`
- **Pronunciation:** A spoken approximation is `tahl`; its true name is a chord.

Tal is not merely heard. It is felt through teeth, tools, floors, and the
Arcanite lattice inside a Crystal Dwarf's body. A word may contain a fundamental
tone for subject, an overtone for relation, and a pulse for time. Skilled
resonators can carry an argument through solid stone farther than a shout
crosses open air.

Organic Kellustans speak and sign a surface form of Tal using voice, tuning
shards, and resonance notation. Crystal Dwarves regard this form as accented
but valid. The most important distinction is not pronunciation but listening:
a Tal statement is unfinished until the speaker has tested how it resonates in
the material around them.

Tal's famous lack of “maybe” is often misunderstood. It expresses uncertainty
as competing harmonics rather than a single word. To an untrained ear, doubt
sounds like music refusing to resolve.

**Sample expression:** _“Hear the hidden fracture.”_ Strength includes honest
knowledge of where one may break.

**Player help summary:** The harmonic Heart Tongue of the Crystal Reaches and
Kellust, spoken in voice, vibration, and stone.

## Ubdinic

- **Stable ID:** `language/ubdinic`
- **Pronunciation:** `oob-DIN-ik`

Ubdinic descends from Old Anterean but has outgrown the empire that named it.
Its Hearth script circles a central mark representing shelter. East Ubdinic
adds bridge-shaped clauses and preserves formal ancestral titles. West Ubdinic
uses open circles, leaving a gap for the missing, disputed, or not-yet-returned.
The registers sound different but remain mutually intelligible.

Every Ubdinic noun can be marked as living, dead, returned, missing, or
remembered. The marking describes relationship rather than biology. A ruined
house may be “dead” if no one mourns it, while a grandparent a century gone may
remain “living” in household decisions.

Speakers from both provinces share the **Mercy Future**, a tense for an action
one intends but has postponed so that another person may survive or retain
dignity. It appears often in thaw-feast truces and rarely in imperial tax law.

**Sample expression:** _“The hearth has an open name.”_ There is shelter here
for someone not yet known or not yet returned.

**Player help summary:** The shared Heart Tongue of East and West Ubdina, rich
in words for memory, states of being, and merciful delay.

## Regional Registers Are Not Separate Rewards

These named registers add flavor but do not require separate proficiencies:

- **Sanctine Silent Register:** A hostile or compromised current register, not
  the language granted at creation.
- **Eastern and Western Ubdinic:** Mutually intelligible registers of Ubdinic.
- **Peshic Hiri:** The fast market register of Hiri.
- **Surface Tal:** A voiced and signed register of Tal used by organic
  Kellustans.
- **Ashen quay-sign:** The manual register of Ashen Cant.
- **Oorpic whistle speech:** The distance register of Oorpic.

## Implementation Requirements

1. A Homeland choice grants exactly the stable Heart Tongue listed in the
   registry. East and West Ubdina both grant Ubdinic.
2. Common remains universal and is never displayed as the Homeland's special
   language reward.
3. UI facts use the display name, never an internal effect or spell-category
   label.
4. Language help includes the player help summary and a link or reference to
   its full record.
5. Existing characters retain legacy data. A migration may infer a Heart
   Tongue from a saved Homeland only when doing so cannot remove a language the
   character already knows.
6. Tests iterate all thirteen Homelands, reject Common as the mapped reward,
   reject blank/placeholder names, and verify that each stable language ID
   resolves.
7. The language layer owns communication mechanics. Lore text must not imply
   combat, spell, or social bonuses unless source mechanics explicitly add
   them.

## Provenance and Promotion Notes

- Tal and its harmonic role are established in
  `lore_docs/canon/locations/the_five_nations.md`,
  `lore_docs/canon/cultures/races_of_lumia.md`, and the Lumia timeline.
- The Three Tongue model, Old Anterean, Verdanian, Sanctus Silent, and Shallow
  Sea language ideas were promoted and substantially reconciled from
  `lore_docs/drafts/cultures/CULTURES_OF_LUMIA.md`.
- All other named languages and writing systems are newly established here to
  make the approved Homeland registry complete.
- The current source fallback at
  `/home/aiwithapex/projects/Luminari-Source/src/race.c:6421-6426` returns
  Common for every default-campaign region. It is documented evidence of an
  implementation gap, not language canon.

---

_Common lets you ask where the road goes. A Heart Tongue lets you understand
why someone stayed._
