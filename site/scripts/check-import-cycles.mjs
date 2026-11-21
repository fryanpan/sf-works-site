#!/usr/bin/env node
// Fail when site code imports itself in a loop.
//
//   node scripts/check-import-cycles.mjs [<dir> ...]     defaults to src and scripts
//
// Follows relative imports and the `@/` alias (src/), in .ts, .mjs, .js and .astro
// files. Package imports and `astro:` modules are ignored. Exit 1 if any cycle exists.

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const EXTS = ['.ts', '.mjs', '.js', '.astro', '.tsx', '.jsx']
const IMPORT = /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|import\s+['"]([^'"]+)['"]/g

function listFiles(dir) {
  if (!fs.existsSync(dir))
    return []
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    const p = path.join(dir, d.name)
    if (d.isDirectory())
      return d.name === 'node_modules' ? [] : listFiles(p)
    return EXTS.includes(path.extname(d.name)) ? [p] : []
  })
}

function resolve(from, spec, root) {
  let base
  if (spec.startsWith('@/'))
    base = path.join(root, 'src', spec.slice(2))
  else if (spec.startsWith('.'))
    base = path.resolve(path.dirname(from), spec)
  else
    return null
  for (const candidate of [base, ...EXTS.map(e => base + e), ...EXTS.map(e => path.join(base, `index${e}`))]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile())
      return candidate
  }
  return null
}

export function findCycles(dirs, root = SITE) {
  const graph = new Map()
  for (const file of dirs.flatMap(d => listFiles(path.resolve(root, d)))) {
    const text = fs.readFileSync(file, 'utf8')
    const deps = new Set()
    for (const m of text.matchAll(IMPORT)) {
      const target = resolve(file, m[1] ?? m[2] ?? m[3], root)
      if (target)
        deps.add(target)
    }
    graph.set(file, deps)
  }

  const cycles = []
  const state = new Map() // 1 = on the current path, 2 = finished
  const stack = []
  function visit(node) {
    state.set(node, 1)
    stack.push(node)
    for (const dep of graph.get(node) ?? []) {
      if (state.get(dep) === 1)
        cycles.push([...stack.slice(stack.indexOf(dep)), dep].map(f => path.relative(root, f)))
      else if (!state.has(dep))
        visit(dep)
    }
    stack.pop()
    state.set(node, 2)
  }
  for (const node of graph.keys()) {
    if (!state.has(node))
      visit(node)
  }
  return cycles
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dirs = process.argv.slice(2)
  const cycles = findCycles(dirs.length ? dirs : ['src', 'scripts'])
  for (const c of cycles) console.log(`cycle: ${c.join(' -> ')}`)
  console.log(cycles.length ? `${cycles.length} import cycle(s)` : 'no import cycles')
  process.exit(cycles.length ? 1 : 0)
}
