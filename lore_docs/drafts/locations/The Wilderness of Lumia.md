# The Wilderness of Lumia

*Converted from: The Wilderness of Lumia.docx*

The Wilderness of Lumia

Introduction

This document contains the origins, design, implementation, maintenance and future plans for the Wilderness of Lumia, as implemented in Luminari MUD.

I will be writing this in first, second and third person, as needed, so I apologize for any confusion - It just helps me get all of the concepts written so that others can hopefully pick up where I left off and improve on the system.  This is a living document, so please make notes, changes or reorganize the content as needed as the system changes and evolves.  There is such a thing as too much documentation but I think everyone will agree that Luminari is nowhere near having that problem.  

There will be some lore, bullshit, code, theory and other topics mixed in here so please keep that in mind.  This will not be strictly technical documentation.  

Origins

I have been playing MUDs since the 1990s, and I have always been fascinated by wilderness/overland systems and their role in these text MMOs.  They often serve as the glue that holds together the other zones, giving the world some scale and providing very fun and interesting mechanics that are outside of the typical room-based game that MUDs usually present.  This was my goal with this project, although I had some other influences and inspiration.

Roguelike games, such as Angband, Rogue, NetHack, etc., have always had a special place in my heart ever since I ordered my first 3.5” floppy from the newsprint shareware catalog as a kid.  My childhood gaming world was filled with ASCII characters, s-shaped snakes, > symbols that beckoned  me to delve deeper into the dungeon and all of the stress and pleasure that come out of exploring the unknown.  Seeing the similarity between this genre of game and the representation of the wilderness map in many MUD games I wanted to explore this a little more with the wilderness in Luminari.  I began thinking about how to implement the wilderness at first with image-based maps and arrays, etc. but it was quickly obvious that this would be far too limiting.  

At this point, I became extremely ill and needed to go into the hospital.  The details are unimportant, except to say that I was in the hospital for almost a week and during this time I was able to design the wilderness, nearly in its entirety.  Fusing the idea of the traditional ‘glue’ overland with it’s static terrain and zone entrances with the terrain generation and quasi-physics engine of the roguelike I decided to pull it all together through the use of ‘regions’ that define areas of the map that can be transformed, processed and dynamically altered as needed.  

Design

The Wilderness is designed with several interacting systems:

Terrain Generation:  The base terrain of the world is defined using several layers of variants of Perlin noise.  This technique uses the predictability of the random number generator when fed with a non-changing seed to create repeatable output.  I will not get into the theory or math here, but several different types of this noise are layered to produce the Elevation and Moisture maps that are combined with a more linear Temperature gradient.  The combination of these values is then used to calculate the specific terrain type at any given (x,y) coordinate.

The Map View: The view of the terrain is presented to the player via a minimap (and for now, the output of the map command).  The minimap has a Field of View (FOV) algorithm applied that will prevent the player from seeing into certain types of terrain due to obstruction.  As the player moves across the Wilderness, their FOV changes.

The Room Pool:  There were some challenges fitting the design into the MUD itself so some compromise was required.  Rooms could not be created or deleted dynamically because the room lists are allocated on MUD start.  Thus a pool of pre-allocated rooms must be available for customization as required.  No Wilderness room really exists until a player (or object or mobile) is in that room.  This is both a help and a hindrance as you will see.

Hand-built rooms, ‘Buildpainting’, and Zone Entrances: Because of the implementation of the room pool it is possible to create hand-built rooms that integrate completely into the Wilderness, indistinguishable from generated wilderness rooms except for the customizations created by the building team.  This provides nearly infinite flexibility when creating the world.  Zone entrances are the transition between the Wilderness and a hand-built zone.  It is helpful to think of this as ‘zooming in’ to the hand-built zone as the maps are presented in a completely different way.  If you use the buildwalk command in the wilderness, you can ‘buildpaint’ - making rooms as you walk around that replace the generated rooms in the wilderness.  Flags on the rooms themselves control if the room appears as a wilderness room or a ‘zoomed in’ zone room.  These rooms exist inside the wilderness zone.  A special structure in memory allows extremely fast retrieval of these rooms, making the transition seamless.

Regions and Paths:  Regions and Paths are probably both the most important and the least understood aspect of the wilderness.  Regions define areas of the map - polygons, but a polygon can be one single room - that are DIFFERENT.  They can modify terrain or provide functionality such as timed event execution.  Paths define things like rivers and roads, or even a crevasse where players would need to potentially traverse to a different elevation.  Regions and Paths are the most effective way to modify the wilderness and are exceptionally powerful.

Tools: Some may not consider this a system, but it is as important as all of the other items on this list.  The wilderness tools are the system that allows the builders and developers to interact with and modify the Wilderness.  Some tools are simply the same as for standard building, like buildwalk, while others modify or display the regions, like genriver, reglist and pathlist.  As of this writing, the tool system is EXTREMELY limited which makes building in the wilderness very difficult. 

Implementation

Terrain Generation

What is all this NOISE?

Main layers

Elevation

Distortion

Moisture

Sector Limits

Constants

NOISE_MATERIAL_PLANE_ELEV_SEED

NOISE_MATERIAL_PLANE_MOISTURE_SEED

NOISE_MATERIAL_PLANE_DIST_SEED

NOISE_WEATHER_SEED

WATERLINE

SHALLOW_WATER_THRESHOLD

COASTLINE_THRESHOLD

PLAINS_THRESHOLD

HIGH_MOUNTAIN_THRESHOLD

MOUNTAIN_THRESHOLD

HILL_THRESHOLD

NOISE_MATERIAL_PLANE_ELEV

NOISE_MATERIAL_PLANE_ELEV_DIST

NOISE_MATERIAL_PLANE_MOISTURE

NOISE_WEATHER

NUM_NOISE

Always less than MAX_GENERATED_NOISE in perlin.h

Navigating the Wilderness 

The Magic Number

Finding an available wilderness room

The Virtual Room Pool

Prebuilt rooms

Finding containing regions

Finding nearby regions

Finding containing paths

Zooming In

Dynamic Descriptions

Hitting the edge

Building in the Wilderness

The Wilderness Map

Size

Map Tiles

Glyphs

UTF8

Color

Regions 

Max 24 regions for a single tile

Field of View calculations

Map Image generation

Bringing the Wilderness to Life

Lore, and Why it is Important

Attention to Detail

Building in the Wilderness

Bringing the Wilderness to Life

Lore and Why it is Important

Player Engagement

Attention to Detail

Building in the wilderness

Room flags

Terrain types

Hand-built rooms

Why?

Adding Rooms

Removing Rooms

Don’t Soil the Pool!

Coordinates vs. exit vnum

The Magic Number (reprised)

Region Data

Region Types

Geographic Regions

What is in a name?  When tying the Lore into the wilderness, it is helpful to name regions of the wilderness, both for navigation and for atmosphere.  Geographic regions allow this.

Geographic Regions name an area of the wilderness.  It is that simple, there is no further functionality.  The name of the region is used by the dynamic description engine when allocating wilderness rooms or generating descriptions for pre-built rooms with the dynamic description flag set.

Encounter Regions

Encounter Regions define an area where players might stumble onto random encounters.  These encounters are set up by the builder as individual rooms, known as Encounter Rooms. 

Encounter Rooms can load mobiles, objects, effects, scripts, traps or whatever else a builder might dream up.  For example, an encounter room might be an entrance to a zone or contain a portal.  The room might have a group of mobiles that act as guards, and a chest could have a chance of loading.  For all intents and purposes, encounter rooms are the same as regular hand-built wilderness rooms, they just move around according to a timer.  

Encounter rooms are built in the wilderness zone using the usual building tools and are subject to the wilderness zone reset timer.  The encounter room should be given an initial location within the Encounter Region.  N, S, E, W exits should be set to the Magic Number, but the U and D exits are available for builders to utilize.  

At a set interval, defined by a mud event, the encounters within an Encounter Region are evaluated and if no player is present in the room they are processed.  A new coordinate location for the encounter (within the Encounter Region) is calculated using the following algorithm:

Get the envelope (closest fitting box) for the Encounter Region from the Database

Calculate the maximum and minimum x and y values for that envelope.

Choose random x and y values between those maximums and minimums

Check to see if the chosen point is within the Encounter Region, if so, this is the point we choose.  Otherwise, go to step 3 and repeat. 

(Checking if the point is within the actual Encounter Region is important because the shape of the Region might be concave, meaning that there are points within the envelope for that region that are not actually within the region.)

Once the destination coordinates are selected, the terrain type for that coordinate location is compared to the encounter room.  If it matches, the encounter room’s coordinates are changed to the new coordinates.  This effectively moves the encounter to that location on the map.  The code will search for a suitable room up to 128 times.  If no appropriate room is found then the encounter room does not move.

Pre-built rooms are exempt from becoming encounter rooms.

The timing events for the reset are created when the Encounter Region is loaded as the MUD boots.   

Sector Regions

Sector Regions overwrite the automatically generated terrain type with the region’s terrain type.  This is an essential tool allowing the builders to craft the world deliberately, no matter what kind of terrain is generated.

Sector Transform Regions

Sector Transform Regions modify the existing terrain in some way.  For example they can be used to lower the elevation of an area, changing the terrain.  This can be used in such a way that you can create artificial lakes or craters on the wilderness map.  This feature is not currently very robust, so see the future plans section of this document for more details about the vision for this type of region.

Region Properties

Region Shape

Region Events

Region Events have applications outside of Encounter Regions, for example, changing the shape of the region over time. 

Adding New Region Types

Adding new Region Properties

Path Data

Path types

Road

Dirt Road

River

Stream

Geographic

Path properties

Glyphs

Path shape

Adding new path types

Adding new path properties 

Weather

The difference between in-memory and in-database structures

Why this is (mostly) terrible design and should be fixed

How?

Lists

Loading and Reloading

KDTree

Why?

https://en.wikipedia.org/wiki/K-d_tree

Tradeoffs

MySql

In-Memory vs. DB 

Why?

Tradeoffs

Is this REALLY necessary?

Fetching data from the database

Storing data in the database

Triggers 

Database connections

Database Instances, DEV vs PROD

What happens when I can’t connect?

Database Schema

Diagram of the Schema

GIS 

Innodb vs MyIsam storage engine and Geolocation searching

Region_data, region_index

Path_data, path_index

Loading the Wilderness

Re-Loading the Wilderness

Tooling

The Tooling System, or lack thereof

Current commands

genriver

Reglist

pathlist

deletepath

Extremely Technical Math Stuff

Perlin Noise Generation

Bresenham lines

Maintenance

Tooling

Backups

Future Plans - Improvements and Enhancements

Tooling

OLC Region Editor

OLC is very important for builders, simplifying the building process and offering the instant gratification that comes with seeing your creations instantly appear in the game.  This should be no different for Regions.

Command: regedit <region vnum>

This command opens up an ‘Oasis style’ OLC editor menu, similar to redit, medit and oedit.  The main difference between these commands is that you must always specify which region you want to edit, as regions can overlap.

On opening the editor, if the provided region vnum exists, then that region data should be read from the database into the OLC region structure.  Otherwise, a blank region template should be allocated and modified as the user works through the OLC.  This follows the same design pattern as the rest of the xxxedit commands.

The main editor window should look similar to the following:

-- Region number : [1000001] Region zone: [10000]

1) Name          : New Anteria

2) Region Type   : Geographic (1)

3) Region Props  : N/A

4) Region Vertices : Set.

W) Copy Region

X) Delete Region

Q) Quit

Selecting 1 lets you set the name of the Region.

Selecting 2 lets you set the Region Type - The menu should have constants that correspond to the different region types, but also should display the numeric value of those types.

Selecting 3 lets you set the Region Properties.  This is only applicable for certain region types.  For example, if the Region is of type Sector, then the region properties contain the numeric value of the sector type that the region will use.  Again, the sector type should be displayed and selectable here, and the numeric value of the sector type should be displayed.  By the time this tool is created, the region properties should be converted into name:value pairs.

Selecting 4 opens the Region Shape Editor Menu, allowing the builder to set the vertices of the region polygon manually.

Region Shape Editor Menu

  1. Vertex : [(100, 25)]

E) Edit this Vertex

N) Goto next Vertex: Set.

D) Display Region Shape 

X) Delete this Vertex

Q) Quit

This menu shows the current Vertex starting at 1.  All region polygons start at the first vertex and end at the first vertex.  The edges of the polygon should not intersect.

Selecting E allows you to edit the Vertex.

Enter new X-value: 98

Enter new Y-value: 23

Selecting N moves the editor to the next vertex.

Selecting D displays the entire wkt-string of vertices for this Region:

POLYGON ((30 10, 40 40, 20 40, 10 20, 30 10))

This is the representation used to manipulate the shape data in the MySQL database.  Follow this link for details:

https://en.m.wikipedia.org/wiki/Well-known_text_representation_of_geometry

Selecting X deletes the current Vertex.  Selecting Q quits and returns the user to the previous menu.

Region properties should be eventually converted to a set of name:value pairs that are parsed at region query/load time.  In that case, the menu option for 3 would be displayed like:

3) Region Props  : Not Set.

When this option is selected then you would go to a submenu.  See the documentation for similar types of submenus.

If the Region is of type Encounter, then the following menu option will be available:

E) Encounter Data : Set.

Selecting this menu option opens the following submenu:

Encounter Data Menu

T) Region Reset Time : 720 seconds

  1. Encounter Room number : [1000128]

E) Edit this Encounter Room

N) Goto next Encounter Room: Set.

X) Delete this Encounter Room

Q) Quit

Selecting T allows you to set the Encounter Region’s reset time.  In this case, the encounters will be moved every 720 seconds, assuming the encounter room is not occupied.  

Each Encounter Region can have multiple Encounter Rooms.  Selecting option E allows the builder to change the vnum for this Encounter Room.  Selecting N goes to the next encounter room, displaying the vnum and data for that Encounter Room.  Selecting X deletes the current Encounter Room (Note: This only deletes the reference to the encounter room, and not the encounter room itself!  If you want to delete the encounter room you do so in the same way you delete any hand-built room.).  Selecting Q quits this menu and returns to the region editor.

Once the user quits, if they made changes to the region they will be asked if they want to save the region.  The region will then be inserted into the database and the transaction committed.  If there is an error inserting the data, that error should be logged and provided to the user as feedback.  If everything was successful then the in-memory region data should be reloaded.  

Once the in-memory structures are removed from the design then this reload will no longer be necessary and the system will run directly from the database.

OLC Path Editor

Command: pathedit <region vnum>

This editor works very similarly to the region editor, except that instead of creating POLYGON shapes, we create LINESTRING shapes.

The main editor window should look similar to the following:

(NOT FINISHED)

-- Path number : [1000001] Path zone: [10000]

1) Name          : The Northern Road

2) Region Type   : Road (1)

3) Region Props  : N/A

4) Region Vertices : Set.

W) Copy Region

X) Delete Region

Q) Quit

Tooling

Graphical Region Editor

Graphical Path Editor

Encounter Editor

Toggle that marks encounter rooms loaded on the map for immortals

View Regions/Paths on the Map

Regions/Paths OLC

Dynamically change wilderness parameters

Grow/Shrink Wilderness Virtual Pool

Map Glyph OLC

Survey

Tracking

Code reorganization

Data-driven wilderness

All wilderness values directly from database

Single Source of Truth

Remove In-Memory Region/Path lists, pull directly from Database

Multiple Wildernesses

Overland Travel

New Region types

New Path types

Divination and Transportation Magic

Automatic terrain feature generation

Enhanced Dynamic Descriptions

Landmarks and Waypoints

Enhanced Weather

Viewing the Night Sky

Seasonal Changes

Map glyph changes/ description changes based on light levels and other environmental changes

Sound in the Wilderness

Perception in the Wilderness

Changing the Wilderness using Magic

Resource layer and crafting materials

Automatic dungeon generation

Dynamic room allocation/destruction