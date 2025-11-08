"""
HTTP Logging Utility

Provides comprehensive request/response logging for all external API calls.
Disabled by default to reduce noise. Can be enabled via HTTP_LOGGING_ENABLED env var.
"""
import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


# Check if logging is enabled (opt-in, default: false)
HTTP_LOGGING_ENABLED = str(os.getenv("HTTP_LOGGING_ENABLED", "false")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Directory for HTTP log artifacts
HTTP_LOGS_DIR = Path(".http-artifacts")


def _is_logging_enabled() -> bool:
    """Check if HTTP logging is enabled (default: False)."""
    return HTTP_LOGGING_ENABLED


def _enabled():
    """Alias for _is_logging_enabled for consistency."""
    return HTTP_LOGGING_ENABLED

def _sanitize_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Sanitize headers by redacting sensitive values.
    
    Args:
        headers: Dictionary of HTTP headers
    
    Returns:
        Dictionary with sensitive headers redacted
    """
    if not headers:
        return {}
    
    # Headers to redact
    sensitive_keys = {
        "authorization",
        "api-key",
        "x-api-key",
        "api_key",
        "secret",
        "token",
        "password",
        "bearer",
    }
    
    sanitized = {}
    for key, value in headers.items():
        key_lower = key.lower()
        # Check if any sensitive keyword is in the key
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = value
    
    return sanitized


def print_http_request(
    *,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data_body: Optional[Any] = None,
    timeout: Optional[float] = None,
) -> None:
    """
    Print HTTP request details to stdout (only if HTTP_LOGGING_ENABLED=true).
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        headers: Request headers (will be sanitized)
        params: Query parameters
        json_body: JSON request body
        data_body: Non-JSON request body
        timeout: Request timeout in seconds
    """
    if not _enabled():
        return
    
    print("\n" + "=" * 70 + "\n=== HTTP REQUEST ===\n" + "=" * 70)
    print(f"Method: {method}")
    print(f"URL: {url}")
    if params:
        print("Params:", params)
    if headers:
        safe = _sanitize_headers(headers)
        print("Headers:", safe)
    if json_body is not None:
        print("JSON:", json_body)
    if data_body is not None:
        print("Data:", data_body)
    if timeout is not None:
        print(f"Timeout: {timeout}s")
    print("=" * 70 + "\n")


def print_http_response(resp) -> None:
    """
    Print HTTP response details to stdout (only if HTTP_LOGGING_ENABLED=true).
    
    Args:
        resp: requests.Response object
    """
    if not _enabled():
        return
    
    print("\n" + "=" * 70 + "\n=== HTTP RESPONSE ===\n" + "=" * 70)
    print(f"Status: {resp.status_code} {resp.reason}")
    ct = resp.headers.get("content-type", "")
    if "json" in ct.lower():
        try:
            print("Body:", resp.json())
        except Exception:
            print("Body(raw):", resp.text[:2000])
    else:
        print("Body(text):", resp.text[:2000])
    print("=" * 70 + "\n")


def save_http_artifacts(tag, request_artifact, response_artifact):
    """
    Save HTTP request and response as JSON artifacts (only if HTTP_LOGGING_ENABLED=true).
    
    Args:
        tag: Tag for filename (e.g., "llm", "metaculus")
        request_artifact: Request artifact dict
        response_artifact: Response artifact dict
    """
    if not _enabled():
        return
    import json
    import os

    os.makedirs(".http-artifacts", exist_ok=True)
    with open(f".http-artifacts/{tag}_request.json", "w") as f:
        json.dump(request_artifact, f, indent=2)
    with open(f".http-artifacts/{tag}_response.json", "w") as f:
        json.dump(response_artifact, f, indent=2)


def prepare_request_artifact(**kwargs):
    """
    Prepare lightweight request artifact dict (always available).
    
    Returns:
        Dict with request metadata (headers excluded for brevity)
    """
    return {"request": {k: v for k, v in kwargs.items() if k != "headers"}}


def prepare_response_artifact(resp):
    """
    Prepare lightweight response artifact dict (always available).
    
    Returns:
        Dict with response metadata and sample body
    """
    return {
        "status": resp.status_code,
        "reason": resp.reason,
        "headers": dict(resp.headers),
        "body_sample": resp.text[:1024],
    }
