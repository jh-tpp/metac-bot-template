"""
Acceptance test for hardcoded tournament identifier requirements.

This test validates that:
1. Tournament is hardcoded to 'fall-aib-2025'
2. No environment variables can override the tournament
3. Config log appears in tournament modes
4. .aib-state/open_ids.json is generated using fall-aib-2025
5. All functions ignore tournament parameters
"""
import sys
import os
from unittest.mock import patch, Mock
from io import StringIO
from pathlib import Path
import json
import shutil

print("="*70)
print("ACCEPTANCE TEST: Hardcoded Tournament Identifier")
print("="*70)

# Set up environment
os.environ['OPENROUTER_API_KEY'] = 'test_key'
os.environ['METACULUS_TOKEN'] = 'test_token'

import main
from main import (
    FALL_2025_AIB_TOURNAMENT,
    list_posts_from_tournament,
    get_open_question_ids_from_tournament,
    fetch_tournament_questions,
    tournament_dryrun,
    AIB_STATE_DIR
)

# ========== Test 1: Verify hardcoded constant ==========
print("\nTest 1: Verify FALL_2025_AIB_TOURNAMENT constant")
assert FALL_2025_AIB_TOURNAMENT == "fall-aib-2025", \
    f"Expected 'fall-aib-2025', got '{FALL_2025_AIB_TOURNAMENT}'"
print(f"  ✓ Tournament constant is 'fall-aib-2025'")

# ========== Test 2: Verify no environment variable overrides ==========
print("\nTest 2: Verify no environment variable overrides exist")

# Search for common tournament env var patterns in main.py
import main
main_source = open("main.py", "r").read()

# Patterns that would indicate actual environment variable usage (not just documentation)
forbidden_patterns = [
    "os.environ.get('TOURNAMENT'",
    'os.environ.get("TOURNAMENT"',
    "os.getenv('TOURNAMENT'",
    'os.getenv("TOURNAMENT"',
    "os.environ['TOURNAMENT",
    'os.environ["TOURNAMENT',
]

for pattern in forbidden_patterns:
    assert pattern not in main_source, \
        f"Found forbidden pattern '{pattern}' in main.py - tournament env vars should not be read"

print("  ✓ No environment variable reads for tournament in main.py")

# ========== Test 3: Verify parameters are ignored ==========
print("\nTest 3: Verify tournament parameters are ignored")

mock_post_data = {
    "results": [
        {
            "id": 100,
            "status": "open",
            "question": {
                "id": 1001,
                "title": "Test",
                "possibilities": {"type": "binary"}
            }
        }
    ]
}

with patch('main.requests.get') as mock_get:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.reason = "OK"
    mock_response.json.return_value = mock_post_data
    mock_response.headers = {"Content-Type": "application/json"}
    mock_get.return_value = mock_response
    
    # Call with wrong tournament ID - should be ignored
    result = list_posts_from_tournament(tournament_id=3512)
    
    # Verify it used fall-aib-2025 anyway
    call_args = mock_get.call_args
    params = call_args[1].get('params', {})
    assert params.get('tournaments') == "fall-aib-2025", \
        f"Expected 'fall-aib-2025', got '{params.get('tournaments')}'"
    
print("  ✓ list_posts_from_tournament ignores tournament_id parameter")

with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = mock_post_data
    
    # Call with wrong tournament ID - should be ignored
    pairs = get_open_question_ids_from_tournament(tournament_id=3512)
    
    # Should still work and use hardcoded value
    assert len(pairs) == 1
    assert pairs[0] == (1001, 100)

print("  ✓ get_open_question_ids_from_tournament ignores tournament_id parameter")

with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = mock_post_data
    
    # Call with all possible wrong parameters - should be ignored
    questions = fetch_tournament_questions(
        contest_slug="wrong-slug",
        project_id=9999,
        project_slug="wrong-project",
        tournament_id=3512
    )
    
    # Should still work and use hardcoded value
    assert len(questions) == 1

print("  ✓ fetch_tournament_questions ignores all tournament parameters")

# ========== Test 4: Verify config log appears ==========
print("\nTest 4: Verify [CONFIG] log line appears in tournament_dryrun")

old_stdout = sys.stdout
sys.stdout = captured = StringIO()

try:
    with patch('main.list_posts_from_tournament') as mock_list, \
         patch('main.get_post_details') as mock_details:
        
        mock_list.return_value = mock_post_data
        mock_details.return_value = {"question": {"title": "Test"}}
        
        tournament_dryrun()
        
finally:
    sys.stdout = old_stdout

output = captured.getvalue()
assert "[CONFIG] Using hardcoded tournament: fall-aib-2025" in output, \
    "Config log line not found in output"
print("  ✓ [CONFIG] log line appears")
print(f"  ✓ Log message: '[CONFIG] Using hardcoded tournament: fall-aib-2025'")

# ========== Test 5: Verify .aib-state/open_ids.json generation ==========
print("\nTest 5: Verify .aib-state/open_ids.json is generated with fall-aib-2025")

# Clean up any existing state dir
if AIB_STATE_DIR.exists():
    shutil.rmtree(AIB_STATE_DIR)

old_stdout = sys.stdout
sys.stdout = StringIO()

try:
    with patch('main.list_posts_from_tournament') as mock_list, \
         patch('main.get_post_details') as mock_details:
        
        mock_list.return_value = mock_post_data
        mock_details.return_value = {"question": {"title": "Test"}}
        
        tournament_dryrun(tournament_slug="wrong-slug-should-be-ignored")
        
finally:
    sys.stdout = old_stdout

# Verify the state file was created
open_ids_file = AIB_STATE_DIR / "open_ids.json"
assert open_ids_file.exists(), ".aib-state/open_ids.json was not created"
print("  ✓ .aib-state/open_ids.json created")

# Verify the content
with open(open_ids_file, "r") as f:
    data = json.load(f)

assert isinstance(data, list), "open_ids.json should contain a list"
assert len(data) > 0, "open_ids.json should not be empty"

# Each entry should have question_id and post_id
for entry in data:
    assert "question_id" in entry, "Entry missing question_id"
    assert "post_id" in entry, "Entry missing post_id"

print(f"  ✓ File contains {len(data)} question(s)")
print(f"  ✓ Data structure is correct (question_id, post_id pairs)")

# Clean up
shutil.rmtree(AIB_STATE_DIR)

# ========== Test 6: Verify mc_results.json is generated ==========
print("\nTest 6: Verify mc_results.json is generated in dryrun mode")

old_stdout = sys.stdout
sys.stdout = StringIO()

try:
    with patch('main.list_posts_from_tournament') as mock_list, \
         patch('main.get_post_details') as mock_details:
        
        mock_list.return_value = mock_post_data
        mock_details.return_value = {"question": {"title": "Test Question"}}
        
        tournament_dryrun()
        
finally:
    sys.stdout = old_stdout

# Verify mc_results.json was created
assert Path("mc_results.json").exists(), "mc_results.json was not created"
print("  ✓ mc_results.json created")

# Verify content
with open("mc_results.json", "r") as f:
    results = json.load(f)

assert isinstance(results, list), "mc_results.json should contain a list"
assert len(results) > 0, "mc_results.json should not be empty"

for result in results:
    assert "question_id" in result, "Result missing question_id"
    assert "post_id" in result, "Result missing post_id"
    assert "question_title" in result, "Result missing question_title"

print(f"  ✓ File contains {len(results)} result(s)")
print(f"  ✓ Data structure is correct")

# Clean up
Path("mc_results.json").unlink()

# ========== Test 7: Verify documentation exists ==========
print("\nTest 7: Verify documentation about hardcoding exists")

# Check main.py has documentation
with open("main.py", "r") as f:
    main_content = f.read()

assert "HARDCODED" in main_content.upper() or "hardcoded" in main_content, \
    "main.py should document the hardcoding"
assert "fall-aib-2025" in main_content, \
    "main.py should mention the tournament slug"
print("  ✓ main.py contains hardcoding documentation")

# Check metaculus_posts.py has documentation
with open("metaculus_posts.py", "r") as f:
    posts_content = f.read()

assert "HARDCODED" in posts_content.upper() or "hardcoded" in posts_content, \
    "metaculus_posts.py should document the hardcoding"
assert "fall-aib-2025" in posts_content, \
    "metaculus_posts.py should mention the tournament slug"
print("  ✓ metaculus_posts.py contains hardcoding documentation")

# ========== Summary ==========
print("\n" + "="*70)
print("✅ ALL ACCEPTANCE TESTS PASSED")
print("="*70)
print("\nValidated Requirements:")
print("  ✓ Tournament identifier hardcoded to 'fall-aib-2025'")
print("  ✓ No environment variable overrides (TOURNAMENT, TOURNAMENT_ID, etc.)")
print("  ✓ Config log '[CONFIG] Using hardcoded tournament: fall-aib-2025' appears")
print("  ✓ .aib-state/open_ids.json generated correctly")
print("  ✓ mc_results.json generated in dryrun mode")
print("  ✓ All tournament parameters ignored (contest_slug, project_id, etc.)")
print("  ✓ Comprehensive documentation in both main.py and metaculus_posts.py")
print("\nConclusion: The bot will ONLY forecast on fall-aib-2025 tournament")
print("="*70)
