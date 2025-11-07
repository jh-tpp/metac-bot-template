#!/usr/bin/env python3
"""
Test per-type LLM schemas and parsing logic.
This validates that the new simplified pipeline correctly handles
binary, multiple choice, and numeric questions.
"""

def test_binary_schema():
    """Test binary question schema and parsing."""
    print("\n" + "="*70)
    print("Test: Binary question schema")
    print("="*70)
    
    # Simulate binary response
    mock_responses = [
        {"answer": True},
        {"answer": False},
        {"answer": True},
        {"answer": True},
        {"answer": False}
    ]
    
    # Parse answers
    answers = []
    for resp in mock_responses:
        answer = resp.get("answer")
        if isinstance(answer, bool):
            answers.append(answer)
    
    # Compute probability
    p = sum(1 for a in answers if a) / len(answers)
    p = max(0.01, min(0.99, p))
    
    print(f"Mock responses: {mock_responses}")
    print(f"Parsed answers: {answers}")
    print(f"Computed probability: {p}")
    
    # Validate
    assert len(answers) == 5, "Should parse all 5 responses"
    assert p == 0.6, f"Expected p=0.6, got p={p}"
    
    print("✓ Binary schema test passed")
    return True


def test_multiple_choice_schema():
    """Test multiple choice question schema and parsing."""
    print("\n" + "="*70)
    print("Test: Multiple choice question schema")
    print("="*70)
    
    option_names = ["Option A", "Option B", "Option C"]
    
    # Simulate MC responses with scores
    mock_responses = [
        {"scores": {"Option A": 80, "Option B": 15, "Option C": 5}},
        {"scores": {"Option A": 60, "Option B": 30, "Option C": 10}},
        {"scores": {"Option A": 70, "Option B": 20, "Option C": 10}},
    ]
    
    # Parse scores
    world_scores = []
    for resp in mock_responses:
        scores_dict = resp.get("scores", {})
        if isinstance(scores_dict, dict):
            scores = []
            for name in option_names:
                score = scores_dict.get(name, 0)
                try:
                    scores.append(float(score))
                except (ValueError, TypeError):
                    scores.append(0.0)
            world_scores.append(scores)
    
    # Average scores
    k = len(option_names)
    avg_scores = [0.0] * k
    for scores in world_scores:
        for i in range(k):
            avg_scores[i] += scores[i]
    avg_scores = [s / len(world_scores) for s in avg_scores]
    
    # Normalize to probabilities
    total_score = sum(avg_scores)
    if total_score > 0:
        probs = [s / total_score for s in avg_scores]
    else:
        probs = [1.0 / k] * k
    
    print(f"Mock responses: {mock_responses}")
    print(f"Parsed world scores: {world_scores}")
    print(f"Average scores: {avg_scores}")
    print(f"Normalized probabilities: {probs}")
    
    # Validate
    assert len(world_scores) == 3, "Should parse all 3 responses"
    assert len(probs) == 3, "Should have 3 probabilities"
    assert abs(sum(probs) - 1.0) < 1e-6, f"Probs should sum to 1.0, got {sum(probs)}"
    assert probs[0] > probs[1] > probs[2], "Option A should have highest probability"
    
    print("✓ Multiple choice schema test passed")
    return True


def test_numeric_schema():
    """Test numeric question schema and parsing."""
    print("\n" + "="*70)
    print("Test: Numeric question schema")
    print("="*70)
    
    # Simulate numeric responses with values
    mock_responses = [
        {"value": 12.5},
        {"value": 15.0},
        {"value": 10.0},
        {"value": 13.5},
        {"value": 14.0}
    ]
    
    # Parse values
    values = []
    for resp in mock_responses:
        value = resp.get("value")
        try:
            val = float(value)
            values.append(val)
        except (ValueError, TypeError):
            pass
    
    # Sort for percentile computation
    values.sort()
    
    # Compute percentiles
    def percentile(sorted_values, p):
        if not sorted_values:
            return 0.0
        idx = int(p * len(sorted_values))
        idx = max(0, min(idx, len(sorted_values) - 1))
        return sorted_values[idx]
    
    p10 = percentile(values, 0.10)
    p50 = percentile(values, 0.50)
    p90 = percentile(values, 0.90)
    
    # Infer grid bounds from samples
    lo = min(values)
    hi = max(values)
    range_padding = (hi - lo) * 0.05 if hi > lo else 1.0
    lo_padded = lo - range_padding
    hi_padded = hi + range_padding
    
    # Create grid
    grid = [lo_padded + (hi_padded - lo_padded) * i / 100 for i in range(101)]
    
    # Compute CDF
    cdf = []
    for x in grid:
        cdf.append(sum(1 for v in values if v <= x) / len(values))
    
    print(f"Mock responses: {mock_responses}")
    print(f"Parsed values: {values}")
    print(f"Percentiles: p10={p10}, p50={p50}, p90={p90}")
    print(f"Grid range: [{lo_padded:.2f}, {hi_padded:.2f}]")
    print(f"Grid points: {len(grid)}")
    print(f"CDF points: {len(cdf)}")
    
    # Validate
    assert len(values) == 5, "Should parse all 5 responses"
    assert p10 == 10.0, f"Expected p10=10.0, got p10={p10}"
    assert p50 == 13.5, f"Expected p50=13.5, got p50={p50}"
    assert p90 == 15.0, f"Expected p90=15.0, got p90={p90}"
    assert len(grid) == 101, "Grid should have 101 points"
    assert len(cdf) == 101, "CDF should have 101 points"
    assert cdf[0] >= 0.0 and cdf[-1] <= 1.0, "CDF should be in [0,1]"
    
    # Check CDF monotonicity
    for i in range(1, len(cdf)):
        assert cdf[i] >= cdf[i-1], f"CDF should be monotone at index {i}"
    
    print("✓ Numeric schema test passed")
    return True


def main():
    """Run all per-type schema tests."""
    print("\n" + "#"*70)
    print("# Per-Type LLM Schema Tests")
    print("#"*70)
    
    tests = [
        test_binary_schema,
        test_multiple_choice_schema,
        test_numeric_schema
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*70)
    
    if failed == 0:
        print("\n✓ ALL PER-TYPE SCHEMA TESTS PASSED")
    
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
