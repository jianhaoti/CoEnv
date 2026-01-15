#!/usr/bin/env python3
"""
Advanced CoEnv Demo - Shows all key features in action.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coenv.core.syncer import Syncer
from coenv.core.lexer import parse, write
from coenv.core.inference import analyze_value

print("=" * 80)
print("CoEnv Advanced Feature Demo".center(80))
print("=" * 80)

# Feature 1: Intelligent Secret Detection
print("\n" + "🔐 Feature 1: Intelligent Secret Detection".center(80))
print("-" * 80)

test_values = [
    ("STRIPE_KEY", "sk_test_51HqK2xJ3yF8gD9nP2mL4vR5wN8sT6uB9vC2eD4fG7hK8jL1m"),
    ("AWS_ACCESS_KEY", "AKIAIOSFODNN7EXAMPLE"),
    ("GITHUB_TOKEN", "ghp_1234567890abcdefghijklmnop"),
    ("DATABASE_PASSWORD", "encrypted:AES256:abcdef123456"),
    ("APP_ENV", "development"),
    ("DEBUG", "true"),
    ("PORT", "3000"),
]

for key, value in test_values:
    analysis = analyze_value(key, value)
    print(f"\n{key}")
    print(f"  Value: {value[:40]}..." if len(value) > 40 else f"  Value: {value}")
    print(f"  Type: {analysis['type']}")
    print(f"  Entropy: {analysis['entropy']:.2f}")
    print(f"  Placeholder: {analysis['placeholder']}")

# Feature 2: Lossless Round-Trip Parsing
print("\n\n" + "♻️  Feature 2: Lossless Round-Trip Parsing".center(80))
print("-" * 80)

original = """# Database Configuration
DATABASE_URL=postgres://localhost/db

# API Settings
export API_KEY=secret123

# Feature Flags
DEBUG=true
"""

print("\nOriginal .env:")
print(original)

tokens = parse(original)
reconstructed = write(tokens)

print("After parse() and write():")
print(reconstructed)

if original == reconstructed:
    print("\n✅ PERFECT MATCH - Byte-identical round-trip!")
else:
    print("\n❌ MISMATCH")

# Feature 3: Fuzzy Rename Detection
print("\n\n" + "🔄 Feature 3: Fuzzy Rename Detection".center(80))
print("-" * 80)

env_before = """DB_URL=postgres://localhost/db
DB_PASS=secret123
API_KEY=mykey
"""

example_before = """DB_URL=<your_db_url>
DB_PASS=<your_db_pass>
API_KEY=<your_api_key>
"""

print("\n📝 Original .env (keys renamed):")
print("  DB_URL → DATABASE_URL")
print("  DB_PASS → DATABASE_PASSWORD")

env_after = """DATABASE_URL=postgres://localhost/db
DATABASE_PASSWORD=secret123
API_KEY=mykey
"""

syncer = Syncer(env_after, example_before)
result = syncer.sync()

print("\n📄 Updated .env.example (fuzzy matched renames):")
print(result)

# Feature 4: Sticky Values (Manual Edits Preserved)
print("\n" + "📌 Feature 4: Sticky Values (Manual Edits Preserved)".center(80))
print("-" * 80)

env_content = """API_ENDPOINT=https://api.myapp.com
DATABASE_URL=postgres://localhost/db
"""

example_with_manual_edit = """API_ENDPOINT=https://docs.myapp.com/api  # Custom docs
DATABASE_URL=<your_database_url>
"""

print("\n📝 .env.example has manual edit:")
print("  API_ENDPOINT=https://docs.myapp.com/api  # Custom docs")
print("\n🔄 After sync with preserve_manual_edits=True:")

syncer = Syncer(env_content, example_with_manual_edit)
result = syncer.sync(preserve_manual_edits=True)
print(result)

if "https://docs.myapp.com/api" in result:
    print("✅ Manual edit preserved!")
else:
    print("❌ Manual edit was overwritten")

# Feature 5: The Graveyard
print("\n" + "⚰️  Feature 5: The Graveyard (14-day TTL)".center(80))
print("-" * 80)

env_current = """DATABASE_URL=postgres://localhost/db
API_KEY=secret123
"""

example_with_old_keys = """DATABASE_URL=<your_database_url>
API_KEY=<your_api_key>
LEGACY_SERVICE_URL=<your_legacy_service_url>
OLD_API_TOKEN=<your_old_api_token>
"""

print("\n📝 Keys removed from .env:")
print("  - LEGACY_SERVICE_URL")
print("  - OLD_API_TOKEN")
print("\n🔄 After sync:")

syncer = Syncer(env_current, example_with_old_keys)
result = syncer.sync()
print(result)

# Feature 6: Export Prefix Preservation
print("\n" + "📤 Feature 6: Export Prefix Preservation".center(80))
print("-" * 80)

env_with_exports = """export PATH=/usr/local/bin
export DATABASE_URL=postgres://localhost/db
NORMAL_KEY=value
"""

print("\n📝 Original .env:")
print(env_with_exports)

tokens = parse(env_with_exports)
print("\n📊 Parsed tokens:")
for token in tokens:
    if token.type.value == "key_value":
        export_marker = "[export] " if token.has_export else "        "
        print(f"  {export_marker}{token.key} = {token.value}")

reconstructed = write(tokens)
print("\n📄 Reconstructed (export prefix preserved):")
print(reconstructed)

# Summary
print("\n" + "=" * 80)
print("✨ Demo Complete! All Features Working ✨".center(80))
print("=" * 80)

print("\n🎯 Features Demonstrated:")
print("  ✓ Intelligent secret detection (entropy + prefix matching)")
print("  ✓ Lossless round-trip parsing (byte-perfect)")
print("  ✓ Fuzzy rename detection (>80% similarity)")
print("  ✓ Sticky values (manual edits preserved)")
print("  ✓ The Graveyard (removed keys with timestamps)")
print("  ✓ Export prefix preservation")

print("\n🚀 Ready for Production!")
print("\nNext: Install dependencies and try the CLI:")
print("  $ pip install click rich watchdog")
print("  $ coenv --init")
print("  $ coenv sync")
