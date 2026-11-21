// A function's source, ready to copy into a page's <script>.
// Under the dev server, Vite rewrites a call to an imported function as
// `(0,__vite_ssr_import_9__.wedgeUI)(...)`, and those names don't exist in the
// browser. The page also copies the imported function itself, so the plain name
// is what the browser needs. The production build leaves names alone, so this
// changes nothing there.
export function fnSource(fn) {
  return fn.toString()
    .replace(/\(0,\s*__vite_ssr_import_\d+__\.(\w+)\)/g, "$1")
    .replace(/__vite_ssr_import_\d+__\.(\w+)/g, "$1");
}
