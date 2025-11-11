"""
Quick integration test to verify numeric CDF sanitizer is properly integrated
into the payload generation pipeline.
"""

import numpy as np
from adapters import mc_results_to_metaculus_payload


def test_numeric_integration():
    """Test that numeric payloads use sanitized CDFs."""
    
    # Create a question with open bounds
    question_obj = {
        "id": 40221,
        "type": "numeric",
        "title": "Test numeric question",
        "possibilities": {
            "type": "continuous",
            "open_lower_bound": True,
            "open_upper_bound": True
        }
    }
    
    # Create MC result with a CDF that needs sanitization
    # - Wrong length (50 instead of 201)
    # - Starts at 0.0 (should be >= 0.001 for open lower bound)
    # - Ends at 1.0 (should be <= 0.999 for open upper bound)
    mc_result = {
        "cdf": list(np.linspace(0.0, 1.0, 50)),
        "grid": list(np.linspace(0, 100, 50))
    }
    
    # Generate payload
    payload = mc_results_to_metaculus_payload(question_obj, mc_result)
    
    # Verify structure
    assert "continuous_cdf" in payload, "Payload missing continuous_cdf"
    assert payload["probability_yes"] is None, "Binary field should be None"
    assert payload["probability_yes_per_category"] is None, "MC field should be None"
    
    cdf = payload["continuous_cdf"]
    
    # Verify sanitization occurred
    assert len(cdf) == 201, f"Expected 201 points after sanitization, got {len(cdf)}"
    assert cdf[0] >= 0.001, f"Open lower bound: first value should be >= 0.001, got {cdf[0]}"
    assert cdf[-1] <= 0.999, f"Open upper bound: last value should be <= 0.999, got {cdf[-1]}"
    
    # Verify monotonicity
    for i in range(1, len(cdf)):
        assert cdf[i] >= cdf[i-1], f"CDF not monotonic at index {i}"
    
    # Verify values in [0, 1]
    assert all(0.0 <= v <= 1.0 for v in cdf), "CDF contains values outside [0, 1]"
    
    print("✅ Numeric integration test PASSED")
    print(f"  - Length: {len(cdf)} (✓ 201)")
    print(f"  - First value: {cdf[0]:.6f} (✓ >= 0.001)")
    print(f"  - Last value: {cdf[-1]:.6f} (✓ <= 0.999)")
    print(f"  - Monotonic: ✓")
    print(f"  - All in [0, 1]: ✓")


def test_numeric_closed_bounds():
    """Test numeric payloads with closed bounds."""
    
    question_obj = {
        "id": 123,
        "type": "numeric",
        "title": "Test numeric question",
        "possibilities": {
            "type": "continuous",
            "open_lower_bound": False,
            "open_upper_bound": False
        }
    }
    
    # CDF that should end exactly at 0.0 and 1.0
    mc_result = {
        "cdf": list(np.linspace(0.0, 1.0, 201)),
        "grid": list(np.linspace(0, 100, 201))
    }
    
    payload = mc_results_to_metaculus_payload(question_obj, mc_result)
    cdf = payload["continuous_cdf"]
    
    # With closed bounds, endpoints should be exact
    assert abs(cdf[0] - 0.0) < 1e-9, f"Closed lower bound: first value should be 0.0, got {cdf[0]}"
    assert abs(cdf[-1] - 1.0) < 1e-9, f"Closed upper bound: last value should be 1.0, got {cdf[-1]}"
    
    print("✅ Closed bounds test PASSED")
    print(f"  - First value: {cdf[0]:.6f} (✓ exactly 0.0)")
    print(f"  - Last value: {cdf[-1]:.6f} (✓ exactly 1.0)")


def test_multiple_choice_integration():
    """Test that multiple choice payloads use enhanced normalization."""
    
    question_obj = {
        "id": 456,
        "type": "multiple_choice",
        "title": "Test MC question",
        "options": [
            {"name": "Option A"},
            {"name": "Option B"},
            {"name": "Option C"}
        ]
    }
    
    # MC result with negative values (should be clamped to 0)
    mc_result = {
        "probs": [-0.1, 0.5, 0.7]  # Negative value should be clamped
    }
    
    payload = mc_results_to_metaculus_payload(question_obj, mc_result)
    
    # Verify structure
    assert "probability_yes_per_category" in payload
    probs_dict = payload["probability_yes_per_category"]
    
    # Verify all non-negative
    for opt, prob in probs_dict.items():
        assert prob >= 0.0, f"Option {opt} has negative probability {prob}"
    
    # Verify sum = 1.0
    total = sum(probs_dict.values())
    assert abs(total - 1.0) < 1e-9, f"Probabilities sum to {total}, not 1.0"
    
    print("✅ Multiple choice integration test PASSED")
    print(f"  - All non-negative: ✓")
    print(f"  - Sum = 1.0: ✓ ({total:.6f})")
    print(f"  - Options mapped: {list(probs_dict.keys())}")


if __name__ == "__main__":
    print("Running integration tests...\n")
    
    test_numeric_integration()
    print()
    test_numeric_closed_bounds()
    print()
    test_multiple_choice_integration()
    
    print("\n✅ ALL INTEGRATION TESTS PASSED!")
