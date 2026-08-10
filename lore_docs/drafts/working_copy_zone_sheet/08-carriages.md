# Carriages

> Extracted from `Working Copy of Zone Sheet.xlsx`. Original worksheet state: `visible`.

The first column is the original Excel row number; lettered columns preserve the workbook layout exactly. Blank cells are intentionally retained.

## Data

| Source row | A |
| ---: | --- |
| 1 | // To get the map coords, use the coords found in the wilderness area where the zone connects. |
| 2 | // Same applies to the airship map points below. Map point will be the spot where the airship tower is. |
| 3 |  |
| 4 | // location name, carriage stop room vnum, cost to travel here, continent name (matched below), zone description, mapp coord x, map coord y |
| 5 | const char *carriage_locales[][7] = { |
| 6 | {"ardeep forest",                         "144062", "45",   "Continent1", "level 3-12 mobs", "-40", "82"}, |
| 7 | {"ashenport",                             "103000", "10",   "Continent1", "central city for low to mid levels and main quest line", "-59", "92"}, |
| 8 | {"blindbreak rest",                       "40400",  "105",  "Continent1", "level 10-11 mobs, questline", "-53", "63"}, |
| 9 | {"bloodfist caverns",                     "102501", "40",   "Continent8", "level 1-23 mobs", "-66", "-676"}, |
| 10 | {"corm orp",                              "105001", "40",   "Continent4", "level 1-10 mobs", "167", "-85"}, |
| 11 | {"dollhouse",                             "11899",  "65",   "Continent1", "level 5-8 mobs, questline", "169", "171"}, |
| 12 | {"evereska",                              "120800", "65",   "Continent9", "level 1-4 mobs", "-767", "157"}, |
| 13 | {"frozen castle",                         "1101",   "65",   "Continent8", "level 25-30 mobs", "-662", "-595"}, |
| 14 | {"giant darkwood tree",                   "6901",   "70",   "Continent9", "level 15-20 mobs", "-717", "-51"}, |
| 15 | {"glass tower",                           "11410",  "65",   "Continent5", "level 20-23 mobs", "641", "87"}, |
| 16 | {"graven hollow",                         "6766",   "70",   "Continent1", "level 7-12 mobs, questline", "5", "67"}, |
| 17 | {"grunwald",                              "117400", "70",   "Continent7", "level 1-16 mobs", "-509", "-170"}, |
| 18 | {"hardbuckler",                           "118594", "70",   "Continent5", "level 1-12 mobs", "624", "114"}, |
| 19 | {"lizard marsh",                          "121200", "70",   "Continent8", "level 10-30 mobs", "-821", "-413"}, |
| 20 | {"mere of dead men",                      "126860", "110",  "Continent1", "level 9-30 mobs", "305", "313"}, |
| 21 | {"memlin caverns",                        "2701",   "50",   "Continent1", "level 8-20 mobs", "80", "115"}, |
| 22 | {"mithril hall",                          "108101", "120",  "Continent2", "level 6-27 mobs", "349", "769"}, |
| 23 | {"mosaic cave",                           "40600",  "120",  "Continent1", "level 16-22 mobs, questline", "3", "4"}, |
| 24 | {"mosswood village",                      "145387", "10",   "Continent1", "starting area, levels 1-5", "-51", "99"}, |
| 25 | {"neverwinter",                           "122413", "140",  "Continent3", "level 1-24 mobs", "-591", "805"}, |
| 26 | {"neverwinter catacombs",                 "123200", "140",  "Continent1", "level 16-30 mobs", "60", "54"}, |
| 27 | {"orc ruins",                             "106200", "30",   "Continent1", "level 9-30 mobs", "210", "233"}, |
| 28 | {"orcish fort",                           "148100", "30",   "Continent1", "level 14-16 mobs", "-54", "118"}, |
| 29 | {"pesh",                                  "125900", "30",   "Continent7", "level 1-19 mobs", "-150", "-180"}, |
| 30 | {"quagmire",                              "13240",  "30",   "Continent1", "level 1-30 mobs", "-58", "192"}, |
| 31 | {"rat hills",                             "115500", "70",   "Continent1", "level 3-12 mobs", "-54", "78"}, |
| 32 | {"reaching woods",                        "127265", "70",   "Continent9", "level 1-9, 16-19, 27 mobs", "-764", "138"}, |
| 33 | {"ruined keep",                           "101701", "70",   "Continent7", "level 6-18 mobs", "-121", "-99"}, |
| 34 | {"sanctus",                               "140",    "70",   "Continent5", "level 3-20 mobs, major city of eastern continents", "695", "-240"}, |
| 35 | {"spider swamp",                          "199",    "70",   "Continent1", "level 10-20 mobs", "-44", "128"}, |
| 36 | {"the depths",                            "9200",   "70",   "Continent5", "level 20-22 mobs", "643", "-10"}, |
| 37 | {"tugrahk gol",                           "199",    "70",   "Continent7", "level 6-30 mobs", "-54", "-320"}, |
| 38 | {"wizard training mansion",               "5900",   "10",   "Continent1", "level 3-6 mobs, questline", "-20", "99"}, |
| 39 | {"zhentil keep",                          "119100", "70",   "Continent8", "level 1-30 mobs", "-563", "-583"}, |
| 40 | {"always the last item",                  "0",      "0",    "Nowhere",    "nothing", "0", "0"} |
| 41 | }; |
