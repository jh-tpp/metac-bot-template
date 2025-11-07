import os
import json
import requests
from typing import Dict, Any, List, Optional
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
    - Numeric/date: continuous_cdf is a list (201-length) of floats
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

# ------------------ CDF Normalization Helpers ------------------
MIN_CDF_STEP = 5e-5
CDF_TARGET_LEN = 201

def _linear_interpolate(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 * (1 - t) + y1 * t

def _resample_cdf_to_len(cdf: List[float], grid: Optional[List[float]] = None, target_len: int = CDF_TARGET_LEN) -> List[float]:
    """Resample an input CDF to exactly target_len points using linear interpolation.
    If grid is provided (same length as cdf) we interpolate across its numeric range.
    Otherwise we treat index domain as [0,1]. Duplicate / non-increasing grid points are collapsed.
    """
    n = len(cdf)
    if n == 0:
        raise ValueError("Numeric result missing 'cdf' list")

    # Clamp to [0,1]
    base = []
    for v in cdf:
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        fv = 0.0 if fv < 0 else 1.0 if fv > 1 else fv
        base.append(fv)

    if grid and isinstance(grid, list) and len(grid) == n:
        src_x: List[float] = []
        src_y: List[float] = []
        for i in range(n):
            x = float(grid[i])
            y = base[i]
            if not src_x or x > src_x[-1]:
                src_x.append(x)
                src_y.append(y)
            else:
                # Combine duplicates by taking max CDF at that position
                src_y[-1] = max(src_y[-1], y)
        if len(src_x) < 2:
            # Fallback to index domain
            src_x = [i / (len(src_y) - 1) if len(src_y) > 1 else 0.0 for i in range(len(src_y))]
        xmin, xmax = src_x[0], src_x[-1]
        if xmax == xmin:
            tgt_x = [xmin for _ in range(target_len)]
        else:
            tgt_x = [xmin + (xmax - xmin) * i / (target_len - 1) for i in range(target_len)]
        out: List[float] = []
        j = 1
        for x in tgt_x:
            while j < len(src_x) and x > src_x[j]:
                j += 1
            if j == 0:
                y = src_y[0]
            elif j >= len(src_x):
                y = src_y[-1]
            else:
                y = _linear_interpolate(x, src_x[j-1], src_y[j-1], src_x[j], src_y[j])
            out.append(y)
        return out
    else:
        # Index domain interpolation
        if n == 1:
            return [base[0]] * target_len
        src_x = [i / (n - 1) for i in range(n)]
        tgt_x = [i / (target_len - 1) for i in range(target_len)]
        out: List[float] = []
        j = 1
        for x in tgt_x:
            while j < n and x > src_x[j]:
                j += 1
            if j == 0:
                y = base[0]
            elif j >= n:
                y = base[-1]
            else:
                y = _linear_interpolate(x, src_x[j-1], base[j-1], src_x[j], base[j])
            out.append(y)
        return out

def _enforce_monotone_min_step(cdf: List[float], min_step: float = MIN_CDF_STEP) -> List[float]:
    """Force CDF to be strictly increasing by at least min_step each step, remain within [0,1]."""
    if not cdf:
        return [0.0] * CDF_TARGET_LEN
    n = len(cdf)
    out = [0.0] * n
    # Clamp input
    vals = [0.0 if v < 0 else 1.0 if v > 1 else float(v) for v in cdf]
    max_start = 1.0 - (n - 1) * min_step
    out[0] = min(max(vals[0], 0.0), max_start)
    for i in range(1, n):
        v = max(vals[i], out[i-1] + min_step)
        max_here = 1.0 - (n - 1 - i) * min_step
        v = min(v, max_here)
        v = 0.0 if v < 0 else 1.0 if v > 1 else v
        out[i] = v
    return out

# ------------------ Payload Mapping ------------------

def mc_results_to_metaculus_payload(question_obj: Dict, mc_result: Dict) -> Dict:
    """Map MC result to original template payload, adding CDF normalization for numeric."""
    qtype = question_obj.get("type", "").lower()

    if "binary" in qtype:
        p = mc_result.get("p")
        if p is None:
            raise ValueError("Binary result missing 'p'")
        p = max(0.01, min(0.99, float(p)))
        return create_forecast_payload(p, "binary")

    if "multiple" in qtype or "mc" in qtype or qtype == "discrete":
        probs = mc_result.get("probs")
        if probs is None:
            raise ValueError("Multiple choice result missing 'probs'")
        opts = question_obj.get("options", [])
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

    if "numeric" in qtype or "continuous" in qtype or qtype == "date":
        cdf = mc_result.get("cdf")
        grid = mc_result.get("grid")
        if not isinstance(cdf, list) or len(cdf) == 0:
            raise ValueError("Numeric result missing 'cdf' list")
        cdf_201 = _resample_cdf_to_len(cdf, grid=grid, target_len=CDF_TARGET_LEN)
        cdf_201 = _enforce_monotone_min_step(cdf_201, min_step=MIN_CDF_STEP)
        return create_forecast_payload(cdf_201, "numeric")

    raise ValueError(f"Unknown question type: {qtype}")

def submit_forecast(question_id: int, forecast_payload: Dict, token: str, trace=None):
    """Submit forecast via POST /api/questions/forecast/"""
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

    if trace:
        try:
            from main import _diag_save
            _diag_save(trace, "30_submission_payload", {
                "url": url,
                "question_id": question_id,
                "payload": final_payload,
                "headers": _redact_headers(headers),
            }, redact=True)
        except Exception:
            pass

    print_http_request(method="POST", url=url, headers=headers, json_body=final_payload, timeout=30)
    request_artifact = prepare_request_artifact(method="POST", url=url, headers=headers, json_body=final_payload, timeout=30)
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
    """Post private comment via POST /api/comments/create/"""
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

    print_http_request(method="POST", url=url, headers=headers, json_body=payload, timeout=30)
    request_artifact = prepare_request_artifact(method="POST", url=url, headers=headers, json_body=payload, timeout=30)
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