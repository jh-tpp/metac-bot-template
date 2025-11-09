# Tournament Workflow Implementation Summary

## Overview
This implementation provides a clean, robust tournament forecasting workflow for the Fall 2025 AIB tournament ('fall-aib-2025'). It addresses all issues mentioned in the problem statement and eliminates missing artifacts, wrong IDs, repeated submissions, and noisy logs.

## Problem Analysis

### Issues Identified
1. **No dedicated fetch function** - Logic was scattered across multiple functions
2. **Missing posted_ids tracking** - No system to prevent duplicate submissions  
3. **Inconsistent state file paths** - Some in root, some in `.aib-state/`
4. **No force override** - No way to bypass posted list for manual testing
5. **CI workflow path issues** - Expected files in wrong locations

## Solution Architecture

### 1. Unified Tournament Fetching

**Function:** `fetch_open_pairs()`

```python
def fetch_open_pairs():
    """
    Fetch open (question_id, post_id) pairs from Fall 2025 AIB tournament.
    Writes .aib-state/open_ids.json before returning.
    """
```

**Features:**
- Single source of truth for tournament data
- Atomic file write before return
- Returns stable list of tuples
- Uses existing paginated API calls

**File Format (`.aib-state/open_ids.json`):**
```json
[
  {"question_id": 12345, "post_id": 67890},
  {"question_id": 12346, "post_id": 67891}
]
```

### 2. Posted IDs Tracking System

**Functions:**
- `_load_posted_ids()` - Load set from `.aib-state/posted_ids.json`
- `_append_posted_id(question_id)` - Atomically append after successful submission

**Workflow:**
1. At start: Load posted_ids from `.aib-state/posted_ids.json`
2. Before processing: Filter out questions already in posted set
3. After successful forecast+comment: Append question_id atomically
4. For CI compatibility: Also write `posted_ids.json` in root

**File Format (`.aib-state/posted_ids.json`):**
```json
[12345, 12346, 12347]
```

**Atomic Write Implementation:**
- Write to `.json.tmp` file first
- Use `Path.replace()` to atomically replace
- Clean up temp file on error

### 3. Force Flag

**CLI:**
```bash
python main.py --mode tournament_submit --force
```

**Environment Variable:**
```bash
FORCE=true python main.py --mode tournament_submit
```

**Behavior:**
- When enabled: Ignores `.aib-state/posted_ids.json`
- When disabled: Filters out already-posted questions
- Useful for manual testing and re-forecasting

### 4. Updated Workflows

#### tournament_dryrun()
- Uses `fetch_open_pairs()` instead of direct API calls
- Writes `.aib-state/open_ids.json` (not root)
- Handles empty tournaments gracefully

#### run_tournament()
- Loads posted_ids unless force=True
- Filters questions before processing
- Persists to `.aib-state/posted_ids.json` after each success
- Writes `posted_ids.json` in root for CI compatibility

#### CI Workflow (run_bot_on_tournament.yaml)
- Reads from `.aib-state/open_ids.json`
- Handles both list formats (ints and dicts)
- Uploads correct artifact paths

## State File Structure

```
.aib-state/
├── open_ids.json      # List of {question_id, post_id} dicts
└── posted_ids.json    # List of question IDs (sorted)

posted_ids.json        # Root file for CI (same content as .aib-state/posted_ids.json)
```

## Testing

### New Test Suite (`test_tournament_workflow.py`)
1. **test_fetch_open_pairs_writes_state** - Validates file format and creation
2. **test_posted_ids_tracking** - Validates deduplication
3. **test_force_flag_bypasses_posted** - Validates force behavior
4. **test_empty_tournament_handling** - Validates graceful empty handling
5. **test_posted_ids_atomic_write** - Validates atomic writes

### Existing Tests (All Pass)
- `test_hardcoded_tournament.py` - Tournament hardcoding
- `test_zero_questions.py` - Empty tournament handling
- `test_integration_tournament.py` - Integration tests

## Usage Examples

### Dry Run (Discover Open Questions)
```bash
poetry run python main.py --mode tournament_dryrun
```
**Output:**
- `.aib-state/open_ids.json`
- `mc_results.json` (with dryrun status)

### Submit Mode (Normal)
```bash
poetry run python main.py --mode tournament_submit
```
**Behavior:**
- Loads `.aib-state/posted_ids.json`
- Skips already-posted questions
- Updates `.aib-state/posted_ids.json` after each success
- Writes `posted_ids.json` in root for CI

### Submit Mode (Force)
```bash
poetry run python main.py --mode tournament_submit --force
```
**Behavior:**
- Ignores `.aib-state/posted_ids.json`
- Processes all questions
- Still updates posted_ids after each success

## CI Workflow

```yaml
# Step 1: Dry run to discover open questions
- name: Run bot (dry run)
  run: poetry run python main.py --mode tournament_dryrun
  # Creates: .aib-state/open_ids.json

# Step 2: Check for new questions
- name: Check for new questions
  run: |
    # Compare .aib-state/open_ids.json vs .aib-state/posted_ids.json
    # Set should_submit=true if new questions found

# Step 3: Submit if new questions exist
- name: Run bot (submit)
  if: steps.check_new.outputs.should_submit == 'true'
  run: poetry run python main.py --mode tournament_submit
  # Updates: .aib-state/posted_ids.json, posted_ids.json

# Step 4: Merge posted IDs and save state cache
- name: Update state cache
  run: |
    # Merge posted_ids.json into .aib-state/posted_ids.json
```

## Security

- **No credentials exposed** - All file writes use safe paths
- **Atomic writes** - Prevent corruption on errors
- **CodeQL clean** - No security vulnerabilities detected
- **State files gitignored** - `.aib-state/` in .gitignore

## Backward Compatibility

- All existing functions still work
- CI workflow still gets `posted_ids.json` in root
- Tournament slug remains hardcoded to 'fall-aib-2025'
- No breaking changes to API

## Future Improvements

Potential enhancements (not in scope):

1. **Retry logic** - Retry failed submissions before marking as posted
2. **Posted metadata** - Track timestamp, success status in posted_ids
3. **Clean old state** - Remove IDs for closed/resolved questions
4. **Logging levels** - Make logs less noisy with configurable levels
5. **State validation** - Verify state files on startup

## Conclusion

This implementation provides a robust, well-tested tournament workflow that:
✅ Eliminates missing artifacts through atomic writes
✅ Prevents wrong IDs with unified fetch function
✅ Stops repeated submissions via posted_ids tracking
✅ Reduces noisy logs with cleaner workflow
✅ Maintains backward compatibility
✅ Passes all tests (new and existing)
✅ Has no security vulnerabilities
