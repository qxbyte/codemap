# codemap-vue

> A Vue Single File Component (`.vue`) indexer for
> [CodeMap](https://github.com/qxbyte/codemap), distributed as an
> independent PyPI package.

## What it captures

Backed by a small regex-based SFC scanner + tree-sitter:

| SFC block | Indexed | Backed by |
|---|---|---|
| `<template>` | ❌ Ignored | — |
| `<script>` (`lang="js"` / default) | ✅ | `tree-sitter-javascript` (required) |
| `<script>` (`lang="jsx"`) | ✅ | `tree-sitter-javascript` (required) |
| `<script>` (`lang="ts"`) | ✅ (with `[typescript]` extra) | `tree-sitter-typescript` (optional) |
| `<script>` (`lang="tsx"`) | ✅ (with `[typescript]` extra) | `tree-sitter-typescript` (optional) |
| `<script setup>` (`lang="ts"`) | ✅ (with `[typescript]` extra) | `tree-sitter-typescript` (optional) |
| `<style>` | ❌ Ignored | — |

Inside the `<script>` block, the same symbol kinds as `codemap-javascript`
and `codemap-typescript` are surfaced:

| AST node | Symbol kind |
|---|---|
| `function_declaration` | `function` |
| `class_declaration` | `class` |
| `method_definition` (inside class) | `method` |
| Top-level `const` / `let` / `var` | `variable` (with `extra.vue_block_lang`) |

Line numbers are translated back to the original `.vue` file coordinate
space, so `codemap get` jumps to the correct line even when the script
block starts hundreds of lines below `<template>`.

## Install

```bash
# JavaScript-only Vue projects (no <script lang="ts">):
pip install codemap-vue

# Vue projects that use TypeScript in <script setup lang="ts"> (the
# Vue 3 default):
pip install "codemap-vue[typescript]"
```

`tree-sitter-typescript` is an optional dependency because some Vue
projects (Vue 2 codebases, JS-only sites) do not need it. When you index
a `.vue` file with `<script lang="ts">` and the extra is not installed,
the plugin emits a `VUE003` warning instead of crashing.

## Implementation notes

`tree-sitter-vue` is not currently published on PyPI. Rather than
bundle a hand-compiled grammar, this plugin uses a permissive regex
scanner (`codemap_vue.sfc.extract_script_blocks`) to locate every
top-level `<script>` block in the SFC, read its `lang=` attribute, and
slice out the inner bytes. The inner bytes are then handed to the
appropriate tree-sitter grammar.

The scanner is intentionally permissive about malformed input: a
missing `</script>` closing tag still produces a block that runs to
EOF, so indexing partial / in-progress files still yields useful
symbols.

## SymbolID encoding

```
scip-vue . . . src/components/UserList.vue/fetchUser().
└──────┘     └────────────────────────────────────────┘
  scheme         file → namespaces / type / method
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Limits / next steps

* `<template>` contents (directives, expressions, `v-on` handlers) are
  not parsed. A future `codemap-vue` minor release could expose
  declared template refs (`<input ref="emailRef" />`) and `defineProps`
  / `defineEmits` macros as symbols.
* `<script setup>` macros (`defineProps`, `defineExpose`, …) are
  surfaced only when they appear as ordinary function calls inside a
  variable declaration. Treating them as first-class component-shape
  symbols is a v0.2.x improvement.
* Class-based component decorators (vue-class-component / vue-property-decorator)
  are not yet captured.

## License

MIT — same as the host project.
