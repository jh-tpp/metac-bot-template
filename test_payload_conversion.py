"""
Test mc_results_to_metaculus_payload conversion using ORIGINAL template format.

This test verifies that MC results are correctly converted to the original
Metaculus API payload format with probability_yes, probability_yes_per_category,
and continuous_cdf fields.
"""
import sys
import os

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("TEST: Payload Conversion Verification")
print("="*70)

from adapters import mc_results_to_metaculus_payload

# Test 1: Binary question conversion
print("\nTest 1: Binary question payload conversion")

binary_question = {
    "id": 578,
    "type": "binary",
    "title": "Test binary question",
    "options": []
}

binary_result = {
    "p": 0.65,
    "reasoning": ["Base rate is 50%", "Recent events suggest 65%"]
}

payload = mc_results_to_metaculus_payload(binary_question, binary_result)

# Verify structure
assert "probability_yes" in payload, "Binary payload should have probability_yes"
assert "probability_yes_per_category" in payload, "Binary payload should have probability_yes_per_category"
assert "continuous_cdf" in payload, "Binary payload should have continuous_cdf"

# Verify values
assert payload["probability_yes"] == 0.65, f"Expected 0.65, got {payload['probability_yes']}"
assert payload["probability_yes_per_category"] is None, "probability_yes_per_category should be None for binary"
assert payload["continuous_cdf"] is None, "continuous_cdf should be None for binary"

print("✓ Binary question correctly converted")
print(f"  probability_yes: {payload['probability_yes']}")
print(f"  probability_yes_per_category: {payload['probability_yes_per_category']}")
print(f"  continuous_cdf: {payload['continuous_cdf']}")

# Test 2: Binary question with clamping
print("\nTest 2: Binary question with clamping")

edge_cases = [
    (0.005, 0.01, "too low"),
    (0.995, 0.99, "too high"),
    (0.5, 0.5, "normal"),
]

for input_p, expected_p, description in edge_cases:
    result = {"p": input_p}
    payload = mc_results_to_metaculus_payload(binary_question, result)
    assert payload["probability_yes"] == expected_p, (
        f"For {description}: expected {expected_p}, got {payload['probability_yes']}"
    )

print("✓ Clamping works correctly (0.01 to 0.99)")

# Test 3: Multiple choice question conversion
print("\nTest 3: Multiple choice question payload conversion")

mc_question = {
    "id": 999,
    "type": "multiple_choice",
    "title": "Test MC question",
    "options": ["Option A", "Option B", "Option C"]
}

mc_result = {
    "probs": [0.5, 0.3, 0.2],
    "reasoning": ["Reasoning for multiple choice"]
}

payload = mc_results_to_metaculus_payload(mc_question, mc_result)

# Verify structure
assert "probability_yes" in payload, "MC payload should have probability_yes"
assert "probability_yes_per_category" in payload, "MC payload should have probability_yes_per_category"
assert "continuous_cdf" in payload, "MC payload should have continuous_cdf"

# Verify values
assert payload["probability_yes"] is None, "probability_yes should be None for MC"
assert payload["continuous_cdf"] is None, "continuous_cdf should be None for MC"
assert isinstance(payload["probability_yes_per_category"], dict), "probability_yes_per_category should be dict"

# Verify mapping
prob_dict = payload["probability_yes_per_category"]
assert "Option A" in prob_dict, "Should have Option A"
assert "Option B" in prob_dict, "Should have Option B"
assert "Option C" in prob_dict, "Should have Option C"
assert prob_dict["Option A"] == 0.5, f"Expected 0.5 for A, got {prob_dict['Option A']}"
assert prob_dict["Option B"] == 0.3, f"Expected 0.3 for B, got {prob_dict['Option B']}"
assert prob_dict["Option C"] == 0.2, f"Expected 0.2 for C, got {prob_dict['Option C']}"

print("✓ Multiple choice correctly converted to dict mapping")
print(f"  probability_yes: {payload['probability_yes']}")
print(f"  probability_yes_per_category: {payload['probability_yes_per_category']}")

# Test 4: Multiple choice with normalization
print("\nTest 4: Multiple choice with normalization")

mc_result_unnormalized = {
    "probs": [1.0, 1.0, 1.0],  # Sum = 3.0, should normalize to [0.333, 0.333, 0.333]
    "reasoning": []
}

payload = mc_results_to_metaculus_payload(mc_question, mc_result_unnormalized)
prob_dict = payload["probability_yes_per_category"]

# Check that values sum to 1.0 (with floating point tolerance)
total = sum(prob_dict.values())
assert abs(total - 1.0) < 0.001, f"Probabilities should sum to 1.0, got {total}"

print("✓ Multiple choice normalization works correctly")
print(f"  Input probs: [1.0, 1.0, 1.0]")
print(f"  Normalized: {list(prob_dict.values())}")
print(f"  Sum: {total}")

# Test 5: Multiple choice with mismatched length
print("\nTest 5: Multiple choice with length enforcement")

# Too few probabilities
mc_result_short = {"probs": [0.7, 0.3], "reasoning": []}
payload = mc_results_to_metaculus_payload(mc_question, mc_result_short)
prob_dict = payload["probability_yes_per_category"]
assert len(prob_dict) == 3, f"Should pad to 3 options, got {len(prob_dict)}"

# Too many probabilities
mc_result_long = {"probs": [0.3, 0.3, 0.2, 0.1, 0.1], "reasoning": []}
payload = mc_results_to_metaculus_payload(mc_question, mc_result_long)
prob_dict = payload["probability_yes_per_category"]
assert len(prob_dict) == 3, f"Should truncate to 3 options, got {len(prob_dict)}"

print("✓ Length enforcement works (padding and truncation)")

# Test 6: Numeric question conversion
print("\nTest 6: Numeric question payload conversion")

numeric_question = {
    "id": 1234,
    "type": "numeric",
    "title": "Test numeric question",
    "options": []
}

numeric_result = {
    "cdf": [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
    "grid": [10, 20, 30, 40, 50, 60, 70],
    "reasoning": ["Numeric reasoning"]
}

payload = mc_results_to_metaculus_payload(numeric_question, numeric_result)

# Verify structure
assert "probability_yes" in payload, "Numeric payload should have probability_yes"
assert "probability_yes_per_category" in payload, "Numeric payload should have probability_yes_per_category"
assert "continuous_cdf" in payload, "Numeric payload should have continuous_cdf"

# Verify values
assert payload["probability_yes"] is None, "probability_yes should be None for numeric"
assert payload["probability_yes_per_category"] is None, "probability_yes_per_category should be None for numeric"
assert payload["continuous_cdf"] == numeric_result["cdf"], "continuous_cdf should match input CDF"

print("✓ Numeric question correctly converted")
print(f"  probability_yes: {payload['probability_yes']}")
print(f"  continuous_cdf length: {len(payload['continuous_cdf'])}")

# Test 7: Continuous question (same as numeric)
print("\nTest 7: Continuous question payload conversion")

continuous_question = {
    "id": 5678,
    "type": "continuous",
    "title": "Test continuous question",
    "options": []
}

payload = mc_results_to_metaculus_payload(continuous_question, numeric_result)

assert payload["continuous_cdf"] == numeric_result["cdf"], "Continuous should use CDF"
assert payload["probability_yes"] is None
assert payload["probability_yes_per_category"] is None

print("✓ Continuous question correctly converted (same as numeric)")

# Test 8: Verify reasoning is NOT in payload (handled separately)
print("\nTest 8: Verify reasoning is not included in forecast payload")

for qtype, question, result in [
    ("binary", binary_question, binary_result),
    ("MC", mc_question, mc_result),
    ("numeric", numeric_question, numeric_result),
]:
    payload = mc_results_to_metaculus_payload(question, result)
    assert "reasoning" not in payload, f"{qtype} payload should not include reasoning"

print("✓ Reasoning correctly excluded from forecast payload")
print("  (Reasoning is handled via separate comment submission)")

print("\n" + "="*70)
print("ALL TESTS PASSED")
print("="*70)
print("\nSummary:")
print("✓ Binary questions: probability_yes field")
print("✓ Multiple choice: probability_yes_per_category dict mapping")
print("✓ Numeric/continuous: continuous_cdf list")
print("✓ Clamping works (binary 0.01-0.99)")
print("✓ Normalization works (MC probs sum to 1.0)")
print("✓ Length enforcement works (padding/truncating)")
print("✓ Reasoning excluded from payload (separate comment)")
print("\n✅ Payload conversion verified successfully")
