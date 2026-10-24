# No-build Visualizer frontend with vendored libraries

The Visualizer frontend is plain HTML, CSS and ES modules with no bundler or npm toolchain. Its libraries are vendored whole into the Python package as pinned files: Legend-State `3.0.0-beta.48` with a `process.env` shim, and Apache ECharts `6.1.0`. Nothing loads from a CDN at runtime. This keeps the repo Python-only, so the package ships the frontend as plain package data. The app also works offline and runs no outside script, which fits the mod rule that the app never talks to anything but localhost and the wiki.gg icon cache. The trade-offs:
- Designs, including the Claude Design prototype, have to be ported to plain JS rather than dropped in as framework components.
- Library upgrades are a manual `task vendor` re-pin.
- Legend-State is used through `observe()` without its React bindings.
