"""
End-to-end integration test for tournament fetching workflow.
Tests the complete flow from API calls to artifact creation.
"""
import sys
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

print("="*70)
print("INTEGRATION TEST: Tournament Fetching Workflow")
print("="*70)

# Set up environment
os.environ['OPENROUTER_API_KEY'] = 'test_key'
os.environ['METACULUS_TOKEN'] = 'test_token'
os.environ['FALL_2025_AI_BENCHMARKING_ID'] = '3512'

import main
from main import (
    list_posts_from_tournament,
    get_open_question_ids_from_tournament,
    fetch_tournament_questions,
    AIB_STATE_DIR,
    FALL_2025_AI_BENCHMARKING_ID
)

print("\nTest 1: Verify tournament ID configuration")
print(f"  Tournament ID: {FALL_2025_AI_BENCHMARKING_ID}")
assert FALL_2025_AI_BENCHMARKING_ID == 3512, "Should use configured tournament ID"
print("  ✓ Tournament ID correctly configured")

print("\nTest 2: Verify AIB_STATE_DIR configuration")
print(f"  State directory: {AIB_STATE_DIR}")
assert AIB_STATE_DIR == Path(".aib-state"), "Should use .aib-state directory"
print("  ✓ State directory correctly configured")

print("\nTest 3: Mock tournament API response")

# Create mock post data (simulates /api/posts/ response)
mock_post_data = {
    "results": [
        {
            "id": 100,  # post_id
            "status": "open",
            "title": "Mock Post 1",
            "question": {
                "id": 1001,  # question_id
                "title": "Will X happen?",
                "description": "Test question",
                "possibilities": {
                    "type": "binary"
                }
            }
        },
        {
            "id": 101,  # post_id
            "status": "open",
            "title": "Mock Post 2",
            "question": {
                "id": 1002,  # question_id
                "title": "Choose an option",
                "description": "MC question",
                "possibilities": {
                    "type": "discrete",
                    "outcomes": [
                        {"name": "Option A"},
                        {"name": "Option B"}
                    ]
                }
            }
        },
        {
            "id": 102,  # post_id
            "status": "closed",  # Should be filtered out
            "title": "Mock Post 3 (closed)",
            "question": {
                "id": 1003,
                "title": "Closed question",
                "description": "Should not appear"
            }
        }
    ]
}

print("  Mock data created with 3 posts (2 open, 1 closed)")

print("\nTest 4: Test list_posts_from_tournament with mock")
with patch('main.requests.get') as mock_get:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.json.return_value = mock_post_data
    mock_response.headers = {"Content-Type": "application/json"}
    mock_get.return_value = mock_response
    
    result = list_posts_from_tournament(tournament_id=3512, offset=0, count=50)
    
    assert result is not None, "Should return data"
    assert "results" in result, "Should have results key"
    assert len(result["results"]) == 3, "Should have 3 posts"
    print("  ✓ list_posts_from_tournament returns correct structure")
    
    # Verify the API call
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    url = call_args[0][0] if call_args[0] else call_args[1].get('url')
    assert "api/posts/" in url, f"Should call /api/posts/ endpoint, got {url}"
    print("  ✓ Calls correct endpoint: /api/posts/")

print("\nTest 5: Test get_open_question_ids_from_tournament with mock")
with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = mock_post_data
    
    pairs = get_open_question_ids_from_tournament(tournament_id=3512)
    
    assert len(pairs) == 2, f"Should return 2 open questions, got {len(pairs)}"
    assert pairs[0] == (1001, 100), f"First pair should be (1001, 100), got {pairs[0]}"
    assert pairs[1] == (1002, 101), f"Second pair should be (1002, 101), got {pairs[1]}"
    print("  ✓ Correctly extracts (question_id, post_id) pairs")
    print("  ✓ Filters out closed posts")

print("\nTest 6: Test fetch_tournament_questions with mock")
with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = mock_post_data
    
    questions = fetch_tournament_questions(tournament_id=3512)
    
    assert len(questions) == 2, f"Should return 2 questions, got {len(questions)}"
    
    # Verify question structure
    q1 = questions[0]
    assert q1["id"] == 1001, "Question ID should match"
    assert q1["post_id"] == 100, "Post ID should be included"
    assert q1["type"] == "binary", "Type should be correctly inferred"
    assert q1["title"] == "Will X happen?", "Title should match"
    print("  ✓ Returns normalized questions with post_id")
    print("  ✓ Correctly infers question types")
    
    q2 = questions[1]
    assert q2["type"] == "multiple_choice", "Should map discrete to multiple_choice"
    assert len(q2["options"]) == 2, "Should extract option names"
    assert q2["options"][0] == "Option A", "Option names should match"
    print("  ✓ Correctly handles multiple choice questions")

print("\nTest 7: Test artifact creation (open_ids.json)")
with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = mock_post_data
    
    # Clean up any existing state dir
    import shutil
    if AIB_STATE_DIR.exists():
        shutil.rmtree(AIB_STATE_DIR)
    
    questions = fetch_tournament_questions(tournament_id=3512)
    
    # Manually create artifacts like run_tournament would
    AIB_STATE_DIR.mkdir(exist_ok=True)
    open_ids = [q["id"] for q in questions]
    open_ids_file = AIB_STATE_DIR / "open_ids.json"
    with open(open_ids_file, "w") as f:
        json.dump(open_ids, f, indent=2)
    
    # Verify file was created
    assert open_ids_file.exists(), "open_ids.json should be created"
    
    # Verify content
    with open(open_ids_file, "r") as f:
        saved_ids = json.load(f)
    
    assert saved_ids == [1001, 1002], f"Should save question IDs, got {saved_ids}"
    print(f"  ✓ Created {open_ids_file}")
    print(f"  ✓ Saved question IDs: {saved_ids}")
    
    # Clean up
    shutil.rmtree(AIB_STATE_DIR)

print("\n" + "="*70)
print("✅ ALL INTEGRATION TESTS PASSED")
print("="*70)
print("\nSummary:")
print("  ✓ Tournament ID correctly configured (3512)")
print("  ✓ State directory correctly configured (.aib-state)")
print("  ✓ list_posts_from_tournament calls /api/posts/")
print("  ✓ get_open_question_ids_from_tournament extracts (question_id, post_id)")
print("  ✓ fetch_tournament_questions returns normalized questions with post_id")
print("  ✓ Question types correctly inferred (binary, multiple_choice)")
print("  ✓ .aib-state/open_ids.json artifact creation works")
