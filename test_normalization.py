#!/usr/bin/env python3
"""
Unit tests for Metaculus API v2 normalization.
Tests the _infer_qtype_and_fields function with v2 API response structures.
"""

import sys
from main import _infer_qtype_and_fields, _get_core_question


def test_v2_binary_question():
    """Test binary question with nested question object."""
    q = {
        "id": 578,
        "question": {
            "id": 578,
            "title": "Will AI achieve X by 2030?",
            "description": "Binary question",
            "possibilities": {
                "type": "binary"
            }
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "binary", f"Expected 'binary', got '{qtype}'"
    print("✓ test_v2_binary_question passed")


def test_v2_discrete_to_multiple_choice():
    """Test discrete question mapping to multiple_choice."""
    q = {
        "id": 22427,
        "question": {
            "id": 22427,
            "title": "Which option will win?",
            "description": "Multiple choice question",
            "possibilities": {
                "type": "discrete",
                "outcomes": [
                    {"name": "Option A"},
                    {"label": "Option B"},
                    {"name": "Option C"}
                ]
            }
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
    assert "options" in extra, "Expected 'options' in extra"
    assert len(extra["options"]) == 3, f"Expected 3 options, got {len(extra['options'])}"
    assert extra["options"] == ["Option A", "Option B", "Option C"], f"Unexpected options: {extra['options']}"
    print("✓ test_v2_discrete_to_multiple_choice passed")


def test_v2_continuous_to_numeric():
    """Test continuous question mapping to numeric."""
    q = {
        "id": 14333,
        "question": {
            "id": 14333,
            "title": "What will be the value?",
            "description": "Numeric question",
            "possibilities": {
                "type": "continuous",
                "range": [0, 100],
                "unit": "percentage",
                "scale": "linear"
            }
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "numeric", f"Expected 'numeric', got '{qtype}'"
    assert "numeric_bounds" in extra, "Expected 'numeric_bounds' in extra"
    assert extra["numeric_bounds"]["min"] == 0, f"Expected min=0, got {extra['numeric_bounds'].get('min')}"
    assert extra["numeric_bounds"]["max"] == 100, f"Expected max=100, got {extra['numeric_bounds'].get('max')}"
    assert extra["numeric_bounds"]["unit"] == "percentage", f"Expected unit='percentage'"
    assert extra["numeric_bounds"]["scale"] == "linear", f"Expected scale='linear'"
    print("✓ test_v2_continuous_to_numeric passed")


def test_v2_continuous_min_max():
    """Test continuous question with min/max instead of range."""
    q = {
        "id": 14334,
        "question": {
            "id": 14334,
            "title": "What will be the temperature?",
            "description": "Numeric question",
            "possibilities": {
                "type": "continuous",
                "min": -10,
                "max": 50
            }
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "numeric", f"Expected 'numeric', got '{qtype}'"
    assert "numeric_bounds" in extra, "Expected 'numeric_bounds' in extra"
    assert extra["numeric_bounds"]["min"] == -10, f"Expected min=-10, got {extra['numeric_bounds'].get('min')}"
    assert extra["numeric_bounds"]["max"] == 50, f"Expected max=50, got {extra['numeric_bounds'].get('max')}"
    print("✓ test_v2_continuous_min_max passed")


def test_flat_structure_fallback():
    """Test that flat structure (non-nested) still works."""
    q = {
        "id": 12345,
        "title": "Flat question",
        "description": "No nested question object",
        "possibility": {
            "type": "binary"
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "binary", f"Expected 'binary', got '{qtype}'"
    print("✓ test_flat_structure_fallback passed")


def test_get_core_question():
    """Test _get_core_question helper pivots correctly."""
    # Nested structure
    q1 = {
        "id": 1,
        "question": {
            "id": 1,
            "title": "Nested"
        }
    }
    core1 = _get_core_question(q1)
    assert core1["title"] == "Nested", "Should pivot into nested question"
    
    # Flat structure
    q2 = {
        "id": 2,
        "title": "Flat"
    }
    core2 = _get_core_question(q2)
    assert core2["title"] == "Flat", "Should return flat structure as-is"
    
    # None/empty
    core3 = _get_core_question(None)
    assert core3 == {}, "Should return empty dict for None"
    
    print("✓ test_get_core_question passed")


def test_discrete_with_fallback_options():
    """Test discrete question that falls back to core.options."""
    q = {
        "id": 22428,
        "question": {
            "id": 22428,
            "title": "Choose an option",
            "possibilities": {
                "type": "discrete"
            },
            "options": [
                {"name": "Alpha"},
                {"label": "Beta"},
                "Gamma"
            ]
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
    assert "options" in extra, "Expected 'options' in extra"
    assert len(extra["options"]) == 3, f"Expected 3 options, got {len(extra['options'])}"
    assert extra["options"] == ["Alpha", "Beta", "Gamma"], f"Unexpected options: {extra['options']}"
    print("✓ test_discrete_with_fallback_options passed")


def test_outcomes_with_label_fallback():
    """Test that outcomes can use label when name is missing."""
    q = {
        "id": 22429,
        "question": {
            "possibilities": {
                "type": "discrete",
                "outcomes": [
                    {"label": "First"},
                    {"name": "Second"},
                    {"label": "Third"}
                ]
            }
        }
    }
    
    qtype, extra = _infer_qtype_and_fields(q)
    assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
    assert extra["options"] == ["First", "Second", "Third"], f"Unexpected options: {extra['options']}"
    print("✓ test_outcomes_with_label_fallback passed")


def main():
    """Run all tests."""
    tests = [
        test_v2_binary_question,
        test_v2_discrete_to_multiple_choice,
        test_v2_continuous_to_numeric,
        test_v2_continuous_min_max,
        test_flat_structure_fallback,
        test_get_core_question,
        test_discrete_with_fallback_options,
        test_outcomes_with_label_fallback,
    ]
    
    print("Running normalization tests...")
    print("=" * 60)
    
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1
    
    print("=" * 60)
    if failed == 0:
        print(f"All {len(tests)} tests passed!")
        return 0
    else:
        print(f"{failed}/{len(tests)} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
