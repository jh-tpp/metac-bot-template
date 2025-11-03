"""Test OPENROUTER_DEBUG flag functionality"""
import sys
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("Test 1: OPENROUTER_DEBUG flag parsing")
print("="*70)

# Import after path is set up
from main import _parse_bool_flag

# Test true values for debug flag
assert _parse_bool_flag("true") == True, "Failed: 'true' should be True"
assert _parse_bool_flag("1") == True, "Failed: '1' should be True"
assert _parse_bool_flag("yes") == True, "Failed: 'yes' should be True"
assert _parse_bool_flag("on") == True, "Failed: 'on' should be True"

# Test false values
assert _parse_bool_flag("false") == False, "Failed: 'false' should be False"
assert _parse_bool_flag("0") == False, "Failed: '0' should be False"

# Test default behavior (debug should default to false)
assert _parse_bool_flag(None, default=False) == False, "Failed: None with default=False should be False"
assert _parse_bool_flag("", default=False) == False, "Failed: empty string with default=False should be False"

print("✓ OPENROUTER_DEBUG flag parsing tests passed")

print("\n" + "="*70)
print("Test 2: llm_call with debug disabled (default)")
print("="*70)

# Mock environment with debug disabled
with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key', 'OPENROUTER_DEBUG': 'false'}, clear=False):
    # Reimport to pick up new env vars
    import importlib
    import main
    importlib.reload(main)
    
    # Mock requests.post
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {'content-type': 'application/json'}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"test": "value"}'
                }
            }
        ]
    }
    
    with patch('main.requests.post', return_value=mock_response) as mock_post:
        result = main.llm_call("test prompt", max_tokens=100, temperature=0.5)
        
        # Verify result
        assert result == {"test": "value"}, "Failed: Result should match expected JSON"
        
        # Verify no debug files were created
        cache_dir = Path("cache")
        if cache_dir.exists():
            debug_files = list(cache_dir.glob("debug_llm_*"))
            # Note: there might be debug files from previous tests, so we can't assert zero
            # But we can verify the call was made correctly
        
        # Verify request was made with correct timeout (90s)
        assert mock_post.called, "Failed: requests.post should be called"
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['timeout'] == 90, f"Failed: timeout should be 90, got {call_kwargs['timeout']}"

print("✓ llm_call with debug disabled tests passed")

print("\n" + "="*70)
print("Test 3: llm_call with debug enabled")
print("="*70)

# Create a temporary cache directory for this test
test_cache_dir = Path("/tmp/test_cache_openrouter_debug")
test_cache_dir.mkdir(exist_ok=True)

# Mock environment with debug enabled
with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key', 'OPENROUTER_DEBUG': 'true'}, clear=False):
    # Reimport to pick up new env vars
    import importlib
    import main
    importlib.reload(main)
    
    # Patch CACHE_DIR to use test directory
    with patch('main.CACHE_DIR', test_cache_dir):
        # Mock requests.post
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.headers = {
            'content-type': 'application/json',
            'x-request-id': 'test-request-123',
            'x-ratelimit-limit': '100',
            'x-ratelimit-remaining': '99'
        }
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"debug_test": "enabled"}'
                    }
                }
            ]
        }
        
        with patch('main.requests.post', return_value=mock_response):
            result = main.llm_call("test debug prompt", max_tokens=100, temperature=0.5)
            
            # Verify result
            assert result == {"debug_test": "enabled"}, "Failed: Result should match expected JSON"
            
            # Verify debug files were created
            debug_request_files = list(test_cache_dir.glob("debug_llm_*_request.json"))
            debug_response_files = list(test_cache_dir.glob("debug_llm_*_response.json"))
            
            assert len(debug_request_files) > 0, "Failed: Debug request file should be created"
            assert len(debug_response_files) > 0, "Failed: Debug response file should be created"
            
            # Verify request file contents (should not contain Authorization header)
            request_file = sorted(debug_request_files)[-1]  # Get latest
            with open(request_file, 'r') as f:
                request_data = json.load(f)
                assert "url" in request_data, "Failed: Request should have url"
                assert "model" in request_data, "Failed: Request should have model"
                assert "prompt" in request_data, "Failed: Request should have prompt"
                assert request_data["prompt"] == "test debug prompt", "Failed: Prompt should match"
                assert "Authorization" not in str(request_data), "Failed: Authorization should not be in request file"
            
            # Verify response file contents
            response_file = sorted(debug_response_files)[-1]  # Get latest
            with open(response_file, 'r') as f:
                response_data = json.load(f)
                assert "status" in response_data, "Failed: Response should have status"
                assert response_data["status"] == 200, "Failed: Status should be 200"
                assert "headers" in response_data, "Failed: Response should have headers"
                assert "body" in response_data, "Failed: Response should have body"

print("✓ llm_call with debug enabled tests passed")

print("\n" + "="*70)
print("Test 4: llm_call error handling with better diagnostics")
print("="*70)

# Test empty content error
with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key', 'OPENROUTER_DEBUG': 'false'}, clear=False):
    import importlib
    import main
    importlib.reload(main)
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {'content-type': 'application/json'}
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": ""  # Empty content
                }
            }
        ]
    }
    
    with patch('main.requests.post', return_value=mock_response):
        try:
            result = main.llm_call("test prompt")
            assert False, "Failed: Should raise RuntimeError for empty content"
        except RuntimeError as e:
            error_msg = str(e)
            assert "Empty content" in error_msg, f"Failed: Error should mention empty content, got: {error_msg}"
            assert "Response JSON" in error_msg, f"Failed: Error should include response JSON, got: {error_msg}"

print("✓ Empty content error handling tests passed")

# Test JSON parse error
mock_response = Mock()
mock_response.status_code = 200
mock_response.reason = "OK"
mock_response.headers = {'content-type': 'application/json'}
mock_response.json.return_value = {
    "choices": [
        {
            "message": {
                "content": "not valid json"
            }
        }
    ]
}

with patch('main.requests.post', return_value=mock_response):
    try:
        result = main.llm_call("test prompt")
        assert False, "Failed: Should raise RuntimeError for invalid JSON"
    except RuntimeError as e:
        error_msg = str(e)
        assert "Failed to parse JSON" in error_msg, f"Failed: Error should mention JSON parse failure, got: {error_msg}"
        assert "Raw response" in error_msg, f"Failed: Error should include raw response, got: {error_msg}"

print("✓ JSON parse error handling tests passed")

# Test unexpected response shape error
mock_response = Mock()
mock_response.status_code = 200
mock_response.reason = "OK"
mock_response.headers = {'content-type': 'application/json'}
mock_response.json.return_value = {
    "unexpected": "shape"  # Missing choices array
}

with patch('main.requests.post', return_value=mock_response):
    try:
        result = main.llm_call("test prompt")
        assert False, "Failed: Should raise RuntimeError for unexpected shape"
    except RuntimeError as e:
        error_msg = str(e)
        assert "Unexpected OpenRouter response shape" in error_msg, f"Failed: Error should mention unexpected shape, got: {error_msg}"
        assert "Response JSON" in error_msg, f"Failed: Error should include response JSON, got: {error_msg}"

print("✓ Unexpected shape error handling tests passed")

print("\n" + "="*70)
print("All OPENROUTER_DEBUG tests passed!")
print("="*70)
