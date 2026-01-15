# 🔗 CoEnv (Collaborative Environments)

**CoEnv** is an intelligent, lossless, and ownership-aware bridge between your local `.env` and your team's `.env.example`. 

> "Stop breaking the build. The intelligent, ownership-aware bridge between your local .env and your team's .env.example."

---

## ✨ Key Features

- **Lossless Parsing:** Unlike other tools, CoEnv preserves every comment and whitespace in your files.
- **Fuzzy Renames:** Detects when you rename a key (e.g., `DB_PASS` → `DATABASE_PASSWORD`) and updates the example file in-place.
- **Ownership Tracking:** Uses Git metadata to track who added or last modified each variable. Know exactly who to ask for a secret.
- **AI-Native:** Built-in MCP (Model Context Protocol) server so Claude, Cursor, or Windsurf can manage your environment for you.
- **The Graveyard:** Automatically moves stale keys to a deprecated section and prunes them after 14 days.

## 🚀 Quick Start

```bash
pip install coenv

# Initialize project and git hooks
coenv --init

# Start the background watcher
coenv --watch

# Check environment alignment
coenv status
