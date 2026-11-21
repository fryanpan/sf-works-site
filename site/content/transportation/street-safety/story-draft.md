---
title: "Where People Get Hurt: A Map Story (Test)"
summary: "A test of the Street Safety map stepping through a story as you scroll."
status: draft
---

Test page. The map stays put while you scroll, and each step changes what it shows.

<MapStory map="street-safety">
<MapStep state={{"view": "injuries", "hin": ["2024"]}}>

**The city aims its safety work at 13% of streets.** SFMTA's 2024 High Injury Network covers 13% of streets and 74% of serious injuries and deaths in its 2020 to 2024 data ([SFMTA, 30 March 2026](https://www.sfmta.com/blog/new-high-injury-network-map-helps-guide-us-safer-city)).

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2022", "2017"]}}>

**Hotspots move.** Only 2 of today's worst 40 places were in the worst 40 of 2019 to 2021. The 2022 network, drawn before these crashes, held 620 of the 922 people hurt (67%).

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "filter": {"hin": "off"}}}>

**One in five people was hurt off the network.** 191 of the 922 were hurt off the 2024 network, on 176 blocks, with no block holding more than 5.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "camera": {"center": [-122.432, 37.758], "zoom": 13.4}}}>

**Busy streets reach past the network.** Take one part of the city: first the people hurt here, then the traffic on the same streets.

</MapStep>
<MapStep state={{"view": "stress", "camera": {"center": [-122.432, 37.758], "zoom": 13.4}}}>

The same streets by cars at the busiest hour. Of the 5,643 residential blocks with a measured, modelled or estimated figure, 4,285 carry 1.5 cars a minute or more. The other 4,407 of the city's 10,050 have no figure.

</MapStep>
<MapStep state={{"view": "through", "camera": {"center": [-122.46, 37.736], "zoom": 13.6}, "filter": {"area": {"hood": "West of Twin Peaks"}}}}>

**West of Twin Peaks, the main streets are through streets.** On 145 of the 275 blocks the model carries there, most car trips start and end more than a mile away: Portola Drive, Monterey Boulevard, Ocean Avenue and 19th Avenue. Steer that traffic onto a few corridors and the parallel streets can carry less, while the corridors get the tools to manage it.

</MapStep>
<MapStep state={{"view": "through", "camera": {"center": [-122.4368, 37.7505], "zoom": 14.6}, "chart": {"id": "none"}}}>

**Residential streets send mixed messages.** Diamond Street through Noe Valley is a residential street, but on its blocks from 18th Street to Diamond Heights 14 to 29% of the car trips start and end more than a mile away.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "camera": {"center": [-122.43605, 37.79984], "zoom": 17.2}, "highlight": {"circle": {"center": [-122.43605, 37.79984], "feet": 120}}}}>

**Zoom in: it's the intersection.** 599 of 922 people were hurt at an intersection. For people walking it's 240 of 338 (71%). This corner is Lombard and Fillmore.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "camera": {"center": [-122.43605, 37.79984], "zoom": 17.2}, "highlight": {"circle": {"center": [-122.43605, 37.79984], "feet": 120}}, "crash": "220399065"}}>

**Different crashes need different fixes.** Each crash here has its own card: who was hurt, who hit them and how.

</MapStep>
<MapStep state={{"view": "crime", "camera": {"center": [-122.414, 37.781], "zoom": 13.2}}}>

**Crime is part of the walk too.** 63% of all SFPD reports fall within 300 ft of a Muni stop.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"]}}>

**What to do instead:** rank by crash type, and treat every place with that type. [Open the full map](/transportation/street-safety) to explore it yourself.

</MapStep>
</MapStory>
