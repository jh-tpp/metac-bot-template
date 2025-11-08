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

def sanitize_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
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
            sanitized[key] = "[REDACTED]"
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
        safe = sanitize_headers(headers)
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
    
    Returns:
        Tuple of (request_file_path, response_file_path) or (None, None) if disabled
    """
    if not _enabled():
        return None, None
    
    try:
        import json
        import os

        os.makedirs(".http-artifacts", exist_ok=True)
        
        # Generate timestamp for unique filenames
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        
        # Save request
        request_file = Path(f".http-artifacts/{timestamp}_{tag}_request.json")
        with open(request_file, "w") as f:
            json.dump(request_artifact, f, indent=2)
        
        # Save response
        response_file = Path(f".http-artifacts/{timestamp}_{tag}_response.json")
        with open(response_file, "w") as f:
            json.dump(response_artifact, f, indent=2)
        
        return request_file, response_file
    except Exception as e:
        # Don't fail the main operation if logging fails
        if _enabled():
            print(f"[WARN] Failed to save HTTP artifacts: {e}", file=sys.stderr, flush=True)
        return None, None


def prepare_request_artifact(
    method: str = None,
    url: str = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data_body: Optional[Any] = None,
    timeout: Optional[float] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Prepare lightweight request artifact dict (always available).
    
    Returns:
        Dict with request metadata
    """
    artifact = {
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if method is not None:
        artifact["method"] = method
    if url is not None:
        artifact["url"] = url
    if headers is not None:
        artifact["headers"] = sanitize_headers(headers)
    if params is not None:
        artifact["params"] = params
    if json_body is not None:
        artifact["json_body"] = json_body
    if data_body is not None:
        if isinstance(data_body, (dict, list)):
            artifact["data_body"] = data_body
        else:
            artifact["data_body"] = str(data_body)
    if timeout is not None:
        artifact["timeout"] = timeout
    
    # Include any additional kwargs
    artifact.update(kwargs)
    
    return artifact


def prepare_response_artifact(resp) -> Dict[str, Any]:
    """
    Prepare lightweight response artifact dict (always available).
    
    Returns:
        Dict with response metadata and sample body
    """
    artifact = {
        "timestamp": datetime.utcnow().isoformat(),
        "status_code": resp.status_code,
        "reason": resp.reason,
        "headers": sanitize_headers(dict(resp.headers)),
        "content_type": resp.headers.get("Content-Type", "unknown"),
        "encoding": resp.encoding,
    }
    
    # Try to include body
    try:
        # Try JSON first
        artifact["body"] = resp.json()
    except Exception:
        # Fall back to text
        try:
            artifact["body"] = resp.text
        except Exception as e:
            # Binary or encoding issues
            artifact["body"] = f"<error reading body: {e}>"
            if hasattr(resp, 'content'):
                artifact["content_length"] = len(resp.content)
    
    return artifact
