import requests
from typing import Dict, Any

def mc_results_to_metaculus_payload(question_obj: Dict, mc_result: Dict) -> Dict:
    """
    Map MC results to Metaculus submission payload.
    
    Args:
        question_obj: Metaculus question dict
        mc_result: dict with 'p', 'probs', or 'cdf'/'grid'
    
    Returns:
        Payload dict suitable for Metaculus API
    """
    qtype = question_obj.get("type", "").lower()
    
    if "binary" in qtype:
        p = mc_result["p"]
        # Clamp (redundant if validated)
        p = max(0.01, min(0.99, p))
        return {
            "prediction": p,
            "reasoning": "\n".join(mc_result.get("reasoning", []))
        }
    
    elif "multiple" in qtype or "mc" in qtype:
        probs = mc_result["probs"]
        k = len(question_obj.get("options", []))
        
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
        
        return {
            "prediction": probs,
            "reasoning": "\n".join(mc_result.get("reasoning", []))
        }
    
    elif "numeric" in qtype or "continuous" in qtype:
        # Metaculus numeric format varies; assume they want CDF or percentiles
        # Adjust to actual API spec
        return {
            "prediction": {
                "p10": mc_result.get("p10"),
                "p50": mc_result.get("p50"),
                "p90": mc_result.get("p90"),
                "cdf": mc_result.get("cdf"),
                "grid": mc_result.get("grid")
            },
            "reasoning": "\n".join(mc_result.get("reasoning", []))
        }
    
    raise ValueError(f"Unknown question type: {qtype}")

def submit_forecast(question_id: int, payload: Dict, token: str):
    """
    POST forecast to Metaculus.
    
    Args:
        question_id: Metaculus question ID
        payload: submission payload
        token: Metaculus API token
    
    Raises on failure.
    """
    url = f"https://www.metaculus.com/api/questions/{question_id}/forecast/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()