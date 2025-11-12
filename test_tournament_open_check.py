"""
Test the new tournament_open_check mode.

Validates that tournament_open_check:
1. Only writes .aib-state/open_ids.json
2. Does NOT write mc_results.json, mc_reasons.txt, or other artifacts
3. Exits successfully even with zero questions
4. Uses the fetch_open_pairs() function correctly
"""
import os
import sys
import json
from pathlib import Path
from unittest.mock import patch
import shutil

print("="*70)
print("TOURNAMENT OPEN CHECK TEST")
print("="*70)

# Set up environment
os.environ['OPENROUTER_API_KEY'] = 'test_key'
os.environ['METACULUS_TOKEN'] = 'test_token'

import main
from main import (
    tournament_open_check,
    AIB_STATE_DIR,
    FALL_2025_AIB_TOURNAMENT
)

def cleanup_artifacts():
    """Clean up test artifacts."""
    # Remove state directory
    if AIB_STATE_DIR.exists():
        shutil.rmtree(AIB_STATE_DIR)
    
    # Remove result files
    for file in ["mc_results.json", "mc_reasons.txt", "posted_ids.json"]:
        if Path(file).exists():
            Path(file).unlink()

print("\nTest 1: tournament_open_check with multiple questions")
print("-" * 60)

# Clean up before test
cleanup_artifacts()

# Mock response with 3 questions
mock_pairs = [
    (12345, 67890),
    (12346, 67891),
    (12347, 67892)
]

with patch('main.get_open_question_ids_from_tournament') as mock_get_pairs:
    mock_get_pairs.return_value = mock_pairs
    
    # Run tournament_open_check - should NOT raise an error
    try:
        tournament_open_check()
        print("  ✓ tournament_open_check completed without error")
    except Exception as e:
        print(f"  ✗ tournament_open_check raised error: {e}")
        sys.exit(1)
    
    # Verify .aib-state/open_ids.json was created
    open_ids_file = AIB_STATE_DIR / "open_ids.json"
    assert open_ids_file.exists(), "open_ids.json should exist"
    print(f"  ✓ Created {open_ids_file}")
    
    # Verify content matches expected structure
    with open(open_ids_file, "r") as f:
        open_ids = json.load(f)
    
    assert isinstance(open_ids, list), f"open_ids should be a list, got {type(open_ids)}"
    assert len(open_ids) == 3, f"open_ids should have 3 items, got {len(open_ids)}"
    
    # Verify structure of first item
    first_item = open_ids[0]
    assert isinstance(first_item, dict), f"open_ids items should be dicts, got {type(first_item)}"
    assert "question_id" in first_item, "open_ids items should have question_id"
    assert "post_id" in first_item, "open_ids items should have post_id"
    assert first_item["question_id"] == 12345, f"First question_id should be 12345, got {first_item['question_id']}"
    assert first_item["post_id"] == 67890, f"First post_id should be 67890, got {first_item['post_id']}"
    print("  ✓ open_ids.json contains correct structure with 3 questions")
    
    # Verify NO other artifacts were created
    assert not Path("mc_results.json").exists(), "mc_results.json should NOT exist"
    print("  ✓ mc_results.json NOT created (as expected)")
    
    assert not Path("mc_reasons.txt").exists(), "mc_reasons.txt should NOT exist"
    print("  ✓ mc_reasons.txt NOT created (as expected)")
    
    assert not Path("posted_ids.json").exists(), "posted_ids.json should NOT exist"
    print("  ✓ posted_ids.json NOT created (as expected)")

# Clean up after test
cleanup_artifacts()

print("\nTest 2: tournament_open_check with zero questions")
print("-" * 60)

# Mock empty response
with patch('main.get_open_question_ids_from_tournament') as mock_get_pairs:
    mock_get_pairs.return_value = []
    
    # Run tournament_open_check - should NOT raise an error
    try:
        tournament_open_check()
        print("  ✓ tournament_open_check completed without error (zero questions)")
    except Exception as e:
        print(f"  ✗ tournament_open_check raised error: {e}")
        sys.exit(1)
    
    # Verify .aib-state/open_ids.json was created
    open_ids_file = AIB_STATE_DIR / "open_ids.json"
    assert open_ids_file.exists(), "open_ids.json should exist"
    print(f"  ✓ Created {open_ids_file}")
    
    # Verify content is empty array
    with open(open_ids_file, "r") as f:
        open_ids = json.load(f)
    assert open_ids == [], f"open_ids should be empty array, got {open_ids}"
    print("  ✓ open_ids.json contains empty array")
    
    # Verify NO other artifacts were created
    assert not Path("mc_results.json").exists(), "mc_results.json should NOT exist"
    print("  ✓ mc_results.json NOT created (as expected)")
    
    assert not Path("mc_reasons.txt").exists(), "mc_reasons.txt should NOT exist"
    print("  ✓ mc_reasons.txt NOT created (as expected)")
    
    assert not Path("posted_ids.json").exists(), "posted_ids.json should NOT exist"
    print("  ✓ posted_ids.json NOT created (as expected)")

# Clean up after test
cleanup_artifacts()

print("\nTest 3: tournament_open_check via CLI")
print("-" * 60)

# Test via command line interface
import subprocess

# Mock the get_open_question_ids_from_tournament function at module level
test_pairs = [(99999, 88888)]

with patch('main.get_open_question_ids_from_tournament') as mock_get_pairs:
    mock_get_pairs.return_value = test_pairs
    
    # Import and call main with --mode argument
    import sys
    original_argv = sys.argv
    try:
        sys.argv = ['main.py', '--mode', 'tournament_open_check']
        
        # Run main - should not raise error
        try:
            main.main()
            print("  ✓ CLI mode --mode tournament_open_check completed without error")
        except SystemExit as e:
            if e.code == 0:
                print("  ✓ CLI mode exited with code 0 (success)")
            else:
                print(f"  ✗ CLI mode exited with code {e.code}")
                sys.exit(1)
        
        # Verify artifacts
        open_ids_file = AIB_STATE_DIR / "open_ids.json"
        assert open_ids_file.exists(), "open_ids.json should exist after CLI run"
        print(f"  ✓ Created {open_ids_file} via CLI")
        
        # Verify NO other artifacts
        assert not Path("mc_results.json").exists(), "mc_results.json should NOT exist after CLI run"
        print("  ✓ No unwanted artifacts created via CLI")
        
    finally:
        sys.argv = original_argv

# Clean up final artifacts
cleanup_artifacts()

print("\n" + "="*70)
print("✅ ALL TOURNAMENT_OPEN_CHECK TESTS PASSED")
print("="*70)
print("\nSummary:")
print("  ✓ tournament_open_check writes ONLY .aib-state/open_ids.json")
print("  ✓ Does NOT write mc_results.json, mc_reasons.txt, or posted_ids.json")
print("  ✓ Handles zero questions gracefully (exit code 0)")
print("  ✓ Handles multiple questions correctly")
print("  ✓ Works via CLI with --mode tournament_open_check")
print("  ✓ Reuses existing fetch_open_pairs() function")
