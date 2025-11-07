#!/usr/bin/env python3
"""
Test that MC world prompts use actual option names instead of placeholders.
This validates the fix for the "MC parse got all zeros" issue.
"""
import os
import sys
from unittest.mock import Mock, patch

# Set up test environment
os.environ['OPENROUTER_API_KEY'] = 'test-key'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mc_worlds


def test_mc_prompt_with_actual_option_names():
    """Test that MC prompts include actual option names in JSON hint."""
    print("\n" + "="*70)
    print("Test: MC prompt uses actual option names")
    print("="*70)
    
    # Create test question with real option names like Q22427
    test_question = {
        "id": 22427,
        "type": "multiple_choice",
        "title": "Test MC Question",
        "description": "Test description",
        "options": [
            {"name": "0"},
            {"name": "1"},
            {"name": "2+"}
        ]
    }
    
    test_facts = ["Test fact 1", "Test fact 2"]
    
    # Track the prompt that was sent to the LLM
    captured_prompt = [None]
    
    def mock_llm_call(prompt, **kwargs):
        captured_prompt[0] = prompt
        # Return a valid response with actual option names
        return {
            "world_summary": "Test world",
            "scores": {"0": 30, "1": 50, "2+": 20}
        }
    
    # Mock llm_call (imported from main into mc_worlds)
    with patch('main.llm_call', side_effect=mock_llm_call):
        # Mock diagnostic functions
        with patch('main._diag_save'):
            result = mc_worlds.run_mc_worlds(
                question_obj=test_question,
                context_facts=test_facts,
                n_worlds=1,
                return_evidence=False
            )
    
    # Verify the prompt
    assert captured_prompt[0] is not None, "Prompt should have been captured"
    prompt = captured_prompt[0]
    
    print(f"\nCaptured prompt snippet (last 300 chars):")
    print(prompt[-300:])
    
    # Verify the JSON hint includes actual option names
    assert '"0": number' in prompt, "Prompt should include option '0' in JSON hint"
    assert '"1": number' in prompt, "Prompt should include option '1' in JSON hint"
    assert '"2+": number' in prompt, "Prompt should include option '2+' in JSON hint"
    
    # Verify it doesn't use placeholders
    assert '"Option1"' not in prompt, "Prompt should NOT use placeholder 'Option1'"
    assert '"Option2"' not in prompt, "Prompt should NOT use placeholder 'Option2'"
    assert '"Option3"' not in prompt, "Prompt should NOT use placeholder 'Option3'"
    
    print(f"\n✓ Prompt correctly uses actual option names: 0, 1, 2+")
    
    # Verify result was parsed correctly
    assert "probs" in result, "Result should have 'probs' key"
    assert len(result["probs"]) == 3, f"Should have 3 probabilities, got {len(result['probs'])}"
    print(f"✓ Result parsed correctly: {result['probs']}")


def test_mc_prompt_with_string_options():
    """Test that MC prompts work with string options (not dicts)."""
    print("\n" + "="*70)
    print("Test: MC prompt with string options")
    print("="*70)
    
    # Create test question with string options
    test_question = {
        "id": 99999,
        "type": "multiple_choice",
        "title": "Test String Options",
        "description": "Test",
        "options": ["Low", "Medium", "High"]
    }
    
    test_facts = ["Test fact"]
    
    captured_prompt = [None]
    
    def mock_llm_call(prompt, **kwargs):
        captured_prompt[0] = prompt
        return {
            "world_summary": "Test",
            "scores": {"Low": 20, "Medium": 50, "High": 30}
        }
    
    with patch('main.llm_call', side_effect=mock_llm_call):
        with patch('main._diag_save'):
            result = mc_worlds.run_mc_worlds(
                question_obj=test_question,
                context_facts=test_facts,
                n_worlds=1,
                return_evidence=False
            )
    
    prompt = captured_prompt[0]
    print(f"\nCaptured prompt snippet (last 300 chars):")
    print(prompt[-300:])
    
    # Verify the JSON hint includes actual option names
    assert '"Low": number' in prompt, "Prompt should include option 'Low'"
    assert '"Medium": number' in prompt, "Prompt should include option 'Medium'"
    assert '"High": number' in prompt, "Prompt should include option 'High'"
    
    print(f"✓ Prompt correctly uses string options: Low, Medium, High")
    
    assert "probs" in result, "Result should have 'probs'"
    print(f"✓ Result parsed correctly: {result['probs']}")


def test_mc_prompt_with_special_chars():
    """Test that MC prompts properly escape option names with special characters."""
    print("\n" + "="*70)
    print("Test: MC prompt with special character escaping")
    print("="*70)
    
    # Create test question with options containing quotes and special chars
    test_question = {
        "id": 88888,
        "type": "multiple_choice",
        "title": "Test Special Chars",
        "description": "Test",
        "options": [
            {"name": 'Option "A"'},
            {"name": "Option\\B"},
            {"name": "Option\nC"}
        ]
    }
    
    test_facts = ["Test"]
    
    captured_prompt = [None]
    
    def mock_llm_call(prompt, **kwargs):
        captured_prompt[0] = prompt
        return {
            "world_summary": "Test",
            "scores": {'Option "A"': 50, 'Option\\B': 30, 'Option\nC': 20}
        }
    
    with patch('main.llm_call', side_effect=mock_llm_call):
        with patch('main._diag_save'):
            result = mc_worlds.run_mc_worlds(
                question_obj=test_question,
                context_facts=test_facts,
                n_worlds=1,
                return_evidence=False
            )
    
    prompt = captured_prompt[0]
    print(f"\nCaptured prompt snippet (last 300 chars):")
    print(prompt[-300:])
    
    # The JSON escaping should handle special characters
    # We just verify the result was parsed correctly
    assert "probs" in result, "Result should have 'probs'"
    assert len(result["probs"]) == 3, f"Should have 3 probabilities"
    print(f"✓ Special characters handled correctly")
    print(f"✓ Result: {result['probs']}")


def main():
    """Run all MC JSON hint tests."""
    print("\n" + "#"*70)
    print("# MC JSON Hint Tests")
    print("#"*70)
    
    tests = [
        test_mc_prompt_with_actual_option_names,
        test_mc_prompt_with_string_options,
        test_mc_prompt_with_special_chars,
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
        print("\n✓ ALL MC JSON HINT TESTS PASSED")
    
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
