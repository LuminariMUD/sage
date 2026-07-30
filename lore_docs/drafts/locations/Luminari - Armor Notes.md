# Luminari - Armor Notes

*Converted from: Luminari - Armor Notes.docx*

http://www.d20pfsrd.com/gamemastering/other-rules/piecemeal-armor

Value 0: (stock) armor class apply (AC) {not settable}

Value 1: armor-type [or switched with value 2] {settable}

Value 2:

Value 3:

Value 4: enhancement bonus {*settable}

Builder would set:

armor-type

material (if they want to change it from base material)

enhancement bonus

special abilities on armor (not currently implemented)

custom cost (if they want to change it from base cost)

Then the armor-struct would auto-assign:

armor class (based on material, armor-type, and wear location)

wear position

base material

cost

maximum dex bonus (“ “)

armor check penalty (“ “)

arcane spell failure chance (“ “)

weight (“ “)

Don-time [OPTIONAL]

Remove-time [OPTIONAL]

Speed (30 ft) [OPTIONAL]

Speed (20 ft) [OPTIONAL]

The armor type struct (which contains all the data about various armor types) needs to have the armor bonus organized by wear location, as this will determine the armor bonus of body, arms and legs.

*IDEA: have our rating system suggest an enhancement bonus based on level, material, etc

Armor Types

Number of ‘protective’ slots, rating:

#SlotFull Plate (8.0)

1Head1.5

2Body3.5

3Arms1.5

4Legs1.5

The rest of the armor slots AC

Slot(70)(60)(50)(40)(30)(20)(10)

Head (0.1875)1.31.1.9.7.5.3.1

Body (0.4375)3.12.72.31.91.51.1.7

Arms (0.1875)1.31.1.9.7.5.3.1

Legs (0.1875)1.31.1.9.7.5.3.1

Shields

ShieldsACChkDex

Buckler.5-10

Medium1.0-20

Heavy2.0-30

*Tower4.0-102

Slots not listed above are considered to be supplemental and should not exceed the above numbers.

WEIGHT distribution on above items (lbs):

Slot(50)(45)(40)(25)(15)(10)

Head (0.1875)987421

Body (0.4375)2321191397

Arms (0.1875)987421

Legs (0.1875)987421

All of these modifications based on wear location would be performed on object creation, the VAL0 of the object being set to the appropriate % of the Armor Bonus of the appropriate armor type.

Enhancement Bonus:

It is problematic to stack 4 pieces of gear enhancement bonus, so we’ve changed it to calculate the average of their worn gear for enhancement bonus.

Other Bonuses:

This rearrangement of armor means we need to be careful of handling other bonuses.  One way of managing stacking bonuses is through the introduction of ‘bonus types’ which are a standard part of the d20 ruleset.  For example, if you have a pair of boots that give an armor class bonus +2, a ring of protection that gives an armor class bonus of +3 and another ring that gives a bonus of +2, combined in a typeless stacking system you get +7.  This can lead to some very impressive bonuses.  If, however, we typed bonuses - Now the rings give deflection bonus and the boots give dodge bonus - Bonuses of the same type do not stack generally (Untyped and Dodge bonuses are the only ones that stack.)  As a result the total bonus would be the higher bonus from the two rings, so +3 plus the +2 dodge bonus, giving +5.  

The implementation of this is as follows:

The affected_type struct has a new field, called ‘bonus_type’.  This field is an integer, the values of which are set via #define statements.

When applying bonuses, we go through the affects and only apply the largest affect.  This way, bonuses of the same type overlap and bonuses of different types stack.

Bonuses for Random Treasure Drops:

We are adhering to the following rules:

armor pieces/weapons (body, legs, arms, helm, shield, wield) will just get an enhancement bonus: level / 6 (max 5) + rarity (max 7)

misc pieces will get various bonuses, same evaluation as armor with the exception of +Hit-Points or +Movement-Points, in which case its 12 for each point (max 96)

Bonuses for In-Game Gear Via Combat, Quests, Etc.:

Bonuses for Crafted Gear:

TBD - similar to random treasure drop, except we can go into the realm of Epic or better with rare crafting componenents

More Info:

We put more info about stat distribution and points value in a file named:

“current stat distribution on random drops”