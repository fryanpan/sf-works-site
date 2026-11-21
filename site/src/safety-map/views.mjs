// The Street Safety map's named views: the dashboard at a preset state, one page each at
// /transportation/street-safety/view/<name>/, for a board doc's `::safety{block="<name>"}` line and for a link that
// should carry its own title into a link preview.
//
// A board embed's path template can't carry the address fragment the state lives in (only `block` reaches the URL),
// and the board refuses a frame inside a sandboxed frame, so a view needs a path of its own. Each page opens the
// dashboard at its state with the filters folded, so the card shows the generated title (state.js `title`), and that
// title is the page's <title> and og:title, which a link preview reads without running the page.
//
// Each entry: [name, address fragment, what it shows]. Names never change once a doc uses them; add, don't rename.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

export const NAMED_VIEWS = [
  ["intro", "", "The whole city, as the dashboard opens"],
  ["city-hall", "at=-122.41925,37.77930,16.00", "About five by five blocks around City Hall, close enough that each person hurt shows"],
  ["bayview", "hood=Bayview%20Hunters%20Point", "Filtered to Bayview Hunters Point and zoomed to it"],
  ["by-cause", "chart=by-cause", "The whole city, with the chart split by the police report's cause"],
  ["dui-night", "pick=dui&time=night", "DUI crashes at night (10 pm to 6 am), DUI picked on the cause chart"],
  ["pedestrian-violation", "pick=pedestrian-violation", "Pedestrian violation crashes, picked on the cause chart"],
  ["red-light", "pick=red-light", "Red light crashes, picked on the cause chart"],
  ["unsafe-speed", "pick=unsafe-speed", "Unsafe speed crashes, picked on the cause chart"],
  ["on-off-hin", "color=hin&chart=by-hin", "Everyone hurt in the police reports' years, each coloured on or off the 2024 network (60 ft), the chart split the same way"],
  ["hin-groups", "hin=groups&rank=2022-2024&years=2022-2024&chart=by-hin-group", "The 2024 network in 10-mile groups, worst to best on 2022 to 2024, the chart one bar per group"],
  ["hin-group-1", "hin=groups&rank=2022-2024&years=2022-2024&groups=1&chart=by-hin-group", "The worst 10 miles of the 2024 network on 2022 to 2024, picked on the group chart"],
  ["hin-group-2", "hin=groups&rank=2022-2024&years=2022-2024&groups=2&chart=by-hin-group", "The second worst 10 miles of the 2024 network on 2022 to 2024, picked on the group chart"],
  ["hin-group-3", "hin=groups&rank=2022-2024&years=2022-2024&groups=3&chart=by-hin-group", "The third worst 10 miles of the 2024 network on 2022 to 2024, picked on the group chart"],
  ["hin-group-4", "hin=groups&rank=2022-2024&years=2022-2024&groups=4&chart=by-hin-group", "The fourth worst 10 miles of the 2024 network on 2022 to 2024, picked on the group chart"],
  ["worst-2020", "hin=none&worst=2020&chart=worst-overlap", "The worst 10 miles of street in 2020, with how much was also the year before's worst"],
  ["worst-2021", "hin=none&worst=2021&chart=worst-overlap", "The worst 10 miles of street in 2021, with how much was also the year before's worst"],
  ["worst-2022", "hin=none&worst=2022&chart=worst-overlap", "The worst 10 miles of street in 2022, with how much was also the year before's worst"],
  ["worst-2023", "hin=none&worst=2023&chart=worst-overlap", "The worst 10 miles of street in 2023, with how much was also the year before's worst"],
  ["worst-2024", "hin=none&worst=2024&chart=worst-overlap", "The worst 10 miles of street in 2024, with how much was also the year before's worst"],
  ["worst-2025", "hin=none&worst=2025&chart=worst-overlap", "The worst 10 miles of street in 2025, with how much was also the year before's worst"],
];

const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(import.meta.dirname, "state.js"), "utf8"), ctx);
const S = ctx.SafetyMapState;

/** The generated title for a fragment, or null when it sets no filter. `causes` is map.json's cause tree. */
export function viewTitle(hash, causes) {
  return S.title(S.fromHash(hash), causes, 60);
}
