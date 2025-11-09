"""
Test that tournament modes handle zero open questions gracefully.
"""
import os
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch
import shutil

print("="*70)
print("ZERO QUESTIONS TEST: Graceful handling")
print("="*70)

# Set up environment
os.environ['OPENROUTER_API_KEY'] = 'test_key'
os.environ['METACULUS_TOKEN'] = 'test_token'

import main
from main import (
    tournament_dryrun,
    run_tournament,
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

print("\nTest 1: tournament_dryrun with zero questions")
print("-" * 60)

# Clean up before test
cleanup_artifacts()

# Mock empty response
empty_post_data = {
    "results": []
}

with patch('main.list_posts_from_tournament') as mock_list:
    mock_list.return_value = empty_post_data
    
    # Run tournament_dryrun - should NOT raise an error
    try:
        tournament_dryrun()
        print("  ✓ tournament_dryrun completed without error")
    except Exception as e:
        print(f"  ✗ tournament_dryrun raised error: {e}")
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
    
    # Verify mc_results.json was created
    assert Path("mc_results.json").exists(), "mc_results.json should exist"
    print("  ✓ Created mc_results.json")
    
    # Verify mc_results.json structure
    with open("mc_results.json", "r") as f:
        results = json.load(f)
    
    # Should have results key with empty array and count of 0
    assert "results" in results or isinstance(results, list), "Should have results structure"
    if isinstance(results, list):
        assert len(results) == 0, f"Results should be empty, got {len(results)} items"
        print("  ✓ mc_results.json contains empty list")
    else:
        assert results.get("results", []) == [], "Results should be empty"
        assert results.get("count", -1) == 0, "Count should be 0"
        print("  ✓ mc_results.json has correct summary structure")

# Clean up after test
cleanup_artifacts()

print("\nTest 2: tournament_real (run_tournament) with zero questions")
print("-" * 60)

# Mock empty tournament questions
with patch('main.fetch_tournament_questions') as mock_fetch:
    mock_fetch.return_value = []
    
    # Run tournament in submit mode - should NOT raise an error
    try:
        run_tournament(mode="submit", publish=False)
        print("  ✓ run_tournament completed without error")
    except Exception as e:
        print(f"  ✗ run_tournament raised error: {e}")
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
    
    # Verify mc_results.json was created
    assert Path("mc_results.json").exists(), "mc_results.json should exist"
    print("  ✓ Created mc_results.json")
    
    # Verify mc_results.json structure
    with open("mc_results.json", "r") as f:
        results = json.load(f)
    
    # Should have results key with empty array and count of 0
    assert "results" in results or isinstance(results, list), "Should have results structure"
    if isinstance(results, list):
        assert len(results) == 0, f"Results should be empty, got {len(results)} items"
        print("  ✓ mc_results.json contains empty list")
    else:
        assert results.get("results", []) == [], "Results should be empty"
        assert results.get("count", -1) == 0, "Count should be 0"
        print("  ✓ mc_results.json has correct summary structure")

# Clean up after test
cleanup_artifacts()

print("\nTest 3: tournament_real with publish=True and zero questions")
print("-" * 60)

# Mock empty tournament questions
with patch('main.fetch_tournament_questions') as mock_fetch:
    mock_fetch.return_value = []
    
    # Run tournament in submit mode with publish - should NOT raise an error
    try:
        run_tournament(mode="submit", publish=True)
        print("  ✓ run_tournament with publish=True completed without error")
    except Exception as e:
        print(f"  ✗ run_tournament raised error: {e}")
        sys.exit(1)
    
    # Verify artifacts exist
    assert (AIB_STATE_DIR / "open_ids.json").exists(), "open_ids.json should exist"
    assert Path("mc_results.json").exists(), "mc_results.json should exist"
    print("  ✓ All artifacts created")
    
    # Verify posted_ids.json was created with empty array
    assert Path("posted_ids.json").exists(), "posted_ids.json should exist in submit mode"
    with open("posted_ids.json", "r") as f:
        posted_ids = json.load(f)
    assert posted_ids == [], f"posted_ids should be empty array, got {posted_ids}"
    print("  ✓ posted_ids.json created with empty array")

# Clean up final artifacts
cleanup_artifacts()

print("\n" + "="*70)
print("✅ ALL ZERO QUESTIONS TESTS PASSED")
print("="*70)
print("\nSummary:")
print("  ✓ tournament_dryrun handles zero questions gracefully")
print("  ✓ run_tournament handles zero questions gracefully")
print("  ✓ All required artifacts created even when empty")
print("  ✓ open_ids.json contains empty array []")
print("  ✓ mc_results.json contains proper empty structure")
print("  ✓ posted_ids.json created in submit mode with empty array")
print("  ✓ No errors raised (exit code 0)")
