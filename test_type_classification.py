"""
Test _classify_question with various edge cases.

This test suite validates the new simplified type classification logic
that fixes the issue where Q22427 was incorrectly classified as unknown
when possibilities was empty but core.type and core.options were present.
"""
import sys
import os

# Add the main module to the path using relative directory
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from main import _classify_question

# Test Case 1: possibilities empty dict, core.type == 'multiple_choice', core.options populated
print("="*70)
print("Test 1: Empty possibilities, core.type='multiple_choice', core.options populated")
print("="*70)
test_case_1 = {
    "id": 22427,
    "question": {
        "id": 22427,
        "type": "multiple_choice",
        "title": "Test question with empty possibilities",
        "description": "This mimics Q22427",
        "possibilities": {},  # Empty dict
        "options": [
            {"name": "Option A"},
            {"name": "Option B"},
            {"name": "Option C"}
        ]
    }
}

qtype, options_list = _classify_question(test_case_1)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 3, f"Expected 3 options, got {len(options_list)}"
assert options_list == ["Option A", "Option B", "Option C"], f"Options mismatch: {options_list}"
print("✓ Test 1 passed\n")

# Test Case 2: no possibilities key, core.type == 'multiple_choice'
print("="*70)
print("Test 2: No possibilities key, core.type='multiple_choice'")
print("="*70)
test_case_2 = {
    "id": 99999,
    "question": {
        "id": 99999,
        "type": "multiple_choice",
        "title": "Test with no possibilities key",
        "options": [
            {"name": "Red"},
            {"name": "Blue"}
        ]
    }
}

qtype, options_list = _classify_question(test_case_2)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 2, f"Expected 2 options, got {len(options_list)}"
assert options_list == ["Red", "Blue"], f"Options mismatch: {options_list}"
print("✓ Test 2 passed\n")

# Test Case 3: discrete type with outcomes (normal case)
print("="*70)
print("Test 3: Discrete type with outcomes (normal case)")
print("="*70)
test_case_3 = {
    "question": {
        "id": 12345,
        "title": "Normal discrete question",
        "possibilities": {
            "type": "discrete",
            "outcomes": [
                {"name": "Outcome 1"},
                {"name": "Outcome 2"},
                {"name": "Outcome 3"}
            ]
        }
    }
}

qtype, options_list = _classify_question(test_case_3)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 3, f"Expected 3 options, got {len(options_list)}"
assert options_list == ["Outcome 1", "Outcome 2", "Outcome 3"], f"Options mismatch: {options_list}"
print("✓ Test 3 passed\n")

# Test Case 4: discrete type with empty outcomes, fallback to core.options
print("="*70)
print("Test 4: Discrete type with empty outcomes, fallback to core.options")
print("="*70)
test_case_4 = {
    "question": {
        "id": 88888,
        "type": "discrete",
        "possibilities": {
            "type": "discrete",
            "outcomes": []  # Empty outcomes
        },
        "options": [
            {"name": "Fallback A"},
            {"name": "Fallback B"}
        ]
    }
}

qtype, options_list = _classify_question(test_case_4)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 2, f"Expected 2 options, got {len(options_list)}"
assert options_list == ["Fallback A", "Fallback B"], f"Options mismatch: {options_list}"
print("✓ Test 4 passed\n")

# Test Case 5: binary type
print("="*70)
print("Test 5: Binary type")
print("="*70)
test_case_5 = {
    "question": {
        "id": 578,
        "title": "Binary question",
        "possibilities": {
            "type": "binary"
        }
    }
}

qtype, options_list = _classify_question(test_case_5)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "binary", f"Expected 'binary', got '{qtype}'"
assert len(options_list) == 0, f"Expected empty options list, got {options_list}"
print("✓ Test 5 passed\n")

# Test Case 6: numeric/continuous type
print("="*70)
print("Test 6: Numeric/continuous type")
print("="*70)
test_case_6 = {
    "question": {
        "id": 14333,
        "title": "Numeric question",
        "possibilities": {
            "type": "continuous",
            "range": [0, 100]
        }
    }
}

qtype, options_list = _classify_question(test_case_6)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "numeric", f"Expected 'numeric', got '{qtype}'"
assert len(options_list) == 0, f"Expected empty options list, got {options_list}"
print("✓ Test 6 passed\n")

# Test Case 7: Fallback - options present but no explicit type
print("="*70)
print("Test 7: Fallback - options present but no explicit type")
print("="*70)
test_case_7 = {
    "question": {
        "id": 77777,
        "title": "Question with options but no type",
        "options": [
            {"label": "Choice 1"},
            {"label": "Choice 2"}
        ]
    }
}

qtype, options_list = _classify_question(test_case_7)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 2, f"Expected 2 options, got {len(options_list)}"
assert options_list == ["Choice 1", "Choice 2"], f"Options mismatch: {options_list}"
print("✓ Test 7 passed\n")

# Test Case 8: Fallback - numeric indicators present but no explicit type
print("="*70)
print("Test 8: Fallback - numeric indicators in possibilities")
print("="*70)
test_case_8 = {
    "question": {
        "id": 66666,
        "title": "Question with unit but no type",
        "possibilities": {
            "unit": "meters",
            "min": 0,
            "max": 1000
        }
    }
}

qtype, options_list = _classify_question(test_case_8)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "numeric", f"Expected 'numeric', got '{qtype}'"
assert len(options_list) == 0, f"Expected empty options list, got {options_list}"
print("✓ Test 8 passed\n")

# Test Case 9: Unknown type - no indicators at all
print("="*70)
print("Test 9: Unknown type - no indicators")
print("="*70)
test_case_9 = {
    "question": {
        "id": 55555,
        "title": "Question with no type indicators"
    }
}

qtype, options_list = _classify_question(test_case_9)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype is None, f"Expected None, got '{qtype}'"
assert len(options_list) == 0, f"Expected empty options list, got {options_list}"
print("✓ Test 9 passed\n")

# Test Case 10: core.options as string list (simpler format)
print("="*70)
print("Test 10: core.options as string list")
print("="*70)
test_case_10 = {
    "question": {
        "id": 44444,
        "type": "multiple_choice",
        "options": ["String Option 1", "String Option 2"]
    }
}

qtype, options_list = _classify_question(test_case_10)
print(f"Question type: {qtype}")
print(f"Options: {options_list}")
assert qtype == "multiple_choice", f"Expected 'multiple_choice', got '{qtype}'"
assert len(options_list) == 2, f"Expected 2 options, got {len(options_list)}"
assert options_list == ["String Option 1", "String Option 2"], f"Options mismatch: {options_list}"
print("✓ Test 10 passed\n")

print("="*70)
print("ALL TESTS PASSED ✓")
print("="*70)
print("\nKey test cases validated:")
print("  ✓ Empty possibilities with core.type and core.options (Q22427 scenario)")
print("  ✓ Missing possibilities key")
print("  ✓ Normal discrete type with outcomes")
print("  ✓ Empty outcomes with fallback to core.options")
print("  ✓ Binary and numeric types")
print("  ✓ Fallback detection by options presence")
print("  ✓ Fallback detection by numeric indicators")
print("  ✓ Unknown type when no indicators present")
print("  ✓ String list options format")
