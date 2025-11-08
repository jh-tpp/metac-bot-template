"""
Test the new modules without requiring network access or API tokens.
"""
import os
import json
import tempfile
from pathlib import Path

def test_http_logging_disabled_by_default():
    """Test that HTTP logging is disabled by default."""
    import http_logging
    assert http_logging.HTTP_LOGGING_ENABLED is False, "HTTP logging should be disabled by default"
    assert http_logging._enabled() is False, "_enabled() should return False by default"
    print("✓ HTTP logging is disabled by default")


def test_http_logging_can_be_enabled():
    """Test that HTTP logging can be enabled via env var."""
    # Save original value
    original = os.environ.get("HTTP_LOGGING_ENABLED")
    try:
        # Enable logging
        os.environ["HTTP_LOGGING_ENABLED"] = "true"
        # Reload module to pick up env var
        import importlib
        import http_logging
        importlib.reload(http_logging)
        assert http_logging.HTTP_LOGGING_ENABLED is True, "HTTP logging should be enabled when env var is set"
        print("✓ HTTP logging can be enabled")
    finally:
        # Restore original value
        if original is not None:
            os.environ["HTTP_LOGGING_ENABLED"] = original
        else:
            os.environ.pop("HTTP_LOGGING_ENABLED", None)
        # Reload again to restore default
        importlib.reload(http_logging)


def test_metaculus_fetch_imports():
    """Test that metaculus_fetch module imports correctly."""
    import metaculus_fetch
    assert hasattr(metaculus_fetch, "FetchError"), "FetchError should be defined"
    assert hasattr(metaculus_fetch, "fetch_post"), "fetch_post should be defined"
    assert hasattr(metaculus_fetch, "fetch_question"), "fetch_question should be defined"
    assert hasattr(metaculus_fetch, "fetch_question_with_fallback"), "fetch_question_with_fallback should be defined"
    print("✓ metaculus_fetch module imports correctly")


def test_metaculus_posts_imports():
    """Test that metaculus_posts module imports correctly."""
    import metaculus_posts
    assert hasattr(metaculus_posts, "list_posts_from_tournament"), "list_posts_from_tournament should be defined"
    assert hasattr(metaculus_posts, "get_open_question_ids_from_tournament"), "get_open_question_ids_from_tournament should be defined"
    assert hasattr(metaculus_posts, "get_post_details"), "get_post_details should be defined"
    assert metaculus_posts.FALL_2025_AIB_TOURNAMENT == "fall-aib-2025", "FALL_2025_AIB_TOURNAMENT should be 'fall-aib-2025'"
    print("✓ metaculus_posts module imports correctly")


def test_main_helpers():
    """Test that main.py helper functions are accessible."""
    import main
    assert hasattr(main, "_ensure_state_dir"), "_ensure_state_dir should be defined"
    assert hasattr(main, "_write_open_ids"), "_write_open_ids should be defined"
    assert hasattr(main, "tournament_dryrun"), "tournament_dryrun should be defined"
    print("✓ main.py helper functions are accessible")


def test_state_dir_helpers():
    """Test state directory helpers work correctly."""
    import main
    
    # Use a temp directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        test_state_dir = Path(tmpdir) / ".aib-state"
        
        # Temporarily override AIB_STATE_DIR
        original_dir = main.AIB_STATE_DIR
        try:
            main.AIB_STATE_DIR = test_state_dir
            
            # Test _ensure_state_dir
            main._ensure_state_dir()
            assert test_state_dir.exists(), "State directory should be created"
            assert test_state_dir.is_dir(), "State directory should be a directory"
            
            # Test _write_open_ids
            test_pairs = [(123, 456), (789, 101112)]
            main._write_open_ids(test_pairs)
            
            # Verify file was created
            open_ids_file = test_state_dir / "open_ids.json"
            assert open_ids_file.exists(), "open_ids.json should be created"
            
            # Verify content
            with open(open_ids_file) as f:
                data = json.load(f)
            assert len(data) == 2, "Should have 2 entries"
            assert data[0]["question_id"] == 123, "First question_id should be 123"
            assert data[0]["post_id"] == 456, "First post_id should be 456"
            assert data[1]["question_id"] == 789, "Second question_id should be 789"
            assert data[1]["post_id"] == 101112, "Second post_id should be 101112"
            
            print("✓ State directory helpers work correctly")
        finally:
            # Restore original
            main.AIB_STATE_DIR = original_dir


def test_gitignore_updated():
    """Test that .gitignore includes new directories."""
    with open(".gitignore") as f:
        content = f.read()
    assert ".aib-state/" in content, ".aib-state/ should be in .gitignore"
    assert ".http-artifacts/" in content, ".http-artifacts/ should be in .gitignore"
    print("✓ .gitignore updated with new directories")


if __name__ == "__main__":
    print("Running tests...\n")
    test_http_logging_disabled_by_default()
    test_http_logging_can_be_enabled()
    test_metaculus_fetch_imports()
    test_metaculus_posts_imports()
    test_main_helpers()
    test_state_dir_helpers()
    test_gitignore_updated()
    print("\n✅ All tests passed!")
