// Street names as the site prints them, from the city's upper-case records.

/** "MISSION ST" to "Mission St", "03RD ST" to "3rd St". */
export const streetName = (n) => n.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(\d+)(St|Nd|Rd|Th)\b/g, (_, d, x) => d + x.toLowerCase()).replace(/\b0+(\d)/g, "$1");
