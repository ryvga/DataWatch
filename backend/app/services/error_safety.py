"""Stable public error messages that never echo connector/credential details."""

from __future__ import annotations


def safe_connection_error(error: Exception) -> str:
    """Classify common connection failures without returning the driver message."""
    message = str(error).lower()
    if any(
        phrase in message
        for phrase in (
            "name or service not known",
            "could not connect",
            "connection refused",
            "nodename nor servname",
            "temporary failure in name resolution",
            "network is unreachable",
        )
    ):
        return "Cannot reach the database host. Check hostname and network access."
    if any(
        phrase in message
        for phrase in ("authentication failed", "access denied", "login failed")
    ):
        return "Database authentication failed. Check the configured credentials."
    if any(phrase in message for phrase in ("certificate", "ssl", "tls")):
        return "Database TLS verification failed. Check the certificate and TLS settings."
    if any(phrase in message for phrase in ("timed out", "timeout")):
        return "Database connection timed out. Check network access and server load."
    return f"Connection test failed ({type(error).__name__})."


def safe_profile_error(error: Exception) -> str:
    """Return an auditable error category without persisting query/driver secrets."""
    return f"Profiling failed ({type(error).__name__})."
