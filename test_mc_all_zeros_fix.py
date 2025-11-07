#!/usr/bin/env python3
"""
Test to simulate the "MC parse got all zeros" issue and verify it's fixed.
This test verifies that when LLM returns scores with actual option names
(matching the JSON hint), the parser correctly extracts them.
"""
import os
import sys
from unittest.mock import Mock, patch

os.environ['OPENROUTER_API_KEY'] = 'test-key'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mc_worlds


def test_mc_parse_avoids_all_zeros():
    """
    Test that MC parser avoids 'all zeros' when LLM uses actual option names.
    
    This test simulates the scenario from the bug report where:
    1. Question has options like "0", "1", "2+"
    2. LLM is instructed to use those option names in the JSON hint
    3. LLM returns scores with those names
    4. Parser correctly extracts the scores (not all zeros)
    """
    print("\n" + "="*70)
    print("Test: MC parse avoids 'all zeros' with matching option names")
    print("="*70)
    
    # Simulate Q22427 with real option names
    test_question = {
        "id": 22427,
        "type": "multiple_choice",
        "title": "Number of countries",
        "description": "How many countries?",
        "options": [
            {"name": "0"},
            {"name": "1"},
            {"name": "2+"}
        ]
    }
    
    test_facts = ["Recent news fact"]
    
    # Track what the LLM receives and returns
    captured_prompts = []
    call_count = [0]
    
    def mock_llm_call(prompt, **kwargs):
        captured_prompts.append(prompt)
        call_count[0] += 1
        
        # LLM returns scores using the actual option names from the hint
        # (which now match the real option names from the question)
        return {
            "world_summary": f"World scenario {call_count[0]}",
            "scores": {
                "0": 10 + call_count[0],
                "1": 20 + call_count[0] * 2,
                "2+": 30 - call_count[0]
            }
        }
    
    with patch('main.llm_call', side_effect=mock_llm_call):
        with patch('main._diag_save'):
            result = mc_worlds.run_mc_worlds(
                question_obj=test_question,
                context_facts=test_facts,
                n_worlds=5,
                return_evidence=False
            )
    
    # Verify prompts contained the correct option names
    print(f"\n✓ Generated {len(captured_prompts)} prompts")
    assert len(captured_prompts) == 5, "Should have 5 prompts"
    
    for i, prompt in enumerate(captured_prompts):
        assert '"0": number' in prompt, f"Prompt {i} should include option '0'"
        assert '"1": number' in prompt, f"Prompt {i} should include option '1'"
        assert '"2+": number' in prompt, f"Prompt {i} should include option '2+'"
    
    print(f"✓ All prompts correctly included actual option names")
    
    # Verify result was successfully parsed (not "all zeros" failure)
    assert "probs" in result, "Result should have 'probs' key"
    assert len(result["probs"]) == 3, f"Should have 3 probabilities, got {len(result['probs'])}"
    
    # Verify probabilities sum to 1.0
    total = sum(result["probs"])
    assert abs(total - 1.0) < 1e-6, f"Probabilities should sum to 1.0, got {total}"
    
    # Verify all probabilities are positive (not zeros)
    for i, prob in enumerate(result["probs"]):
        assert prob > 0, f"Probability {i} should be positive, got {prob}"
    
    print(f"✓ Successfully parsed probabilities: {result['probs']}")
    print(f"✓ No 'all zeros' error - all probabilities are positive")


def test_mc_parse_detects_key_mismatch():
    """
    Test that parser still detects 'all zeros' when LLM uses wrong keys.
    
    This verifies the guard is still working if there's a genuine mismatch.
    """
    print("\n" + "="*70)
    print("Test: MC parse still detects genuine key mismatches")
    print("="*70)
    
    test_question = {
        "id": 99999,
        "type": "multiple_choice",
        "title": "Test question",
        "description": "Test",
        "options": [
            {"name": "Alpha"},
            {"name": "Beta"},
            {"name": "Gamma"}
        ]
    }
    
    test_facts = ["Test fact"]
    
    def mock_llm_call_wrong_keys(prompt, **kwargs):
        # LLM returns scores with WRONG keys (doesn't follow the hint)
        return {
            "world_summary": "Wrong keys scenario",
            "scores": {
                "WrongKey1": 50,
                "WrongKey2": 30,
                "WrongKey3": 20
            }
        }
    
    with patch('main.llm_call', side_effect=mock_llm_call_wrong_keys):
        with patch('main._diag_save'):
            try:
                result = mc_worlds.run_mc_worlds(
                    question_obj=test_question,
                    context_facts=test_facts,
                    n_worlds=3,
                    return_evidence=False
                )
                # If we get here, all worlds failed to parse (which is expected)
                print(f"✗ Should have raised RuntimeError for no valid worlds")
                assert False, "Should have raised error"
            except RuntimeError as e:
                error_msg = str(e)
                assert "No valid worlds generated" in error_msg, \
                    f"Expected 'No valid worlds' error, got: {error_msg}"
                print(f"✓ Correctly detected key mismatch and raised error: {error_msg}")


def main():
    """Run all MC parse tests."""
    print("\n" + "#"*70)
    print("# MC Parse 'All Zeros' Fix Tests")
    print("#"*70)
    
    tests = [
        test_mc_parse_avoids_all_zeros,
        test_mc_parse_detects_key_mismatch,
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
        print("\n✓ ALL MC PARSE TESTS PASSED")
        print("\nSummary:")
        print("- MC prompts now use actual option names in JSON hints")
        print("- Parser correctly extracts scores when keys match")
        print("- 'All zeros' guard still works for genuine mismatches")
    
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
