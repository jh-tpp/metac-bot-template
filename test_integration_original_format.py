"""
Integration test for original template forecast and comment submission.

This test verifies the complete flow:
1. Convert MC results to payload
2. Submit forecast with array format
3. Submit reasoning comment after forecast
"""
import sys
import os
from unittest.mock import patch, Mock

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("INTEGRATION TEST: Full Forecast and Comment Flow")
print("="*70)

from adapters import mc_results_to_metaculus_payload, submit_forecast, submit_comment

# Test: Complete binary question flow
print("\nTest 1: Complete flow for binary question")

# Step 1: Create question and MC result
question = {
    "id": 578,
    "type": "binary",
    "title": "Will AI achieve AGI by 2030?",
    "options": []
}

mc_result = {
    "p": 0.45,
    "reasoning": [
        "Base rate analysis: Historical AI progress suggests 40% baseline",
        "Recent developments (GPT-4, Claude) accelerate timeline: +10%",
        "Economic incentives strong: +5%",
        "Technical challenges remain: -10%",
        "Final estimate: 45% probability"
    ]
}

# Step 2: Convert to payload
payload = mc_results_to_metaculus_payload(question, mc_result)

print(f"✓ Payload created:")
print(f"  probability_yes: {payload['probability_yes']}")
print(f"  probability_yes_per_category: {payload['probability_yes_per_category']}")
print(f"  continuous_cdf: {payload['continuous_cdf']}")

# Step 3: Simulate forecast submission
with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    submit_forecast(question["id"], payload, "test-token")
    
    # Verify forecast submission
    assert mock_post.called
    forecast_call = mock_post.call_args
    forecast_url = forecast_call[0][0]
    forecast_body = forecast_call[1]["json"]
    
    assert forecast_url == "https://www.metaculus.com/api/questions/forecast/"
    assert isinstance(forecast_body, list)
    assert len(forecast_body) == 1
    assert forecast_body[0]["question"] == 578
    assert forecast_body[0]["probability_yes"] == 0.45
    
    print(f"✓ Forecast submitted successfully")
    print(f"  URL: {forecast_url}")
    print(f"  Body: {forecast_body}")

# Step 4: Simulate comment submission
reasoning_text = "\n".join(mc_result["reasoning"])

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"success": True, "id": 99999}
    mock_post.return_value = mock_response
    
    # Use question ID as post_id (fallback behavior)
    post_id = question.get("post_id") or question["id"]
    submit_comment(post_id, reasoning_text, "test-token")
    
    # Verify comment submission
    assert mock_post.called
    comment_call = mock_post.call_args
    comment_url = comment_call[0][0]
    comment_body = comment_call[1]["json"]
    
    assert comment_url == "https://www.metaculus.com/api/comments/create/"
    assert comment_body["text"] == reasoning_text
    assert comment_body["on_post"] == post_id
    assert comment_body["included_forecast"] is True
    
    print(f"✓ Comment submitted successfully")
    print(f"  URL: {comment_url}")
    print(f"  Comment length: {len(comment_body['text'])} chars")
    print(f"  on_post: {comment_body['on_post']}")

print("\n✅ Complete flow verified: Forecast → Comment")

# Test: Complete multiple choice flow
print("\nTest 2: Complete flow for multiple choice question")

mc_question = {
    "id": 12345,
    "type": "multiple_choice",
    "title": "Which company will lead AI in 2026?",
    "options": ["Google", "OpenAI", "Anthropic", "Other"],
    "post_id": 12300  # Explicit post_id
}

mc_mc_result = {
    "probs": [0.35, 0.40, 0.20, 0.05],
    "reasoning": [
        "OpenAI has strong momentum with GPT series",
        "Google has infrastructure and resources",
        "Anthropic making steady progress",
        "Final distribution based on current trajectories"
    ]
}

payload = mc_results_to_metaculus_payload(mc_question, mc_mc_result)

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = {}
    mock_post.return_value = mock_response
    
    # Submit forecast
    submit_forecast(mc_question["id"], payload, "test-token")
    
    forecast_body = mock_post.call_args[1]["json"]
    assert forecast_body[0]["probability_yes_per_category"] is not None
    assert len(forecast_body[0]["probability_yes_per_category"]) == 4
    
    print(f"✓ MC forecast submitted")
    print(f"  Options: {list(forecast_body[0]['probability_yes_per_category'].keys())}")
    print(f"  Probs: {list(forecast_body[0]['probability_yes_per_category'].values())}")

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    # Submit comment using explicit post_id
    reasoning_text = "\n".join(mc_mc_result["reasoning"])
    submit_comment(mc_question["post_id"], reasoning_text, "test-token")
    
    comment_body = mock_post.call_args[1]["json"]
    assert comment_body["on_post"] == 12300  # Uses explicit post_id
    
    print(f"✓ MC comment submitted to post_id {comment_body['on_post']}")

print("\n✅ MC flow verified: Forecast → Comment with explicit post_id")

# Test: Numeric question flow
print("\nTest 3: Complete flow for numeric question")

numeric_question = {
    "id": 14333,
    "type": "numeric",
    "title": "Age of oldest human in 2100",
    "options": []
}

numeric_result = {
    "cdf": [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
    "grid": [110, 115, 120, 125, 130, 135, 140],
    "reasoning": ["CDF constructed from MC sampling"]
}

payload = mc_results_to_metaculus_payload(numeric_question, numeric_result)

with patch('adapters.requests.post') as mock_post:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    submit_forecast(numeric_question["id"], payload, "test-token")
    
    forecast_body = mock_post.call_args[1]["json"]
    assert forecast_body[0]["continuous_cdf"] is not None
    assert len(forecast_body[0]["continuous_cdf"]) == 7
    
    print(f"✓ Numeric forecast submitted")
    print(f"  CDF length: {len(forecast_body[0]['continuous_cdf'])}")

print("\n✅ Numeric flow verified")

print("\n" + "="*70)
print("ALL INTEGRATION TESTS PASSED")
print("="*70)
print("\nVerified:")
print("✓ Binary: Payload conversion → Forecast submission → Comment submission")
print("✓ Multiple Choice: Payload conversion → Forecast submission → Comment submission")
print("✓ Numeric: Payload conversion → Forecast submission")
print("✓ post_id handling (explicit vs fallback to question_id)")
print("✓ Array payload format with 'question' field")
print("✓ Original API endpoints (/api/ not /api2/)")
print("\n✅ Integration flow complete and working correctly")
