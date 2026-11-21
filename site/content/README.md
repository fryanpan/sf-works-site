# The words on each page

One file per page. `home.html` is the front page, `transportation.html` is
`sf-works.org/transportation`, and so on. These are the only files you need to open to
change what a page says.

## Editing

Open the file, change the words, save, and run:

```
npm run build
```

The page is rebuilt into `dist/`. Nothing else has to be touched.

## The two things in curly braces

Figures are not typed in. They are filled in at build time from the city data
the collectors wrote, so a sentence cannot go stale while the number beside it
moves.

```
{{ shortfall }} of {{ onPlan }} segments fell short.
```

renders as *62 of 111 segments fell short*.

```
{{# shortfallTable }}
```

drops in a whole block — a table, a generated list. It is built in the page's
`.mjs` file because it is made of data, not words.

**You can move a placeholder, delete it, or use it twice.** What you cannot do
is invent one: `{{ somethingNew }}` fails the build, naming the file and the
name, because a page that quietly drops a figure still reads as a finished
sentence and nothing about it looks wrong. If you need a figure that does not
exist yet, that is a change to the page's `.mjs` file.

To see what is available to a page, look at the `content(...)` call in
`src/pages/<page>.mjs`: every name listed there can be used in the prose.

## Why HTML and not markdown

The prose was already written as HTML, so this keeps it as it was rather than
rewriting every page. The site now builds with Astro, so a new page that wants
markdown can be a `.md` file under `site/astro/pages/`.

In practice you are editing the words between the tags:

```html
<p>Most of San Francisco's own requirements are written with a
practicability test that the city itself applies.</p>
```

`<p>` is a paragraph, `<h2>` a heading, `<strong>` bold, `<em>` italic, and
`<a href="...">` a link. Leave the tags alone and change what is between them.

## A whole page in markdown

A markdown file under `content/` that opens with front matter is a page of its
own, at the matching address: `content/whitepaper/part-1.md` is
`sf-works.org/whitepaper/part-1`, and an `index.md` is its folder's address.

```
---
title: How SFMTA Decides What Gets Built
summary: One or two sentences, shown in Recent Changes on the front page.
status: teaser
---
```

`status` is `draft` (the default: built on staging only), `teaser` (the title,
summary and "coming soon", with buttons to ask for it next or offer to help;
the body is not shown) or `published`. Leave `updated` out and the page is
dated by its last commit. The fields are checked against
`site/content/.workspaces/doc-metadata.schema.json`, and a bad one fails the build. A line
`::sfworks{block="goal-chart"}` drops in a chart or a live map, the same
blocks the bike post uses. `content/examples/markdown-page.md` shows both.

## A page with published versions

A page that keeps its old versions lives in a folder of its own:
`content/transportation/whitepaper/page.mdx` (or `page.md`) is
`sf-works.org/transportation/whitepaper`, with its images and figure pages
(`embeds/<name>.html`, which `::scratch{block="<name>"}` frames before the
shared `data/embeds/` copy) beside it.

When the page is ready to publish as a new version, run from `site/`:

```
npm run new-version -- transportation/whitepaper
```

That copies the folder, all but `versions/`, into `versions/<n>/` and adds the
date, commit and a hash of the copy to `versions/versions.json`. Commit both.
The deploy then builds version `n` at `/transportation/whitepaper/v/<n>` from
its own copy, the revision history at `/transportation/whitepaper/v/`, and the
line "Last updated … Version n. See the revision history" under the title.
Never edit inside `versions/`: `npm run check` and the deploy fail when a
published version's folder is gone or its files have changed.

## A board doc as a page

A doc written on the board publishes as it is, as `.mdx`, with no conversion:
its `<PlotChart>` charts, `<Carousel>` groups, `::scratch{block="..."}`
figures, `^[...]` notes and `images/` all render (`src/md-components.mjs`).

1. On the board, move the doc's file under `site/content/` with
   `move_doc_file`, so the binding follows it: for example
   `site/content/whitepaper/part-1.mdx` is `sf-works.org/whitepaper/part-1`.
   Copy its `images/` folder beside it.
2. In the editor's metadata fields, set the title and `status: published`.
3. From `site/`, run `npm run deploy-docs -- --push`. It copies each framed
   figure from `scratch/embeds/` into `data/embeds/`, runs the checks, builds,
   opens every page in headless Chrome (`site/scripts/check-rendered-docs.mjs` at
   the repo root), then commits the page, its images and figures on a branch
   and merges them through a PR. The merge deploys. Without `--push` it stops
   after the checks.

A relative link to another note (`./something.md`) fails the rendered check,
since it would be a dead link on the site.
