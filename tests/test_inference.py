"""
Tests for the inference module (secret and encryption detection).
"""

import pytest
from coenv.core.inference import (
    calculate_entropy,
    is_secret,
    is_encrypted,
    generate_placeholder,
    infer_type,
    analyze_value,
)


class TestEntropy:
    """Test Shannon entropy calculation."""

    def test_entropy_empty_string(self):
        """Empty string should have 0 entropy."""
        assert calculate_entropy("") == 0.0

    def test_entropy_single_char(self):
        """Single repeated character should have low entropy."""
        assert calculate_entropy("aaaa") == 0.0

    def test_entropy_random_string(self):
        """Random-looking string should have high entropy."""
        # A typical API key
        entropy = calculate_entropy("abc123XYZ789QWErty456ASDfgh")
        assert entropy > 4.0

    def test_entropy_low_randomness(self):
        """Simple words should have lower entropy."""
        entropy = calculate_entropy("development")
        assert entropy < 4.0


class TestSecretDetection:
    """Test secret detection logic."""

    def test_is_secret_high_entropy(self):
        """High entropy strings should be detected as secrets."""
        # Realistic API key
        assert is_secret("sk_test_51HqK2xJ3yF8gD9nP2mL4vR5wN8sT6uB9vC2eD4fG7hK8jL1m")

    def test_is_secret_stripe_prefix(self):
        """Stripe keys should be detected."""
        assert is_secret("sk_test_123")
        assert is_secret("pk_live_456")

    def test_is_secret_aws_prefix(self):
        """AWS keys should be detected."""
        assert is_secret("AKIAIOSFODNN7EXAMPLE")

    def test_is_secret_github_prefix(self):
        """GitHub tokens should be detected."""
        assert is_secret("ghp_1234567890abcdef")
        assert is_secret("gho_1234567890abcdef")
        assert is_secret("ghs_1234567890abcdef")

    def test_is_secret_vault_prefix(self):
        """HashiCorp Vault references should be detected."""
        assert is_secret("vault:secret/data/myapp")

    def test_not_secret_simple_value(self):
        """Simple config values should not be secrets."""
        assert not is_secret("development")
        assert not is_secret("true")
        assert not is_secret("3000")
        assert not is_secret("localhost")

    def test_not_secret_empty(self):
        """Empty strings should not be secrets."""
        assert not is_secret("")


class TestEncryptionDetection:
    """Test encryption detection logic."""

    def test_is_encrypted_with_prefix(self):
        """Common encryption prefixes should be detected."""
        assert is_encrypted("encrypted:AES256:base64data")
        assert is_encrypted("sops:ENC[...]")
        assert is_encrypted("ENC[AES256,data:base64...]")
        assert is_encrypted("vault:v1:encrypted_data")
        assert is_encrypted("age:encrypted_data")

    def test_is_encrypted_enc_brackets(self):
        """ENC[...] format should be detected."""
        assert is_encrypted("ENC[AES256,data:abc123,iv:def456,tag:ghi789]")

    def test_not_encrypted_plain_text(self):
        """Plain text should not be detected as encrypted."""
        assert not is_encrypted("my_secret_value")
        assert not is_encrypted("development")

    def test_not_encrypted_empty(self):
        """Empty strings should not be encrypted."""
        assert not is_encrypted("")


class TestPlaceholderGeneration:
    """Test placeholder generation."""

    def test_placeholder_for_secret(self):
        """Secrets should get standard placeholder."""
        placeholder = generate_placeholder("API_KEY", "sk_test_12345")
        assert placeholder == "<your_api_key>"

    def test_placeholder_for_encrypted(self):
        """Encrypted values should get _encrypted suffix."""
        placeholder = generate_placeholder("DATABASE_PASSWORD", "encrypted:abc123")
        assert placeholder == "<your_database_password_encrypted>"

    def test_placeholder_for_simple_value(self):
        """Simple values might be exposed as-is."""
        placeholder = generate_placeholder("DEBUG", "true")
        assert placeholder == "true"

    def test_placeholder_for_env_name(self):
        """Environment names should be exposed."""
        placeholder = generate_placeholder("NODE_ENV", "development")
        assert placeholder == "development"

    def test_placeholder_conservative_for_urls(self):
        """URLs should get placeholders for safety."""
        placeholder = generate_placeholder("DATABASE_URL", "postgres://localhost/db")
        assert placeholder == "<your_database_url>"

    def test_placeholder_lowercase_key(self):
        """Key should be lowercased in placeholder."""
        placeholder = generate_placeholder("MY_API_KEY", "sk_test_123")
        assert placeholder == "<your_my_api_key>"


class TestTypeInference:
    """Test value type inference."""

    def test_infer_encrypted(self):
        """Encrypted values should be identified."""
        assert infer_type("encrypted:abc123") == "encrypted"
        assert infer_type("sops:data") == "encrypted"

    def test_infer_secret(self):
        """Secrets should be identified."""
        assert infer_type("sk_test_123456789") == "secret"
        assert infer_type("AKIAIOSFODNN7EXAMPLE") == "secret"

    def test_infer_value(self):
        """Regular values should be identified."""
        assert infer_type("development") == "value"
        assert infer_type("true") == "value"
        assert infer_type("3000") == "value"


class TestAnalyzeValue:
    """Test complete value analysis."""

    def test_analyze_secret(self):
        """Analyzing a secret should return complete info."""
        result = analyze_value("API_KEY", "sk_test_123456789")

        assert result['key'] == "API_KEY"
        assert result['type'] == "secret"
        assert result['is_secret'] is True
        assert result['is_encrypted'] is False
        assert result['placeholder'] == "<your_api_key>"
        assert 'entropy' in result

    def test_analyze_encrypted(self):
        """Analyzing encrypted value should return complete info."""
        result = analyze_value("PASSWORD", "encrypted:abc123")

        assert result['key'] == "PASSWORD"
        assert result['type'] == "encrypted"
        assert result['is_secret'] is True
        assert result['is_encrypted'] is True
        assert result['placeholder'] == "<your_password_encrypted>"

    def test_analyze_regular_value(self):
        """Analyzing regular value should return complete info."""
        result = analyze_value("DEBUG", "true")

        assert result['key'] == "DEBUG"
        assert result['type'] == "value"
        assert result['is_secret'] is False
        assert result['is_encrypted'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
