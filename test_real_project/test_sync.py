#!/usr/bin/env python3
"""
Test CoEnv on a real project .env file.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coenv.core.syncer import sync_files
from coenv.core.lexer import parse, get_keys

print("=" * 80)
print("Testing CoEnv on Real Project".center(80))
print("=" * 80)

# Test sync
env_path = Path(__file__).parent / ".env"
example_path = Path(__file__).parent / ".env.example"

print(f"\n📄 Reading: {env_path}")
with open(env_path, 'r') as f:
    env_content = f.read()

# Show what we have
env_keys = get_keys(parse(env_content))
print(f"✓ Found {len(env_keys)} environment variables\n")

# Perform sync
print("⚙️  Syncing to .env.example...")
result = sync_files(str(env_path), str(example_path))

# Write result
with open(example_path, 'w') as f:
    f.write(result)

print(f"✓ Created: {example_path}\n")

# Show the result
print("=" * 80)
print("Generated .env.example:".center(80))
print("=" * 80)
print(result)

# Analyze what was done
print("=" * 80)
print("Analysis:".center(80))
print("=" * 80)

example_keys = get_keys(parse(result))

secrets_replaced = []
values_kept = []

for key in sorted(env_keys.keys()):
    env_val = env_keys[key]
    example_val = example_keys.get(key, "")

    if example_val.startswith("<your_"):
        secrets_replaced.append((key, env_val[:30]))
    else:
        values_kept.append((key, example_val))

print(f"\n🔐 Secrets detected and replaced: {len(secrets_replaced)}")
for key, val in secrets_replaced:
    print(f"  • {key}: {val}... → <your_{key.lower()}>")

print(f"\n✓ Simple values kept as-is: {len(values_kept)}")
for key, val in values_kept[:5]:  # Show first 5
    print(f"  • {key}: {val}")
if len(values_kept) > 5:
    print(f"  ... and {len(values_kept) - 5} more")

print("\n" + "=" * 80)
print("✅ SUCCESS - Ready to commit .env.example!".center(80))
print("=" * 80)
print("\nNext steps:")
print("  1. Review .env.example to ensure no secrets leaked")
print("  2. git add .env.example")
print("  3. git commit -m 'Add .env.example with CoEnv'")
print("  4. Make sure .env is in .gitignore!")
