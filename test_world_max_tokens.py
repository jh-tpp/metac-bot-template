"""Test WORLD_MAX_TOKENS environment variable configuration"""
import sys
import os
from unittest.mock import patch

# Add the main module to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("="*70)
print("Test 1: WORLD_MAX_TOKENS defaults to 700")
print("="*70)

# Test default when env var is not set
with patch.dict(os.environ, {}, clear=True):
    import importlib
    if 'mc_worlds' in sys.modules:
        importlib.reload(sys.modules['mc_worlds'])
    else:
        import mc_worlds
    
    from mc_worlds import WORLD_MAX_TOKENS
    assert WORLD_MAX_TOKENS == 700, f"Expected default 700, got {WORLD_MAX_TOKENS}"
    print(f"✓ WORLD_MAX_TOKENS defaults to 700")

print()

print("="*70)
print("Test 2: WORLD_MAX_TOKENS can be overridden via environment")
print("="*70)

# Test custom value
with patch.dict(os.environ, {"WORLD_MAX_TOKENS": "1000"}, clear=True):
    import importlib
    if 'mc_worlds' in sys.modules:
        importlib.reload(sys.modules['mc_worlds'])
    
    from mc_worlds import WORLD_MAX_TOKENS
    assert WORLD_MAX_TOKENS == 1000, f"Expected 1000, got {WORLD_MAX_TOKENS}"
    print(f"✓ WORLD_MAX_TOKENS can be set to custom value (1000)")

print()

print("="*70)
print("Test 3: WORLD_MAX_TOKENS handles different numeric values")
print("="*70)

test_values = [200, 500, 700, 1500, 2000]

for val in test_values:
    with patch.dict(os.environ, {"WORLD_MAX_TOKENS": str(val)}, clear=True):
        import importlib
        if 'mc_worlds' in sys.modules:
            importlib.reload(sys.modules['mc_worlds'])
        
        from mc_worlds import WORLD_MAX_TOKENS
        assert WORLD_MAX_TOKENS == val, f"Expected {val}, got {WORLD_MAX_TOKENS}"
        print(f"✓ WORLD_MAX_TOKENS={val} works correctly")

print()

print("="*70)
print("Test 4: Verify WORLD_MAX_TOKENS is used in llm_call")
print("="*70)

# We'll inspect the source to verify the variable is used correctly
import inspect
from mc_worlds import run_mc_worlds

source = inspect.getsource(run_mc_worlds)
assert "max_tokens=WORLD_MAX_TOKENS" in source, "WORLD_MAX_TOKENS should be used in llm_call"
print("✓ WORLD_MAX_TOKENS is used in llm_call within run_mc_worlds")

print()

print("="*70)
print("All WORLD_MAX_TOKENS tests passed!")
print("="*70)
