from packages.execution.errors import ErrorCategory, classify_database_error


def test_error_classifier_redacts_sensitive_values():
    classified = classify_database_error(Exception("connection failed password=topsecret"))
    assert classified.category == ErrorCategory.CONNECTION
    assert "topsecret" not in classified.safe_message
    assert "[REDACTED]" in classified.safe_message


def test_connection_timeout_is_not_repairable_sql_error():
    classified = classify_database_error(Exception("connection timeout expired"))

    assert classified.category == ErrorCategory.CONNECTION
    assert classified.repairable is False


def test_statement_timeout_remains_repairable():
    classified = classify_database_error(Exception("canceling statement due to statement timeout"))

    assert classified.category == ErrorCategory.TIMEOUT
    assert classified.repairable is True
