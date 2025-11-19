"""
Test numeric CDF open bounds handling end-to-end.

This test validates the complete integration of numeric CDF sanitization
for open-bound questions, as specified in the problem statement.
"""

import numpy as np
from adapters import _sanitize_numeric_cdf, mc_results_to_metaculus_payload


def test_open_lower_and_upper_bounds():
    """
    Test case: Open lower & open upper with endpoints 0.0 & 1.0 -> sanitized to 0.001 & 0.999
    """
    print("\n[TEST] Open lower & upper bounds: 0.0/1.0 -> 0.001/0.999")
    
    question_obj = {
        "id": 40221,
        "type": "numeric",
        "possibilities": {
            "open_lower_bound": True,
            "open_upper_bound": True
        }
    }
    
    # Create CDF with forbidden endpoints for open bounds
    raw_cdf = list(np.linspace(0.0, 1.0, 201))
    
    result = _sanitize_numeric_cdf(question_obj, raw_cdf)
    
    # Assertions
    assert len(result) == 201, f"Expected 201 points, got {len(result)}"
    assert result[0] >= 0.001, f"First value should be >= 0.001, got {result[0]}"
    assert result[-1] <= 0.999, f"Last value should be <= 0.999, got {result[-1]}"
    assert all(result[i] >= result[i-1] for i in range(1, len(result))), "CDF not monotonic"
    assert all(0.0 <= v <= 1.0 for v in result), "CDF values outside [0, 1]"
    
    print(f"  ✓ First value: {result[0]} (>= 0.001)")
    print(f"  ✓ Last value: {result[-1]} (<= 0.999)")
    print(f"  ✓ Monotonic: True")
    print(f"  ✓ All in [0,1]: True")


def test_already_compliant_endpoints():
    """
    Test case: Already compliant endpoints (0.002, 0.998) remain same
    """
    print("\n[TEST] Already compliant endpoints: 0.002/0.998 remain unchanged")
    
    question_obj = {
        "id": 123,
        "type": "numeric",
        "possibilities": {
            "open_lower_bound": True,
            "open_upper_bound": True
        }
    }
    
    # Create CDF with already-compliant endpoints
    raw_cdf = list(np.linspace(0.002, 0.998, 201))
    
    result = _sanitize_numeric_cdf(question_obj, raw_cdf)
    
    # Endpoints should remain close to original (within rounding)
    assert abs(result[0] - 0.002) < 0.001, f"First value changed unnecessarily: {result[0]}"
    assert abs(result[-1] - 0.998) < 0.001, f"Last value changed unnecessarily: {result[-1]}"
    
    print(f"  ✓ First value: {result[0]} (close to 0.002)")
    print(f"  ✓ Last value: {result[-1]} (close to 0.998)")


def test_interior_monotonic_violation():
    """
    Test case: Interior monotonic violation (cdf[i] < cdf[i-1]) repaired
    """
    print("\n[TEST] Interior monotonic violation repaired")
    
    question_obj = {
        "id": 124,
        "type": "numeric"
    }
    
    # Create CDF with monotonic violations
    raw_cdf = [0.0] * 50 + [0.5] * 50 + [0.3] * 50 + [1.0] * 51
    
    result = _sanitize_numeric_cdf(question_obj, raw_cdf)
    
    # Check monotonicity
    for i in range(1, len(result)):
        assert result[i] >= result[i-1], f"CDF not monotonic at index {i}: {result[i]} < {result[i-1]}"
    
    print(f"  ✓ Monotonicity enforced throughout")
    print(f"  ✓ Length: {len(result)}")


def test_closed_bounds_unchanged():
    """
    Test case: Closed bounds unchanged except monotonic fix
    """
    print("\n[TEST] Closed bounds: endpoints remain 0.0/1.0")
    
    question_obj = {
        "id": 125,
        "type": "numeric",
        "possibilities": {
            "open_lower_bound": False,
            "open_upper_bound": False
        }
    }
    
    # Create valid CDF for closed bounds
    raw_cdf = list(np.linspace(0.0, 1.0, 201))
    
    result = _sanitize_numeric_cdf(question_obj, raw_cdf)
    
    # Endpoints should be exactly 0.0 and 1.0 for closed bounds
    assert result[0] == 0.0, f"First value should be 0.0 for closed bounds, got {result[0]}"
    assert result[-1] == 1.0, f"Last value should be 1.0 for closed bounds, got {result[-1]}"
    
    print(f"  ✓ First value: {result[0]} (exactly 0.0)")
    print(f"  ✓ Last value: {result[-1]} (exactly 1.0)")


def test_end_to_end_payload_generation():
    """
    Test case: End-to-end payload generation with open bounds
    """
    print("\n[TEST] End-to-end payload generation with open bounds")
    
    question_obj = {
        "id": 40221,
        "type": "numeric",
        "possibilities": {
            "open_lower_bound": True,
            "open_upper_bound": True
        }
    }
    
    mc_result = {
        "cdf": list(np.linspace(0.0, 1.0, 201)),
        "grid": list(np.linspace(0, 100, 201)),
        "p10": 10.0,
        "p50": 50.0,
        "p90": 90.0
    }
    
    payload = mc_results_to_metaculus_payload(question_obj, mc_result)
    
    # Check payload structure
    assert "continuous_cdf" in payload, "Payload missing continuous_cdf"
    assert payload["probability_yes"] is None, "probability_yes should be None for numeric"
    assert payload["probability_yes_per_category"] is None, "probability_yes_per_category should be None"
    
    cdf = payload["continuous_cdf"]
    assert len(cdf) == 201, f"Payload CDF should have 201 points, got {len(cdf)}"
    assert cdf[0] >= 0.001, f"Payload CDF first value should be >= 0.001, got {cdf[0]}"
    assert cdf[-1] <= 0.999, f"Payload CDF last value should be <= 0.999, got {cdf[-1]}"
    
    print(f"  ✓ Payload structure correct")
    print(f"  ✓ CDF sanitized: first={cdf[0]}, last={cdf[-1]}")
    print(f"  ✓ Length: {len(cdf)}")


def test_no_open_bounds_specified():
    """
    Test case: No open bounds specified (default to closed)
    """
    print("\n[TEST] No open bounds specified: default to closed")
    
    question_obj = {
        "id": 126,
        "type": "numeric",
        "possibilities": {}  # No open_lower_bound or open_upper_bound
    }
    
    raw_cdf = list(np.linspace(0.0, 1.0, 201))
    
    result = _sanitize_numeric_cdf(question_obj, raw_cdf)
    
    # Should default to closed bounds (0.0 and 1.0)
    assert result[0] == 0.0, f"First value should be 0.0 (default closed), got {result[0]}"
    assert result[-1] == 1.0, f"Last value should be 1.0 (default closed), got {result[-1]}"
    
    print(f"  ✓ First value: {result[0]} (default closed)")
    print(f"  ✓ Last value: {result[-1]} (default closed)")


if __name__ == "__main__":
    print("=" * 70)
    print("NUMERIC CDF OPEN BOUNDS - END-TO-END INTEGRATION TESTS")
    print("=" * 70)
    
    test_open_lower_and_upper_bounds()
    test_already_compliant_endpoints()
    test_interior_monotonic_violation()
    test_closed_bounds_unchanged()
    test_end_to_end_payload_generation()
    test_no_open_bounds_specified()
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED")
    print("=" * 70)
