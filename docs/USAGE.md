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
- Install git hooks (pre-commit, post-merge)
- Add `.env` to `.gitignore`

### 2. Create Your .env File

```bash
# .env
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
STRIPE_SECRET_KEY=sk_test_51HqK2xJ3yF8gD9nP...
API_KEY=your_secret_api_key
DEBUG=true
```

### 3. Sync to .env.example

```bash
coenv sync
```

This generates `.env.example` with safe placeholders:

```bash
# .env.example
DATABASE_URL=<your_database_url>
STRIPE_SECRET_KEY=<your_stripe_secret_key>
API_KEY=<your_api_key>
DEBUG=true
```

**Note:** Secrets are automatically detected and replaced with placeholders!

## Commands

### `coenv status`

Show environment variable status table with:
- Key name
- Repo status (synced/missing)
- Health (set/empty)
- Owner (who added it)

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

### `coenv sync`

Sync `.env` to `.env.example`:
- Adds new keys with intelligent placeholders
- Updates existing keys (unless manually edited)
- Detects renamed keys via fuzzy matching
- Moves removed keys to "The Graveyard"

```bash
$ coenv sync
✓ Synced 15 keys to .env.example
```

### `coenv doctor`

Add missing keys from `.env.example` to `.env`:

```bash
$ coenv doctor
Found 3 missing keys in .env
  + NEW_API_KEY
  + FEATURE_FLAG
  + REDIS_URL

✓ Added 3 keys to .env
⚠ Please update the placeholder values with actual values
```

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

### The Graveyard

Removed keys are moved to a deprecated section:

```bash
# === DEPRECATED ===
# OLD_API_KEY - Removed on: 2026-01-14
# LEGACY_DB_URL - Removed on: 2026-01-10
```

Entries are automatically deleted after 14 days.

### Sticky Values

Manual edits in `.env.example` are preserved:

```bash
# .env.example (manually edited)
API_ENDPOINT=https://api.production.com  # Custom documentation

# After sync: Value is preserved!
API_ENDPOINT=https://api.production.com  # Still there
```

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
│ Doctor runs: 5                 │
│ Total keys affected: 147       │
│ Active users: 3 (alice, bob, charlie) │
└─────────────────────────────────┘
```

## Git Hooks

CoEnv installs git hooks during `--init`:

### Pre-commit Hook
Automatically syncs `.env` to `.env.example` before each commit:

```bash
#!/bin/sh
coenv sync
git add .env.example
```

### Post-merge Hook
Runs `coenv doctor` after merging to add missing keys:

```bash
#!/bin/sh
coenv doctor
```

## MCP Server for AI Agents

CoEnv includes an MCP server for Claude, Cursor, Windsurf, and other AI agents.

### Available Tools

- `get_status`: Get environment variable status
- `trigger_sync`: Sync .env to .env.example
- `run_doctor`: Add missing keys from .env.example

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
- Command usage counts (sync, status, doctor)
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
2. **Never commit .env**: Keep secrets out of the repository
3. **Run `coenv status` regularly**: Check for missing or outdated keys
4. **Use `coenv doctor` after pulling**: Ensure you have all required keys
5. **Review .env.example changes**: Make sure sensitive data isn't leaked

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

### Fuzzy matching not working

The threshold is 0.8 (80% similarity). Very different keys won't match. Rename manually if needed.

## Advanced Usage

### Custom Project Root

```bash
coenv sync --project-root /path/to/project
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
