import requests
import numpy as np
from typing import Dict, Any, List, Optional
from http_logging import (
    print_http_request, print_http_response,
    save_http_artifacts, prepare_request_artifact, prepare_response_artifact
)

def _sanitize_numeric_cdf(question_obj: Dict, raw_cdf: List[float]) -> List[float]:
    """
    Sanitize numeric/continuous CDF to meet Metaculus API requirements.
    
    Enforces:
    - Length exactly 201
    - Monotone increasing with min step >= 5e-05 between adjacent points
    - Values in [0, 1] (clamped)
    - NaN handling (replaced with interpolation or boundary values)
    - Open bound constraints:
      * If lower bound open: first value >= 0.001
      * If upper bound open: last value <= 0.999
    
    Args:
        question_obj: Question metadata (to check for open bounds)
        raw_cdf: Raw CDF values from MC worlds
    
    Returns:
        Sanitized CDF with exactly 201 points meeting all constraints
    """
    MIN_STEP = 5e-05
    TARGET_LENGTH = 201
    
    # Handle empty or invalid input
    if not raw_cdf:
        # Return uniform CDF from 0 to 1
        return list(np.linspace(0.0, 1.0, TARGET_LENGTH))
    
    # Convert to numpy array for easier manipulation
    cdf = np.array(raw_cdf, dtype=float)
    
    # Step 1: Handle NaNs - replace with linear interpolation or boundary values
    if np.any(np.isnan(cdf)):
        print(f"[SANITIZE] Q{question_obj.get('id', '?')}: Found NaN values, interpolating", flush=True)
        nan_mask = np.isnan(cdf)
        
        # Find valid indices
        valid_indices = np.where(~nan_mask)[0]
        
        if len(valid_indices) == 0:
            # All NaN - return uniform
            cdf = np.linspace(0.0, 1.0, len(cdf))
        elif len(valid_indices) == 1:
            # Only one valid value - use it for all
            cdf = np.full(len(cdf), cdf[valid_indices[0]])
        else:
            # Interpolate NaN values
            cdf[nan_mask] = np.interp(
                np.where(nan_mask)[0],
                valid_indices,
                cdf[valid_indices]
            )
    
    # Step 2: Clamp to [0, 1]
    cdf = np.clip(cdf, 0.0, 1.0)
    
    # Step 3: Ensure monotonicity with minimum step
    # Forward pass: ensure each value >= previous + MIN_STEP (or at least >= previous)
    for i in range(1, len(cdf)):
        if cdf[i] < cdf[i-1]:
            cdf[i] = cdf[i-1]
        # Optionally enforce minimum step (but might cause last value to exceed 1.0)
        # We'll handle this in a second pass
    
    # Step 4: Backward pass to ensure we don't exceed 1.0 while maintaining monotonicity
    # and minimum steps where possible
    for i in range(len(cdf) - 2, -1, -1):
        if cdf[i] > cdf[i+1]:
            cdf[i] = cdf[i+1]
        # Ensure we have room for minimum step if not at boundary
        max_allowed = cdf[i+1] - MIN_STEP
        if i < len(cdf) - 1 and cdf[i] > max_allowed and max_allowed >= 0.0:
            cdf[i] = max(max_allowed, 0.0)
    
    # Step 5: Enforce minimum step where possible (forward pass again)
    for i in range(1, len(cdf)):
        min_required = cdf[i-1] + MIN_STEP
        if cdf[i] < min_required and min_required <= 1.0:
            cdf[i] = min(min_required, 1.0)
    
    # Step 6: Check for open bounds and enforce constraints
    # Check if question has open bounds
    # For Metaculus, we check possibilities/possibility for open_lower_bound and open_upper_bound
    poss = question_obj.get("possibilities") or question_obj.get("possibility") or {}
    if not isinstance(poss, dict):
        poss = {}
    
    open_lower = poss.get("open_lower_bound", False)
    open_upper = poss.get("open_upper_bound", False)
    
    if open_lower and cdf[0] < 0.001:
        print(f"[SANITIZE] Q{question_obj.get('id', '?')}: Open lower bound, adjusting first value from {cdf[0]:.6f} to 0.001", flush=True)
        cdf[0] = 0.001
        # Ensure monotonicity still holds
        for i in range(1, len(cdf)):
            if cdf[i] < cdf[i-1]:
                cdf[i] = cdf[i-1]
    
    if open_upper and cdf[-1] > 0.999:
        print(f"[SANITIZE] Q{question_obj.get('id', '?')}: Open upper bound, adjusting last value from {cdf[-1]:.6f} to 0.999", flush=True)
        cdf[-1] = 0.999
        # Ensure monotonicity still holds (backward pass)
        for i in range(len(cdf) - 2, -1, -1):
            if cdf[i] > cdf[i+1]:
                cdf[i] = cdf[i+1]
    
    # Step 7: Resize to exactly 201 points
    if len(cdf) != TARGET_LENGTH:
        print(f"[SANITIZE] Q{question_obj.get('id', '?')}: Resizing from {len(cdf)} to {TARGET_LENGTH} points", flush=True)
        # Use linear interpolation to resize
        old_indices = np.linspace(0, 1, len(cdf))
        new_indices = np.linspace(0, 1, TARGET_LENGTH)
        cdf = np.interp(new_indices, old_indices, cdf)
    
    # Step 8: Final clamp and convert to list
    cdf = np.clip(cdf, 0.0, 1.0)
    
    # Step 9: Ensure exact endpoints (important for API)
    cdf[0] = max(0.0, cdf[0]) if not open_lower else max(0.001, cdf[0])
    cdf[-1] = min(1.0, cdf[-1]) if not open_upper else min(0.999, cdf[-1])
    
    return cdf.tolist()


def mc_results_to_metaculus_payload(question_obj: Dict, mc_result: Dict) -> Dict:
    """
    Map MC results to Metaculus submission payload using ORIGINAL template format.
    
    Args:
        question_obj: Metaculus question dict
        mc_result: dict with 'p', 'probs', or 'cdf'/'grid'
    
    Returns:
        Payload dict suitable for Metaculus /api/ endpoint (original format)
        Format: {"probability_yes": float, "probability_yes_per_category": dict|None, "continuous_cdf": list|None}
        Note: reasoning is handled separately via comment submission
    """
    qtype = question_obj.get("type", "").lower()
    
    if "binary" in qtype:
        p = mc_result["p"]
        # Clamp (redundant if validated)
        p = max(0.01, min(0.99, p))
        return {
            "probability_yes": p,
            "probability_yes_per_category": None,
            "continuous_cdf": None,
        }
    
    elif "multiple" in qtype or "mc" in qtype:
        probs = mc_result["probs"]
        options = question_obj.get("options", [])
        k = len(options)
        
        # Ensure non-negative probabilities
        probs = [max(0.0, p) for p in probs]
        
        # Enforce length match
        if len(probs) < k:
            probs = probs + [0.0] * (k - len(probs))
        elif len(probs) > k:
            probs = probs[:k]
        
        # Normalize to sum=1.0
        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]
        else:
            # Uniform distribution if all zeros
            probs = [1.0 / k] * k
        
        # Map to option names (extract from dict or use as-is if string)
        # Options can be list of dicts with 'name' key or list of strings
        option_names = []
        for opt in options:
            if isinstance(opt, dict):
                option_names.append(opt.get("name", str(opt)))
            else:
                option_names.append(str(opt))
        
        prob_dict = {option_names[i]: probs[i] for i in range(len(option_names))}
        
        return {
            "probability_yes": None,
            "probability_yes_per_category": prob_dict,
            "continuous_cdf": None,
        }
    
    elif "numeric" in qtype or "continuous" in qtype:
        # Original format uses continuous_cdf as list
        raw_cdf = mc_result.get("cdf", [])
        
        # Sanitize CDF to meet API requirements
        sanitized_cdf = _sanitize_numeric_cdf(question_obj, raw_cdf)
        
        return {
            "probability_yes": None,
            "probability_yes_per_category": None,
            "continuous_cdf": sanitized_cdf,
        }
    
    raise ValueError(f"Unknown question type: {qtype}")

def submit_forecast(question_id: int, payload: Dict, token: str, trace=None):
    """
    POST forecast to Metaculus using ORIGINAL template format.
    
    Args:
        question_id: Metaculus question ID
        payload: submission payload (probability_yes, probability_yes_per_category, continuous_cdf)
        token: Metaculus API token
        trace: Optional DiagnosticTrace for saving diagnostics
    
    Raises on failure with detailed error information.
    
    Note: This uses the original /api/ endpoint with array format: [{"question": <id>, ...}]
    """
    from main import _diag_save
    
    url = "https://www.metaculus.com/api/questions/forecast/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    
    # Original template format: wrap payload in array with "question" field
    request_body = [
        {
            "question": question_id,
            **payload,
        }
    ]
    
    # Pre-submission validation
    _validate_payload_before_submit(question_id, payload)
    
    # Save submission payload diagnostics
    if trace:
        try:
            submission_diag = {
                "url": url,
                "question_id": question_id,
                "payload": request_body,
                "headers": {k: v for k, v in headers.items() if k.lower() != "authorization"}
            }
            _diag_save(trace, "30_submission_payload", submission_diag, redact=True)
        except Exception as e:
            print(f"[WARN] Failed to save submission payload diagnostics: {e}", flush=True)
    
    # HTTP logging: log request
    print_http_request(
        method="POST",
        url=url,
        headers=headers,
        json_body=request_body,
        timeout=30
    )
    
    resp = requests.post(url, json=request_body, headers=headers, timeout=30)
    
    # HTTP logging: log response
    print_http_response(resp)
    
    # HTTP logging: save artifacts
    request_artifact = prepare_request_artifact(
        method="POST",
        url=url,
        headers=headers,
        json_body=request_body,
        timeout=30
    )
    response_artifact = prepare_response_artifact(resp)
    save_http_artifacts(f"metaculus_submit_{question_id}", request_artifact, response_artifact)
    
    # Save submission response diagnostics
    if trace:
        try:
            # Try to get JSON body
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            
            response_diag = {
                "status": resp.status_code,
                "reason": resp.reason,
                "headers": {k: v for k, v in resp.headers.items() if k.lower() not in ["authorization", "set-cookie"]},
                "body": body
            }
            _diag_save(trace, "31_submission_response", response_diag, redact=True)
        except Exception as e:
            print(f"[WARN] Failed to save submission response diagnostics: {e}", flush=True)
    
    # Enhanced error handling for non-2xx responses
    if not resp.ok:
        error_msg = f"[FORECAST ERROR] question_id={question_id} status={resp.status_code}\n"
        error_msg += f"  payload={request_body}\n"
        
        try:
            error_body = resp.json()
            error_msg += f"  response={error_body}\n"
            
            # Extract field-level errors if present
            if isinstance(error_body, dict):
                for field, messages in error_body.items():
                    if isinstance(messages, list):
                        error_msg += f"  field_error[{field}]={messages}\n"
                    else:
                        error_msg += f"  field_error[{field}]={messages}\n"
        except Exception:
            error_body = resp.text[:500]
            error_msg += f"  response_text={error_body}\n"
        
        print(error_msg, flush=True)
        resp.raise_for_status()


def _validate_payload_before_submit(question_id: int, payload: Dict):
    """
    Validate payload before submission to catch common errors early.
    
    Args:
        question_id: Question ID for logging
        payload: Submission payload to validate
    
    Raises:
        ValueError: If validation fails
    """
    # Binary validation
    if payload.get("probability_yes") is not None:
        p = payload["probability_yes"]
        if not isinstance(p, (int, float)):
            raise ValueError(f"Q{question_id}: probability_yes must be numeric, got {type(p)}")
        if not (0.01 <= p <= 0.99):
            raise ValueError(f"Q{question_id}: probability_yes={p} outside [0.01, 0.99]")
    
    # Multiple choice validation
    if payload.get("probability_yes_per_category") is not None:
        probs = payload["probability_yes_per_category"]
        if not isinstance(probs, dict):
            raise ValueError(f"Q{question_id}: probability_yes_per_category must be dict, got {type(probs)}")
        
        # Check all values are numeric and in [0, 1]
        for option, prob in probs.items():
            if not isinstance(prob, (int, float)):
                raise ValueError(f"Q{question_id}: option '{option}' has non-numeric prob {type(prob)}")
            if not (0.0 <= prob <= 1.0):
                raise ValueError(f"Q{question_id}: option '{option}' prob={prob} outside [0, 1]")
        
        # Check sum is approximately 1.0
        total = sum(probs.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Q{question_id}: probabilities sum to {total}, not 1.0")
    
    # Numeric validation
    if payload.get("continuous_cdf") is not None:
        cdf = payload["continuous_cdf"]
        if not isinstance(cdf, list):
            raise ValueError(f"Q{question_id}: continuous_cdf must be list, got {type(cdf)}")
        
        if len(cdf) != 201:
            raise ValueError(f"Q{question_id}: continuous_cdf must have 201 points, got {len(cdf)}")
        
        # Check values are in [0, 1] and monotonic
        for i, val in enumerate(cdf):
            if not isinstance(val, (int, float)):
                raise ValueError(f"Q{question_id}: continuous_cdf[{i}] is non-numeric")
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Q{question_id}: continuous_cdf[{i}]={val} outside [0, 1]")
            if i > 0 and val < cdf[i-1]:
                raise ValueError(f"Q{question_id}: continuous_cdf not monotonic at index {i}")
        
        # Enforce endpoints
        if abs(cdf[0]) > 1e-6:
            print(f"[WARN] Q{question_id}: continuous_cdf[0]={cdf[0]}, should be ~0.0; adjusting", flush=True)
            cdf[0] = 0.0
        if abs(cdf[-1] - 1.0) > 1e-6:
            print(f"[WARN] Q{question_id}: continuous_cdf[-1]={cdf[-1]}, should be 1.0; adjusting", flush=True)
            cdf[-1] = 1.0


def submit_comment(post_id: int, comment_text: str, token: str, trace=None):
    """
    POST a reasoning comment to Metaculus using ORIGINAL template format.
    
    Args:
        post_id: Metaculus post ID (not question ID)
        comment_text: The reasoning/comment text
        token: Metaculus API token
        trace: Optional DiagnosticTrace for saving diagnostics
    
    Raises on failure.
    
    Note: This uses the original /api/comments/create/ endpoint
    Comments should be posted AFTER forecasts
    """
    from main import _diag_save
    
    url = "https://www.metaculus.com/api/comments/create/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    
    request_body = {
        "text": comment_text,
        "parent": None,
        "included_forecast": True,
        "is_private": True,
        "on_post": post_id,
    }
    
    # Save comment payload diagnostics
    if trace:
        try:
            comment_diag = {
                "url": url,
                "post_id": post_id,
                "payload": request_body,
                "headers": {k: v for k, v in headers.items() if k.lower() != "authorization"}
            }
            _diag_save(trace, "32_comment_payload", comment_diag, redact=True)
        except Exception as e:
            print(f"[WARN] Failed to save comment payload diagnostics: {e}", flush=True)
    
    # HTTP logging: log request
    print_http_request(
        method="POST",
        url=url,
        headers=headers,
        json_body=request_body,
        timeout=30
    )
    
    resp = requests.post(url, json=request_body, headers=headers, timeout=30)
    
    # HTTP logging: log response
    print_http_response(resp)
    
    # HTTP logging: save artifacts
    request_artifact = prepare_request_artifact(
        method="POST",
        url=url,
        headers=headers,
        json_body=request_body,
        timeout=30
    )
    response_artifact = prepare_response_artifact(resp)
    save_http_artifacts(f"metaculus_comment_{post_id}", request_artifact, response_artifact)
    
    # Save comment response diagnostics
    if trace:
        try:
            # Try to get JSON body
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            
            response_diag = {
                "status": resp.status_code,
                "reason": resp.reason,
                "headers": {k: v for k, v in resp.headers.items() if k.lower() not in ["authorization", "set-cookie"]},
                "body": body
            }
            _diag_save(trace, "33_comment_response", response_diag, redact=True)
        except Exception as e:
            print(f"[WARN] Failed to save comment response diagnostics: {e}", flush=True)
    
    resp.raise_for_status()
