# Pipeline Simplification Changes

## Summary
This PR implements a focused cleanup of the forecasting pipeline as specified in the problem statement, with three main areas of change:

## A) Hydration Simplification

**Before:** 
- Attempted multiple URL variants (with/without trailing slash)
- Merged data from multiple attempts
- Complex merging logic for nested objects

**After:**
- Single attempt using preferred URL with trailing slash
- Log and return None on failure
- Simplified error handling

**Files Modified:**
- `main.py`: `_hydrate_question_with_diagnostics()` (lines 1717-1827)

## B) Minimal Question Processing

**Before:**
- Complex type inference using `_infer_qtype_and_fields()`
- Extracted and attached bounds, min/max, unit, scale for numeric questions
- Deep processing of question metadata

**After:**
- Minimal pass-through processing
- Type determination: `core.possibilities.type` → `core.type` → skip
- Multiple choice: extract options only from `possibilities.outcomes[]` or `core.options[]`
- Do NOT attach bounds, min/max, unit, or scale
- Return minimal dict: `{id, type, title, description, url, options?}`

**Files Modified:**
- `main.py`: `fetch_tournament_questions()` (lines 698-774)
- `main.py`: `_normalize_question_type()` - added discrete/binary/continuous mappings

## C) Per-Type World Schemas and Parsing

**Before:**
- Single WORLD_PROMPT with complex schema for all types
- Placeholder heuristics for parsing world responses
- Complex aggregation with bounds checking and clamping

**After:**
- **Binary:**
  - Schema: `{"answer": true|false}`
  - Parsing: collect booleans, probability = mean(answers==true)
  - Clamping: [0.01, 0.99]

- **Multiple Choice:**
  - Schema: `{"scores": {"option1": score, ...}}`
  - Parsing: average scores across worlds, normalize to probabilities
  - Validation: sum to 1.0, all in [0, 1]

- **Numeric:**
  - Schema: `{"value": number}`
  - Parsing: average values directly, NO normalization/clamping
  - Grid: infer bounds from samples + 5% padding
  - CDF: computed from sorted samples

**Files Modified:**
- `mc_worlds.py`: Complete rewrite of `run_mc_worlds()` and helper functions
- Added: `_run_binary_worlds()`, `_run_multiple_choice_worlds()`, `_run_numeric_worlds()`
- WORLD_PROMPT kept intact but unused (per requirements)

## Security Improvements

- Sanitize multiple choice option names to prevent prompt injection
- Remove quotes, newlines, and control characters
- Truncate to 100 chars max

## Testing

**New Tests Added:**
- `test_per_type_schemas.py`: Tests for binary, MC, and numeric schema parsing

**Existing Tests:**
- ✓ `test_infer_qtype.py`: Type inference tests pass
- ✓ `test_normalization.py`: Question normalization tests pass
- ✓ `test_http_logging.py`: HTTP logging tests pass
- ✓ `test_openrouter_debug.py`: Debug tests pass

## Unchanged (per requirements)

- Model selection: `openai/gpt-5-nano`
- Reasoning effort: `"minimal"`
- HTTP logging: fully intact and functional

## Validation Code

Validation code (`validate_mc_result`, `parse_numeric_bounds`) still uses bounds for checking, but:
- NOT called during question preparation
- Only used during post-forecast validation
- Can re-parse bounds from raw question if needed

## Summary of Benefits

1. **Simpler pipeline**: Less code, fewer edge cases
2. **Type-specific schemas**: Clearer expectations, easier to debug
3. **No over-normalization**: Raw values preserved, minimal inference
4. **Better security**: Sanitized inputs prevent prompt injection
5. **Maintainable**: Each question type handled independently
