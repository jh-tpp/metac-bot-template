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
        
        # Map to option labels (original format uses dict)
        prob_dict = {option: probs[i] for i, option in enumerate(options)}
        
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
    
    Raises on failure.
    
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
    
    resp.raise_for_status()


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
