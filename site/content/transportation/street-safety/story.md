---
title: "The High Injury Network Leads to Poor Decisions"
summary: "San Francisco aims its street safety work with the High Injury Network, a map of where people were hurt worst in the past. Here's what it hides, and a prototype map that shows more."
status: draft
---

The Department of Public Health (SFDPH) has built and gradually improved a High Injury Network map. From the most recent published iteration, the [2024 HIN from March 2026](https://www.sf.gov/2024-high-injury-network-hin-map), the purpose of the map is the following:

> Its primary goal is to provide the most comprehensive analysis to date of the locations where a majority of severe and fatal injuries occur, enabling the City to make more targeted street safety investments.

This is an important part of understanding how to tackle safety, but what I’ve often seen is that when the HIN is the primary data stakeholders use, it’s misleading. Looking only at the highest-injury street segments from the past dehumanizes us and hides key details about how people move around the city.

Instead of helping us invest limited resources wisely, the HIN blinds us from seeing the most important types of safety problems people face. Plus it points us towards an artificially narrow set of solutions where we only think of street segments.

Let’s try to make a better interactive safety map, and then use that prototype to show you how we might make better decisions.

Note: This is just a prototype. City departments should be able to do a better job with access to richer internal data, which we point out at the end.

## Questions the HIN Doesn't Answer

- **Crash mechanics**
  - Why did people crash into each other (or crash on their own)?
    - Did one party break the law?
    - How did human factors & street environment contribute?
  - When did the crash happen? (e.g. daylight vs. darkness, rush hour, TGIF, weekend)
  - Where did the crash happen within the street block?
  - What sequence of events led up to the crash?
  - Are there factors that exacerbated severity? e.g., big difference in velocity or mass between parties
- **Network effects**
  - Where were people coming from or going to?
  - Did anyone have a good alternative route or travel mode with lower crash risk?
- **Other safety gaps**
  - What about the 1/3 of people hurt off of the HIN?
  - Where are people having less severe injuries? Near misses? Or people feeling traffic stress?
  - Where are people feeling unsafe from the risk of crime on trips?

These details matter because they guide which solutions to use. A high-speed DUI crash at 4 AM might demand better late-night police enforcement or new state laws, while an intersection where drivers consistently can’t see pedestrians might call for better hardened daylighting.

## Prototyping A Better Street Safety Map

<MapStory map="street-safety">
<MapStep state={{"view": "injuries", "hin": ["2024"]}}>

To address this problem, we built a prototype street safety map that tries to better answer the questions above. It’s based on public data only.

Here were some of the key design goals while building this map:

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "camera": {"center": [-122.4135, 37.7838], "zoom": 16.4}}}>

1. **Center individual people.** This is a map where every person injured and each person who died on our streets is represented when you zoom in. Key details from the police report and related news articles help understand how they got hurt or died. You always have access to the details.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "chart": {"id": "by-cause"}}}>

2. **Identify top problems from multiple angles.** The map also helps you look at the data from different directions to try and ask the questions above, and see where they help you find types of safety problems that happen often.

</MapStep>
<MapStep state={{"view": "through"}}>

3. **Use best practices** Our Safe Systems approach came from earlier Swedish and Dutch methods, but lost some key parts of the Dutch method: separation of through-traffic from local and how to shift people to lower risk trips

</MapStep>
</MapStory>

This map is imperfect — often I found that I didn’t quite have the data I hoped for. Our transportation models (i.e. SFCHAMP) mainly have data for cars on main streets. Other road users are second class citizens. Police reports also don’t include enough information on year and model to understand how changing vehicle mass of our cars, bikes and scooters come into play. Nor do these reports contain any information about where the parties were going.

And also, ideally we’d do a more systematic review of causes and solutions, which we might do later.

One of the more important decision intelligence principles I learned during my career though is to do what you can with the data you have. And then ask is it good enough to make the right decision? If it is, go with it. Avoid analysis paralysis.

So here we go…

## Why HIN Leads to Poor Decision-Making

### HIN Leads to Too Much Focus on (Worst) Segments

<MapStory map="street-safety">
<MapStep state={{"view": "injuries", "hin": ["groups"], "filter": {"hinGroup": [1]}, "chart": {"id": "by-hin-group"}}}>

In the SFCTA Board Meeting on November 17, 2026, supervisor Dorsey asked about the "8.8 miles of streets in which 40 plus people have been killed or severely injured (KSI) over the last four years." These are the highest injury segments from the 2024 HIN. Supervisor Fielder wanted to know if any of these 8.8 miles overlapped District 9. SFMTA said "I don't know off the top of my head," but had told Dorsey that of the "400 plus intersections" it has identified on the HIN, "where it's more dangerous is where we're going to go first." ([SFGovTV captions, 1:20:56 and 2:06:21](https://sanfrancisco.granicus.com/MediaPlayer.php?view_id=24&clip_id=53601))

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "worst": 2020, "chart": {"id": "worst-overlap"}}}>

The worst segments are a moving target.

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "worst": 2024, "chart": {"id": "worst-overlap"}}}>

They change every year due to reversion to the mean.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["groups"], "chart": {"id": "by-hin-group"}}}>

Many other segments are about as bad over the long term.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["groups"], "filter": {"hinGroup": [1]}, "chart": {"id": "by-hin-group"}}}>

Plus, the worst 8.8 miles of streets only accounted for 14% of KSI from 2021 to August 2026 ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)).

</MapStep>
</MapStory>

<p><small>The 8.8 miles are DPH's top tier of the 2024 network: stretches with 40 or more people killed or severely injured per mile in 2020 to 2024. DPH hasn't published which stretches those are, so we estimated them from police reports, which count fewer people than DPH's linked hospital data. The map shows the worst 10 miles of the 2024 network, the closest group it draws.</small></p>

The worst segments help us define one problem to solve, but it’s not clear it’s the best problem or that it leads to the effective solutions.

### HIN Hides What Causes Crashes

When we look at only street segments, we miss why crashes happened. This leads us to focus too much on building out physical interventions and signal changes, and not enough on other tools in the toolbox.

All observations below are based on KSI from 2021 to August 2026.

<MapStory map="street-safety">
<MapStep state={{"view": "injuries", "hin": [], "filter": {"cause": ["unsafe-speed"], "severity": "pain"}, "chart": {"id": "by-cause", "top": true}}}>

#### Unsafe Speed

Of the top-level police categories, unsafe speed accounts for the most injuries, about 1 in 5, and is one of the top causes of death ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), 2021 to August 2026).

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "filter": {"cause": ["unsafe-speed"]}, "chart": {"id": "by-cause", "top": true}}}>

Some of the tools we already use are effective at reducing speed (e.g., lower speed limits, speed cameras, road diets).

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "filter": {"cause": ["pedestrian-violation"]}, "chart": {"id": "by-cause", "top": true}}}>

#### Pedestrian Violations

Pedestrian violations accounted for 22% of deaths and 13% of KSI ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), 2021 to August 2026). This includes cases such as a pedestrian walking into moving traffic in the mid-block or in a crosswalk while the "no crossing” light was up.

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "filter": {"cause": ["red-light"]}, "chart": {"id": "by-cause", "top": true}}}>

#### Running Red Lights

About 12% of KSI came from vehicles running red lights ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), 2021 to August 2026). Red light cameras help with this, but our current fleet of cameras at 18 intersections only covers 4% (7 of 165) of the intersections with a severe or fatal red light violation injury ([SFMTA](https://www.sfmta.com/RedLight), [DataSF uzmr-g2uc](https://data.sfgov.org/d/uzmr-g2uc)).

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "filter": {"time": ["night"], "other": ["none"], "severity": "killed"}, "chart": {"id": "by-cause"}}}>

#### Late Night DUI

8% of the deaths on streets from 2021 to August 2026 (14 of 178) came from late-night crashes with only one vehicle involved. Police recorded drinking or DUI in only 2 of the 14, and marked impairment "not known" in 12 ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) and [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6)).

</MapStep>
<MapStep state={{"view": "injuries", "hin": [], "filter": {"time": ["night"]}, "chart": {"id": "by-time"}}}>

All late-night crashes, 10 pm to 4 am, led to more deaths (57 to 25) and more KSI (372 to 239) than the 8.8 miles of worst segments over the same years.

<p><small>The map's Night filter runs 10 pm to 6 am, so it shows more deaths and injuries than the 10 pm to 4 am figures here.</small></p>

</MapStep>
</MapStory>

#### Recommended Alternative

This is only a cursory look, and what would be most helpful is to look both at clusters that might have a common cause and way(s) to fix, and consider what tools are most effective at addressing each cluster.

LADOT did such an analysis in their 2024 [Vision Zero report](https://ladot.lacity.gov/sites/default/files/documents/la-vz-safety-study-2024.pdf), and it was interesting.

### HIN Misses Dutch Best Practices

In the Dutch sustainable safety approach both of these principles make it easier to have safe roads:

1. Strictly separate through-traffic from local traffic. And if these need to mix with bikers or pedestrians, then these grey zones need extra care (e.g. 20mph speed limits)
2. Move people to lower risk streets (and we extend this to consider modes of travel)

<MapStory map="street-safety">
<MapStep state={{"view": "through"}}>

In our prototype we try to show where we have through traffic as a starting point for discussion. Typically in our street grids, cars go everywhere and rush hour through traffic fills much of the grid. Where do communities actually want to have through traffic?

</MapStep>
<MapStep state={{"view": "from", "filter": {"area": {"hood": "West of Twin Peaks"}}}}>

Also we study where people are trying to go to, and review what might need to happen to give them a safer more convenient alternative.

</MapStep>
</MapStory>

### HIN Masks Equity Impact

We see where injuries happen in equity priority communities but can’t tell if those injured came from that community. Or if they travelled from a different equity priority community.

This clouds our ability to prioritize the communities we want to support most.

I’m not sure yet how to address this with the data I have.

### HIN Misses Broader Safety Issues People Care About

<MapStory map="street-safety">
<MapStep state={{"view": "injuries", "hin": ["2024"], "color": "hin", "chart": {"id": "by-hin"}}}>

Looking at only KSI misses all of the places people feel unsafe on the street.

</MapStep>
<MapStep state={{"view": "injuries", "hin": ["2024"], "filter": {"hin": "off"}, "chart": {"id": "by-hin"}}}>

First, about 1/3 of all injuries and 1/4 of severe injuries and deaths happen off of the HIN ([SFMTA](https://www.sfmta.com/blog/new-high-injury-network-map-helps-guide-us-safer-city) puts 74% of severe and fatal injuries on it; [police reports, 2021 to August 2026](https://data.sfgov.org/d/nwes-mmgh)).

</MapStep>
<MapStep state={{"view": "stress"}}>

Beyond injuries and deaths, residents feel unsafe on many more streets off the HIN. Often from rush hour through-traffic rushing through main streets and side streets.

</MapStep>
</MapStory>

<p><small>On the map, a person is off the network when they were hurt more than 60 ft from it, and its chart counts the people killed or severely injured from 2021 to now.</small></p>

## Key Recommendations

As the city considers updated metrics and dashboards please consider all of the factors above and more.

And if these city isn’t able to cover the key factors above, I do plan on asking for better data and making sunshine requests so the public can fill the gap.

## Key Data Requests

- **Better injury records** For each party involved in a collision we’d like the police to share the following in public data sets:
  - **Year, make, and model**<br>This lets us see how vehicle mass and type contribute to injury
  - **Analysis neighborhoods**<br>To see where each party was coming from and going to. And if any party resides in an equity priority neighborhood.
  - This will let us estimate fraction of injuries due to through traffic.
  - Have informed discussions about which streets are meant for through traffic. And which communities need better safer travel alternatives

## Asking Questions

One of the most important habits when using data is to keep asking questions. So please be skeptical of what I share here, and be just as skeptical of any other data.

- Is this data leading me to make the right decision?
- What is the data or model hiding? Am I missing other perspectives or solutions because of that?
- Why did the people in a crash need to be in the same place at the same time? What factors caused this? e.g. why did a pedestrian need to be near a fast-moving car or bike?

The data we have tries to place each crash into buckets and assign blame to a human (e.g., "Unsafe speed", "Pedestrian violation", etc.) We lose sight of the fact that while maybe some training can reduce disobedience, we can't change human nature. Human error happens.

Other, more progressive street designers (e.g., the Dutch) try to design streets with enough separation so that even when humans make an error or disobey a law, it doesn’t result in a collision, injury, or death.

[Open the full Street Safety map](/transportation/street-safety) to explore it yourself.
