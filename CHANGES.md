# Changes History

## Restore Original Forecast and Comment Submission Logic (Current PR)

### Summary
This PR restores the forecast and comment submission logic to match the ORIGINAL template approach from `main_with_no_framework.py`, using `/api/` endpoints (not `/api2/`) with the original payload format and separate comment submission.

### Key Changes

**1. Forecast Endpoint & Payload Format**
- **Before**: Used various payload formats with `{"prediction": ...}` structure
- **After**: Uses ORIGINAL format:
  - URL: `https://www.metaculus.com/api/questions/forecast/`
  - Payload: Array format `[{"question": <id>, "probability_yes": ..., "probability_yes_per_category": ..., "continuous_cdf": ...}]`
  - Binary: `{"probability_yes": p, "probability_yes_per_category": null, "continuous_cdf": null}`
  - Multiple Choice: `{"probability_yes": null, "probability_yes_per_category": {option: prob}, "continuous_cdf": null}`
  - Numeric: `{"probability_yes": null, "probability_yes_per_category": null, "continuous_cdf": [...]}`

**2. Comment Submission**
- **Before**: No separate comment submission
- **After**: Added `submit_comment()` function
  - URL: `https://www.metaculus.com/api/comments/create/`
  - Payload: `{"text": <reasoning>, "parent": null, "included_forecast": true, "is_private": true, "on_post": <post_id>}`
  - Comments posted AFTER successful forecast submission
  - Comment failure does not fail the entire forecast operation

**3. Reasoning Handling**
- **Before**: Reasoning included in forecast payload
- **After**: Reasoning extracted from `mc_result["reasoning"]` and submitted separately as a comment

### Files Modified
- `adapters.py`: 
  - Updated `mc_results_to_metaculus_payload()` to use original format
  - Updated `submit_forecast()` to wrap payload in array with "question" field
  - Added `submit_comment()` function for reasoning submission
- `main.py`:
  - Imported `submit_comment` function
  - Updated `post_forecast_safe()` to submit comments after forecasts
- `test_forecast_endpoint.py`: Updated to test original `/api/` format
- `test_comment_submission.py`: New test for comment submission
- `test_payload_conversion.py`: New comprehensive test for payload conversion

### Testing
All tests pass:
- ✓ `test_forecast_endpoint.py`: Verifies `/api/` endpoint and array payload format
- ✓ `test_comment_submission.py`: Verifies comment endpoint and payload structure
- ✓ `test_payload_conversion.py`: Comprehensive payload conversion for all question types
- ✓ `test_normalization.py`: Question normalization still works
- ✓ `test_infer_qtype.py`: Type inference still works
- ✓ `test_http_logging.py`: HTTP logging still works
- ✓ `test_http_logging_integration.py`: Integration tests pass

### Security
- ✓ CodeQL scan: 0 alerts
- ✓ No new vulnerabilities introduced
- ✓ Authorization headers properly set
- ✓ Sensitive data (tokens) redacted in logs and diagnostics

---

## Previous: Pipeline Simplification Changes

### Summary
This PR implements a focused cleanup of the forecasting pipeline as specified in the problem statement, with three main areas of change:

### A) Hydration Simplification

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

### B) Minimal Question Processing

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

### C) Per-Type World Schemas and Parsing

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

### Security Improvements

- Sanitize multiple choice option names to prevent prompt injection
- Remove quotes, newlines, and control characters
- Truncate to 100 chars max

### Testing

**New Tests Added:**
- `test_per_type_schemas.py`: Tests for binary, MC, and numeric schema parsing

**Existing Tests:**
- ✓ `test_infer_qtype.py`: Type inference tests pass
- ✓ `test_normalization.py`: Question normalization tests pass
- ✓ `test_http_logging.py`: HTTP logging tests pass
- ✓ `test_openrouter_debug.py`: Debug tests pass

### Unchanged (per requirements)

- Model selection: `openai/gpt-5-nano`
- Reasoning effort: `"minimal"`
- HTTP logging: fully intact and functional

### Validation Code

Validation code (`validate_mc_result`, `parse_numeric_bounds`) still uses bounds for checking, but:
- NOT called during question preparation
- Only used during post-forecast validation
- Can re-parse bounds from raw question if needed

### Summary of Benefits

1. **Simpler pipeline**: Less code, fewer edge cases
2. **Type-specific schemas**: Clearer expectations, easier to debug
3. **No over-normalization**: Raw values preserved, minimal inference
4. **Better security**: Sanitized inputs prevent prompt injection
5. **Maintainable**: Each question type handled independently
