# tools/street-safety

The High Injury Network, the injury map, speed cameras, and the Street Safety map with its traffic layers: through traffic, where traffic comes from, mode share by place and residents' Telraam counts.

    python3 pipeline/transportation-update.py --only telraam,sfpd-crime,street-safety-cards,injury-map,injury-severe-why,through-traffic,where-traffic-comes-from,where-traffic-modes,street-safety-map
    python3 tools/street-safety/telraam-gates-test.py
