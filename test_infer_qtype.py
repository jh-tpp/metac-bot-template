"""Test _infer_qtype_and_fields with nested question objects"""
import sys
import os

# Add the main module to the path using relative directory
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from main import _infer_qtype_and_fields, _classify_question, _get_core_question

# Test with nested 'question' object
test_nested = {
    "id": 578,
    "question": {
        "id": 578,
        "title": "Will AGI be developed by 2030?",
        "description": "Resolution criteria...",
        "possibilities": {
            "type": "binary"
        }
    }
}

print("="*70)
print("Test: _infer_qtype_and_fields with nested question")
print("="*70)
qtype, extra = _infer_qtype_and_fields(test_nested)
print(f"Question type: {qtype}")
print(f"Extra fields: {extra}")
assert qtype == "binary", f"Expected 'binary', got '{qtype}'"
print("✓ Test passed")

# Also test with new function
print("\nVerifying with _classify_question:")
qtype_new, options_new = _classify_question(test_nested)
print(f"Question type: {qtype_new}")
print(f"Options: {options_new}")
assert qtype_new == "binary", f"Expected 'binary', got '{qtype_new}'"
print("✓ New function matches\n")

# Test with discrete type
test_discrete = {
    "question": {
        "id": 12345,
        "title": "Multiple choice",
        "possibilities": {
            "type": "discrete",
            "outcomes": [
                {"name": "Option A"},
                {"name": "Option B"}
            ]
        }
    }
}

print("="*70)
print("Test: _infer_qtype_and_fields with discrete type")
print("="*70)
qtype, extra = _infer_qtype_and_fields(test_discrete)
print(f"Question type: {qtype}")
print(f"Extra fields: {extra}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert "options" in extra
assert len(extra["options"]) == 2
print("✓ Test passed")

# Also test with new function
print("\nVerifying with _classify_question:")
qtype_new, options_new = _classify_question(test_discrete)
print(f"Question type: {qtype_new}")
print(f"Options: {options_new}")
assert qtype_new == "multiple_choice", f"Expected 'multiple_choice', got '{qtype_new}'"
assert len(options_new) == 2
print("✓ New function matches\n")

# Test with continuous type
test_continuous = {
    "question": {
        "id": 14333,
        "title": "Numeric question",
        "possibilities": {
            "type": "continuous",
            "range": [0, 100]
        }
    }
}

print("="*70)
print("Test: _infer_qtype_and_fields with continuous type")
print("="*70)
qtype, extra = _infer_qtype_and_fields(test_continuous)
print(f"Question type: {qtype}")
print(f"Extra fields: {extra}")
assert qtype == "numeric", f"Expected 'numeric', got '{qtype}'"
assert "numeric_bounds" in extra
assert extra["numeric_bounds"]["min"] == 0
assert extra["numeric_bounds"]["max"] == 100
print("✓ Test passed")

# Also test with new function
print("\nVerifying with _classify_question:")
qtype_new, options_new = _classify_question(test_continuous)
print(f"Question type: {qtype_new}")
print(f"Options: {options_new}")
assert qtype_new == "numeric", f"Expected 'numeric', got '{qtype_new}'"
print("✓ New function matches\n")

print("="*70)
print("ALL TESTS PASSED ✓")
print("="*70)
print("\nBackward compatibility verified:")
print("  ✓ _infer_qtype_and_fields still works correctly")
print("  ✓ _classify_question produces compatible results")
