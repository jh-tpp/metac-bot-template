"""
Test that submit_forecast uses the correct API endpoint (/api2/ not /api/)

This test verifies the fix for the 404 Not Found issue where forecast
submissions were failing because they used the legacy /api/ endpoint
instead of the modern /api2/ endpoint.
"""
import sys
import os
from unittest.mock import patch, Mock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("TEST: Forecast Endpoint URL Verification")
print("="*70)

# Test 1: Verify submit_forecast uses /api2/ endpoint
print("\nTest 1: Verify submit_forecast constructs URL with /api2/")

from adapters import submit_forecast

# Mock the requests.post call to capture the URL
with patch('adapters.requests.post') as mock_post:
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    # Test parameters
    test_qid = 578
    test_payload = {"prediction": 0.65}
    test_token = "test-token-123"
    
    # Call submit_forecast (it should not raise an exception)
    try:
        submit_forecast(test_qid, test_payload, test_token)
    except Exception as e:
        print(f"✗ submit_forecast raised unexpected exception: {e}")
        sys.exit(1)
    
    # Verify the URL passed to requests.post
    assert mock_post.called, "requests.post should have been called"
    call_args = mock_post.call_args
    
    # Extract the URL from the call
    url_used = call_args[0][0]  # First positional argument to requests.post
    
    # Verify it uses /api2/ not /api/
    expected_url = f"https://www.metaculus.com/api2/questions/{test_qid}/forecast/"
    assert url_used == expected_url, (
        f"Expected URL: {expected_url}\n"
        f"Actual URL:   {url_used}"
    )
    
    # Also verify it doesn't use the old /api/ endpoint
    assert "/api/questions/" not in url_used, (
        f"URL should not use legacy /api/ endpoint. Got: {url_used}"
    )
    
    print(f"✓ submit_forecast correctly uses /api2/ endpoint")
    print(f"  URL: {url_used}")

# Test 2: Verify URL format for different question IDs
print("\nTest 2: Verify URL format for various question IDs")

test_cases = [
    (1, "https://www.metaculus.com/api2/questions/1/forecast/"),
    (12345, "https://www.metaculus.com/api2/questions/12345/forecast/"),
    (999999, "https://www.metaculus.com/api2/questions/999999/forecast/"),
]

for qid, expected_url in test_cases:
    with patch('adapters.requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response
        
        try:
            submit_forecast(qid, {"prediction": 0.5}, "test-token")
        except Exception:
            pass  # We only care about the URL
        
        url_used = mock_post.call_args[0][0]
        assert url_used == expected_url, (
            f"For QID {qid}:\n"
            f"  Expected: {expected_url}\n"
            f"  Got:      {url_used}"
        )

print("✓ URL format is correct for all test cases")

print("\n" + "="*70)
print("ALL TESTS PASSED")
print("="*70)
print("\nSummary:")
print("✓ submit_forecast uses /api2/ endpoint (not legacy /api/)")
print("✓ URL format is consistent for different question IDs")
print("\n✅ Endpoint fix verified successfully")
