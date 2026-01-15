# 🔗 CoEnv (Collaborative Environments)

**CoEnv** is an intelligent, lossless, and ownership-aware bridge between your local `.env` and your team's `.env.example`. 

> "Stop breaking the build. The intelligent, ownership-aware bridge between your local .env and your team's .env.example."

---

## ✨ Key Features

- **Lossless Parsing:** Unlike other tools, CoEnv preserves every comment and whitespace in your files.
- **Fuzzy Renames:** Detects when you rename a key (e.g., `DB_PASS` → `DATABASE_PASSWORD`) and updates the example file in-place.
- **Ownership Tracking:** Uses Git metadata to track who added or last modified each variable. Know exactly who to ask for a secret.
- **AI-Native:** Built-in MCP (Model Context Protocol) server so Claude, Cursor, or Windsurf can manage your environment for you.
- **Deprecation:** Explicitly tombstone keys with `coenv deprecate` to prevent resurrection.
- **Excludes:** Skip local-only files (e.g., `coenv exclude-file .env.local`).

## 🚀 Quick Start

```bash
pip install coenv

# Initialize project and git hooks
coenv --init

# Make a commit to generate .env.example (pre-commit hook)
git commit -m "chore: bootstrap env docs"

# Check environment alignment
coenv status
```

Note: `.env.example` is auto-generated on commit and should be treated as read-only.
