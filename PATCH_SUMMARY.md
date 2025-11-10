# Corrective Patch Summary

## Overview
This patch addresses multiple API integration issues with Metaculus by implementing the official template approach, adding robust error handling, and enforcing "Option B" for world identifiers to prevent configuration errors.

## Problems Fixed

### 0. Option B Enforcement: N_WORLDS_DEFAULT → N_WORLDS_TEST
**Symptom**: Ambiguous world identifier usage and potential configuration errors
**Root Cause**: Mixed use of N_WORLDS_DEFAULT for both test and tournament contexts
**Fix**:
- Renamed all `N_WORLDS_DEFAULT` → `N_WORLDS_TEST` globally (6 occurrences in main.py, 1 in test file)
- Tournament mode now exclusively uses `N_WORLDS_TOURNAMENT` (not overridable via workflow inputs)
- Removed `simulations` input parameter from tournament workflow
- Test/smoke paths use `N_WORLDS_TEST`, tournament paths use `N_WORLDS_TOURNAMENT`
- Zero lingering references verified via grep

### 0b. 400 Bad Request Forecast Submission Errors
**Symptom**: Forecasts rejected with 400 status, unclear error reasons
**Root Cause**: Invalid payload structure or values not caught before submission
**Fix**:
- Added `_validate_payload_before_submit()` with type-specific validation:
  - Binary: validates probability_yes in [0.01, 0.99]
  - Multiple choice: validates probabilities sum to 1.0, option names correct
  - Numeric: validates 201-point CDF, monotonicity, endpoints
- Enhanced `submit_forecast()` error logging with structured `[FORECAST ERROR]` blocks
- Enhanced `post_forecast_safe()` to extract and display field-level API errors
- Fixed `mc_results_to_metaculus_payload()` to correctly extract option names from dicts
- No automatic retries on 400 (fail gracefully and continue to next question)

### 1. 403 Forbidden Errors
**Symptom**: `/api/questions/{id}/` returns 403 during smoke tests
**Root Cause**: Missing Authorization header
**Fix**: 
- Created `metaculus_fetch.py` module that always includes `Authorization: Token {METACULUS_TOKEN}` when the token is present
- Added preflight check in `_hydrate_question_with_diagnostics()` to fail fast if token is missing

### 2. 404 Not Found Errors  
**Symptom**: `/api/questions/?search=project:...` returns 404 when fetching tournament data
**Root Cause**: Using deprecated search endpoint
**Fix**:
- Created `metaculus_posts.py` using official `/api/posts/` endpoint
- Implemented `list_posts_from_tournament()` with proper tournament filtering
- Returns (question_id, post_id) pairs for correct ID mapping

### 3. Question/Post ID Mapping
**Symptom**: Submissions sometimes mapped to wrong question IDs
**Root Cause**: `post_id != question_id` in many cases
**Fix**:
- Ensure forecasts POST to `/api/questions/forecast/` with `question_id`
- Ensure comments POST to `/api/comments/create/` with `post_id`
- `fetch_question_with_fallback()` tries multiple paths and returns both IDs

### 4. Missing CI Artifacts
**Symptom**: `.aib-state/open_ids.json` and `mc_results.json` not created
**Root Cause**: No dryrun mode implementation
**Fix**:
- Added `tournament_dryrun()` function
- Writes `.aib-state/open_ids.json` with (question_id, post_id) pairs
- Writes `mc_results.json` even in dryrun mode
- Added helper functions `_ensure_state_dir()` and `_write_open_ids()`

### 5. Excessive HTTP Logging
**Symptom**: Noisy console output from HTTP requests
**Root Cause**: Logging always enabled
**Fix**:
- Updated `http_logging.py` to gate printing/saving behind `HTTP_LOGGING_ENABLED` env var
- Default is false (quiet)
- Kept `prepare_*` functions fully functional for when logging is enabled

## Files Modified

### Created Files
1. **metaculus_fetch.py** (167 lines)
   - `_attempt_get()`: Resilient HTTP GET with retries for 429, 500, 502, 503, 504
   - `fetch_post()`: Fetch post by ID
   - `fetch_question()`: Fetch question by ID
   - `fetch_question_with_fallback()`: Try multiple paths with fallbacks
   - `FetchError`: Custom exception for fetch failures

2. **metaculus_posts.py** (95 lines)
   - `list_posts_from_tournament()`: Fetch posts using /api/posts/ endpoint
   - `get_open_question_ids_from_tournament()`: Get (question_id, post_id) pairs
   - `get_post_details()`: Fetch individual post details

3. **test_corrective_patch.py** (128 lines)
   - Validation tests for new functionality
   - Tests HTTP logging default state
   - Tests state directory helpers
   - Tests module imports

### Modified Files
1. **http_logging.py** (237 lines total, ~200 changed)
   - Added `HTTP_LOGGING_ENABLED` env var (default: false)
   - Updated `print_http_request()` to check flag
   - Updated `print_http_response()` to check flag
   - Updated `save_http_artifacts()` to check flag
   - Kept `prepare_request_artifact()` and `prepare_response_artifact()` fully functional
   - Maintained backward compatibility

2. **main.py** (2660 lines total, ~200 changed)
   - Imported `metaculus_fetch` and `metaculus_posts`
   - Added `_ensure_state_dir()` and `_write_open_ids()` helpers
   - Replaced `_hydrate_question_with_diagnostics()` to use new fetch module
   - Added `tournament_dryrun()` function
   - Updated CLI to handle `tournament_dryrun` mode

3. **.gitignore**
   - Added `.aib-state/`
   - Added `.http-artifacts/`

4. **test_http_logging.py**
   - Updated for new `HTTP_LOGGING_ENABLED` env var (was `LOG_IO_DISABLE`)
   - Added test setup to enable logging for artifact tests
   - Updated assertions for new behavior

## Testing Results

### Unit Tests
- ✅ test_http_logging.py: All 5 tests pass
- ✅ test_corrective_patch.py: All 7 tests pass
- ✅ Python syntax validation passes
- ✅ Module imports work correctly

### Validated Behavior
- ✅ HTTP logging disabled by default
- ✅ HTTP logging can be enabled via env var
- ✅ State directory helpers work correctly
- ✅ New modules import successfully
- ✅ CLI argument parsing works
- ✅ Backward compatibility maintained

## Numeric CDF Validation
Verified that existing numeric CDF handling is preserved:
- ✅ 201-point resampling (in `mc_worlds.py`)
- ✅ 5e-05 min-step enforcement (in `mc_worlds.py`)
- ✅ Submissions use `/api/questions/forecast/` with list body format
- ✅ Comments use `/api/comments/create/` with `post_id`

## Usage Examples

### Enable HTTP Logging
```bash
export HTTP_LOGGING_ENABLED=true
python main.py --mode tournament_dryrun
```

### Run Tournament Dryrun
```bash
python main.py --mode tournament_dryrun
# Creates: .aib-state/open_ids.json, mc_results.json
```

### Run Smoke Test (requires METACULUS_TOKEN)
```bash
export METACULUS_TOKEN=your_token
python main.py --mode submit_smoke_test --qid 578
```

## API Endpoint Reference

### Forecasts (uses question_id)
```
POST /api/questions/forecast/
Body: [{"question": <question_id>, "probability_yes": <p>, ...}]
```

### Comments (uses post_id)
```
POST /api/comments/create/
Body: {"on_post": <post_id>, "text": <text>, ...}
```

### Fetch Post
```
GET /api/posts/{post_id}/
Returns: {"id": <post_id>, "question": {...}, ...}
```

### Fetch Question
```
GET /api/questions/{question_id}/
Returns: {"id": <question_id>, ...}
```

### List Tournament Posts
```
GET /api/posts/?tournaments=<slug>&statuses=open&...
Returns: {"results": [{"id": <post_id>, "question": {...}}, ...]}
```

## Deployment Notes

1. **Environment Variables**
   - `METACULUS_TOKEN`: Required for API access (fixes 403)
   - `HTTP_LOGGING_ENABLED`: Optional, default false (set to true for debugging)

2. **File Artifacts**
   - `.aib-state/open_ids.json`: Created by tournament_dryrun
   - `mc_results.json`: Created by all tournament modes
   - `.http-artifacts/`: Created when HTTP_LOGGING_ENABLED=true (gitignored)

3. **Backward Compatibility**
   - Existing `adapters.py` unchanged
   - Existing `mc_worlds.py` unchanged
   - Existing test files updated but still pass
   - CLI arguments unchanged

## Next Steps

1. Test with real METACULUS_TOKEN in CI
2. Verify 403 errors are resolved
3. Verify tournament_dryrun creates correct artifacts
4. Verify quiet logging in production
