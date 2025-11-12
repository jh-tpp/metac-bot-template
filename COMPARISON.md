# Comparison: tournament_dryrun vs tournament_open_check

## Side-by-Side Comparison

| Aspect | `tournament_dryrun` | `tournament_open_check` |
|--------|---------------------|-------------------------|
| **Purpose** | Full dryrun with metadata fetching | Minimal fetch-only operation |
| **API Calls** | Fetches pairs + fetches post details for titles | Fetches pairs only |
| **Artifacts Created** | `.aib-state/open_ids.json` + `mc_results.json` | `.aib-state/open_ids.json` ONLY |
| **Title Fetching** | ✅ Yes (calls `get_post_details` for each question) | ❌ No |
| **mc_results.json** | ✅ Written with dryrun structure | ❌ Not created |
| **Performance** | Slower (multiple API calls per question) | Faster (single paginated fetch) |
| **Use Case** | Manual testing with metadata | CI workflow pre-check phase |
| **Exit Code** | 0 (success) | 0 (success) |
| **Zero Questions** | Writes empty mc_results.json | Writes nothing extra |

## Code Flow Comparison

### tournament_dryrun
```
1. Log configuration
2. Call fetch_open_pairs() → writes .aib-state/open_ids.json
3. If zero questions:
   - Write empty mc_results.json with summary structure
   - Exit
4. If questions exist:
   - Loop through each (qid, pid) pair
   - Call get_post_details(pid) for each to get title
   - Build results array with titles
   - Write mc_results.json with full results
5. Exit
```

### tournament_open_check (NEW)
```
1. Log configuration
2. Call fetch_open_pairs() → writes .aib-state/open_ids.json
3. Print count
4. Exit
```

## Example Outputs

### tournament_dryrun with 3 questions
**Console Output:**
```
[CONFIG] Using hardcoded tournament: fall-aib-2025
[TOURNAMENT DRYRUN] Starting for tournament: fall-aib-2025
[INFO] Fetching open questions from tournament fall-aib-2025
[INFO] Wrote 3 open question pairs to .aib-state/open_ids.json
[INFO] Found 3 open questions in tournament
[TOURNAMENT DRYRUN] Complete. Wrote .aib-state/open_ids.json and mc_results.json for 3 questions
```

**Files Created:**
- `.aib-state/open_ids.json`:
```json
[
  {"question_id": 12345, "post_id": 67890},
  {"question_id": 12346, "post_id": 67891},
  {"question_id": 12347, "post_id": 67892}
]
```

- `mc_results.json`:
```json
[
  {
    "question_id": 12345,
    "post_id": 67890,
    "question_title": "Will AGI be developed by 2030?",
    "forecast_payload": "<dryrun>",
    "status": "dryrun"
  },
  ...
]
```

### tournament_open_check with 3 questions
**Console Output:**
```
[CONFIG] Using hardcoded tournament: fall-aib-2025
[TOURNAMENT OPEN CHECK] Fetch-only mode - will write .aib-state/open_ids.json only
[INFO] Fetching open questions from tournament fall-aib-2025
[INFO] Wrote 3 open question pairs to .aib-state/open_ids.json
[TOURNAMENT OPEN CHECK] Found 3 open question(s)
[TOURNAMENT OPEN CHECK] Complete. Wrote .aib-state/open_ids.json
```

**Files Created:**
- `.aib-state/open_ids.json`:
```json
[
  {"question_id": 12345, "post_id": 67890},
  {"question_id": 12346, "post_id": 67891},
  {"question_id": 12347, "post_id": 67892}
]
```

- `mc_results.json`: ❌ NOT CREATED

## Workflow Impact

### Before (using tournament_dryrun)
```yaml
# Step: Check for new questions
poetry run python main.py --mode tournament_dryrun
# Result: Creates .aib-state/open_ids.json AND mc_results.json
```

**Issues:**
- Creates unnecessary `mc_results.json` during pre-check
- Fetches titles (extra API calls)
- Slower execution
- Artifact pollution during check phase

### After (using tournament_open_check)
```yaml
# Step: Check for new questions  
poetry run python main.py --mode tournament_open_check
# Result: Creates ONLY .aib-state/open_ids.json
```

**Benefits:**
- ✅ No unnecessary artifacts during pre-check
- ✅ Faster execution (fewer API calls)
- ✅ Clear separation of concerns
- ✅ Easier debugging (know which phase created which artifact)

## When to Use Each Mode

### Use `tournament_open_check` when:
- Running in CI workflow pre-check phase
- Only need to check which questions are open
- Want minimal artifacts and fast execution
- Need clean separation between check and forecast phases

### Use `tournament_dryrun` when:
- Testing locally and want to see question titles
- Need `mc_results.json` for debugging/inspection
- Want full metadata without actual forecasting
- Manual testing or development

## Migration Path

Existing code using `tournament_dryrun` can continue to use it. The workflow has been updated to use the new `tournament_open_check` mode for the pre-check phase, but `tournament_dryrun` remains available and unchanged for other use cases.

No breaking changes - both modes coexist peacefully.
