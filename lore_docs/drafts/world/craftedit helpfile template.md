# craftedit helpfile template

*Converted from: craftedit helpfile template.docx*

@n

-- Craftedit Menu : [1]             @WID number@n

1) Craft Name     : <No Name>       @WThe name of this craft@n

2) Craft Timer    : 0 seconds       @WHow long to create@n

3) Craft Item     : "None"          @WThe result product (vnum)@n

4) Craft Self Msg : "You craft $p." @WMessage for crafting item $p@n

5) Craft Room Msg : "$n crafts $p." @WTo-room for crafting item $p@n

S) Craft Skill    : No Skill (0)    @WSkill required to create this@n

F) Flags          : None            @WSet flags here, see below@n

R) Requirements   :                 @WList of req. objs, see below@n

  None

X) Delete                           @WThis options will delete this@n

Q) Quit                             @WThis options will exit@n

@n

@WFLAGS:@n

  @c"Needs recipe"@n - does this particular craft require you have the recipe?

                   a recipe is a object of 'blueprint' type that refers to

                   the ID number of this craft

  @c--more flags to come soon!--@n

@n

@WREQUIREMENTS:@n

  Here you will enter a list of requirements to create this object, it can include

components to assemble, an in-room component(s) such as a forge, and these items

can either be destroyed or preserved depending on failure or success.  Here are

the details of the requirement-flags:

  @c"INROOM"@n - This particular requirement has to be in the room you are in, example

             is a forge

  @c"SAVEonFAIL"@n - by default if you fail the craft, you lose all the components,

                 setting this flag will preserve this particular item on FAILed craft

  @c"!REMOVE"@n - by default all the components are consumed, this particular item

              will not be consumed (fail or not)

@n

@WNotes:@n

  @c*There is no VNUM system for this crafting system, just a reference ID number.@n

  @c*You can use > show craft <name> to display info on a craft. @n

     @cThe information varies if the craft is a RECIPE(BLUEPRINT)/NON-RECIPE(NON-BLUEPRINT)@n

  @c*Typing "craft" will bring up the crafts list for your character, and colour code@n

     @cwhich crafts you have the goods to create.@n

@n