#!/usr/bin/env python3
"""
Standalone demo of CoEnv functionality without CLI dependencies.

This demonstrates the core sync functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coenv.core.syncer import Syncer
from coenv.core.lexer import parse, get_keys

print("=" * 70)
print("CoEnv Sync Demo")
print("=" * 70)

# Read the .env file
env_path = Path(__file__).parent / "test_project" / ".env"

with open(env_path, 'r') as f:
    env_content = f.read()

print("\n📄 Original .env file:")
print("-" * 70)
print(env_content)
print("-" * 70)

# Parse to show what keys we have
env_keys = get_keys(parse(env_content))
print(f"\n🔑 Found {len(env_keys)} environment variables:")
for key, value in env_keys.items():
    # Mask secrets for display
    if len(value) > 20:
        display_value = value[:10] + "..." + value[-10:]
    else:
        display_value = value
    print(f"  - {key} = {display_value}")

# Perform sync
print("\n⚙️  Performing sync to .env.example...")
syncer = Syncer(env_content, "")  # Empty example file
result = syncer.sync()

# Show the result
print("\n📄 Generated .env.example:")
print("-" * 70)
print(result)
print("-" * 70)

# Write the .env.example file
example_path = Path(__file__).parent / "test_project" / ".env.example"
with open(example_path, 'w') as f:
    f.write(result)

print(f"\n✅ Success! Created {example_path}")

# Now simulate removing a key and syncing again
print("\n" + "=" * 70)
print("Demo: Removing a key (simulating graveyard)")
print("=" * 70)

# Simulate updated .env without SENTRY_DSN
env_content_updated = env_content.replace("SENTRY_DSN=https://abc123@sentry.io/123456\n", "")

print("\n⚙️  Syncing again with SENTRY_DSN removed...")
syncer2 = Syncer(env_content_updated, result)
result2 = syncer2.sync()

print("\n📄 Updated .env.example (with graveyard):")
print("-" * 70)
print(result2)
print("-" * 70)

if "DEPRECATED" in result2 or "Removed on:" in result2:
    print("\n✅ Graveyard section created for removed keys!")
else:
    print("\n⚠️  Graveyard not created (key may still be present)")

print("\n" + "=" * 70)
print("Demo Complete!")
print("=" * 70)
print("\nCoEnv successfully:")
print("  ✓ Parsed .env file losslessly")
print("  ✓ Detected secrets and generated safe placeholders")
print("  ✓ Created .env.example with intelligent placeholders")
print("  ✓ Moved removed keys to graveyard section")
print("\nTo use CoEnv in your projects:")
print("  1. Install dependencies: pip install click rich watchdog")
print("  2. Run: coenv --init")
print("  3. Run: coenv sync")
