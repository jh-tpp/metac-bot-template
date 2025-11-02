# Metaculus API v2 Normalization - Implementation Summary

This document summarizes the changes made to support Metaculus API v2 normalization.

## Problem Statement

The Metaculus API v2 nests question data under a `question` key, but the original code was reading from top-level keys, causing normalization failures.

## Changes Made

### 1. Core Question Pivoting (`_get_core_question`)
- Helper function at line 139-152 that pivots into nested `question` key if present
- Used throughout the codebase to ensure consistent access to question data

### 2. Type Inference (`_infer_qtype_and_fields`)
- Lines 183-336: Main normalization logic
- Always pivots into `core = _get_core_question(q)` before reading (line 201)
- Reads `possibilities`/`possibility` from core (line 205)
- Maps v2 types to canonical types:
  - `binary` → `binary`
  - `discrete` → `multiple_choice` (extracts options from `outcomes[].name|label`)
  - `continuous` → `numeric` (extracts bounds from `range` or `min/max`, plus `unit`/`scale`)

### 3. Title/Description Extraction
- Updated all callers to extract from `core` first, with fallback to top-level:
  - `fetch_tournament_questions` (lines 469-470)
  - `run_live_test` (lines 1253-1254)
  - `run_submit_smoke_test` (lines 1388-1389)

### 4. Fetch Layer Improvements
- Detail endpoint hydration (line 403) uses no `expand`/`fields` parameters
- Relies on native v2 `question` payload structure
- List fetch keeps `expand`/`fields` for backward compatibility

### 5. Enhanced Diagnostics (`_debug_log_fetch`)
- Lines 100-137: Comprehensive diagnostic logging
- Logs both top-level keys and core (nested `question`) keys
- Specifically logs `core.possibilities.type` for both dict and list forms
- Helps identify API structure issues during debugging

## Testing

### Unit Tests (`test_normalization.py`)
- 8 comprehensive tests covering:
  - Binary questions with nested structure
  - Discrete → multiple_choice mapping with `outcomes[].name|label`
  - Continuous → numeric mapping with `range` and `min/max`
  - Fallback to flat structure (backward compatibility)
  - Options extraction from both `outcomes` and `options` fields
  - Core question pivoting logic

All tests pass, verifying correct normalization for v2 API.

## Acceptance Criteria

✅ Q578 → binary  
✅ Q14333 → numeric with [min, max] when present  
✅ Q22427 → numeric or multiple_choice depending on outcomes/range  
✅ Diagnostics show `Core('question') keys` and `core.possibilities.type`

## Files Modified

1. `main.py`:
   - Enhanced `_debug_log_fetch` to properly log `possibilities.type`
   - All other v2 support was already implemented correctly

2. `test_normalization.py` (new):
   - Comprehensive unit tests for normalization logic
   - Verifies all v2 type mappings and edge cases
