"""
Test comment submission functionality using ORIGINAL template format.

This test verifies that reasoning comments are submitted to the correct endpoint
with the proper payload format.
"""
import sys
import os
from unittest.mock import patch, Mock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("TEST: Comment Submission Verification")
print("="*70)

# Test 1: Verify submit_comment uses /api/comments/create/ endpoint
print("\nTest 1: Verify submit_comment uses correct endpoint")

from adapters import submit_comment

with patch('adapters.requests.post') as mock_post:
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"success": True, "id": 12345}
    mock_post.return_value = mock_response
    
    # Test parameters
    test_post_id = 578
    test_comment = "This is my reasoning for the forecast."
    test_token = "test-token-123"
    
    # Call submit_comment
    try:
        submit_comment(test_post_id, test_comment, test_token)
    except Exception as e:
        print(f"✗ submit_comment raised unexpected exception: {e}")
        sys.exit(1)
    
    # Verify the URL
    assert mock_post.called, "requests.post should have been called"
    call_args = mock_post.call_args
    url_used = call_args[0][0]
    
    expected_url = "https://www.metaculus.com/api/comments/create/"
    assert url_used == expected_url, (
        f"Expected URL: {expected_url}\n"
        f"Actual URL:   {url_used}"
    )
    
    print(f"✓ submit_comment correctly uses /api/comments/create/ endpoint")
    print(f"  URL: {url_used}")

# Test 2: Verify comment payload format
print("\nTest 2: Verify comment payload structure")

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    test_post_id = 999
    test_comment = "My detailed reasoning:\n1. Factor A\n2. Factor B"
    
    submit_comment(test_post_id, test_comment, "test-token")
    
    # Extract the JSON body
    call_kwargs = mock_post.call_args[1]
    json_body = call_kwargs.get("json")
    
    # Verify payload structure
    assert isinstance(json_body, dict), (
        f"Payload should be a dict. Got: {type(json_body)}"
    )
    
    # Verify required fields
    assert "text" in json_body, "Payload should have 'text' field"
    assert json_body["text"] == test_comment, "Comment text should match"
    
    assert "parent" in json_body, "Payload should have 'parent' field"
    assert json_body["parent"] is None, "Parent should be None for top-level comments"
    
    assert "included_forecast" in json_body, "Payload should have 'included_forecast' field"
    assert json_body["included_forecast"] is True, "included_forecast should be True"
    
    assert "is_private" in json_body, "Payload should have 'is_private' field"
    assert json_body["is_private"] is True, "is_private should be True"
    
    assert "on_post" in json_body, "Payload should have 'on_post' field"
    assert json_body["on_post"] == test_post_id, (
        f"on_post should be {test_post_id}. Got: {json_body['on_post']}"
    )
    
    print(f"✓ Comment payload correctly structured")
    print(f"  Payload keys: {list(json_body.keys())}")
    print(f"  text length: {len(json_body['text'])} chars")
    print(f"  on_post: {json_body['on_post']}")

# Test 3: Verify authorization header is set
print("\nTest 3: Verify authorization header")

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    test_token = "my-secret-token-abc123"
    
    submit_comment(123, "Test comment", test_token)
    
    # Extract headers
    call_kwargs = mock_post.call_args[1]
    headers = call_kwargs.get("headers")
    
    assert "Authorization" in headers, "Headers should include Authorization"
    expected_auth = f"Token {test_token}"
    assert headers["Authorization"] == expected_auth, (
        f"Authorization header should be '{expected_auth}'. Got: {headers['Authorization']}"
    )
    
    print(f"✓ Authorization header correctly set")

# Test 4: Test comment with special characters
print("\nTest 4: Test comment with special characters and formatting")

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    test_comment = """My forecast reasoning:
    
• Base rate: ~30%
• Recent data suggests 📈 trend
• Key factors: "uncertainty" & risk
    
<b>Conclusion:</b> 65% probability
"""
    
    submit_comment(456, test_comment, "test-token")
    
    call_kwargs = mock_post.call_args[1]
    json_body = call_kwargs.get("json")
    
    assert json_body["text"] == test_comment, (
        "Comment text should preserve special characters and formatting"
    )
    
    print(f"✓ Special characters and formatting preserved")

print("\n" + "="*70)
print("ALL TESTS PASSED")
print("="*70)
print("\nSummary:")
print("✓ submit_comment uses /api/comments/create/ endpoint")
print("✓ Payload includes: text, parent, included_forecast, is_private, on_post")
print("✓ Authorization header correctly formatted")
print("✓ Special characters and formatting preserved")
print("\n✅ Comment submission verified successfully")
