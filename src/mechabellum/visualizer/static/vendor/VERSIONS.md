# Vendored libraries

Pinned per ADR 0001 (`docs/adr/0001-no-build-frontend-vendored-libraries.md`). Nothing loads from a CDN at runtime; `task vendor` re-downloads these files.

| File | Library | Version | Source | sha256 |
| --- | --- | --- | --- | --- |
| `legend-state.mjs` | `@legendapp/state` core (`index.mjs`, no imports; reads `process.env.NODE_ENV`, so `index.html` sets a `globalThis.process` shim first) | 3.0.0-beta.48 | https://cdn.jsdelivr.net/npm/@legendapp/state@3.0.0-beta.48/index.mjs | `d0f4572a6a8522d6bf82af31a2746108c58f3430c0fb513491781b93f15dfddb` |
| `echarts.esm.min.js` | Apache ECharts (`dist/echarts.esm.min.js`) | 6.1.0 | https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.esm.min.js | `28515f26aa57f87eb1e4ed4eb446927eaf329b5f5e02b4bfd4b0264fea40d1da` |

Licences: Legend-State is MIT; ECharts is Apache-2.0 (its licence header is kept at the top of the file).
