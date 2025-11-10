import requests
from typing import Dict, Any
from http_logging import (
    print_http_request, print_http_response,
    save_http_artifacts, prepare_request_artifact, prepare_response_artifact
)

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
        
        # Enforce length
        if len(probs) < k:
            probs = probs + [0.0] * (k - len(probs))
        elif len(probs) > k:
            probs = probs[:k]
        
        # Normalize
        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]
        else:
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
        cdf = mc_result.get("cdf", [])
        return {
            "probability_yes": None,
            "probability_yes_per_category": None,
            "continuous_cdf": cdf,
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
