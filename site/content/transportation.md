# The State of San Francisco's Bike Network

<p class="lede">San Francisco has improved its bike network over the last decade and has more improvements in the plans. This page explores much progress we've made. To plan for the future, in March 2025, the city adopted the <a href="{{ planUrl }}">Biking and Rolling Plan</a> (BRP) which proposes a future bicycle network that it claims to be good enough for "all ages and abilities." If we go with this definition for what's good enough, then the city has gone from {{ resStart }}% of residents connected to the network in {{ resStartYear }} to {{ resEnd }}% in {{ resEndYear }}:</p>

<div class="fig wide">{{# map }}</div>

<ul class="cite" data-for="Network map"><li><a href="https://data.sf.gov/d/p2fw-hsrv">Census Bureau 2020 census blocks</a>, with American Community Survey estimates for other years</li><li><a href="{{ layerUrl }}">SFMTA's bikeway layer</a>, read {{ networkQueried }}, last edited {{ layerEditedIso }}, newest install dated {{ layerLatestInstall }}</li><li>recent <a href="https://www.sfmta.com/projects">SFMTA project pages</a></li><li><a href="/transportation/bike/about#years">historical copies of the bikeway layer on Internet Archive</a></li></ul>

## What's Good Enough for All Ages and Abilities?

The map below shows the "North Star" network for "all ages and abilities", the aspirational goal from the <a href="{{ planUrl }}">Biking and Rolling Plan</a>.

The plan considers all of these bikeway types to be okay for "all ages and abilities": off-street paths like the Panhandle, separated bike lanes, Slow Streets like Page Street, and unprotected routes on quieter streets. And the plan also says an SF resident is connected to the network if they live within a quarter mile of a bikeway. Choose what you think "good enough" means and see how that affects the quality of the plan.

<div class="fig wide">{{# explorer }}</div>

<ul class="cite" data-for="Explorer" data-how="/transportation/bike/about#explorer"><li><a href="https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000">Census Bureau American Community Survey</a> population estimates</li><li><a href="{{ schoolsUrl }}">California Department of Education</a> public schools open in {{ lastYear }}</li><li><a href="https://data.sf.gov/d/7e7j-59qk">DataSF</a> private K-12 schools open in {{ lastYear }}</li><li><a href="https://data.sf.gov/d/nc68-ngbr">City Facilities</a> library branches</li><li><a href="{{ layerUrl }}">SFMTA's bikeway layer</a></li></ul>

## The All Ages and Abilities Network Grew by {{ avgPace }} Miles a Year on Average Between {{ avgFrom }}–{{ avgTo }} {#pace}

<div class="fig">{{# paceChart }}</div>

<p class="verdict-note">Miles count each direction of travel, as the plan does.</p>

<ul class="cite" data-for="Pace chart" data-how="/transportation/bike/about#planned"><li><a href="{{ layerUrl }}">SFMTA's bikeway layer</a></li><li><a href="/transportation/bike/about#years">historical copies of the bikeway layer on Internet Archive</a></li><li>recent <a href="https://www.sfmta.com/projects">SFMTA project pages</a></li></ul>

## At That Pace, It Would Take {{ yearsToGo }} Years to Build the Plan's North Star Network

<div class="fig">{{# goalChart }}</div>

<p class="verdict-note">The dotted line assumes every North Star street segment meets the all-ages test once it's built as drawn.</p>

<ul class="cite" data-for="Goal chart" data-how="/transportation/bike/about#north-star-goal"><li><a href="{{ layerUrl }}">SFMTA's bikeway layer</a></li><li><a href="/transportation/bike/about#years">historical copies of the bikeway layer on Internet Archive</a></li><li>recent <a href="https://www.sfmta.com/projects">SFMTA project pages</a></li><li>the <a href="{{ planUrl }}">Biking and Rolling Plan</a>'s Appendix L network, as we traced it</li></ul>

## SF Is Failing to Build an All Ages & Abilities Network {#problem}

In the last two years, progress has slowed dramatically. In 2025, the city added only {{ planYearAdded }} miles of additional all-ages bikeway, and progress is almost as slow in 2026. At this rate, the children living today in San Francisco won't get to bike and roll on the planned all-ages network until they're well into adulthood.

On top of that, what the Biking and Rolling Plan counts as "connected" falls well short of cities that bike more. Montreal's street grid is as fine as ours, with about 250 blocks per square mile in each city, yet half of Montrealers live within about 1,000 feet's walk of a physically protected bikeway, against about a quarter of San Franciscans. In Paris it's 87%, and in Barcelona and Seville about three in four (<a href="https://atlas.itdp.org/">ITDP Atlas of Sustainable City Transport</a>, end of 2025). A quarter mile isn't close enough.

So not only are we building the plan slowly. But also, the plan itself is a pretty poor fit for all ages and abilities.

## The City Already Made One Promise, But We're Not Keeping It {#coordination}

City law says a repaving project "shall include, to the maximum extent practicable and feasible, … Pedestrian and bicycle safety improvement measures" from the city's adopted plans (<a href="https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_publicworks/0-0-0-4453">§2.4.13(a)(2)</a>, <a href="https://sfgov.legistar.com/LegislationDetail.aspx?ID=1424825&amp;GUID=6025A6BD-D4B3-4781-8435-1D5C2807B7C9&amp;FullText=1">Ordinance 220-14</a>). So when Public Works or the city's water and sewer agency (SFPUC) repaves a street in the plan's network, the city is already required to add the plan's bike improvements where it can. Here's how that's gone.

The city has not followed this guideline in the last year. We took every street the city's <a href="https://data.sf.gov/d/78va-8dhi">pavement records</a> show as repaved from {{ pastFromLong }}, the month after the plan was adopted, to {{ pastToLong }}, and looked for it in the plan's North Star network. Where the plan calls for a better bikeway than the street had, we checked <a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a> and its project pages to see whether one was built with the repave. The only street that got the required upgrade was {{ cmpRepavedStreets }}.

{{# pastOpen }}

{{# pastView }}

<p class="verdict-note">Miles count each direction of travel, as the plan does. Another {{ pastAlready }} repaved miles already had the bikeway the plan calls for. {{ pastUnmapped }} repaved blocks are counted but not drawn, because they couldn't be matched to the plan's map. SFMTA's bikeway layer was last edited {{ layerEditedIso }}, so a bikeway built with a more recent repave may not show yet.</p>

<ul class="cite" data-for="Repaving since the plan" data-how="/transportation/bike/about#since-plan"><li>city <a href="https://data.sf.gov/d/78va-8dhi">pavement records</a></li><li><a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a></li><li><a href="https://www.sfmta.com/projects">SFMTA project pages</a></li></ul>

## By {{ cmpHorizonYear }}, Our Street Work Will Reach {{ nextNeed }} Miles Needing a Better Bikeway, With Upgrades Planned on Only {{ nextGot }} {#now-and-next}

We took the Public Works and SFPUC jobs in the city's <a href="{{ ovFeedUrl }}">street-work calendar</a> that are under way now or start by {{ cmpHorizonYear }}, leaving out streets already counted above. A block counts as planned when an <a href="https://www.sfmta.com/projects">SFMTA project page</a> or the job's own scope adds the plan's bikeway. Work under way has upgrades planned on {{ nowPct }}% of the {{ nowNeed }} miles that need one, and work starting {{ laterFrom }} to {{ cmpHorizonYear }} on {{ laterPct }}% of {{ laterNeed }}.

{{# nextOpen }}

{{# nextView }}

<p class="verdict-note">Miles count each direction of travel. {{ nextUnmapped }}See <a href="/transportation/bike/projects">every project on these streets</a>.</p>

<ul class="cite" data-for="Street work through {{ cmpHorizonYear }}" data-how="/transportation/bike/about#since-plan"><li>the city's <a href="{{ ovFeedUrl }}">street-work calendar</a>, as of {{ ovFeedQueried }}</li><li><a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a></li><li><a href="https://www.sfmta.com/projects">SFMTA project pages</a></li></ul>

## Can We Do Better? {#conclusion}

At today's pace, it takes {{ yearsToGo }} years to build the plan's network. And even today, only {{ blockShare }}% of residents live within a block of an all-ages bikeway.

The city has already committed to one way to go faster: build the plan's bikeway when it repaves. From {{ pastFromLong }} through {{ cmpHorizonYear }}, city street work reaches {{ cmpCould }} miles of the plan's network that need a better bikeway, and only {{ cmpGot }} of them got it or have it planned. The other {{ cmpMissed }} miles are about {{ cmpYears }} years of building at today's pace. The law asks for these miles, and pressing the city to show why each one wasn't feasible could win many of them back.

There's a second way, and it's worked before: build the parts of the network that matter most, in the districts whose supervisors want them. Downtown, the city built 16.5 of the 21.6 miles of separated bike lanes it has there today between 2017 and 2021, more than half of the separated lanes it added citywide in those years (<a href="{{ layerUrl }}">SFMTA's bikeway layer</a>). The <a href="https://www.sfmta.com/node/26713">17th Street quick-build</a> in Potrero Hill was approved in March 2024 and built by that June (<a href="https://www.potreroview.net/protected-bike-lane-opens-on-17th-street/">Potrero View</a>).

Ride 17th Street and you can see the difference a district makes. It isn't perfect, but in Potrero Hill, in District 10, it's a separated bike lane for all 13 blocks from Potrero Avenue to Mississippi Street. Cross into the Mission, in District 9, and only 4 of its 16 blocks are separated. In District 8, which includes the Castro, it's 1 of 13 (<a href="{{ layerUrl }}">SFMTA's bikeway layer</a>, <a href="https://data.sf.gov/d/f2zs-jevy">supervisor districts</a>). Same street, same street grid. We think the difference is what each district's leaders were willing to back. So let's build first where supervisors want it, let the rest of the city see what it's missing, and elect leaders who care.

We've moved even faster. During the pandemic, SFMTA announced Slow Streets on April 21, 2020, and by July it had put up barricades on 16 corridors, with 17 more on the way, for about $250,000 (<a href="https://www.sfmta.com/media/23090/download?inline">SFMTA staff report, July 2020</a>). That year, Slow Streets added {{ jumpSlow }} miles to the all-ages network, more than three times the {{ avgPace }} miles a year the city averages. The city took about {{ slowDropped }} of those miles back out in {{ slowDroppedYear }}, but the speed was real. When we have the will to do better, we can move fast. But right now, we've forgotten how to move quickly, or our leaders simply don't care.

We'll be back soon with a look at SFMTA's upcoming <a href="https://www.sfmta.com/projects/safe-school-connections">Safe School Connections</a> plan, a first step toward bikeways closer than a quarter mile, which SFMTA expects to take up after the two transportation funding measures on the November 2026 ballot.
