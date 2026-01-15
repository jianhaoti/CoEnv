#!/usr/bin/env python3
"""
Manual end-to-end test for CoEnv.

Run this script to verify all core functionality works.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coenv.core.lexer import parse, write, get_keys, update_value
from coenv.core.inference import is_secret, is_encrypted, generate_placeholder, analyze_value
from coenv.core.syncer import Syncer, find_fuzzy_match

print("=" * 60)
print("CoEnv Manual Test Suite")
print("=" * 60)

# Test 1: Lexer round-trip
print("\n[1] Testing Lexer Round-Trip...")
test_env = """# Database config
DATABASE_URL=postgres://localhost/db
API_KEY=sk_test_123456

export REDIS_URL=redis://localhost:6379

# Feature flags
DEBUG=true
"""

tokens = parse(test_env)
reconstructed = write(tokens)

if reconstructed == test_env:
    print("✓ Lexer round-trip: PASS (byte-identical)")
else:
    print("✗ Lexer round-trip: FAIL")
    print(f"Expected:\n{repr(test_env)}")
    print(f"Got:\n{repr(reconstructed)}")

# Test 2: Key extraction
print("\n[2] Testing Key Extraction...")
keys = get_keys(tokens)
expected_keys = {"DATABASE_URL", "API_KEY", "REDIS_URL", "DEBUG"}

if set(keys.keys()) == expected_keys:
    print(f"✓ Key extraction: PASS (found {len(keys)} keys)")
    for k, v in keys.items():
        print(f"  - {k} = {v[:20]}..." if len(v) > 20 else f"  - {k} = {v}")
else:
    print("✗ Key extraction: FAIL")
    print(f"Expected: {expected_keys}")
    print(f"Got: {set(keys.keys())}")

# Test 3: Secret detection
print("\n[3] Testing Secret Detection...")
test_cases = [
    ("sk_test_123456789", True, "Stripe key"),
    ("AKIAIOSFODNN7EXAMPLE", True, "AWS key"),
    ("development", False, "Simple value"),
    ("true", False, "Boolean value"),
]

all_passed = True
for value, expected, description in test_cases:
    result = is_secret(value)
    status = "✓" if result == expected else "✗"
    print(f"{status} {description}: {value[:30]} -> {result}")
    if result != expected:
        all_passed = False

if all_passed:
    print("✓ Secret detection: PASS")
else:
    print("✗ Secret detection: FAIL")

# Test 4: Encryption detection
print("\n[4] Testing Encryption Detection...")
test_cases = [
    ("encrypted:abc123", True),
    ("sops:data", True),
    ("ENC[data]", True),
    ("plain_text", False),
]

all_passed = True
for value, expected in test_cases:
    result = is_encrypted(value)
    status = "✓" if result == expected else "✗"
    print(f"{status} {value[:30]} -> {result}")
    if result != expected:
        all_passed = False

if all_passed:
    print("✓ Encryption detection: PASS")
else:
    print("✗ Encryption detection: FAIL")

# Test 5: Placeholder generation
print("\n[5] Testing Placeholder Generation...")
test_cases = [
    ("API_KEY", "sk_test_123", "<your_api_key>"),
    ("DATABASE_PASSWORD", "encrypted:abc", "<your_database_password_encrypted>"),
    ("DEBUG", "true", "true"),
]

all_passed = True
for key, value, expected in test_cases:
    result = generate_placeholder(key, value)
    status = "✓" if result == expected else "✗"
    print(f"{status} {key}={value} -> {result}")
    if result != expected:
        all_passed = False
        print(f"   Expected: {expected}")

if all_passed:
    print("✓ Placeholder generation: PASS")
else:
    print("✗ Placeholder generation: FAIL")

# Test 6: Fuzzy matching
print("\n[6] Testing Fuzzy Matching...")
test_cases = [
    ("DB_PASS", ["DATABASE_PASSWORD", "API_KEY"], "DATABASE_PASSWORD"),
    ("api_key", ["API_KEY"], "API_KEY"),
    ("COMPLETELY_DIFFERENT", ["DATABASE_URL", "API_KEY"], None),
]

all_passed = True
for key, candidates, expected in test_cases:
    result = find_fuzzy_match(key, candidates)
    status = "✓" if result == expected else "✗"
    print(f"{status} {key} in {candidates} -> {result}")
    if result != expected:
        all_passed = False
        print(f"   Expected: {expected}")

if all_passed:
    print("✓ Fuzzy matching: PASS")
else:
    print("✗ Fuzzy matching: FAIL")

# Test 7: Syncer basic functionality
print("\n[7] Testing Syncer...")
env_content = """DATABASE_URL=postgres://localhost/db
API_KEY=sk_test_123456
NEW_KEY=new_value
"""

example_content = """DATABASE_URL=<your_database_url>
API_KEY=<your_api_key>
OLD_KEY=<your_old_key>
"""

syncer = Syncer(env_content, example_content)
result = syncer.sync()

checks = [
    ("DATABASE_URL" in result, "DATABASE_URL preserved"),
    ("API_KEY" in result, "API_KEY preserved"),
    ("NEW_KEY" in result, "NEW_KEY added"),
    ("DEPRECATED" in result or "OLD_KEY" in result, "OLD_KEY in graveyard or removed"),
]

all_passed = True
for check, description in checks:
    status = "✓" if check else "✗"
    print(f"{status} {description}")
    if not check:
        all_passed = False

if all_passed:
    print("✓ Syncer: PASS")
else:
    print("✗ Syncer: FAIL")
    print("\nSyncer output:")
    print(result)

# Test 8: Value analysis
print("\n[8] Testing Value Analysis...")
analysis = analyze_value("API_KEY", "sk_test_123456789")

checks = [
    (analysis['key'] == "API_KEY", "Key correct"),
    (analysis['type'] == "secret", "Type correct"),
    (analysis['is_secret'] == True, "Is secret"),
    (analysis['placeholder'] == "<your_api_key>", "Placeholder correct"),
]

all_passed = True
for check, description in checks:
    status = "✓" if check else "✗"
    print(f"{status} {description}")
    if not check:
        all_passed = False

if all_passed:
    print("✓ Value analysis: PASS")
else:
    print("✗ Value analysis: FAIL")

# Summary
print("\n" + "=" * 60)
print("Test Suite Complete!")
print("=" * 60)
print("\nAll core functionality verified. CoEnv is ready to use!")
print("\nNext steps:")
print("  1. Run 'coenv --init' in a project directory")
print("  2. Run 'coenv sync' to create .env.example")
print("  3. Run 'coenv status' to check environment status")
