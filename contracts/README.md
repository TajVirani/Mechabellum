# Data contracts

`match-snapshot/v1/schema.json` defines `MatchSnapshot v1`, shared by collection, persistence, training, and inference. `battle-start.example.json` is a complete example that passes validation against this schema.

The contract version is in the path and in the document field `schemaVersion`. Existing field semantics stay stable within a major version; incompatible structural or semantic changes use a new version directory.

Each line of a JSONL dataset holds one complete snapshot, encoded as UTF-8. Both read and write entry points validate the persisted representation against the schema in this directory and construct strongly typed models for use within the package.
