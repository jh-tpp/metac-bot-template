# Zero Open Questions Handling - Implementation Summary

## Overview
This implementation addresses the issue where tournament dryrun/real modes raise errors when the Posts API returns zero open questions. The solution ensures graceful handling with proper artifacts and exit code 0.

## Changes Made

### 1. metaculus_posts.py - Pagination Support

Added `list_posts_from_tournament_all()` function:
- Accumulates results from multiple API pages
- Parameters: page_size=50 (default), max_pages=40 (default)
- Handles API errors gracefully
- Stops when no more results or max_pages reached

Updated `get_open_question_ids_from_tournament()`:
- Now uses `list_posts_from_tournament_all()` instead of single-page fetch
- Ensures all open questions are retrieved, even across multiple pages

### 2. main.py - Graceful Zero-Question Handling

#### tournament_dryrun()
When zero questions are found:
- Prints: "[INFO] No open questions in tournament fall-aib-2025; wrote empty artifacts and exiting gracefully."
- Creates `.aib-state/open_ids.json` with empty array `[]`
- Creates `mc_results.json` with structure:
  ```json
  {
    "results": [],
    "count": 0,
    "tournament": "fall-aib-2025",
    "status": "dryrun_empty"
  }
  ```
- Returns normally (exit code 0)

#### run_tournament() (used by tournament_submit mode)
When zero questions are found:
- Prints: "[INFO] No open questions in tournament fall-aib-2025; wrote empty artifacts and exiting gracefully."
- Creates `.aib-state/open_ids.json` with empty array `[]`
- Creates `mc_results.json` with proper empty structure
- Creates `posted_ids.json` with empty array `[]` (in submit mode)
- Returns normally (exit code 0)

## Testing

### Test Coverage
1. **test_zero_questions.py** - Validates graceful zero-question handling
   - Tests tournament_dryrun with zero questions
   - Tests run_tournament (submit mode) with zero questions
   - Verifies artifact creation and content
   - Verifies exit code 0

2. **test_pagination.py** - Validates pagination functionality
   - Single page fetching
   - Multi-page fetching with correct offsets
   - max_pages limit enforcement
   - Empty results handling
   - API error handling during pagination

3. **Existing tests** - All pass
   - test_integration_tournament.py passes

### Manual Testing Results
```bash
# Tournament dryrun with zero questions
$ poetry run python main.py --mode tournament_dryrun
[CONFIG] Using hardcoded tournament: fall-aib-2025
[TOURNAMENT DRYRUN] Starting for tournament: fall-aib-2025
[INFO] Found 0 open questions in tournament fall-aib-2025
[INFO] No open questions in tournament fall-aib-2025; wrote empty artifacts and exiting gracefully.
[INFO] Wrote empty .aib-state/open_ids.json
[INFO] Wrote empty mc_results.json
[TOURNAMENT DRYRUN] Complete. No questions to process.
Exit code: 0

# Tournament submit with zero questions
$ poetry run python main.py --mode tournament_submit
[CONFIG] Using hardcoded tournament: fall-aib-2025
[TOURNAMENT MODE: submit] Starting...
[INFO] No open questions in tournament fall-aib-2025; wrote empty artifacts and exiting gracefully.
[INFO] Wrote empty .aib-state/open_ids.json
[INFO] Wrote empty mc_results.json
[INFO] Wrote empty posted_ids.json
[TOURNAMENT MODE: submit] Complete. No questions to process.
Exit code: 0
```

## Acceptance Criteria - All Met ✅

1. ✅ `poetry run python main.py --mode tournament_dryrun` exits with code 0 when there are no open questions
2. ✅ Writes `.aib-state/open_ids.json` as empty array
3. ✅ Writes `mc_results.json` with summary structure containing `results: []`
4. ✅ `poetry run python main.py --mode tournament_real` exits with code 0 when empty
5. ✅ Pagination covers multi-page tournaments (page_size=50, max_pages=40)
6. ✅ No changes to submission endpoints or numeric CDF logic
7. ✅ Clear info logging explaining graceful exit

## Security
- CodeQL scan: 0 vulnerabilities found
- No new security issues introduced
- Graceful error handling prevents crashes

## CI Friendliness
- Exit code 0 prevents CI failures
- All required artifacts created (no "file not found" errors in upload-artifact steps)
- Clear logging for debugging

## Files Modified
- `metaculus_posts.py` - Added pagination function
- `main.py` - Updated tournament modes for graceful handling
- `test_zero_questions.py` - New test file
- `test_pagination.py` - New test file
