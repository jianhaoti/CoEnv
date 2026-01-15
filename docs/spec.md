# CoEnv Technical Specification (v1.0)

## 1. Lexer Architecture (`core/lexer.py`)
- **Constraint:** Must use a Token-stream approach. 
- **Tokens:** `Comment`, `BlankLine`, `KeyValue`, `ExportPrefix`.
- **Requirement:** `write(parse(file))` must produce a byte-identical output to the source if no modifications are made.

## 2. Inference & Placeholders (`core/inference.py`)
- **Secrets:** Entropy check (>4.5) or prefix match (sk_, vault_, etc.).
- **Encrypted:** Recognize `encrypted:`, `sops:`, `ENC[`. 
- **Placeholders:** Generate `<your_key_name>` for secrets and `<your_key_name_encrypted>` for encrypted values.

## 3. Sync Logic (`core/syncer.py`)
- **Fuzzy Matching:** Use `difflib.SequenceMatcher` (ratio > 0.8) to detect renames.
- **Sticky Values:** Never overwrite a manually edited value in `.env.example`.
- **The Graveyard:** Append stale keys to a `# === DEPRECATED ===` section with `# Removed on: YYYY-MM-DD`. Auto-delete after 14 days.

## 4. Metadata & Reporting
- **Ownership:** On every `.env` save, capture `git config user.name` and update `metadata.json`.
- **Friday Pulse:** Calculate syncs/saves for the week. Display a summary via `rich` on the first command run on or after Friday.
- **Telemetry:** Spawns a detached background process to send anonymous JSON packets. No latency allowed in the main CLI thread.

## 5. MCP Server (`mcp.py`)
- Implement MCP spec to expose `get_status`, `trigger_sync`, and `run_doctor` as tools for AI agents.
