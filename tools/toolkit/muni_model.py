"""Muni rows' square-mile effect: mode shift times injury risk per mile, never counting Muni as injury-free.

Car side: new Muni trips x s, the share of new riders who leave a car (10% to 50%, CARB / Handy 2013 from TCRP 95),
each removing a car trip's risk. Trips are compared one for one; NTD counts boardings, so transfers make new
"trips" overstate removed car journeys, which leans toward too much benefit.

Muni side, two forms:
- Fares (no added buses): every new rider carries a Muni mile's risk, r of a car mile's. r = 0.26 (0.24 to 0.29):
  Morency et al. 2018 per passenger km, car vs bus, occupants 3.7 (3.4-4.0), pedestrians struck 4.1 (3.5-4.9),
  cyclists struck 5.3 (3.8-7.6), weighted by SF's 2022-2025 injury crash mix (68% vehicle only, 20% pedestrian,
  12% bicycle, DataSF ubvf-ztfx). change = -x (s - r).
- Frequency (doubled buses): crashes involving a Muni vehicle scale with bus miles, not riders. A transit vehicle was
  a party in 1.6% of SF's injury crashes 2022-2025 (189 of 11,781 cases, DataSF 8gtc-pjc6 parties, queried 2026-10-23), so doubling the buses
  adds 0.8% (if half are rail or would not scale) to 1.6% of the area's injuries. change = -x s + B. This replaces the
  r term, which would count the same bus crashes twice.
Car trips: TDS 2019, 4,457,310 trips a day, 53% private auto or TNC (p. 5). Muni trips: NTD FY2025 unlinked trips,
bus, light rail and streetcar (cable car and paratransit left out). Ratios are citywide.
"""
CAR_TRIPS = 4_457_310 * 0.53 * 365          # a year, citywide
BUS_TRIPS = 81_134_696 + 48_558_132          # NTD FY2025, motor bus + trolleybus
MUNI_TRIPS = BUS_TRIPS + 31_495_404 + 3_582_887  # + light rail and streetcar
S = dict(low=0.10, mid=0.30, high=0.50)
R = dict(low=0.24, mid=0.26, high=0.29)
B = dict(low=0.8, mid=1.2, high=1.6)       # percent of the area's injuries added by doubling bus miles

# Frequency: doubling service; CARB gives frequency +0.5 (cluster +0.3 to +1.0) and service hours +0.7 to +0.8.
# Arc elasticity: new trips = 2**e - 1 of today's bus trips.
FREQ = {k: BUS_TRIPS * (2 ** e - 1) for k, e in dict(low=0.3, mid=0.5, high=0.7).items()}
FREQ_FX = tuple(round(v, 1) for v in (
    -FREQ["high"] / CAR_TRIPS * S["high"] * 100 + B["low"],    # best: most riders, most from cars, fewest bus crashes
    -FREQ["mid"] / CAR_TRIPS * S["mid"] * 100 + B["mid"],
    -FREQ["low"] / CAR_TRIPS * S["low"] * 100 + B["high"]))    # worst
# Free fares: short-run fare elasticity -0.4 on a 100% cut gives 40% more riders (SF's free youth fares: +41% youth tags).
FARE_NEW = MUNI_TRIPS * 0.40
_x = FARE_NEW / CAR_TRIPS
FARE_FX = tuple(round(v, 1) for v in (-_x * (S["high"] - R["low"]) * 100, -_x * (S["mid"] - R["mid"]) * 100,
                                      -_x * (S["low"] - R["high"]) * 100))

if __name__ == "__main__":
    print("car trips a year", round(CAR_TRIPS / 1e6), "M; bus", round(BUS_TRIPS / 1e6, 1), "M; Muni", round(MUNI_TRIPS / 1e6, 1), "M")
    print("frequency new trips", {k: round(v / 1e6, 1) for k, v in FREQ.items()}, "share of car trips",
          {k: round(v / CAR_TRIPS * 100, 1) for k, v in FREQ.items()}, "effect best/mid/worst", FREQ_FX)
    print("fares new trips", round(FARE_NEW / 1e6, 1), "M, share", round(_x * 100, 1), "effect", FARE_FX)
