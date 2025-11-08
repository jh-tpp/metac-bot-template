"""Test http_logging module functionality"""
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("Test 1: sanitize_headers function")
print("="*70)

from http_logging import sanitize_headers

# Test sanitization of sensitive headers
headers = {
    "Authorization": "Bearer secret-token-12345",
    "Content-Type": "application/json",
    "X-API-Key": "my-api-key",
    "User-Agent": "test-agent",
    "api-key": "another-secret",
    "X-Custom-Header": "safe-value"
}

sanitized = sanitize_headers(headers)
assert sanitized["Authorization"] == "[REDACTED]", "Authorization should be redacted"
assert sanitized["Content-Type"] == "application/json", "Content-Type should not be redacted"
assert sanitized["X-API-Key"] == "[REDACTED]", "X-API-Key should be redacted"
assert sanitized["User-Agent"] == "test-agent", "User-Agent should not be redacted"
assert sanitized["api-key"] == "[REDACTED]", "api-key should be redacted"
assert sanitized["X-Custom-Header"] == "safe-value", "X-Custom-Header should not be redacted"

# Test empty headers
assert sanitize_headers(None) == {}, "None headers should return empty dict"
assert sanitize_headers({}) == {}, "Empty headers should return empty dict"

print("✓ sanitize_headers tests passed")

print("\n" + "="*70)
print("Test 2: prepare_request_artifact function")
print("="*70)

from http_logging import prepare_request_artifact

artifact = prepare_request_artifact(
    method="POST",
    url="https://api.example.com/v1/test",
    headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
    params={"limit": 10, "offset": 0},
    json_body={"query": "test query", "max_results": 5},
    timeout=30
)

assert artifact["method"] == "POST", "Method should be preserved"
assert artifact["url"] == "https://api.example.com/v1/test", "URL should be preserved"
assert artifact["headers"]["Authorization"] == "[REDACTED]", "Authorization should be redacted in artifact"
assert artifact["headers"]["Content-Type"] == "application/json", "Content-Type should be preserved"
assert artifact["params"]["limit"] == 10, "Params should be preserved"
assert artifact["json_body"]["query"] == "test query", "JSON body should be preserved"
assert artifact["timeout"] == 30, "Timeout should be preserved"
assert "timestamp" in artifact, "Timestamp should be present"

print("✓ prepare_request_artifact tests passed")

print("\n" + "="*70)
print("Test 3: prepare_response_artifact function")
print("="*70)

from http_logging import prepare_response_artifact

# Create a mock response
mock_response = Mock()
mock_response.status_code = 200
mock_response.reason = "OK"
mock_response.headers = {
    "Content-Type": "application/json",
    "X-Request-ID": "test-123"
}
mock_response.encoding = "utf-8"
mock_response.json.return_value = {"result": "success", "data": [1, 2, 3]}

artifact = prepare_response_artifact(mock_response)

assert artifact["status_code"] == 200, "Status code should be preserved"
assert artifact["reason"] == "OK", "Reason should be preserved"
assert artifact["content_type"] == "application/json", "Content-Type should be extracted"
assert artifact["encoding"] == "utf-8", "Encoding should be preserved"
assert artifact["body"]["result"] == "success", "JSON body should be preserved"
assert "timestamp" in artifact, "Timestamp should be present"

# Test response with text body (not JSON)
mock_response_text = Mock()
mock_response_text.status_code = 200
mock_response_text.reason = "OK"
mock_response_text.headers = {"Content-Type": "text/plain"}
mock_response_text.encoding = "utf-8"
mock_response_text.json.side_effect = ValueError("Not JSON")
mock_response_text.text = "Plain text response"

artifact_text = prepare_response_artifact(mock_response_text)
assert artifact_text["body"] == "Plain text response", "Text body should be preserved"

print("✓ prepare_response_artifact tests passed")

print("\n" + "="*70)
print("Test 4: save_http_artifacts function")
print("="*70)

from http_logging import save_http_artifacts

# Enable HTTP logging for this test
os.environ["HTTP_LOGGING_ENABLED"] = "true"
import importlib
import http_logging
importlib.reload(http_logging)

# Use a temporary directory for testing
with tempfile.TemporaryDirectory() as tmpdir:
    # Override the HTTP_LOGS_DIR for testing (not used anymore, artifacts go to .http-artifacts)
    # But the function creates files in .http-artifacts which is in tmpdir during test
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    
    request_data = {
        "method": "GET",
        "url": "https://api.example.com/test",
        "headers": {"Authorization": "[REDACTED]"}
    }
    
    response_data = {
        "status_code": 200,
        "body": {"result": "ok"}
    }
    
    from http_logging import save_http_artifacts
    req_file, resp_file = save_http_artifacts("test_prefix", request_data, response_data)
    
    assert req_file is not None, "Request file should be created"
    assert resp_file is not None, "Response file should be created"
    assert req_file.exists(), "Request file should exist"
    assert resp_file.exists(), "Response file should exist"
    
    # Verify file contents
    with open(req_file, "r") as f:
        saved_request = json.load(f)
        assert saved_request["method"] == "GET", "Request data should be saved correctly"
    
    with open(resp_file, "r") as f:
        saved_response = json.load(f)
        assert saved_response["status_code"] == 200, "Response data should be saved correctly"
    
    # Restore original directory
    os.chdir(original_cwd)

# Disable HTTP logging after test
os.environ["HTTP_LOGGING_ENABLED"] = "false"
importlib.reload(http_logging)

print("✓ save_http_artifacts tests passed")

print("\n" + "="*70)
print("Test 5: HTTP_LOGGING_ENABLED environment variable")
print("="*70)

# Test with logging disabled (default)
if "HTTP_LOGGING_ENABLED" in os.environ:
    del os.environ["HTTP_LOGGING_ENABLED"]

# Re-import to pick up the environment variable
importlib.reload(http_logging)

from http_logging import _enabled, save_http_artifacts

assert not _enabled(), "Logging should be disabled by default"

# Test that save_http_artifacts returns None when disabled
req_file, resp_file = save_http_artifacts("test", {}, {})
assert req_file is None, "Should return None when logging is disabled"
assert resp_file is None, "Should return None when logging is disabled"

# Test enabling logging
os.environ["HTTP_LOGGING_ENABLED"] = "true"
importlib.reload(http_logging)

assert http_logging._enabled(), "Logging should be enabled when HTTP_LOGGING_ENABLED=true"

# Clean up
del os.environ["HTTP_LOGGING_ENABLED"]
importlib.reload(http_logging)

assert not http_logging._enabled(), "Logging should be disabled by default after cleanup"

print("✓ HTTP_LOGGING_ENABLED tests passed")

print("\n" + "="*70)
print("All HTTP logging tests passed!")
print("="*70)
