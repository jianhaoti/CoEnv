# CoEnv Technical Specification (v1.0)

## 1. Lexer Architecture (`core/lexer.py`)
- **Constraint:** Must use a Token-stream approach. 
- **Tokens:** `Comment`, `BlankLine`, `KeyValue`, `ExportPrefix`.
- **Requirement:** `write(parse(file))` must produce a byte-identical output to the source if no modifications are made.

## 2. Inference & Placeholders (`core/inference.py`)
- **Secrets:** Entropy check (>4.5) or prefix match (sk_, vault_, etc.).
- **Encrypted:** Recognize `encrypted:`, `sops:`, `ENC[`. 
- **Placeholders:** Generate `<your_key_name>` for secrets and `<your_key_name_encrypted>` for encrypted values.

## 3. Commit-Hook Generation (`core/syncer.py`)
- **Run Mode:** `.env.example` is generated via the git pre-commit hook; there is no user-facing sync command.
- **Fuzzy Matching:** Use `difflib.SequenceMatcher` (ratio > 0.8) to detect renames.
- **Derived Output:** Manual edits in `.env.example` are overwritten on commit; treat it as generated.
- **Union Behavior:** Existing `.env.example` keys are preserved unless explicitly deprecated.
- **Deprecation:** Use `coenv deprecate` to add tombstones (`# [TOMBSTONE] KEY - Deprecated on: YYYY-MM-DD`) and block resurrection.
- **Excludes:** Use `coenv exclude-file` to add `# [EXCLUDE_FILE] filename` markers that skip files during aggregation.
- **Idempotent Output:** Duplicate keys in `.env.example` collapse to a single entry.
- **Safety Checks:** Hooks fail if `.env.example` contains merge conflict markers or if `.env.local` exists without an exclude marker.
- **Discovery:** `.env*` files are discovered recursively (monorepo support) unless `COENV_RECURSIVE=0`.
- **Scan Cache:** Set `COENV_USE_SCAN_CACHE=1` to use `.coenv/env_cache.json` for faster scans (may miss newly added env files until refreshed).

## 4. Metadata & Reporting
- **Ownership:** On every `.env` save, capture `git config user.name` and update `metadata.json`.
- **Friday Pulse:** Calculate syncs/saves for the week. Display a summary via `rich` on the first command run on or after Friday.
- **Telemetry:** Spawns a detached background process to send anonymous JSON packets. No latency allowed in the main CLI thread.

## 5. MCP Server (`mcp_server.py`)
- Implement MCP spec to expose `get_status` as a tool for AI agents.

## 6. Hooks
- **Pre-commit:** Runs `coenv commit-hook` and stages `.env.example`.
- **Post-merge/post-rewrite:** Runs `coenv merge-hook` to report changes and re-derive `.env.example`.
