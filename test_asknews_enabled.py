"""Test ASKNEWS_ENABLED flag functionality"""
import sys
import os
import json

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Test the boolean flag parser
print("="*70)
print("Test 1: Boolean flag parser (_parse_bool_flag)")
print("="*70)

# Import after path is set up
from main import _parse_bool_flag

# Test true values
assert _parse_bool_flag("true") == True, "Failed: 'true' should be True"
assert _parse_bool_flag("True") == True, "Failed: 'True' should be True"
assert _parse_bool_flag("TRUE") == True, "Failed: 'TRUE' should be True"
assert _parse_bool_flag("1") == True, "Failed: '1' should be True"
assert _parse_bool_flag("yes") == True, "Failed: 'yes' should be True"
assert _parse_bool_flag("y") == True, "Failed: 'y' should be True"
assert _parse_bool_flag("on") == True, "Failed: 'on' should be True"
assert _parse_bool_flag("t") == True, "Failed: 't' should be True"

# Test false values
assert _parse_bool_flag("false") == False, "Failed: 'false' should be False"
assert _parse_bool_flag("False") == False, "Failed: 'False' should be False"
assert _parse_bool_flag("FALSE") == False, "Failed: 'FALSE' should be False"
assert _parse_bool_flag("0") == False, "Failed: '0' should be False"
assert _parse_bool_flag("no") == False, "Failed: 'no' should be False"
assert _parse_bool_flag("n") == False, "Failed: 'n' should be False"
assert _parse_bool_flag("off") == False, "Failed: 'off' should be False"
assert _parse_bool_flag("f") == False, "Failed: 'f' should be False"

# Test default behavior
assert _parse_bool_flag(None, default=True) == True, "Failed: None with default=True should be True"
assert _parse_bool_flag("", default=True) == True, "Failed: empty string with default=True should be True"
assert _parse_bool_flag(None, default=False) == False, "Failed: None with default=False should be False"
assert _parse_bool_flag("", default=False) == False, "Failed: empty string with default=False should be False"

# Test unrecognized values (should use default)
assert _parse_bool_flag("unknown", default=True) == True, "Failed: unrecognized value should use default"
assert _parse_bool_flag("random", default=False) == False, "Failed: unrecognized value should use default"

print("✓ All boolean flag parser tests passed")

# Test fetch_facts_for_batch when ASKNEWS_USE is False
print("\n" + "="*70)
print("Test 2: fetch_facts_for_batch with ASKNEWS_USE=False")
print("="*70)

# Save original value
import main
original_asknews_use = main.ASKNEWS_USE

try:
    # Temporarily set ASKNEWS_USE to False
    main.ASKNEWS_USE = False
    
    # Test that fetch_facts_for_batch returns empty lists
    from main import fetch_facts_for_batch
    
    qid_to_text = {
        12345: "Will AGI be developed by 2030?",
        12346: "What is the GDP growth rate?",
        12347: "Test question 3"
    }
    
    results = fetch_facts_for_batch(qid_to_text)
    
    # Verify all results are empty lists
    for qid, facts in results.items():
        assert qid in qid_to_text, f"Unexpected question ID {qid} in results"
        assert facts == [], f"Expected empty list for qid {qid}, got {facts}"
    
    # Verify all question IDs are present
    for qid in qid_to_text:
        assert qid in results, f"Missing question ID {qid} in results"
    
    print("✓ fetch_facts_for_batch correctly returns empty lists when disabled")

finally:
    # Restore original value
    main.ASKNEWS_USE = original_asknews_use

# Test _get_asknews_token when ASKNEWS_USE is False
print("\n" + "="*70)
print("Test 3: _get_asknews_token with ASKNEWS_USE=False")
print("="*70)

try:
    # Temporarily set ASKNEWS_USE to False
    main.ASKNEWS_USE = False
    
    from main import _get_asknews_token
    
    token = _get_asknews_token()
    assert token is None, f"Expected None when disabled, got {token}"
    
    print("✓ _get_asknews_token correctly returns None when disabled")

finally:
    # Restore original value
    main.ASKNEWS_USE = original_asknews_use

# Test _fetch_asknews_single when ASKNEWS_USE is False
print("\n" + "="*70)
print("Test 4: _fetch_asknews_single with ASKNEWS_USE=False")
print("="*70)

try:
    # Temporarily set ASKNEWS_USE to False
    main.ASKNEWS_USE = False
    
    from main import _fetch_asknews_single
    
    facts = _fetch_asknews_single("Test question")
    assert facts == [], f"Expected empty list when disabled, got {facts}"
    
    print("✓ _fetch_asknews_single correctly returns empty list when disabled")

finally:
    # Restore original value
    main.ASKNEWS_USE = original_asknews_use

# Test main_with_no_framework.py
print("\n" + "="*70)
print("Test 5: main_with_no_framework.py boolean flag parser")
print("="*70)

import main_with_no_framework

# Test that the parser is defined and works the same way
assert hasattr(main_with_no_framework, "_parse_bool_flag"), "main_with_no_framework should have _parse_bool_flag"
assert main_with_no_framework._parse_bool_flag("true") == True
assert main_with_no_framework._parse_bool_flag("false") == False
assert main_with_no_framework._parse_bool_flag("1") == True
assert main_with_no_framework._parse_bool_flag("0") == False

print("✓ main_with_no_framework.py has working boolean flag parser")

print("\n" + "="*70)
print("ALL TESTS PASSED ✓")
print("="*70)
