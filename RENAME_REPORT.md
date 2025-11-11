# N_WORLDS_DEFAULT → N_WORLDS_TEST Rename Report

## Summary
All occurrences of `N_WORLDS_DEFAULT` have been successfully renamed to `N_WORLDS_TEST` across the codebase. This rename clarifies that the identifier is specifically for test/smoke test paths, not for production tournament runs.

## Verification
```bash
$ grep -r "N_WORLDS_DEFAULT" --include="*.py" --include="*.yaml" --include="*.yml" 2>/dev/null
# Returns: 0 matches in code files
# Only found in CHANGES.md and PATCH_SUMMARY.md documenting this rename
```

## Files Modified (from previous PR)
The rename was completed in a previous commit. Here's the complete list of changes:

### main.py
**Line 49**: Constant definition
```python
-N_WORLDS_DEFAULT = 10  # for tests
+N_WORLDS_TEST = 10  # for tests
```

**Lines with references** (6 total):
- Line 2256: `n_worlds=N_WORLDS_TEST` (run_live_test)
- Line 2303: `n_worlds: Number of MC worlds to generate (default: N_WORLDS_TEST)` (docstring)
- Line 2306: `n_worlds = N_WORLDS_TEST` (run_submit_smoke_test default)
- Line 2530: `n_worlds=N_WORLDS_TEST` (run_test_mode)
- Line 2641: `n_worlds: Number of MC worlds to generate (default: N_WORLDS_TEST for test modes, N_WORLDS_TOURNAMENT for tournament)` (docstring)
- Line 2822: `help="Number of MC worlds to generate (default: N_WORLDS_TEST)"` (argparse help)

### test_submit_single_question.py
**Line**: Help text reference
```python
-# ... reference to N_WORLDS_DEFAULT ...
+# ... reference to N_WORLDS_TEST ...
```

## Usage Clarity

### N_WORLDS_TEST (value: 10)
Used in:
- `run_live_test()` - Live testing on long-lived questions
- `run_submit_smoke_test()` - Single question smoke tests
- `run_test_mode()` - Test mode with example questions
- Default for `--worlds` CLI argument (overridable)

### N_WORLDS_TOURNAMENT (value: 100)
Used in:
- `run_tournament(mode="submit")` - Production tournament runs
- Default in tournament_submit mode
- Set via environment variable in .github/workflows/run_bot_on_tournament.yaml
- NOT overridable via workflow inputs (enforced)

## Benefits of Rename
1. **Clear intent**: `N_WORLDS_TEST` clearly indicates test/development usage
2. **Prevents confusion**: No ambiguity about which constant to use for tournaments
3. **Enforces Option B**: Tournament runs exclusively use `N_WORLDS_TOURNAMENT`
4. **Better documentation**: Self-documenting constant names

## Verification Tests
✅ All existing tests pass with new identifier
✅ No references to old identifier remain in code
✅ Tournament workflow correctly uses N_WORLDS_TOURNAMENT
✅ Test/smoke paths correctly use N_WORLDS_TEST
