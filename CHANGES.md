# Changes History

## Hard Enforce Option B: Worlds Identifiers + 400 Forecast Fix (Current PR)

### Summary
This PR fully implements "Option B" for world identifiers and fixes 400 Bad Request errors in forecast submissions. It renames all N_WORLDS_DEFAULT to N_WORLDS_TEST, ensures tournament workflows exclusively use N_WORLDS_TOURNAMENT, enhances error logging, and adds comprehensive payload validation.

### Key Changes

**1. Identifier Rename (Global)**
- **Renamed**: `N_WORLDS_DEFAULT` → `N_WORLDS_TEST` (100 worlds for test/smoke paths)
- **Updated locations**:
  - `main.py`: Constant definition and 6 function references
  - `test_submit_single_question.py`: Help text
  - All test/smoke test functions now use `N_WORLDS_TEST`
  - Tournament mode defaults to `N_WORLDS_TOURNAMENT` (not overridable)
- **Verified**: Zero lingering `N_WORLDS_DEFAULT` references via grep

**2. Tournament Workflow Integrity**
- **Removed**: `simulations` workflow input parameter (no longer configurable)
- **Enforced**: Tournament runs ONLY use `N_WORLDS_TOURNAMENT` (hardcoded in main.py)
- **Updated**: `.github/workflows/run_bot_on_tournament.yaml` to remove simulation selection logic
- **Fixed**: `mc_results.json` and `mc_reasons.txt` NOT created when zero new questions
- **Conditional upload**: Artifacts only uploaded when files exist

**3. main.py Adjustments**
- **Test paths**: All use `N_WORLDS_TEST` (run_live_test, run_submit_smoke_test, run_test_mode)
- **Tournament paths**: All use `N_WORLDS_TOURNAMENT` (run_tournament default)
- **State management**: `.aib-state/posted_ids.json` created early and idempotently via `_load_posted_ids()`
- **Empty handling**: Skip artifact creation when no new questions to process

**4. Forecast Submission 400 Error Fix**
- **Added**: `_validate_payload_before_submit()` function in `adapters.py`
  - Binary: validates `probability_yes` in [0.01, 0.99]
  - Multiple choice: validates dict structure, probabilities sum to 1.0, all in [0, 1]
  - Numeric: validates 201-point CDF, monotonicity, endpoints at 0.0/1.0
- **Enhanced**: `submit_forecast()` error logging with structured `[FORECAST ERROR]` blocks
  - Logs question_id, status, payload, and API response
  - Extracts field-level validation errors from API response JSON
  - No automatic retries on 400 (fail gracefully and continue)
- **Enhanced**: `post_forecast_safe()` error handling
  - Separate catch for HTTPError with detailed field-level error extraction
  - Logs question type and full context for debugging

**5. Adapters Consistency**
- **Fixed**: `mc_results_to_metaculus_payload()` multiple choice handling
  - Correctly extracts option names from dict objects (`{"name": "..."}`)
  - Handles both dict and string option formats
  - Maps probabilities to option names (not dict objects)
- **Verified**: All question types return correct payload structure:
  - Binary: `probability_yes` only
  - Multiple choice: `probability_yes_per_category` dict only
  - Numeric: `continuous_cdf` list only

**6. Error Visibility**
- **Added**: Comprehensive error context in all submission failures
  - Question type included in error messages
  - Full payload logged for debugging
  - API field-level errors extracted and displayed
  - Structured format: `[FORECAST ERROR] Q{id} HTTP {status}`

### Files Modified
- `main.py`:
  - Renamed constant: `N_WORLDS_DEFAULT` → `N_WORLDS_TEST`
  - Updated 6 function references to use correct identifier
  - Enhanced `_load_posted_ids()` for idempotent creation
  - Enhanced `post_forecast_safe()` error handling
  - Fixed empty question handling (skip artifact creation)
- `adapters.py`:
  - Added `_validate_payload_before_submit()` function
  - Enhanced `submit_forecast()` with validation and error logging
  - Fixed `mc_results_to_metaculus_payload()` option name extraction
- `test_submit_single_question.py`:
  - Updated help text reference
- `.github/workflows/run_bot_on_tournament.yaml`:
  - Removed `simulations` input parameter
  - Removed `--worlds` CLI argument (uses hardcoded value)
  - Added conditional artifact upload (only when files exist)

### Testing
- ✓ Verified zero `N_WORLDS_DEFAULT` references via grep
- ✓ All test/smoke paths use `N_WORLDS_TEST`
- ✓ Tournament path uses `N_WORLDS_TOURNAMENT`
- ✓ Payload validation catches common errors before submission
- ✓ Error messages include full context for debugging

### Troubleshooting 400 Errors

**Common Causes:**
1. **Binary**: `probability_yes` outside [0.01, 0.99]
2. **Multiple choice**: Probabilities don't sum to 1.0 or use wrong option identifiers
3. **Numeric**: CDF not 201 points, not monotonic, or wrong endpoints

**How to Debug:**
1. Check `[FORECAST ERROR]` log block for question_id and status
2. Review logged payload structure
3. Check API field-level errors for specific validation failures
4. Verify question type matches payload structure
5. For MC: ensure option names match Metaculus API expectations exactly

**What We Now Surface:**
- Full payload that was rejected
- HTTP status code and reason
- API response body with field-level errors
- Question type context
- Pre-submission validation errors before API call

### Benefits
1. **Clear separation**: Test worlds (N_WORLDS_TEST) vs Tournament worlds (N_WORLDS_TOURNAMENT)
2. **No accidental overrides**: Tournament runs cannot be misconfigured via workflow inputs
3. **Better error visibility**: 400 errors now show exactly why submission failed
4. **Early validation**: Catch common errors before API submission
5. **Idempotent state**: `.aib-state/posted_ids.json` always exists
6. **Clean artifacts**: No empty mc_results.json files when nothing to process

---

## Hardcode Fall 2025 AIB Tournament

### Summary
This PR enforces the use of the Fall 2025 AI Benchmarking tournament (`fall-aib-2025`) by hardcoding the tournament identifier throughout the codebase. This prevents accidental environment variable overrides that could cause incorrect tournament IDs (e.g., 3512) to be used in production.

### Key Changes

**1. Tournament Hardcoding**
- **Before**: Tournament could be overridden via environment variables:
  - `METACULUS_PROJECT_ID`
  - `METACULUS_PROJECT_SLUG`
  - `METACULUS_CONTEST_SLUG`
  - `FALL_2025_AI_BENCHMARKING_ID`
- **After**: Tournament is hardcoded to `"fall-aib-2025"` in both `main.py` and `metaculus_posts.py`
  - All tournament-related environment variables removed
  - Function parameters for tournament selection ignored (kept for backward compatibility)
  - No way to override the tournament in production code paths

**2. Configuration Logging**
- Added explicit log message: `[CONFIG] Using hardcoded tournament: fall-aib-2025`
- Appears in `tournament_dryrun()` and `run_tournament()` modes
- Makes it clear in CI output which tournament is being used

**3. Documentation**
- Added comprehensive comments in `metaculus_posts.py` explaining rationale
- Updated function docstrings to indicate parameters are ignored
- All tournament functions clearly document hardcoded behavior

### Files Modified
- `metaculus_posts.py`:
  - Added documentation explaining hardcoding rationale
  - Modified `list_posts_from_tournament()` to ignore `tournament_id` parameter
  - Modified `get_open_question_ids_from_tournament()` to ignore `tournament_id` parameter
  
- `main.py`:
  - Removed environment variable constants: `METACULUS_PROJECT_ID`, `METACULUS_PROJECT_SLUG`, `METACULUS_CONTEST_SLUG`, `FALL_2025_AI_BENCHMARKING_ID`
  - Updated `list_posts_from_tournament()` to ignore `tournament_id` and use hardcoded slug
  - Updated `get_open_question_ids_from_tournament()` to ignore `tournament_id`
  - Updated `fetch_tournament_questions()` to ignore all parameters
  - Modified `tournament_dryrun()` and `run_tournament()` to log config message
  
- `test_integration_tournament.py`:
  - Updated to verify hardcoded tournament slug
  - Added verification that tournament parameters are ignored
  - All tests passing ✓

### Testing
All tests pass:
- ✓ `test_integration_tournament.py`: Verifies hardcoded tournament behavior
- ✓ Tournament slug correctly set to `fall-aib-2025`
- ✓ All function parameters properly ignored
- ✓ Configuration log message appears correctly

### Benefits
1. **Stability**: Prevents accidental tournament misconfiguration
2. **Security**: No risk of environment variable injection
3. **Clarity**: Explicit logging shows which tournament is being used
4. **Simplicity**: One less configuration dimension to worry about

---

## Restore Original Forecast and Comment Submission Logic

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
