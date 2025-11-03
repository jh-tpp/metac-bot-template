#!/usr/bin/env python3
"""Manual test for mc_worlds debug functionality"""
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Set up test environment
os.environ['OPENROUTER_DEBUG'] = 'true'
os.environ['OPENROUTER_API_KEY'] = 'test-key'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main
import mc_worlds
import importlib
importlib.reload(main)
importlib.reload(mc_worlds)

print("="*70)
print("Manual Test: mc_worlds debug functionality")
print("="*70)

# Create test question
test_question = {
    "id": 12345,
    "type": "binary",
    "title": "Will test succeed?",
    "description": "This is a test question"
}

test_facts = ["Fact 1: Testing is important", "Fact 2: Debug mode is enabled"]

print(f"\n1. OPENROUTER_DEBUG_ENABLED: {main.OPENROUTER_DEBUG_ENABLED}")
assert main.OPENROUTER_DEBUG_ENABLED == True, "Debug should be enabled"
print("   ✓ Debug mode is enabled")

print("\n2. Testing mc_worlds with successful world generation...")

# Mock successful world generation
mock_response = Mock()
mock_response.status_code = 200
mock_response.reason = "OK"
mock_response.headers = {'content-type': 'application/json'}

def create_world_response(i):
    return {
        "choices": [{
            "message": {
                "content": f'{{"date": "2025-01-01", "summary": "World {i} summary"}}'
            }
        }]
    }

call_count = [0]
def mock_post(*args, **kwargs):
    response = Mock()
    response.status_code = 200
    response.reason = "OK"
    response.headers = {'content-type': 'application/json'}
    response.json.return_value = create_world_response(call_count[0])
    call_count[0] += 1
    return response

cache_dir = Path("cache")
cache_dir.mkdir(exist_ok=True)

# Clear existing debug files for this test
for f in cache_dir.glob("debug_world_q12345_*"):
    f.unlink()

with patch('main.requests.post', side_effect=mock_post):
    result = mc_worlds.run_mc_worlds(
        question_obj=test_question,
        context_facts=test_facts,
        n_worlds=3,
        return_evidence=True
    )
    
    print(f"   Result keys: {list(result.keys())}")
    assert "p" in result, "Binary result should have 'p'"
    assert "world_summaries" in result, "Should include world_summaries"
    print(f"   ✓ Generated {len(result['world_summaries'])} worlds")
    
    # Check for debug prompt files
    prompt_files = list(cache_dir.glob("debug_world_q12345_*_prompt.txt"))
    print(f"\n   Debug prompt files created: {len(prompt_files)}")
    assert len(prompt_files) == 3, f"Should have 3 prompt files, got {len(prompt_files)}"
    
    # Check content of one prompt file
    if prompt_files:
        sample_prompt = sorted(prompt_files)[0]
        print(f"   Sample prompt file: {sample_prompt.name}")
        with open(sample_prompt) as f:
            content = f.read()
            assert "Will test succeed?" in content, "Prompt should contain question title"
            assert "Fact 1" in content, "Prompt should contain facts"
            print(f"   ✓ Prompt file contains expected content")

print("\n3. Testing mc_worlds with world generation failures...")

# Mock failed world generation
call_count_fail = [0]
def mock_post_with_failures(*args, **kwargs):
    if call_count_fail[0] == 1:  # Fail the second call
        call_count_fail[0] += 1
        raise Exception("Simulated world generation failure")
    
    response = Mock()
    response.status_code = 200
    response.reason = "OK"
    response.headers = {'content-type': 'application/json'}
    response.json.return_value = create_world_response(call_count_fail[0])
    call_count_fail[0] += 1
    return response

# Clear existing debug files for this test
for f in cache_dir.glob("debug_world_q12345_*"):
    f.unlink()

with patch('main.requests.post', side_effect=mock_post_with_failures):
    result = mc_worlds.run_mc_worlds(
        question_obj=test_question,
        context_facts=test_facts,
        n_worlds=3,
        return_evidence=True
    )
    
    print(f"   Generated {len(result['world_summaries'])} worlds (1 failed)")
    
    # Check for error file
    error_files = list(cache_dir.glob("debug_world_q12345_*_error.txt"))
    print(f"   Error files created: {len(error_files)}")
    assert len(error_files) == 1, f"Should have 1 error file, got {len(error_files)}"
    
    if error_files:
        error_file = error_files[0]
        print(f"   Error file: {error_file.name}")
        with open(error_file) as f:
            error_content = f.read()
            assert "Simulated world generation failure" in error_content, "Error file should contain error message"
            assert "Traceback" in error_content, "Error file should contain traceback"
            print(f"   ✓ Error file contains expected content")

print("\n4. Testing with debug disabled...")
os.environ['OPENROUTER_DEBUG'] = 'false'
importlib.reload(main)
importlib.reload(mc_worlds)

print(f"   OPENROUTER_DEBUG_ENABLED: {main.OPENROUTER_DEBUG_ENABLED}")
assert main.OPENROUTER_DEBUG_ENABLED == False, "Debug should be disabled"

# Clear existing debug files
for f in cache_dir.glob("debug_world_q12345_*"):
    f.unlink()

call_count_nodebug = [0]
def mock_post_no_debug(*args, **kwargs):
    response = Mock()
    response.status_code = 200
    response.reason = "OK"
    response.headers = {'content-type': 'application/json'}
    response.json.return_value = create_world_response(call_count_nodebug[0])
    call_count_nodebug[0] += 1
    return response

with patch('main.requests.post', side_effect=mock_post_no_debug):
    result = mc_worlds.run_mc_worlds(
        question_obj=test_question,
        context_facts=test_facts,
        n_worlds=2,
        return_evidence=True
    )
    
    # No debug files should be created
    prompt_files = list(cache_dir.glob("debug_world_q12345_*_prompt.txt"))
    error_files = list(cache_dir.glob("debug_world_q12345_*_error.txt"))
    
    print(f"   Prompt files with debug disabled: {len(prompt_files)}")
    print(f"   Error files with debug disabled: {len(error_files)}")
    assert len(prompt_files) == 0, "No prompt files should be created when debug is disabled"
    assert len(error_files) == 0, "No error files should be created when debug is disabled"
    print(f"   ✓ No debug files created when disabled")

print("\n" + "="*70)
print("mc_worlds debug test completed successfully!")
print("="*70)
print("\nSummary:")
print("- World prompts saved to cache/debug_world_q{qid}_{i}_prompt.txt when debug enabled")
print("- Error details saved to cache/debug_world_q{qid}_{i}_error.txt on failures")
print("- No debug files created when OPENROUTER_DEBUG is disabled")
print("- World generation continues correctly in both debug modes")
