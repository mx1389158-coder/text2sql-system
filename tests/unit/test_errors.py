from packages.execution.errors import ErrorCategory, classify_database_error


def test_error_classifier_redacts_sensitive_values():
    classified = classify_database_error(Exception("connection failed password=topsecret"))
    assert classified.category == ErrorCategory.CONNECTION
    assert "topsecret" not in classified.safe_message
    assert "[REDACTED]" in classified.safe_message
