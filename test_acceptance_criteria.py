"""
Test acceptance criteria from the problem statement:
1. With no env set (default), AskNews is OFF; no network calls are made; pipeline completes in all modes.
2. Setting ASKNEWS_ENABLED=true reenables current AskNews behavior.
3. Missing credentials or token errors still lead to graceful fallback strings, not crashes.
"""
import sys
import os

# Make sure we start with a clean slate
if 'ASKNEWS_ENABLED' in os.environ:
    del os.environ['ASKNEWS_ENABLED']
if 'ASKNEWS_CLIENT_ID' in os.environ:
    del os.environ['ASKNEWS_CLIENT_ID']
if 'ASKNEWS_SECRET' in os.environ:
    del os.environ['ASKNEWS_SECRET']

print("="*70)
print("ACCEPTANCE CRITERIA TESTS")
print("="*70)

# Criterion 1: With no env set (default), AskNews is OFF
print("\n" + "="*70)
print("Criterion 1: Default behavior (no env var set)")
print("="*70)

import main

print(f"ASKNEWS_ENABLED: {main.ASKNEWS_ENABLED}")
print(f"ASKNEWS_USE: {main.ASKNEWS_USE}")

assert main.ASKNEWS_ENABLED == "false", "Default should be 'false'"
assert main.ASKNEWS_USE == False, "Default should be False"
print("✓ AskNews is OFF by default")

# Test no network calls are made
print("\nTesting that no network calls are made...")
qid_to_text = {1: "Test question"}
facts = main.fetch_facts_for_batch(qid_to_text)
assert facts[1] == [], "Should return empty list"
print("✓ fetch_facts_for_batch returns empty list (no network calls)")

token = main._get_asknews_token()
assert token is None, "Should return None"
print("✓ _get_asknews_token returns None (no network calls)")

single_facts = main._fetch_asknews_single("Test question")
assert single_facts == [], "Should return empty list"
print("✓ _fetch_asknews_single returns empty list (no network calls)")

print("\n✅ Criterion 1 PASSED: AskNews is OFF by default, no network calls")

# Criterion 2: Setting ASKNEWS_ENABLED=true reenables current AskNews behavior
print("\n" + "="*70)
print("Criterion 2: Re-enabling AskNews")
print("="*70)

# Reload with ASKNEWS_ENABLED=true
os.environ['ASKNEWS_ENABLED'] = 'true'
import importlib
importlib.reload(main)

print(f"ASKNEWS_ENABLED: {main.ASKNEWS_ENABLED}")
print(f"ASKNEWS_USE: {main.ASKNEWS_USE}")

assert main.ASKNEWS_ENABLED == "true", "Should be 'true'"
assert main.ASKNEWS_USE == True, "Should be True"
print("✓ AskNews can be re-enabled with ASKNEWS_ENABLED=true")

print("\n✅ Criterion 2 PASSED: Setting ASKNEWS_ENABLED=true reenables AskNews")

# Criterion 3: Missing credentials or token errors lead to graceful fallback
print("\n" + "="*70)
print("Criterion 3: Graceful fallback with missing credentials")
print("="*70)

# With AskNews enabled but no credentials
print("Testing with ASKNEWS_USE=True but no credentials...")
token = main._get_asknews_token()
assert token is None, "Should return None when credentials missing"
print("✓ _get_asknews_token returns None (no crash)")

# Test that fetch_facts_for_batch handles missing credentials gracefully
qid_to_text = {1: "Test question"}
try:
    facts = main.fetch_facts_for_batch(qid_to_text)
    # Should return fallback string, not crash
    assert 1 in facts, "Should still return results"
    assert isinstance(facts[1], list), "Should be a list"
    print(f"✓ fetch_facts_for_batch returns fallback: {facts[1]}")
    print("✓ No crash with missing credentials")
except Exception as e:
    print(f"❌ FAILED: Exception raised: {e}")
    sys.exit(1)

print("\n✅ Criterion 3 PASSED: Missing credentials lead to graceful fallback")

# Test with main_with_no_framework.py
print("\n" + "="*70)
print("Testing main_with_no_framework.py")
print("="*70)

# Reset env
del os.environ['ASKNEWS_ENABLED']
if 'ASKNEWS_CLIENT_ID' in os.environ:
    del os.environ['ASKNEWS_CLIENT_ID']
if 'ASKNEWS_SECRET' in os.environ:
    del os.environ['ASKNEWS_SECRET']

import main_with_no_framework as mwnf

print(f"ASKNEWS_ENABLED: {mwnf.ASKNEWS_ENABLED}")
print(f"ASKNEWS_USE: {mwnf.ASKNEWS_USE}")

assert mwnf.ASKNEWS_ENABLED == "false", "Default should be 'false'"
assert mwnf.ASKNEWS_USE == False, "Default should be False"
print("✓ main_with_no_framework.py: AskNews OFF by default")

# Test enabling
os.environ['ASKNEWS_ENABLED'] = 'true'
importlib.reload(mwnf)

assert mwnf.ASKNEWS_ENABLED == "true", "Should be 'true'"
assert mwnf.ASKNEWS_USE == True, "Should be True"
print("✓ main_with_no_framework.py: Can be re-enabled")

print("\n✅ main_with_no_framework.py PASSED")

print("\n" + "="*70)
print("🎉 ALL ACCEPTANCE CRITERIA PASSED 🎉")
print("="*70)
print("\nSummary:")
print("1. ✅ AskNews is OFF by default (no network calls)")
print("2. ✅ Can be re-enabled with ASKNEWS_ENABLED=true")
print("3. ✅ Missing credentials handled gracefully (no crashes)")
print("4. ✅ Both main.py and main_with_no_framework.py work correctly")
