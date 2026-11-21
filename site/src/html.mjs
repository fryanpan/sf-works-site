// The one HTML escape every page module uses, for text and for attribute
// values alike. Every attribute the pages write is double-quoted, so `"` is
// the quote that has to be escaped; `'` is left as it is.
export const esc = (s) =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
