# Powers System (Idea from TorilMUD)

*Converted from: Powers System (Idea from TorilMUD).docx*

To use powers, you can just use an alias which is encoded into each power, like for example, bash-power can be used by typing ‘bh’ OR you can use any power by typing: power ‘<name of power>’ <target>

All spells, skills, equipment-specials are suppose to go through this system, basically everything is suppose to go through this system.

More info follows:

====

Help powers

====

POWERS

Syntax:: powers <command> <arguments>

The "powers" command is used to see a list of your powers and get more

information on individual powers.  To see the full listing of options

for this command, type "powers ?" or "powers help".

For more information on the power info display, see the "powers info"

help file.

See also:  POWER, "POWERS INFO"

====

Powers, Powers help, powers ?

====

Powers Syntax Command Usage:

  powers list                      - List powers

  powers info <power>              - Displays information on the specified power

  powers prompt <power> <slot>     - Add a power to a display prompt slot

  powers prompt clear <power, all> - Add a power to a display prompt slot

  powers help                      - Displays this list

====

Powers prompt system

====

**i don’t see any helpfiles on this system, but apparently you can add to your prompt a given power and then it will show on your prompt the cooldown until that power is ready to be used again

=====

Powers list (max level paladin)

=====

Available Powers:

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=--=-=-

Equipment Powers:

Icy Bash                            Melee                Level 1

Icy Shield Punch                    Melee                Level 1

*note: i’m wearing a shield that gives me these two powers

Class Powers:

Holy Word                           Spell     Study      Level 46

Heal                                Spell     Study      Level 41

Holy Shroud                         Spell     Study      Level 41

Continual Light                     Spell     Study      Level 36

Destroy Undead                      Spell     Study      Level 36

Dispel Magic                        Spell     Study      Level 31

True Nemesis                        Melee                Level 30

Whirlwind Smite                     Melee                Level 30

Wrathful Smite                      Melee                Level 30

Cure Blind                          Spell     Study      Level 26

Ward Undead                         Spell     Study      Level 26

]Enervating Smite                    Melee                Level 25

Terrifying Smite                    Melee                Level 25

Cure Critic                         Spell     Study      Level 21

Dispel Evil                         Spell     Study      Level 21

Heal Mount                          Spell     Study      Level 21

Remove Poison                       Spell     Study      Level 21

Protection From Evil                Spell     Study      Level 16

Remove Curse                        Spell     Study      Level 16

Brilliant Smite                     Melee                Level 15

Shielding Smite                     Melee                Level 15

Great Weapon Defense                Inherent             Level 12

Create Food                         Spell     Study      Level 11

Create Water                        Spell     Study      Level 11

Cure Serious                        Spell     Study      Level 11

Armor                               Spell     Study      Level 6

Radiant Charge                      Melee                Level 5

Thunderous Smite                    Melee                Level 5

Bash                                Melee                Level 1

Bless                               Spell     Study      Level 1

Bolstering Strike                   Melee                Level 1

Cure Light                          Spell     Study      Level 1

Detect Evil                         Spell     Study      Level 1

Detect Good                         Spell     Study      Level 1

Detect Magic                        Spell     Study      Level 1

Divine Challenge                    Melee                Level 1

Divine Smite                        Melee                Level 1

Lay On Hands                        Melee                Level 1

Righteous Aura                      Inherent             Level 1

Valiant Strike                      Melee                Level 1

Race Powers:

Furious Assault                     Melee                Level 1

=====

Powers info bash (melee)

=====

Name             : Bash                     

Alias            : bh                       

Type             : Melee                    

Source           : Martial                  

Attack Type      : Armor                    

Target           : Offense, Character in room

Recharge         : 4 seconds 

Implements       : Shield

Restrictions     : Ground, Autofire, Immaterial, Garrote, Size 1, Standing, Target Standing, Can See

, Unmounted

Race Restrict (T): Type Dragon

To-Hit Mods      : Level Diff +1, Str 20%, Shield Weight 100%, Hit Roll 200%

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

Target Effect    : Deal 4d5 bludgeoning damage                        

Target Effect    : Change position to Sitting                         

Target Effect    : Wait for 8 seconds                                 

Self Effect      : Wait for 8 seconds                                 

Miss Effect Self : Wait for 4 seconds 

=====

Powers info Icy Bash (wearing a shield with this power built into it)

=====

Name             : Icy Bash                 

Alias            : Icy Bash                 

Type             : Melee                    

Source           : Martial                  

Attack Type      : Legacy                   

Target           : Offense, Character in room

Recharge         : 4 seconds 

Related Skill    : bash           

Restrictions     : Ground, Autofire, Immaterial, Garrote, Size 1, Standing, Can See, Unmounted

Race Restrict (T): Type Dragon

To-Hit Mods      : Size Diff +5, Fighting -30, Ground Target -75, Level Diff +1, Shield +25, Skill

133%, Base -25

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

Target Effect    : Deal 5d4 cold damage                               

Target Effect    : 15% chance to Stun for 4 seconds                   

Target Effect    : Change position to Prone                           

Target Effect    : Wait for 8 seconds                                 

Self Effect      : Wait for 8 seconds                                 

Miss Effect Self : Change position to Kneeling                        

Miss Effect Self : Wait for 8 seconds                                 

Miss Effect Self : 15% chance to Stun for 4 seconds  

****note, this will add an affect to “power bash” in the affect of 

=====

Powers info holy word (spell)

=====

Name             : Holy Word                

Alias            : hw                       

Type             : Spell                    

Source           : Divine                   

Attack Type      : Auto                     

Prepare          : Study                    

Target           : Self, Offense, Character in room

Stacks           : Yes

Related Skill    : spellcast invocation

Restrictions     : Autofire, Garrote, Standing, Can Speak, Good, Target Evil

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

Target Effect    : Instant death                                      Radius: Huge 

                   Restrictions: Level Percent 33

Target Effect    : Add stun condition for 4 seconds                   Radius: Huge 

                   Save versus constitution to avoid  

Target Effect    : Deal 12d40 good damage                             Radius: Huge 

                   Save versus spell for 50%

Target Effect    : Add major paralysis for 54 seconds                 Radius: Huge 

                   Restrictions: Level Percent 50

                   Save versus paralysis to avoid  

Target Effect    : Add blind for 1 minute 48 seconds                  Radius: Huge 

                   Restrictions: Level Percent 50

                   Save versus spell to avoid  

Target Effect    : 25% chance to Add major paralysis for 54 seconds  Radius: Huge 

                   Restrictions: Level Difference -10

                   Save versus paralysis to avoid  

Target Effect    : 25% chance to Add blind condition for 1 minute 48 seconds  Radius: Huge 

                   Restrictions: Level Difference -10

                   Save versus spell to avoid 

====

Powers info righteous aura (inherint)

====

Name             : Righteous Aura           

Alias            :                          

Type             : Inherent                 

Source           : Divine                   

Triggers         : Threat

Target           : Self

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

Self Effect      : Modify threat by +50%   

====

powers info Great Weapon Defense (inherint)

====

Name             : Great Weapon Defense     

Alias            :                          

Type             : Inherent                 

Source           : Martial                  

Triggers         : Parry Attempts

Target           : Self

Implements       : Two handed

-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

Self Effect      : Modify parry attempts by +1  