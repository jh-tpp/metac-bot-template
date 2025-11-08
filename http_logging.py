"""
HTTP Logging Utility

Provides comprehensive request/response logging for all external API calls.
Always enabled by default to make debugging effortless. Can be disabled via LOG_IO_DISABLE env var.
"""
import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


# Check if logging is disabled (emergency opt-out)
_LOG_IO_DISABLE = os.environ.get("LOG_IO_DISABLE", "").lower() in ("1", "true", "t", "yes", "y", "on")

# Verbosity level: "minimal", "normal", "verbose" (default: minimal to reduce noise)
_LOG_VERBOSITY = os.environ.get("LOG_VERBOSITY", "minimal").lower()

# Directory for HTTP log artifacts
HTTP_LOGS_DIR = Path("cache/http_logs")


def _is_logging_enabled() -> bool:
    """Check if HTTP logging is enabled (default: True, disabled only if LOG_IO_DISABLE is set)."""
    return not _LOG_IO_DISABLE


def _is_verbose() -> bool:
    """Check if verbose logging is enabled (prints full request/response bodies)."""
    return _LOG_VERBOSITY in ("verbose", "full", "debug")

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
        "authorization", "api-key", "x-api-key", "api_key", 
        "secret", "token", "password", "bearer"
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
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data_body: Optional[Any] = None,
    timeout: Optional[float] = None
) -> None:
    """
    Print HTTP request details to stdout with flushing for real-time visibility.
    Verbosity controlled by LOG_VERBOSITY env var (default: minimal).
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        headers: Request headers (will be sanitized)
        params: Query parameters
        json_body: JSON request body
        data_body: Non-JSON request body
        timeout: Request timeout in seconds
    """
    if not _is_logging_enabled():
        return
    
    # Minimal logging: just method and URL
    print(f"[HTTP] {method} {url}", flush=True)
    
    # Verbose logging: include full details
    if _is_verbose():
        print("="*70, flush=True)
        print("=== HTTP REQUEST ===", flush=True)
        print("="*70, flush=True)
        
        if headers:
            print(f"Headers: {json.dumps(sanitize_headers(headers), indent=2)}", flush=True)
        
        if params:
            print(f"Params: {json.dumps(params, indent=2)}", flush=True)
        
        if json_body is not None:
            print("JSON Body:", flush=True)
            print(json.dumps(json_body, indent=2, ensure_ascii=False), flush=True)
        
        if data_body is not None:
            print("Data Body:", flush=True)
            if isinstance(data_body, (dict, list)):
                print(json.dumps(data_body, indent=2, ensure_ascii=False), flush=True)
            else:
                print(str(data_body), flush=True)
        
        if timeout is not None:
            print(f"Timeout: {timeout}s", flush=True)
        
        print("="*70 + "\n", flush=True)


def print_http_response(resp) -> None:
    """
    Print HTTP response details to stdout with flushing for real-time visibility.
    Verbosity controlled by LOG_VERBOSITY env var (default: minimal).
    
    Args:
        resp: requests.Response object
    """
    if not _is_logging_enabled():
        return
    
    # Minimal logging: just status code
    print(f"[HTTP] Response: {resp.status_code} {resp.reason}", flush=True)
    
    # Verbose logging: include full body
    if _is_verbose():
        print("="*70, flush=True)
        print("=== HTTP RESPONSE ===", flush=True)
        print("="*70, flush=True)
        
        # Print headers (sanitized)
        print("Headers:", flush=True)
        sanitized = sanitize_headers(dict(resp.headers))
        for key, value in sanitized.items():
            print(f"  {key}: {value}", flush=True)
        
        # Print content-type and encoding
        content_type = resp.headers.get("Content-Type", "unknown")
        print(f"Content-Type: {content_type}", flush=True)
        print(f"Encoding: {resp.encoding}", flush=True)
        
        # Print full body
        print("\nResponse Body:", flush=True)
        try:
            # Try to parse as JSON for pretty printing
            body_json = resp.json()
            print(json.dumps(body_json, indent=2, ensure_ascii=False), flush=True)
        except Exception:
            # Not JSON or parse error - print as text
            try:
                body_text = resp.text
                print(body_text, flush=True)
            except Exception as e:
                # Binary or encoding issues
                print(f"<Binary content or encoding error: {e}>", flush=True)
                print(f"<Content length: {len(resp.content)} bytes>", flush=True)
        
        print("="*70 + "\n", flush=True)


def save_http_artifacts(
    prefix: str,
    request_dict: Dict[str, Any],
    response_dict: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Save HTTP request and response as JSON artifacts to disk.
    
    Args:
        prefix: Filename prefix (e.g., "llm", "metaculus", "asknews")
        request_dict: Dictionary containing request details
        response_dict: Optional dictionary containing response details
    
    Returns:
        Tuple of (request_file_path, response_file_path) or (None, None) if logging disabled
    """
    if not _is_logging_enabled():
        return None, None
    
    try:
        # Create directory if it doesn't exist
        HTTP_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        
        # Save request
        request_file = HTTP_LOGS_DIR / f"{timestamp}_{prefix}_request.json"
        with open(request_file, "w", encoding="utf-8") as f:
            json.dump(request_dict, f, indent=2, ensure_ascii=False)
        
        response_file = None
        if response_dict:
            # Save response
            response_file = HTTP_LOGS_DIR / f"{timestamp}_{prefix}_response.json"
            with open(response_file, "w", encoding="utf-8") as f:
                json.dump(response_dict, f, indent=2, ensure_ascii=False)
        
        return request_file, response_file
    
    except Exception as e:
        # Don't fail the main operation if logging fails
        print(f"[WARN] Failed to save HTTP artifacts: {e}", file=sys.stderr, flush=True)
        return None, None


def prepare_request_artifact(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data_body: Optional[Any] = None,
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """
    Prepare a request artifact dictionary for saving to disk.
    Headers are sanitized automatically.
    
    Args:
        method: HTTP method
        url: Request URL
        headers: Request headers (will be sanitized)
        params: Query parameters
        json_body: JSON request body
        data_body: Non-JSON request body
        timeout: Request timeout
    
    Returns:
        Dictionary suitable for JSON serialization
    """
    artifact = {
        "timestamp": datetime.utcnow().isoformat(),
        "method": method,
        "url": url
    }
    
    if headers:
        artifact["headers"] = sanitize_headers(headers)
    
    if params:
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
    
    return artifact


def prepare_response_artifact(resp) -> Dict[str, Any]:
    """
    Prepare a response artifact dictionary for saving to disk.
    Headers are sanitized automatically.
    
    Args:
        resp: requests.Response object
    
    Returns:
        Dictionary suitable for JSON serialization
    """
    artifact = {
        "timestamp": datetime.utcnow().isoformat(),
        "status_code": resp.status_code,
        "reason": resp.reason,
        "headers": sanitize_headers(dict(resp.headers)),
        "encoding": resp.encoding,
        "content_type": resp.headers.get("Content-Type", "unknown")
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
            artifact["body"] = f"<Binary content or encoding error: {e}>"
            artifact["content_length"] = len(resp.content)
    
    return artifact
