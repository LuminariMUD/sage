# The Character's Compass

- **Canon status:** [ESTABLISHED]
- **Canon version:** `character-compass-1.0.0`
- **Approved use:** Character creation help, role-play profile guidance,
  background biographies, and inspiration generation
- **Spoiler level:** Player-safe

_A field guide attributed to Nalla Three-Inks, who spent forty years asking
heroes who they were and another twenty learning not to believe the first
answer._

## Why the Compass Exists

A character sheet can tell us how far someone can run, how hard they can
strike, and what miracles answer when they call. It cannot tell us why they
left home, whose name makes them stop at a doorway, or which beautiful lie they
still need to believe.

The Character's Compass has five points:

- **Goals** point toward what the character wants.
- **Personality** describes how they move through the world.
- **Ideals** name the principles by which they choose.
- **Bonds** tie them to people, places, promises, and possessions.
- **Flaws** reveal where pressure may bend or break them.

These are role-play tools, not tests. There is no optimal answer, no required
length, and no demand that a character remain unchanged. A compass is useful
because the traveler moves.

## Complete Role-Play Hub Lexicon

Every item on the role-play profile hub needs a short explanation even while
unset. The hub must never require a player to open an unfamiliar field merely
to learn what it means.

| Profile ID                  | Label             | Hub description                                                                   | Detailed authority                                    |
| --------------------------- | ----------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `profile/short-description` | Short description | A compact first-glance phrase shown when others encounter your character.         | Source-owned descriptor and adjective builder         |
| `profile/long-description`  | Long description  | What another character can observe when they look at yours more closely.          | Player-authored text with source guidance             |
| `profile/background-story`  | Background story  | The formative events and choices that brought your character to the present.      | Player-authored text with source guidance             |
| `profile/background`        | Background        | A permanent life archetype that grants skills and a special ability.              | This Compass plus source-verified mechanics           |
| `profile/goals`             | Goals             | What your character wants, why it matters, and what makes it difficult.           | This Compass                                          |
| `profile/personality`       | Personality       | Habits, mannerisms, tastes, and contradictions that make the character distinct.  | This Compass                                          |
| `profile/ideals`            | Ideals            | Principles the character tries to protect when choices become costly.             | This Compass                                          |
| `profile/bonds`             | Bonds             | People, places, promises, and possessions the character cannot treat as ordinary. | This Compass                                          |
| `profile/flaws`             | Flaws             | Fears, vices, blind spots, or weaknesses that invite meaningful trouble.          | This Compass                                          |
| `profile/age`               | Age               | The character's stage of life and its source-defined ability adjustments.         | Source age table and race rules                       |
| `profile/region`            | Homeland          | The formative origin jurisdiction whose culture and Heart Tongue shaped them.     | `lore_docs/canon/locations/the_thirteen_homelands.md` |
| `profile/faction`           | Faction           | An organization the character joins, with allies, duties, and enemies.            | Live source clan record                               |
| `profile/hometown`          | Hometown          | The city tied to recall, donation services, and hometown-dependent abilities.     | Approved Hometown crosswalk plus source mechanics     |
| `profile/deity`             | Deity             | The divine power the character follows—or an explicit choice to follow none.      | Live source deity record                              |

### Short description

A short description is the first phrase another player sees. It should identify
the character without using their proper name and without describing a
temporary action or mood. Favor a memorable physical feature, bearing, voice,
or manner of dress that remains true across ordinary scenes. The structured
builder owns its allowed features and adjective combinations.

### Long description

A long description answers, “What becomes visible when someone chooses to look
more closely?” Describe enduring appearance, movement, equipment style, and
sensory details another character could reasonably observe. Do not dictate the
observer's emotion, reveal private thoughts, or freeze the character into a
temporary pose they cannot leave.

### Background story

A background story records the path to the beginning of play. Useful histories
name formative people and places, one or two turning points, and at least one
unresolved thread the world may pull later. They need not explain every skill
or pre-solve every mystery. Leave doors for discovery.

### Reflective guidance records

Goals, Personality, Ideals, Bonds, and Flaws each have four public pieces of
copy below. Implementations should keep them in one source-owned record so
terminal and structured clients cannot drift.

### Goals

**Hub summary:** What your character is trying to achieve, why it matters, and
what makes it difficult.

**Screen introduction:** A goal gives your character somewhere to lean. It may
be immediate, such as earning passage across the Shallow Sea; personal, such
as finding a missing teacher; or vast, such as preventing the next Darkling
War. Strong goals include an objective, a reason, and a complication. The
stakes answer what may be lost if the character fails or refuses to try.

**Editor prompt:** What does your character want now? Why do they want it? What
stands in the way, and what will failure cost?

**Generator shape:**

1. **Objective:** A concrete direction, not a guaranteed ending.
2. **Reason:** The need, hope, fear, duty, or desire beneath it.
3. **Complication:** An obstacle that demands choices rather than mere time.
4. **Stakes:** Optional editor guidance describing the cost of failure or
   inaction. A minimal generated outline may fold this into Complication.

Goals can be short-, middle-, or long-term. They can conflict. They should be
revised when play changes the character.

### Personality

**Hub summary:** The habits, mannerisms, tastes, and contradictions that make
your character recognizable.

**Screen introduction:** Personality is how a character's inner life becomes
visible. Prefer specific behavior over broad labels. “I am clever” says
little; “I correct maps in other people's homes” suggests pride, curiosity,
and an excellent way to start an argument. A useful pair of traits often
contains one strength and one complication.

**Editor prompt:** What does your character repeatedly do, notice, enjoy,
avoid, or misunderstand? What would a companion imitate when telling a story
about them?

**Generator shape:** Two distinct first-person traits shaped by the selected
inspiration theme.

### Ideals

**Hub summary:** The principles your character tries to protect when choices
become costly.

**Screen introduction:** An ideal is not a slogan worn when convenient. It is
the belief a character uses to decide between competing goods, or the
justification they reach for when doing harm. Ideals may be noble, selfish,
contradictory, inherited, or newly chosen. The best ones create decisions in
play.

**Editor prompt:** What principle will your character defend at a cost? What
could persuade them that they have understood it wrongly?

**Generator shape:** Two distinct first-person convictions shaped by the
selected inspiration theme. Alignment may color an ideal, but never replaces
one.

### Bonds

**Hub summary:** The people, places, promises, events, and treasured things
your character cannot treat as ordinary.

**Screen introduction:** A bond gives the world a handle on the character. It
may inspire courage or terrible judgment. Name the person, place, promise,
event, or object when possible, and explain why it matters. A bond can be
gained, fulfilled, betrayed, transformed, or released through play.

**Editor prompt:** Who or what can call your character back, draw them onward,
or make them risk more than reason allows?

**Generator shape:** Two distinct first-person connections shaped by the
selected inspiration theme.

### Flaws

**Hub summary:** The fear, vice, compulsion, blind spot, or weakness that can
pull your character against their own interests.

**Screen introduction:** A flaw is an invitation to meaningful trouble, not a
punishment and not permission to spoil another player's play. It should create
choices, consequences, or vulnerability. “I am evil” is too broad. “I mistake
obedience for loyalty when I am afraid” gives the character somewhere to
struggle and grow.

**Editor prompt:** What can provoke, tempt, frighten, or mislead your character?
How does the flaw hurt something they genuinely value?

**Generator shape:** Two distinct first-person complications shaped by the
selected inspiration theme.

## Inspiration Is Not Selection

Personality, Ideals, Bonds, and Flaws may use a Background as an **inspiration
theme**. This does not set, replace, or alter the character's permanent
Background.

Player-facing copy should say:

> Pick an inspiration theme. This only shapes suggestions; it will not set or
> change your character's Background.

Controls should use `Use <theme> for inspiration`, never `Choose <background>`.
Goals do not use a Background theme; they generate a direct goal outline.

The theme descriptions below concern story identity. Permanent Background
mechanics—skill bonuses, feat effects, granted commands, restrictions, and
cooldowns—remain authoritative in Luminari-Source and must be explained from
verified mechanics rather than invented by lore.

## Background Registry

| Runtime value | Stable ID                | Display name | Story promise                                      |
| ------------- | ------------------------ | ------------ | -------------------------------------------------- |
| 1             | `background/acolyte`     | Acolyte      | Service placed between the mortal and the sacred   |
| 2             | `background/charlatan`   | Charlatan    | Desire read quickly and truth bent artfully        |
| 3             | `background/criminal`    | Criminal/Spy | Survival within hidden systems and dangerous trust |
| 4             | `background/entertainer` | Entertainer  | Art made public enough to change a room            |
| 5             | `background/folk-hero`   | Folk Hero    | An ordinary community's extraordinary expectation  |
| 6             | `background/gladiator`   | Gladiator    | Survival performed beneath the judgment of crowds  |
| 7             | `background/trader`      | Trader       | Craft, value, reputation, and exchange             |
| 8             | `background/hermit`      | Hermit       | Solitude that revealed or concealed a truth        |
| 9             | `background/squire`      | Squire       | Service beside an ideal not yet fully earned       |
| 10            | `background/noble`       | Noble        | Privilege carrying power, expectation, and debt    |
| 11            | `background/outlander`   | Outlander    | A life measured by land rather than walls          |
| 12            | `background/pirate`      | Pirate       | Freedom and predation beyond settled law           |
| 13            | `background/sage`        | Sage         | Knowledge pursued until it begins to pursue back   |
| 14            | `background/sailor`      | Sailor       | Duty and belonging aboard a working vessel         |
| 15            | `background/soldier`     | Soldier      | Training, comradeship, and the memory of violence  |
| 16            | `background/urchin`      | Urchin       | A childhood survived in the overlooked city        |

## Acolyte

### Permanent-background biography

You learned sacred work before you understood sacred power. Perhaps you kept
the dawn lamps of Seraphine, counted burial names for Nethris, tuned a roadside
shrine to the Loom, or served a temple whose god never answered in a voice you
could recognize. You know that faith is made from ordinary labor: floors
swept, food shared, rites remembered, grief given a shape it can survive.

An acolyte need not be a divine caster. The calling may be devotion,
scholarship, family duty, refuge, doubt, or an old promise still being tested.

### Inspiration seeds

**Personality**

- I remember the proper rite for every occasion and improvise one when none
  exists.
- I speak gently in temples and argue fiercely about what they owe the hungry.

**Ideals**

- Sacred things are proven by the care they inspire, not the fear they demand.
- A vow freely made can hold more firmly than iron.

**Bonds**

- I still carry the key to a shrine whose doors no longer exist.
- A pilgrim once trusted me with a confession I have never been able to forget.

**Flaws**

- I mistake suffering for proof that a path is righteous.
- When the divine remains silent, I fill the silence with my own certainty.

## Charlatan

### Permanent-background biography

You learned that most people do not buy an object. They buy relief, importance,
hope, revenge, youth, or the brief pleasure of being told the world works as
they wish. You can hear that hidden purchase in a person's voice. Perhaps you
sold false relics in Ashenport, impossible weather insurance in Selerish, or
maps to roads that would exist by the time the buyer arrived.

The art is not merely lying. It is building a bridge from desire and charging
toll before anyone notices the far bank is painted.

### Inspiration seeds

**Personality**

- I give every stranger the version of me they most want to meet.
- I cannot resist improving a dull truth until it sparkles dangerously.

**Ideals**

- If hope keeps someone moving, its pedigree matters less than its effect.
- No title deserves immunity from a well-aimed embarrassment.

**Bonds**

- I owe my life to the only mark who saw through me and laughed.
- Somewhere, a family treasures a worthless charm I sold them for a worthy
  reason.

**Flaws**

- I keep performing sincerity after the truth would serve me better.
- The more impossible the deception, the more personally I need it to work.

## Criminal/Spy

### Permanent-background biography

You know the city beneath the city: chalk signs under bridges, names omitted
from ledgers, doors that open only after the wrong knock. You may have stolen,
smuggled, watched, forged, carried messages, or survived among people for whom
trust is both currency and weapon.

The hidden world is not one family. Ashenport's street crews, Sanctine refugee
networks, Anterean dissidents, Free City spies, and Darkling agents may use the
same tunnel for very different ends. You learned to ask who benefits before
calling any shadow kin.

### Inspiration seeds

**Personality**

- I notice exits before faces and hands before smiles.
- I answer direct questions with useful truths that are not quite answers.

**Ideals**

- A law that protects only the powerful has already declared itself my enemy.
- Trust should be difficult to earn and terrible to betray.

**Bonds**

- My old crew knows the name I wore before I became this person.
- I keep one route open for people escaping the life I once served.

**Flaws**

- I test loyal people until they finally behave like traitors.
- I feel safest when I possess a secret someone else cannot afford to lose.

## Entertainer

### Permanent-background biography

You have felt a crowd become one listening creature. Song, dance, story,
comedy, acrobatics, masks, and small impossibilities are tools; attention is
the true instrument. In Lumia, where memory strengthens the Loom, a
performance can keep a village's name alive or give a frightened company the
courage to take one more step.

You know the labor behind wonder: rehearsal on bleeding feet, strings replaced
in rain, jokes rebuilt for a grieving room, and the lonely walk after applause
has spent itself.

### Inspiration seeds

**Personality**

- I narrate tense moments as if better pacing might save us.
- I collect the laugh of every place and borrow it when my own courage fails.

**Ideals**

- Beauty is not an escape from suffering; it is evidence suffering did not
  take everything.
- A story belongs partly to every listener who carries it onward.

**Bonds**

- My first audience was a village that no longer appears on any map.
- I am searching for the lost final verse of my teacher's greatest song.

**Flaws**

- Silence feels so much like rejection that I fill it before listening.
- I would rather fail spectacularly in public than succeed unnoticed.

## Folk Hero

### Permanent-background biography

You were ordinary where ordinary people knew your name. Then the flood came,
the beast crossed the fence, the tax collector took too much, or the local
strongman learned that fear had limits. You acted. The story grew in the
telling. Now people from home look at you as if their hope were a cloak you
chose to wear.

Perhaps the story is true. Perhaps it leaves out help, luck, or harm. Either
way, a community has placed part of its future in your hands.

### Inspiration seeds

**Personality**

- I speak to rulers with the same plain courtesy I give a neighbor.
- Praise makes me uncomfortable, so I turn every compliment into a task.

**Ideals**

- Great powers exist to serve the people who carry their cost.
- Courage begins when someone decides a familiar wrong is no longer normal.

**Bonds**

- My home keeps a chair for me, and I fear the day I no longer fit it.
- The person who truly saved everyone receives none of the songs sung about me.

**Flaws**

- I accept dangers alone because asking help would complicate the legend.
- I assume humble origins make my judgment morally cleaner than it is.

## Gladiator

### Permanent-background biography

You learned violence beneath watching eyes. Whether the arena was an
Ashenport pit, a noble court, a military exhibition, or a traveling ring, you
were trained to make danger legible to a crowd. A clean victory could be
forgotten; a memorable one bought another week of life.

The audience saw confidence, rivalry, and spectacle. You remember sand in the
mouth, coded glances between opponents, healers waiting just beyond the gate,
and the strange intimacy of trusting another fighter to make a near miss look
fatal.

### Inspiration seeds

**Personality**

- I enter every room as if someone has already announced my name.
- I can read a crowd's mood faster than I can read a private conversation.

**Ideals**

- Skill deserves witness, but no audience owns the person performing it.
- Mercy shown from strength is the highest form of victory.

**Bonds**

- I owe a rival the honest rematch neither of us was allowed.
- I still hear the arena medic who taught me that survival is also a craft.

**Flaws**

- I turn real danger into spectacle and miss when others are truly afraid.
- Being ignored wounds me more deeply than losing.

## Trader

### Permanent-background biography

You learned value at a workbench, market stall, guild table, caravan fire, or
night-tide bazaar. You know that price is never the whole cost. Reputation,
scarcity, time, danger, beauty, and the buyer's need all sit invisibly on the
scale.

Perhaps you craft what you sell. Perhaps you connect distant makers to people
who need their work. Either way, your true inventory is relationship: who pays
fairly, who delivers in winter, who cheats only strangers, and who keeps a
promise after profit disappears.

### Inspiration seeds

**Personality**

- I appraise unfamiliar objects when nervous, including furniture and people.
- I remember every favor as carefully as other traders remember coin.

**Ideals**

- Exchange is honorable only when both people can afford to walk away.
- A well-made thing is a promise from the maker to a future stranger.

**Bonds**

- My guild mark opens doors, and I intend to learn what was done to earn that
  trust.
- A ruined caravan partner's family receives a share of every profit I make.

**Flaws**

- I reduce choices to transactions when no fair price exists.
- I cannot leave a bargain unfinished, even when winning it costs more than
  losing.

## Hermit

### Permanent-background biography

You stepped away from the noise. Perhaps you sought a god, escaped a war,
guarded a place, studied one impossible question, recovered from a wound, or
simply discovered that solitude asked less of you than people did.

In the silence you found something: a truth, a delusion, a discipline, a
friendship with the weather, or the uncomfortable knowledge that isolation had
become another appetite. Returning does not mean the hermitage failed.
Sometimes understanding needs friction before it becomes wisdom.

### Inspiration seeds

**Personality**

- I answer after long pauses because thoughts deserve room to arrive.
- I treat weather, animals, and old buildings as participants in conversation.

**Ideals**

- A truth that cannot survive solitude was probably applause.
- Wisdom must eventually return to the world or become a beautifully guarded
  waste.

**Bonds**

- I left someone maintaining the place that remade me.
- My seclusion began with a question whose answer now frightens me.

**Flaws**

- I call avoidance peace when other people become difficult.
- I assume clarity earned alone grants authority over lives lived together.

## Squire

### Permanent-background biography

You served beside a knight, champion, officer, or sworn wanderer. You polished
steel, kept schedules, calmed mounts, learned heraldry, carried messages, and
saw which glorious stories omitted wet socks and frightened horses. You stood
close enough to an ideal to notice the person failing beneath it.

Perhaps you still seek knighthood. Perhaps you rejected the Orders, lost your
mentor, surpassed them, or discovered that service taught you a form of
leadership ceremony never could.

### Inspiration seeds

**Personality**

- I prepare for other people's needs before asking what I need.
- I judge impressive armor by the state of its least visible strap.

**Ideals**

- Honor is what remains of a vow when nobody important is watching.
- Service should train a person to stand, not teach them to remain kneeling.

**Bonds**

- I carry my mentor's unfinished oath and do not know whether to fulfill it.
- Another squire took blame meant for me; every success since has carried
  their name.

**Flaws**

- I wait for permission from authorities who are no longer present.
- I confuse proximity to greatness with possession of its virtues.

## Noble

### Permanent-background biography

You were raised inside consequence. A family name, inherited office, estate,
court appointment, merchant elevation, or ancestral claim taught others to
listen before you had earned their attention. Privilege can provide education,
safety, and reach. It can also make comfort look like merit and obedience look
like love.

Lumia's nobility is not one species. Anterean houses inherit duties from the
dead. Free City patrons buy public works and private influence. Chulani
magisters turn exam scores into dynasties. Your title may be secure, disputed,
newly granted, disowned, or carried like an unpaid bill.

### Inspiration seeds

**Personality**

- I was trained to make every entrance look intentional, including escapes.
- I know the correct form of address and use the wrong one when respect
  requires it.

**Ideals**

- Privilege is a debt payable only through public service.
- My name should open doors because of what I do with access, not who first
  owned the key.

**Bonds**

- My house protects people history treats as entries beneath its crest.
- A rival relative knows the true cost of my inheritance.

**Flaws**

- I mistake being heard quickly for being right.
- When ashamed, I retreat into rank and make everyone else pay for the
  distance.

## Outlander

### Permanent-background biography

You grew where roads were occasional suggestions. Herd routes, mountain
weather, desert stars, forest permission, and the moods of rivers mattered
more than walls. This does not make you ignorant of civilization. It means you
learned another kind first.

Perhaps you were a nomad, hunter, scout, raider, pilgrim, exile, caravan child,
or keeper of an isolated station. You know landscapes are not empty between
settlements. They are full of appetite, memory, warning, and lives that do not
need a city to become real.

### Inspiration seeds

**Personality**

- I note wind, tracks, and exits aloud without realizing others cannot read
  them.
- I sleep more easily beneath an uncertain sky than a locked roof.

**Ideals**

- Land is relationship, not the blank space between owners.
- Preparation is respect paid to dangers before meeting them.

**Bonds**

- A migration route taught me more faithfully than any living mentor.
- I promised to return with news to people who may already have moved on.

**Flaws**

- I dismiss city customs as softness when I simply do not understand them.
- I keep moving so no place can ask me to become accountable.

## Pirate

### Permanent-background biography

You lived by taking freedom from waters claimed by others—and perhaps by
taking cargo from people who claimed it first. Pirate crews range from brutal
predators to outlaw navies, escaped laborers, political rebels, sanctioned
privateers, and overlooked sailors who made a country from a deck.

The sea does not make anyone noble. It merely removes many witnesses. Whatever
code your crew kept mattered because no distant court could enforce it. You
know exactly what kind of person you became when law was over the horizon.

### Inspiration seeds

**Personality**

- I treat every formal plan as weather: worth reading, foolish to trust.
- I remember people by what they did during storms.

**Ideals**

- No crown owns the horizon.
- A crew survives only when shares, danger, and voice are distributed by a
  code everyone can name.

**Bonds**

- My old vessel is still sailing under someone who should never have inherited
  command.
- I buried a share of treasure for a crewmate who did not live to spend it.

**Flaws**

- I call predation freedom whenever admitting harm would cost me pride.
- Authority provokes me even when cooperation would protect my crew.

## Sage

### Permanent-background biography

You pursued knowledge long enough for it to alter your posture, your sleep,
and the number of friends willing to ask a simple question. Your school may
have been a Chulani college, a Crystal memory vault, a temple archive, a
halfling map library, an apprenticeship, or ruins that killed every previous
researcher.

In Lumia, scholarship is dangerous because some records remember the reader.
The wise learn methods, provenance, and humility. The merely learned acquire
more confident ways to be wrong.

### Inspiration seeds

**Personality**

- I cite sources during arguments and apologize only for the footnote order.
- I become delighted, not embarrassed, when evidence defeats my favorite
  theory.

**Ideals**

- Knowledge deserves stewardship because secrecy and disclosure can both
  wound.
- No authority is old enough to stand above a well-formed question.

**Bonds**

- I seek the missing volume of an archive whose surviving pages refer to me by
  name.
- My greatest discovery belongs partly to an assistant history forgot.

**Flaws**

- I would open a sealed door for the chance to learn why it was sealed.
- I treat people as evidence when their pain complicates my conclusion.

## Sailor

### Permanent-background biography

You served aboard a vessel where every hand's mistake became shared weather.
Merchant hull, fishing boat, naval ship, ferry, explorer, or Swiftpath tender:
the work taught knots, watches, repairs, currents, and the intimacy of trusting
sleep to people you did not choose.

Unlike a pirate, your identity need not reject shore law. Unlike a passenger,
you know a ship is not freedom floating on water. It is obligation made of
wood, cloth, labor, and constant small repairs.

### Inspiration seeds

**Personality**

- I turn household chores into watch rotations before anyone can object.
- I judge a leader by whether they take the worst watch in bad weather.

**Ideals**

- Competence is a form of care when other lives depend on one's hands.
- No voyage justifies treating the crew as cargo.

**Bonds**

- I can find my old ship by the sound of one loose board.
- The sea kept someone I loved, and I still bargain with every horizon for
  their return.

**Flaws**

- I obey a confident order before asking whether it is wise.
- On land, I create emergencies because calm without a task feels like drift.

## Soldier

### Permanent-background biography

You were trained to make fear arrive on schedule. A national army, town
militia, mercenary company, Knight auxiliary, caravan defense, or desperate
uprising taught you weapons, formations, supply, and the thousand uncelebrated
skills that keep fighters alive.

War gave you comrades and may have taken them. It may have taught discipline,
obedience, courage, numbness, cruelty, or the difference between each. Lumia
prepares for another conflict while still misunderstanding the last. You carry
one of its smaller, truer histories.

### Inspiration seeds

**Personality**

- I sit where I can see the door and make it look like chance.
- I use dry humor when everyone else needs permission to admit fear.

**Ideals**

- Discipline exists to protect people from panic, including the panic of
  commanders.
- The purpose of force is to end the need for force.

**Bonds**

- I keep the names of my unit where no official history can revise them.
- A former enemy spared me for a reason I still need to understand.

**Flaws**

- I obey structure when conscience would require disobedience.
- I treat peaceful disagreement as a threat to cohesion.

## Urchin

### Permanent-background biography

You grew in the city spaces maps leave blank: roofs, culverts, market awnings,
abandoned shrines, kitchens after closing, and alleys with six names depending
on who is asking. Survival required speed, observation, alliances, and the
ability to become unimportant when danger looked your way.

Poverty was not a picturesque teacher. It was hunger, exposure, sickness, and
adults deciding not to see. What you learned belongs to you. What happened to
you was not proof that suffering was necessary.

### Inspiration seeds

**Personality**

- I pocket food before remembering I no longer need to.
- I know which grand buildings have warm vents and badly watched windows.

**Ideals**

- Nobody is disposable merely because powerful people learned not to notice
  them.
- Survival creates responsibility when others are still trapped where I
  escaped.

**Bonds**

- A loose family of street children still uses the signs I taught them.
- I owe everything to a shopkeeper who pretended not to notice one theft too
  many.

**Flaws**

- I hoard resources past need because safety still feels temporary.
- Kindness makes me search for the trap until I injure the person offering it.

## Editorial and Implementation Rules

### Public copy

- Use first-person seeds so a player can adopt, revise, or reject them.
- Suggestions are beginnings, never claims that all people with a Background
  behave alike.
- Avoid imported setting names, source-book phrases, gender defaults, and
  alignment-as-personality shortcuts.
- Do not romanticize coercion, poverty, war, criminal harm, or exploitation.
- Keep hidden cosmic truths out of character-creation help unless ordinary
  people in Lumia would know them.

### Generator behavior

- Personality, Ideals, Bonds, and Flaws each draw two distinct nonempty seeds
  from the selected theme.
- A later content expansion may add more seeds without changing stable
  Background IDs.
- Gladiator and Entertainer, Squire and Noble, and Pirate and Sailor are
  deliberately related but not duplicates. Their different seeds must remain
  distinct.
- Goals bypass the theme registry and return an Objective, Reason, and
  Complication outline.

### Mechanics boundary

This document does not certify Background abilities. Before player-facing
mechanics are published, implementation must reconcile the verified source
issues involving Hermit party size, Soldier group detection, Criminal/Noble
shop gates, Folk Hero/Noble pricing language, late-selected Outlander health,
and missing Urchin feat metadata.

The mechanical evidence is in:

- `/home/aiwithapex/projects/Luminari-Source/src/backgrounds.c`
- `/home/aiwithapex/projects/Luminari-Source/src/backgrounds.h`
- `/home/aiwithapex/projects/Luminari-Source/src/feats.c`
- `/home/aiwithapex/projects/Luminari-Source/src/fight.c`

Lore supplies biography, role-play meaning, and inspiration. Source code must
supply truthful effects, commands, limits, and help.

## Provenance

The five concept definitions replace and refine the terminal-only copy at
`/home/aiwithapex/projects/Luminari-Source/src/roleplay.c:808-868`. They remove
an imported setting reference, source-book language, grammar problems, and
gendered defaults while preserving the intended role-play function.

The sixteen Background identities correspond exactly to the stable runtime
values in `/home/aiwithapex/projects/Luminari-Source/src/backgrounds.h:1-19`.
Their biographies and inspiration seeds are original Lumia-specific canon,
informed by the runtime roles but not copied from imported background prose.

---

_A hero is not the answer written at creation. A hero is the argument between
that answer and everything the world asks afterward._
