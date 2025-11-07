"""
Test that submit_forecast uses the ORIGINAL template API format.

This test verifies that forecast submissions use the original /api/ endpoint
(not /api2/) with array payload format: [{"question": <id>, ...}]
"""
import sys
import os
from unittest.mock import patch, Mock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("TEST: Original Template Forecast Format Verification")
print("="*70)

# Test 1: Verify submit_forecast uses /api/ endpoint (not /api2/)
print("\nTest 1: Verify submit_forecast uses ORIGINAL /api/ endpoint")

from adapters import submit_forecast

# Mock the requests.post call to capture the URL and payload
with patch('adapters.requests.post') as mock_post:
    # Setup mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    # Test parameters (original format)
    test_qid = 578
    test_payload = {
        "probability_yes": 0.65,
        "probability_yes_per_category": None,
        "continuous_cdf": None,
    }
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
    
    # Verify it uses /api/ (ORIGINAL format)
    expected_url = "https://www.metaculus.com/api/questions/forecast/"
    assert url_used == expected_url, (
        f"Expected URL: {expected_url}\n"
        f"Actual URL:   {url_used}"
    )
    
    # Verify it doesn't use /api2/
    assert "/api2/" not in url_used, (
        f"URL should use original /api/ endpoint (not /api2/). Got: {url_used}"
    )
    
    print(f"✓ submit_forecast correctly uses ORIGINAL /api/ endpoint")
    print(f"  URL: {url_used}")

# Test 2: Verify payload format is array with "question" field
print("\nTest 2: Verify payload uses array format with 'question' field")

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    test_qid = 12345
    test_payload = {
        "probability_yes": None,
        "probability_yes_per_category": {"Option A": 0.6, "Option B": 0.4},
        "continuous_cdf": None,
    }
    
    submit_forecast(test_qid, test_payload, "test-token")
    
    # Extract the JSON body passed to requests.post
    call_kwargs = mock_post.call_args[1]
    json_body = call_kwargs.get("json")
    
    # Verify it's an array
    assert isinstance(json_body, list), (
        f"Payload should be a list/array. Got: {type(json_body)}"
    )
    
    # Verify array has one element
    assert len(json_body) == 1, (
        f"Payload array should have exactly 1 element. Got: {len(json_body)}"
    )
    
    # Verify element has "question" field
    payload_item = json_body[0]
    assert "question" in payload_item, (
        f"Payload item should have 'question' field. Got keys: {list(payload_item.keys())}"
    )
    
    # Verify question ID matches
    assert payload_item["question"] == test_qid, (
        f"Payload question ID should be {test_qid}. Got: {payload_item['question']}"
    )
    
    # Verify original format fields are present
    assert "probability_yes" in payload_item, (
        f"Payload should have 'probability_yes' field. Got keys: {list(payload_item.keys())}"
    )
    assert "probability_yes_per_category" in payload_item, (
        f"Payload should have 'probability_yes_per_category' field"
    )
    assert "continuous_cdf" in payload_item, (
        f"Payload should have 'continuous_cdf' field"
    )
    
    print(f"✓ Payload correctly uses array format: [{{\"question\": {test_qid}, ...}}]")
    print(f"  Payload keys: {list(payload_item.keys())}")

# Test 3: Verify different question types use correct payload structure
print("\nTest 3: Verify payload structure for different question types")

test_cases = [
    (
        "binary",
        578,
        {"probability_yes": 0.75, "probability_yes_per_category": None, "continuous_cdf": None},
        "Binary question should have probability_yes"
    ),
    (
        "multiple_choice",
        999,
        {"probability_yes": None, "probability_yes_per_category": {"A": 0.5, "B": 0.5}, "continuous_cdf": None},
        "Multiple choice should have probability_yes_per_category dict"
    ),
    (
        "numeric",
        1234,
        {"probability_yes": None, "probability_yes_per_category": None, "continuous_cdf": [0.0, 0.5, 1.0]},
        "Numeric question should have continuous_cdf list"
    ),
]

for qtype, qid, payload, description in test_cases:
    with patch('adapters.requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_post.return_value = mock_response
        
        submit_forecast(qid, payload, "test-token")
        
        json_body = mock_post.call_args[1].get("json")
        payload_item = json_body[0]
        
        # Verify structure
        assert payload_item["question"] == qid
        assert payload_item["probability_yes"] == payload["probability_yes"]
        assert payload_item["probability_yes_per_category"] == payload["probability_yes_per_category"]
        assert payload_item["continuous_cdf"] == payload["continuous_cdf"]
        
        print(f"  ✓ {description}")

print("\n" + "="*70)
print("ALL TESTS PASSED")
print("="*70)
print("\nSummary:")
print("✓ submit_forecast uses ORIGINAL /api/ endpoint (not /api2/)")
print("✓ Payload uses array format: [{\"question\": <id>, ...}]")
print("✓ Payload includes original fields: probability_yes, probability_yes_per_category, continuous_cdf")
print("\n✅ Original template format verified successfully")
