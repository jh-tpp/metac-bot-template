"""Integration test for HTTP logging functionality"""
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("HTTP Logging Integration Test")
print("="*70)

# Test that http_logging is imported correctly in main modules
print("\nTest 1: Verify http_logging imports in main.py")
try:
    import main
    assert hasattr(main, 'print_http_request'), "main.py should import print_http_request"
    assert hasattr(main, 'print_http_response'), "main.py should import print_http_response"
    print("✓ main.py imports http_logging correctly")
except Exception as e:
    print(f"✗ Failed to import http_logging in main.py: {e}")
    sys.exit(1)

print("\nTest 2: Verify http_logging imports in adapters.py")
try:
    import adapters
    assert hasattr(adapters, 'print_http_request'), "adapters.py should import print_http_request"
    assert hasattr(adapters, 'print_http_response'), "adapters.py should import print_http_response"
    print("✓ adapters.py imports http_logging correctly")
except Exception as e:
    print(f"✗ Failed to import http_logging in adapters.py: {e}")
    sys.exit(1)

print("\nTest 3: Verify http_logging imports in main_with_no_framework.py")
try:
    import main_with_no_framework
    assert hasattr(main_with_no_framework, 'print_http_request'), "main_with_no_framework.py should import print_http_request"
    assert hasattr(main_with_no_framework, 'print_http_response'), "main_with_no_framework.py should import print_http_response"
    print("✓ main_with_no_framework.py imports http_logging correctly")
except ModuleNotFoundError as e:
    # Dependencies not installed - skip this test
    print(f"⊘ Skipping main_with_no_framework.py test (dependencies not installed: {e})")
except Exception as e:
    print(f"✗ Failed to import http_logging in main_with_no_framework.py: {e}")
    sys.exit(1)

print("\nTest 4: Test llm_call with mock (verify logging is called)")
# Mock requests.post to avoid actual API call
with patch('requests.post') as mock_post:
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.encoding = "utf-8"
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"result": "test", "reasoning": ["test reason"]}'
                }
            }
        ]
    }
    mock_post.return_value = mock_response
    
    # Set minimal environment variables
    os.environ['OPENROUTER_API_KEY'] = 'test-key'
    os.environ['OPENROUTER_MODEL'] = 'test-model'
    
    # Import after setting env vars
    import importlib
    importlib.reload(main)
    
    try:
        # Capture stdout to verify logging output
        from io import StringIO
        import sys as sys_module
        
        old_stdout = sys_module.stdout
        sys_module.stdout = captured_output = StringIO()
        
        result = main.llm_call("test prompt", max_tokens=100)
        
        # Restore stdout
        sys_module.stdout = old_stdout
        output = captured_output.getvalue()
        
        # Verify logging output contains expected markers
        assert "=== HTTP REQUEST ===" in output, "Should print HTTP request marker"
        assert "=== HTTP RESPONSE ===" in output, "Should print HTTP response marker"
        assert "POST" in output, "Should print HTTP method"
        assert "https://openrouter.ai" in output, "Should print URL"
        assert "[REDACTED]" in output, "Should redact Authorization header"
        
        print("✓ llm_call correctly invokes HTTP logging")
    except Exception as e:
        print(f"✗ llm_call logging test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("\nTest 5: Verify LOG_IO_DISABLE functionality")
# Test that logging can be disabled
os.environ['LOG_IO_DISABLE'] = 'true'

# Reload http_logging to pick up env var
import http_logging
importlib.reload(http_logging)

# Verify logging is disabled
assert not http_logging._is_logging_enabled(), "Logging should be disabled when LOG_IO_DISABLE=true"

# Test that functions return early
req_file, resp_file = http_logging.save_http_artifacts("test", {}, {})
assert req_file is None, "save_http_artifacts should return None when disabled"
assert resp_file is None, "save_http_artifacts should return None when disabled"

print("✓ LOG_IO_DISABLE correctly disables logging")

# Clean up
del os.environ['LOG_IO_DISABLE']
importlib.reload(http_logging)

print("\n" + "="*70)
print("All integration tests passed!")
print("="*70)
print("\nHTTP logging is properly integrated and functional.")
print("Logs will appear in GitHub Actions and local runs by default.")
print("Artifacts will be saved to cache/http_logs/ directory.")
print("Use LOG_IO_DISABLE=true to disable logging in emergencies.")
