"""
Tests for tournament workflow improvements.

This test suite validates:
1. fetch_open_pairs() returns correct format and writes .aib-state/open_ids.json
2. posted_ids tracking prevents duplicate submissions
3. --force flag bypasses posted list
"""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import functions to test
from main import (
    fetch_open_pairs,
    _load_posted_ids,
    _append_posted_id,
    _ensure_state_dir,
    run_tournament,
    AIB_STATE_DIR,
)


def setup_temp_workspace():
    """Create a temporary workspace and return the path."""
    temp_dir = tempfile.mkdtemp()
    
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    
    return temp_dir, original_cwd


def cleanup_temp_workspace(temp_dir, original_cwd):
    """Clean up temp workspace."""
    os.chdir(original_cwd)
    shutil.rmtree(temp_dir)


def test_fetch_open_pairs_writes_state():
    """Test that fetch_open_pairs writes .aib-state/open_ids.json with correct format."""
    temp_dir, original_cwd = setup_temp_workspace()
    
    try:
        # Mock get_open_question_ids_from_tournament to return test data
        mock_pairs = [
            (12345, 67890),
            (12346, 67891),
            (12347, 67892),
        ]
        
        with patch('main.get_open_question_ids_from_tournament', return_value=mock_pairs):
            # Call function
            result = fetch_open_pairs()
            
            # Verify return value
            assert result == mock_pairs, f"Expected {mock_pairs}, got {result}"
            
            # Verify .aib-state/open_ids.json was created
            state_file = Path(".aib-state/open_ids.json")
            assert state_file.exists(), ".aib-state/open_ids.json should exist"
            
            # Verify content format
            with open(state_file, "r") as f:
                content = json.load(f)
            
            assert isinstance(content, list), "Content should be a list"
            assert len(content) == 3, f"Expected 3 items, got {len(content)}"
            
            # Verify each item has question_id and post_id
            for item in content:
                assert "question_id" in item, "Item should have question_id"
                assert "post_id" in item, "Item should have post_id"
            
            # Verify values
            assert content[0]["question_id"] == 12345
            assert content[0]["post_id"] == 67890
            
            print("✓ test_fetch_open_pairs_writes_state passed")
    
    finally:
        cleanup_temp_workspace(temp_dir, original_cwd)


def test_posted_ids_tracking():
    """Test that posted_ids tracking prevents duplicates."""
    temp_dir, original_cwd = setup_temp_workspace()
    
    try:
        # Ensure state directory exists
        _ensure_state_dir()
        
        # Initially should be empty
        posted = _load_posted_ids()
        assert posted == set(), f"Expected empty set, got {posted}"
        
        # Append some IDs
        _append_posted_id(12345)
        _append_posted_id(12346)
        
        # Load and verify
        posted = _load_posted_ids()
        assert 12345 in posted, "12345 should be in posted_ids"
        assert 12346 in posted, "12346 should be in posted_ids"
        assert len(posted) == 2, f"Expected 2 items, got {len(posted)}"
        
        # Append duplicate - should not create duplicate
        _append_posted_id(12345)
        posted = _load_posted_ids()
        assert len(posted) == 2, f"Duplicate should not be added, expected 2 items, got {len(posted)}"
        
        # Verify file format
        with open(Path(".aib-state/posted_ids.json"), "r") as f:
            content = json.load(f)
        assert isinstance(content, list), "Content should be a list"
        assert sorted(content) == sorted([12345, 12346]), f"Expected sorted IDs, got {content}"
        
        print("✓ test_posted_ids_tracking passed")
    
    finally:
        cleanup_temp_workspace(temp_dir, original_cwd)


def test_force_flag_bypasses_posted():
    """Test that --force flag causes run_tournament to ignore posted_ids."""
    temp_dir, original_cwd = setup_temp_workspace()
    
    try:
        # Setup: Create posted_ids.json with some IDs
        _ensure_state_dir()
        _append_posted_id(12345)
        _append_posted_id(12346)
        
        # Mock dependencies
        mock_questions = [
            {
                "id": 12345,
                "type": "binary",
                "title": "Test Q1",
                "description": "Test",
                "post_id": 67890,
            },
            {
                "id": 12346,
                "type": "binary",
                "title": "Test Q2",
                "description": "Test",
                "post_id": 67891,
            },
            {
                "id": 12347,
                "type": "binary",
                "title": "Test Q3",
                "description": "Test",
                "post_id": 67892,
            },
        ]
        
        with patch('main.fetch_tournament_questions', return_value=mock_questions):
            with patch('main.fetch_facts_for_batch', return_value={}):
                with patch('main.run_mc_worlds') as mock_mc:
                    with patch('main.post_forecast_safe') as mock_post:
                        # Configure mocks
                        mock_mc.return_value = {
                            "p": 0.5,
                            "world_summaries": ["Test summary"]
                        }
                        mock_post.return_value = True
                        
                        # Test 1: Without force, should skip posted questions
                        run_tournament(mode="submit", publish=False, force=False)
                        
                        # Should only process Q3 (12347)
                        assert mock_mc.call_count == 1, f"Expected 1 MC call without force, got {mock_mc.call_count}"
                        
                        # Reset mocks
                        mock_mc.reset_mock()
                        mock_post.reset_mock()
                        
                        # Test 2: With force, should process all questions
                        run_tournament(mode="submit", publish=False, force=True)
                        
                        # Should process all 3 questions
                        assert mock_mc.call_count == 3, f"Expected 3 MC calls with force, got {mock_mc.call_count}"
        
        print("✓ test_force_flag_bypasses_posted passed")
    
    finally:
        cleanup_temp_workspace(temp_dir, original_cwd)


def test_empty_tournament_handling():
    """Test that empty tournament is handled gracefully."""
    temp_dir, original_cwd = setup_temp_workspace()
    
    try:
        # Mock empty tournament
        with patch('main.get_open_question_ids_from_tournament', return_value=[]):
            result = fetch_open_pairs()
            
            # Should return empty list
            assert result == [], f"Expected empty list, got {result}"
            
            # Should still write .aib-state/open_ids.json
            state_file = Path(".aib-state/open_ids.json")
            assert state_file.exists(), ".aib-state/open_ids.json should exist"
            
            with open(state_file, "r") as f:
                content = json.load(f)
            assert content == [], f"Expected empty list in file, got {content}"
        
        print("✓ test_empty_tournament_handling passed")
    
    finally:
        cleanup_temp_workspace(temp_dir, original_cwd)


def test_posted_ids_atomic_write():
    """Test that _append_posted_id uses atomic writes."""
    temp_dir, original_cwd = setup_temp_workspace()
    
    try:
        _ensure_state_dir()
        
        # Add some IDs
        _append_posted_id(12345)
        
        # Verify .tmp file is not left behind
        temp_files = list(Path(".aib-state").glob("*.tmp"))
        assert len(temp_files) == 0, f"Temporary file should be cleaned up, found {temp_files}"
        
        # Verify final file exists
        final_file = Path(".aib-state/posted_ids.json")
        assert final_file.exists(), "Final file should exist"
        
        print("✓ test_posted_ids_atomic_write passed")
    
    finally:
        cleanup_temp_workspace(temp_dir, original_cwd)


if __name__ == "__main__":
    print("Running tournament workflow tests...\n")
    
    test_fetch_open_pairs_writes_state()
    test_posted_ids_tracking()
    test_force_flag_bypasses_posted()
    test_empty_tournament_handling()
    test_posted_ids_atomic_write()
    
    print("\n✅ All tournament workflow tests passed!")
