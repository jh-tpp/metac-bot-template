"""Test the new _normalize_question_object function"""
import sys
import json

# Add the main module to the path
sys.path.insert(0, '/home/runner/work/metac-bot-template/metac-bot-template')

from main import _normalize_question_object, _get_core_question

# Test case 1: Binary question with nested 'question' object
test_binary = {
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
print("Test 1: Binary question with nested 'question' object")
print("="*70)
normalized = _normalize_question_object(test_binary)
if normalized:
    print(f"✓ Successfully normalized")
    print(f"  ID: {normalized['id']}")
    print(f"  Type: {normalized['type']}")
    print(f"  Title: {normalized['title']}")
    print(f"  Options: {normalized['options']}")
    print(f"  Bounds: {normalized['bounds']}")
    assert normalized['type'] == 'binary', f"Expected 'binary', got '{normalized['type']}'"
    assert normalized['id'] == 578
    print("✓ All assertions passed")
else:
    print("✗ Failed to normalize")
    sys.exit(1)

# Test case 2: Discrete (multiple choice) question
test_discrete = {
    "question": {
        "id": 12345,
        "title": "Which company will lead AI in 2026?",
        "description": "Choose one",
        "possibilities": {
            "type": "discrete",
            "outcomes": [
                {"name": "Google"},
                {"name": "OpenAI"},
                {"name": "Anthropic"}
            ]
        }
    }
}

print("\n" + "="*70)
print("Test 2: Discrete (multiple choice) question")
print("="*70)
normalized = _normalize_question_object(test_discrete)
if normalized:
    print(f"✓ Successfully normalized")
    print(f"  ID: {normalized['id']}")
    print(f"  Type: {normalized['type']}")
    print(f"  Title: {normalized['title']}")
    print(f"  Options: {normalized['options']}")
    assert normalized['type'] == 'multiple_choice', f"Expected 'multiple_choice', got '{normalized['type']}'"
    assert len(normalized['options']) == 3, f"Expected 3 options, got {len(normalized['options'])}"
    assert normalized['options'] == ['Google', 'OpenAI', 'Anthropic']
    print("✓ All assertions passed")
else:
    print("✗ Failed to normalize")
    sys.exit(1)

# Test case 3: Continuous (numeric) question
test_continuous = {
    "question": {
        "id": 14333,
        "title": "US GDP growth in 2025 (%)?",
        "description": "Numeric prediction",
        "possibilities": {
            "type": "continuous",
            "range": [-5, 10],
            "unit": "%"
        }
    }
}

print("\n" + "="*70)
print("Test 3: Continuous (numeric) question")
print("="*70)
normalized = _normalize_question_object(test_continuous)
if normalized:
    print(f"✓ Successfully normalized")
    print(f"  ID: {normalized['id']}")
    print(f"  Type: {normalized['type']}")
    print(f"  Title: {normalized['title']}")
    print(f"  Bounds: {normalized['bounds']}")
    assert normalized['type'] == 'numeric', f"Expected 'numeric', got '{normalized['type']}'"
    assert normalized['bounds']['min'] == -5
    assert normalized['bounds']['max'] == 10
    assert normalized['bounds']['unit'] == '%'
    print("✓ All assertions passed")
else:
    print("✗ Failed to normalize")
    sys.exit(1)

# Test case 4: Flat structure (no nested 'question')
test_flat = {
    "id": 99999,
    "title": "Flat structure test",
    "description": "No nested question key",
    "possibilities": {
        "type": "binary"
    }
}

print("\n" + "="*70)
print("Test 4: Flat structure (no nested 'question')")
print("="*70)
normalized = _normalize_question_object(test_flat)
if normalized:
    print(f"✓ Successfully normalized")
    print(f"  ID: {normalized['id']}")
    print(f"  Type: {normalized['type']}")
    print(f"  Title: {normalized['title']}")
    assert normalized['type'] == 'binary'
    assert normalized['id'] == 99999
    print("✓ All assertions passed")
else:
    print("✗ Failed to normalize")
    sys.exit(1)

# Test case 5: Unknown type (should return None)
test_unknown = {
    "question": {
        "id": 88888,
        "title": "Unknown type test",
        "description": "No valid type",
        "possibilities": {
            "type": "something_unknown"
        }
    }
}

print("\n" + "="*70)
print("Test 5: Unknown type (should return None)")
print("="*70)
normalized = _normalize_question_object(test_unknown)
if normalized is None:
    print(f"✓ Correctly returned None for unknown type")
else:
    print(f"✗ Expected None, got: {normalized}")
    sys.exit(1)

print("\n" + "="*70)
print("ALL TESTS PASSED ✓")
print("="*70)
