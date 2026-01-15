# CoEnv Usage Guide

Complete guide to using CoEnv in your projects.

## Installation

```bash
pip install coenv
```

## Quick Start

### 1. Initialize CoEnv in Your Project

```bash
cd your-project
coenv --init
```

This will:
- Create `.coenv/` directory for metadata
- Install git hooks (pre-commit, post-merge, post-rewrite)
- Add `.env` to `.gitignore`

### 2. Create Your .env File

```bash
# .env
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
STRIPE_SECRET_KEY=sk_test_51HqK2xJ3yF8gD9nP...
API_KEY=your_secret_api_key
DEBUG=true
```

### 3. Commit to Generate .env.example

```bash
git commit -m "chore: bootstrap env docs"
```

This generates `.env.example` via the pre-commit hook with safe placeholders:

```bash
# .env.example
DATABASE_URL=<your_database_url>
STRIPE_SECRET_KEY=<your_stripe_secret_key>
API_KEY=<your_api_key>
DEBUG=true
```

**Note:** `.env.example` is auto-generated on commit and should be treated as read-only.

## Commands

### `coenv status`

Show environment variable status table with:
- Key name
- Repo status (synced/missing)
- Health (set/empty)
- Owner (per-key blame from your local .env.example)

```bash
$ coenv status

Environment Variable Status
┌─────────────────┬─────────────┬──────────┬────────────┐
│ Key             │ Repo Status │ Health   │ Owner      │
├─────────────────┼─────────────┼──────────┼────────────┤
│ DATABASE_URL    │ ✓ Synced    │ ✓ Set    │ alice      │
│ STRIPE_KEY      │ ✗ Missing   │ ✓ Set    │ bob        │
│ DEBUG           │ ✓ Synced    │ ✓ Set    │ alice      │
└─────────────────┴─────────────┴──────────┴────────────┘
```

Note: `.env.example` is generated automatically on commit; update `.env*` files and commit to refresh it.

### `coenv exclude-file`

Exclude a file from `.env.example` generation:

```bash
$ coenv exclude-file .env.local
```

This writes a marker in `.env.example`:

```bash
# [EXCLUDE_FILE] .env.local
```

If `.env.local` exists and is not excluded, hooks will fail to prevent accidental leakage.

### Monorepos and scan cache

By default, CoEnv scans subdirectories for `.env*` files. To limit discovery to the repo root, set:

```bash
COENV_RECURSIVE=0
```

For large repos, you can enable a cached path list:

```bash
COENV_USE_SCAN_CACHE=1
```

This uses `.coenv/env_cache.json` and can miss newly added `.env*` files until the cache is refreshed (delete the file or run once without the cache).

### `coenv --init`

Initialize CoEnv in a new project. Safe to run multiple times.

### `coenv mcp`

Start the MCP (Model Context Protocol) server for AI agent integration.

## Features in Detail

### Intelligent Secret Detection

CoEnv automatically detects secrets using:
- **Entropy analysis**: High-randomness strings (entropy > 4.5)
- **Prefix matching**: `sk_`, `AKIA`, `vault:`, `ghp_`, etc.

Examples:
```bash
STRIPE_KEY=sk_test_123    → <your_stripe_key>
AWS_KEY=AKIAIOSFODNN7...  → <your_aws_key>
DEBUG=true                 → true (not a secret)
```

### Fuzzy Rename Detection

When you rename a key, CoEnv detects it using fuzzy matching:

```bash
# Before: .env
DB_PASS=secret123

# After: .env
DATABASE_PASSWORD=secret123

# Result: .env.example
DATABASE_PASSWORD=<your_database_password>  # Renamed in-place!
```

### Deprecation (Tombstones)

Removed keys are only excluded when explicitly deprecated:

```bash
coenv deprecate OLD_API_KEY
```

This adds a tombstone in `.env.example` to block resurrection:

```bash
# === DEPRECATED ===
# [TOMBSTONE] OLD_API_KEY - Deprecated on: 2026-01-14
```

Use `coenv undeprecate OLD_API_KEY` to allow it again.

### Ownership Tracking

CoEnv tracks who added each variable using Git:

```bash
$ coenv status
┌──────────────┬──────┐
│ Key          │ Owner│
├──────────────┼──────┤
│ DATABASE_URL │ alice│
│ STRIPE_KEY   │ bob  │
└──────────────┴──────┘
```

### Friday Pulse

Weekly summary of team activity:

```bash
┌─────────────────────────────────┐
│      Friday Pulse              │
├─────────────────────────────────┤
│ Week of 2026-01-10             │
│                                 │
│ Syncs: 23                      │
│ Total keys affected: 147       │
│ Active users: 3 (alice, bob, charlie) │
└─────────────────────────────────┘
```

## Git Hooks

CoEnv installs git hooks during `--init`:

### Pre-commit Hook
Automatically generates `.env.example` before each commit:

```bash
#!/bin/sh
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
coenv commit-hook
git add .env.example
```

### Post-merge Hook
Reports `.env.example` changes (with owners) and regenerates after merging:

```bash
#!/bin/sh
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
coenv merge-hook
```

This prints added/deprecated keys and their last author (from `git blame`).

### Post-rewrite Hook
Runs after rebase or amend to report changes and keep `.env.example` in sync:

```bash
#!/bin/sh
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
coenv merge-hook
```

## MCP Server for AI Agents

CoEnv includes an MCP server for Claude, Cursor, Windsurf, and other AI agents.

### Available Tools

- `get_status`: Get environment variable status

### Configuration

Add to your MCP settings (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "coenv": {
      "command": "coenv",
      "args": ["mcp"]
    }
  }
}
```

Now AI agents can manage your environment variables!

## Telemetry

CoEnv sends anonymous usage data to improve the tool. This includes:
- Command usage counts (pre-commit hook, status)
- Number of keys (not the keys themselves)
- Errors and exceptions

### Opt Out

To disable telemetry:

```bash
# Create opt-out file
touch .coenv/.no-telemetry

# Or set environment variable
export COENV_NO_TELEMETRY=1
```

## Best Practices

1. **Always commit .env.example**: This is your team's documentation
2. **Treat .env.example as generated**: Update `.env*` files and commit, do not edit by hand
3. **Never commit .env**: Keep secrets out of the repository
4. **Run `coenv status` regularly**: Check for missing or outdated keys
5. **Exclude local-only files**: Use `coenv exclude-file .env.local` if needed
6. **Review `.env.example` after pulling**: Ensure you have all required keys
7. **Review .env.example changes**: Make sure sensitive data isn't leaked

## Troubleshooting

### "No module named 'click'"

Install dependencies:
```bash
pip install click rich watchdog
```

### "Not a git repository"

Git hooks won't be installed, but CoEnv will still work. Run `git init` first if you want hooks.

### "Permission denied" on git hooks

Make hooks executable:
```bash
chmod +x .git/hooks/pre-commit .git/hooks/post-merge
```

### Merge conflict markers in .env.example

If `.env.example` contains `<<<<<<<`/`=======`/`>>>>>>>`, hooks will fail. Resolve the conflict manually, then rerun your git command.

### .env.local present but not excluded

If you see an error about `.env.local` not being excluded, run:

```bash
coenv exclude-file .env.local
```

### Fuzzy matching not working

The threshold is 0.8 (80% similarity). Very different keys won't match. Rename manually if needed.

## Advanced Usage

### Custom Project Root

```bash
coenv status --project-root /path/to/project
```

### Programmatic Usage

```python
from coenv.core.syncer import sync_files

result = sync_files('.env', '.env.example')
with open('.env.example', 'w') as f:
    f.write(result)
```

### Custom Secret Detection

```python
from coenv.core.inference import is_secret, SECRET_PREFIXES

# Add custom prefix
SECRET_PREFIXES.append('myapp_')

# Now detects: myapp_secret_key
```

## Examples

See the `demo/` directory for complete examples:

```bash
cd demo
python demo.py
```

## Support

- GitHub Issues: https://github.com/yourusername/coenv/issues
- Documentation: https://github.com/yourusername/coenv/docs
- Contributing: See CONTRIBUTING.md
