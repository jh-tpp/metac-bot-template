# Numeric CDF Sanitizer Summary

## Purpose
The `_sanitize_numeric_cdf()` function ensures that all numeric/continuous forecast CDFs meet Metaculus API requirements, eliminating 400 Bad Request errors (e.g., for questions like Q40221).

## Implementation Location
- **File**: `adapters.py`
- **Function**: `_sanitize_numeric_cdf(question_obj: Dict, raw_cdf: List[float]) -> List[float]`
- **Lines**: ~125 lines
- **Integration**: Automatically applied in `mc_results_to_metaculus_payload()` for all numeric forecasts

## Enforced Constraints

### 1. Length Requirement
- **Constraint**: Exactly 201 points
- **Implementation**: Linear interpolation to resize from any input length
- **Example**: Input of 50 or 500 points → resized to 201 points

### 2. Monotonicity
- **Constraint**: CDF must be strictly non-decreasing (each value >= previous)
- **Implementation**: 
  - Forward pass: Ensures each value >= previous
  - Backward pass: Ensures we don't exceed 1.0 while maintaining monotonicity
- **Example**: `[0.0, 0.5, 0.3, 1.0]` → `[0.0, 0.5, 0.5, 1.0]`

### 3. Minimum Step Between Points
- **Constraint**: Adjacent values should differ by >= 5e-05 where possible
- **Implementation**: Forward pass enforces minimum step without exceeding 1.0
- **Purpose**: Prevents plateau regions that might indicate numerical issues

### 4. Value Range
- **Constraint**: All values must be in [0.0, 1.0]
- **Implementation**: `np.clip(cdf, 0.0, 1.0)` applied throughout
- **Example**: `[-0.1, 0.5, 1.2]` → `[0.0, 0.5, 1.0]`

### 5. NaN Handling
- **Constraint**: No NaN values allowed
- **Implementation**: Linear interpolation from neighboring valid values
- **Example**: `[0.0, NaN, 0.5, NaN, 1.0]` → interpolated smooth curve

### 6. Open Bound Constraints
- **Constraint**: 
  - If lower bound open (unbounded below): first value >= 0.001
  - If upper bound open (unbounded above): last value <= 0.999
- **Implementation**: Checks `question_obj.possibilities.open_lower_bound` / `open_upper_bound`
- **Reasoning**: Open bounds mean the distribution extends beyond the displayed range
- **Example**: Q40221 (open bounds) → first value 0.001, last value 0.999

### 7. Exact Endpoints (Closed Bounds)
- **Constraint**: For closed bounds, endpoints should be exactly 0.0 and 1.0
- **Implementation**: Final enforcement step after all other processing
- **Example**: Closed bounds → `cdf[0] = 0.0`, `cdf[-1] = 1.0`

## Processing Pipeline

```
Input CDF (any length, any values)
    ↓
1. Handle NaNs (linear interpolation)
    ↓
2. Clamp to [0.0, 1.0]
    ↓
3. Forward pass: enforce monotonicity
    ↓
4. Backward pass: maintain monotonicity without exceeding 1.0
    ↓
5. Forward pass: enforce minimum step where possible
    ↓
6. Check and enforce open bound constraints
    ↓
7. Resize to exactly 201 points (linear interpolation)
    ↓
8. Final clamp and endpoint enforcement
    ↓
Output: Sanitized 201-point CDF meeting all requirements
```

## Logging
The sanitizer provides detailed `[SANITIZE]` logs for debugging:
- `[SANITIZE] Q{id}: Found NaN values, interpolating`
- `[SANITIZE] Q{id}: Open lower bound, adjusting first value from X to 0.001`
- `[SANITIZE] Q{id}: Open upper bound, adjusting last value from Y to 0.999`
- `[SANITIZE] Q{id}: Resizing from N to 201 points`

## Example Usage

```python
from adapters import _sanitize_numeric_cdf

# Question with open bounds (like Q40221)
question = {
    "id": 40221,
    "type": "numeric",
    "possibilities": {
        "open_lower_bound": True,
        "open_upper_bound": True
    }
}

# Raw CDF from Monte Carlo simulation (wrong length, wrong endpoints)
raw_cdf = [0.0, 0.2, 0.5, 0.8, 1.0]  # Only 5 points

# Sanitize
sanitized = _sanitize_numeric_cdf(question, raw_cdf)

# Result:
# - Length: 201 (✓)
# - First value: >= 0.001 (✓ open lower bound)
# - Last value: <= 0.999 (✓ open upper bound)
# - Monotonic: ✓
# - All in [0, 1]: ✓
```

## Test Coverage
10 comprehensive tests in `test_numeric_cdf_sanitizer.py`:
1. Basic sanitization
2. Resizing (from 50, from 500)
3. NaN handling
4. Clamping to [0, 1]
5. Monotonicity enforcement
6. Open lower bound constraint
7. Open upper bound constraint
8. Empty input handling
9. All-zeros handling
10. Minimum step enforcement

All tests pass ✅

## Integration
The sanitizer is automatically applied in the payload generation pipeline:

```python
def mc_results_to_metaculus_payload(question_obj: Dict, mc_result: Dict) -> Dict:
    # ...
    elif "numeric" in qtype or "continuous" in qtype:
        raw_cdf = mc_result.get("cdf", [])
        
        # Sanitize CDF to meet API requirements (automatic)
        sanitized_cdf = _sanitize_numeric_cdf(question_obj, raw_cdf)
        
        return {
            "probability_yes": None,
            "probability_yes_per_category": None,
            "continuous_cdf": sanitized_cdf,  # Always sanitized
        }
```

No changes required to existing code that generates forecasts - sanitization happens transparently.

## Impact
- **Before**: Numeric forecasts often rejected with 400 errors
- **After**: All numeric forecasts automatically meet API requirements
- **Q40221 example**: Fixed endpoint constraint violations for open-bound questions
- **Zero downtime**: Existing code continues to work without modification
