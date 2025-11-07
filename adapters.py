import os
import json
import requests
from typing import Dict, Any, List
from http_logging import (
    print_http_request, print_http_response,
    save_http_artifacts, prepare_request_artifact, prepare_response_artifact
)

# Align with original template: use /api (not /api2) and official endpoints
API_BASE_URL = "https://www.metaculus.com/api"

def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {k: ("<redacted>" if k.lower() == "authorization" else v) for k, v in headers.items()}

def create_forecast_payload(
    forecast: float | Dict[str, float] | List[float],
    question_type: str,
) -> Dict[str, Any]:
    """
    Original template payload format used by Metaculus:
    - Binary: probability_yes is a float
    - Multiple choice (discrete): probability_yes_per_category is a dict name->prob
    - Numeric/date: continuous_cdf is a list (typically 201-length) of floats
    """
    if question_type == "binary":
        return {
            "probability_yes": forecast,
            "probability_yes_per_category": None,
            "continuous_cdf": None,
        }
    if question_type == "multiple_choice":
        return {
            "probability_yes": None,
            "probability_yes_per_category": forecast,
            "continuous_cdf": None,
        }
    # numeric or date
    return {
        "probability_yes": None,
        "probability_yes_per_category": None,
        "continuous_cdf": forecast,
    }

def mc_results_to_metaculus_payload(question_obj: Dict, mc_result: Dict) -> Dict:
    """
    Convert Monte Carlo result to the ORIGINAL Metaculus API payload structure
    (as used by the reference template).
    """
    qtype = question_obj.get("type", "").lower()

    if "binary" in qtype:
        p = mc_result.get("p")
        if p is None:
            raise ValueError("Binary result missing 'p'")
        # Clamp to [0.01, 0.99] like the template
        p = max(0.01, min(0.99, float(p)))
        return create_forecast_payload(p, "binary")

    elif "multiple" in qtype or "mc" in qtype or qtype == "discrete":
        probs = mc_result.get("probs")
        if probs is None:
            raise ValueError("Multiple choice result missing 'probs'")
        # Normalize/fit to options
        opts = question_obj.get("options", [])
        # options might be list[str] or list[{name: str}]
        if opts and isinstance(opts[0], dict):
            option_names = [o.get("name") or o.get("label") or o.get("title") for o in opts]
        else:
            option_names = list(opts)
        if not option_names:
            raise ValueError("Multiple choice question is missing options")
        if len(probs) != len(option_names):
            raise ValueError(f"MC probs length {len(probs)} != k={len(option_names)}")
        total = sum(probs)
        if total <= 0:
            probs = [1.0 / len(option_names)] * len(option_names)
        else:
            probs = [max(0.0, p) for p in probs]
            s = sum(probs)
            probs = [p / s for p in probs]
        forecast_dict = {name: prob for name, prob in zip(option_names, probs)}
        return create_forecast_payload(forecast_dict, "multiple_choice")

    elif "numeric" in qtype or "continuous" in qtype or qtype == "date":
        # The original template expects a list of floats for continuous_cdf
        cdf = mc_result.get("cdf")
        if not isinstance(cdf, list) or len(cdf) == 0:
            raise ValueError("Numeric result missing 'cdf' list")
        return create_forecast_payload(cdf, "numeric")

    raise ValueError(f"Unknown question type: {qtype}")

def submit_forecast(question_id: int, forecast_payload: Dict, token: str, trace=None):
    """
    Submit a single forecast to Metaculus using the original endpoint:
      POST {API_BASE_URL}/questions/forecast/
    Body: [ {"question": <id>, <forecast_payload>} ]
    """
    url = f"{API_BASE_URL}/questions/forecast/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    final_payload = [
        {
            "question": question_id,
            **forecast_payload,
        }
    ]

    # Optional trace logging
    if trace:
        try:
            from main import _diag_save  # lazy import to avoid cycles
            _diag_save(trace, "30_submission_payload", {
                "url": url,
                "question_id": question_id,
                "payload": final_payload,
                "headers": _redact_headers(headers),
            }, redact=True)
        except Exception:
            pass

    # HTTP logging
    print_http_request(
        method="POST",
        url=url,
        headers=headers,
        json_body=final_payload,
        timeout=30,
    )
    request_artifact = prepare_request_artifact(
        method="POST",
        url=url,
        headers=headers,
        json_body=final_payload,
        timeout=30,
    )

    resp = requests.post(url, json=final_payload, headers=headers, timeout=30)

    print_http_response(resp)
    response_artifact = prepare_response_artifact(resp)
    save_http_artifacts(f"metaculus_submit_{question_id}", request_artifact, response_artifact)

    if trace:
        try:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            from main import _diag_save
            _diag_save(trace, "31_submission_response", {
                "status": resp.status_code,
                "reason": resp.reason,
                "headers": _redact_headers(dict(resp.headers)),
                "body": body,
            }, redact=True)
        except Exception:
            pass

    resp.raise_for_status()

def post_comment(post_id: int, comment_text: str, token: str, trace=None):
    """
    Post a private comment on a post (original template behavior):
      POST {API_BASE_URL}/comments/create/
      Payload: {
        text, parent=None, included_forecast=True, is_private=True, on_post: <post_id>
      }
    Note: For most questions post_id == question_id, but occasionally they differ.
    """
    url = f"{API_BASE_URL}/comments/create/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": comment_text,
        "parent": None,
        "included_forecast": True,
        "is_private": True,
        "on_post": post_id,
    }

    # HTTP logging
    print_http_request(
        method="POST",
        url=url,
        headers=headers,
        json_body=payload,
        timeout=30,
    )
    request_artifact = prepare_request_artifact(
        method="POST",
        url=url,
        headers=headers,
        json_body=payload,
        timeout=30,
    )

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    print_http_response(resp)
    response_artifact = prepare_response_artifact(resp)
    save_http_artifacts(f"metaculus_comment_{post_id}", request_artifact, response_artifact)

    if trace:
        try:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            from main import _diag_save
            _diag_save(trace, "32_comment_response", {
                "status": resp.status_code,
                "reason": resp.reason,
                "headers": _redact_headers(dict(resp.headers)),
                "body": body,
            }, redact=True)
        except Exception:
            pass

    resp.raise_for_status()