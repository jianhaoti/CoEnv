"""
Secret and encryption detection for .env values.

This module infers whether a value is:
- A secret (high entropy or sensitive prefix)
- An encrypted value (recognized encryption formats)
- A regular value (safe to expose as placeholder)
"""

import math
from typing import Tuple


# Sensitive prefixes that indicate secrets
SECRET_PREFIXES = [
    'sk_',      # Stripe, OpenAI, etc.
    'pk_',      # Public keys (still sensitive in some contexts)
    'AKIA',     # AWS Access Key ID
    'vault:',   # HashiCorp Vault
    'arn:aws:', # AWS ARN
    'ghp_',     # GitHub Personal Access Token
    'gho_',     # GitHub OAuth Token
    'ghs_',     # GitHub Server-to-Server Token
    'key_',     # Generic key prefix
    'token_',   # Generic token prefix
    'secret_',  # Generic secret prefix
]

# Encryption format prefixes
ENCRYPTED_PREFIXES = [
    'encrypted:',
    'sops:',
    'ENC[',
    'vault:',  # Also encryption
    'age:',    # age encryption
]


def calculate_entropy(value: str) -> float:
    """
    Calculate Shannon entropy of a string.

    Args:
        value: String to analyze

    Returns:
        Entropy value (bits per character)
    """
    if not value:
        return 0.0

    # Count frequency of each character
    freq = {}
    for char in value:
        freq[char] = freq.get(char, 0) + 1

    # Calculate entropy
    entropy = 0.0
    length = len(value)

    for count in freq.values():
        probability = count / length
        if probability > 0:
            entropy -= probability * math.log2(probability)

    return entropy


def is_secret(value: str) -> bool:
    """
    Determine if a value is likely a secret.

    A value is considered a secret if:
    - Entropy > 4.5 (high randomness)
    - Starts with a known secret prefix

    Args:
        value: Value to check

    Returns:
        True if likely a secret
    """
    if not value:
        return False

    # Check entropy
    entropy = calculate_entropy(value)
    if entropy > 4.5:
        return True

    # Check prefixes
    for prefix in SECRET_PREFIXES:
        if value.startswith(prefix):
            return True

    return False


def is_encrypted(value: str) -> bool:
    """
    Determine if a value is encrypted.

    Args:
        value: Value to check

    Returns:
        True if value appears to be encrypted
    """
    if not value:
        return False

    for prefix in ENCRYPTED_PREFIXES:
        if value.startswith(prefix):
            return True

    # Check for common encryption patterns
    if value.startswith('ENC[') and value.endswith(']'):
        return True

    return False


def generate_placeholder(key: str, value: str) -> str:
    """
    Generate an appropriate placeholder for a key-value pair.

    Args:
        key: Environment variable key
        value: Current value

    Returns:
        Placeholder string
    """
    # Convert key to lowercase for placeholder
    key_lower = key.lower()

    # Check if encrypted
    if is_encrypted(value):
        return f"<your_{key_lower}_encrypted>"

    # Check if secret
    if is_secret(value):
        return f"<your_{key_lower}>"

    # Regular value - could expose as-is, but be conservative
    # Check if it looks like a simple config value
    if value and len(value) < 50 and not any(char in value for char in ['/', ':', '@', '.']):
        # Probably a simple config value like "development" or "true"
        return value

    # Default to placeholder for safety
    return f"<your_{key_lower}>"


def infer_type(value: str) -> str:
    """
    Infer the type of value.

    Args:
        value: Value to analyze

    Returns:
        One of: "encrypted", "secret", "value"
    """
    if is_encrypted(value):
        return "encrypted"
    elif is_secret(value):
        return "secret"
    else:
        return "value"


def analyze_value(key: str, value: str) -> dict:
    """
    Perform complete analysis of a key-value pair.

    Args:
        key: Environment variable key
        value: Current value

    Returns:
        Dictionary with analysis results
    """
    value_type = infer_type(value)
    entropy = calculate_entropy(value)
    placeholder = generate_placeholder(key, value)

    return {
        'key': key,
        'type': value_type,
        'entropy': entropy,
        'placeholder': placeholder,
        'is_secret': value_type in ('secret', 'encrypted'),
        'is_encrypted': value_type == 'encrypted',
    }
