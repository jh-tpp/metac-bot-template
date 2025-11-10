"""
Test validation function for forecast payloads.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import _validate_payload_before_submit

print("="*70)
print("TEST: Forecast Payload Validation")
print("="*70)

# Test 1: Valid binary payload
print("\nTest 1: Valid binary payload")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": 0.65,
        "probability_yes_per_category": None,
        "continuous_cdf": None
    })
    print("✓ Valid binary payload accepted")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)

# Test 2: Invalid binary payload (too low)
print("\nTest 2: Invalid binary payload (too low)")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": 0.001,
        "probability_yes_per_category": None,
        "continuous_cdf": None
    })
    print("✗ Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"✓ Correctly rejected: {e}")

# Test 3: Invalid binary payload (too high)
print("\nTest 3: Invalid binary payload (too high)")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": 0.999,
        "probability_yes_per_category": None,
        "continuous_cdf": None
    })
    print("✗ Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"✓ Correctly rejected: {e}")

# Test 4: Valid multiple choice payload
print("\nTest 4: Valid multiple choice payload")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": None,
        "probability_yes_per_category": {
            "Option A": 0.3,
            "Option B": 0.5,
            "Option C": 0.2
        },
        "continuous_cdf": None
    })
    print("✓ Valid MC payload accepted")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)

# Test 5: Invalid MC payload (sum != 1.0)
print("\nTest 5: Invalid MC payload (sum != 1.0)")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": None,
        "probability_yes_per_category": {
            "Option A": 0.3,
            "Option B": 0.5,
            "Option C": 0.3  # Sum = 1.1
        },
        "continuous_cdf": None
    })
    print("✗ Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"✓ Correctly rejected: {e}")

# Test 6: Valid numeric payload
print("\nTest 6: Valid numeric payload")
cdf = [i/200.0 for i in range(201)]
cdf[0] = 0.0
cdf[-1] = 1.0
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": None,
        "probability_yes_per_category": None,
        "continuous_cdf": cdf
    })
    print("✓ Valid numeric payload accepted")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)

# Test 7: Invalid numeric payload (wrong length)
print("\nTest 7: Invalid numeric payload (wrong length)")
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": None,
        "probability_yes_per_category": None,
        "continuous_cdf": [0.0, 0.5, 1.0]  # Only 3 points
    })
    print("✗ Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"✓ Correctly rejected: {e}")

# Test 8: Invalid numeric payload (not monotonic)
print("\nTest 8: Invalid numeric payload (not monotonic)")
bad_cdf = [i/200.0 for i in range(201)]
bad_cdf[0] = 0.0
bad_cdf[-1] = 1.0
bad_cdf[50] = 0.1  # Goes down
try:
    _validate_payload_before_submit(12345, {
        "probability_yes": None,
        "probability_yes_per_category": None,
        "continuous_cdf": bad_cdf
    })
    print("✗ Should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"✓ Correctly rejected: {e}")

print("\n" + "="*70)
print("ALL VALIDATION TESTS PASSED")
print("="*70)
print("\nSummary:")
print("✓ Binary payload validation works (accepts [0.01, 0.99])")
print("✓ Multiple choice validation works (sum=1.0, all in [0,1])")
print("✓ Numeric validation works (201 points, monotonic, endpoints)")
print("\n✅ Validation test PASSED")
