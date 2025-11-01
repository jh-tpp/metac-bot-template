import json
from typing import List, Dict, Any

# Keep WORLD_PROMPT intact (per requirements)
WORLD_PROMPT = """You are a geopolitical and macroeconomic analyst. Generate a plausible future world scenario for the date specified. Your output must be valid JSON with the following structure:

{
  "date": "YYYY-MM-DD",
  "summary": "A 2-3 sentence high-level summary of the world state.",
  "geopolitical": {
    "major_conflicts": ["..."],
    "key_alliances": ["..."],
    "stability_score": 0-10
  },
  "economic": {
    "global_growth_rate": float,
    "inflation_trends": "...",
    "major_disruptions": ["..."]
  },
  "technology": {
    "ai_progress": "...",
    "breakthrough_areas": ["..."],
    "regulatory_environment": "..."
  }
}

Be concise and realistic. Do not include any text outside the JSON object.
"""

def run_mc_worlds(question_obj: Dict, context_facts: List[str], n_worlds: int = 30, return_evidence: bool = False) -> Dict[str, Any]:
    """
    Run Monte-Carlo sampling of joint worlds, aggregate forecasts.
    
    Args:
        question_obj: Metaculus question dict
        context_facts: list of news facts
        n_worlds: number of MC samples
        return_evidence: if True, return world_summaries for rationale synthesis
    
    Returns:
        dict with 'p' (binary), 'probs' (MC), or 'cdf'/'grid' (numeric),
        plus optionally 'world_summaries' if return_evidence=True
    """
    from main import llm_call  # import here to avoid circular dependency
    
    qtype = question_obj.get("type", "").lower()
    
    # Sample worlds
    worlds = []
    for i in range(n_worlds):
        try:
            # Build prompt with context
            prompt = WORLD_PROMPT + f"\n\nContext (recent news):\n"
            for fact in context_facts[:5]:  # cap at 5 to keep prompt short
                prompt += f"- {fact}\n"
            prompt += f"\nQuestion to consider: {question_obj['title']}\n"
            
            world = llm_call(prompt, max_tokens=800, temperature=0.7)
            worlds.append(world)
        except Exception as e:
            print(f"[WARN] World {i+1} failed: {e}")
    
    if not worlds:
        raise RuntimeError("No valid worlds generated")
    
    # Collect summaries
    world_summaries = [w.get("summary", "") for w in worlds if "summary" in w]
    
    # Aggregate forecasts per question type
    result = {}
    
    if "binary" in qtype:
        # For binary, we need a second pass: each world votes yes/no
        # (simplified: assume 50% chance per world, or sample from world context)
        # Here we do a simple heuristic: random coin flip weighted by sentiment
        # In real impl, you'd ask LLM "does this world support the question?"
        # For now, placeholder:
        votes_yes = sum(1 for w in worlds if _world_supports_binary(w, question_obj))
        p = votes_yes / len(worlds)
        # Clamp
        p = max(0.01, min(0.99, p))
        result["p"] = p
    
    elif "multiple" in qtype or "mc" in qtype:
        k = len(question_obj.get("options", []))
        if k == 0:
            raise ValueError("MC question has no options")
        
        # Each world votes for one option (simplified)
        votes = [0] * k
        for w in worlds:
            choice = _world_choice_mc(w, question_obj)
            if 0 <= choice < k:
                votes[choice] += 1
        
        probs = [v / len(worlds) for v in votes]
        # Normalize
        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]
        else:
            probs = [1.0 / k] * k  # uniform fallback
        
        result["probs"] = probs
    
    elif "numeric" in qtype or "continuous" in qtype:
        # Each world gives a point estimate
        samples = []
        for w in worlds:
            val = _world_numeric_estimate(w, question_obj)
            if val is not None:
                samples.append(val)
        
        if not samples:
            raise ValueError("No numeric samples generated")
        
        samples.sort()
        # Build CDF on fixed grid
        lo = question_obj.get("min", min(samples))
        hi = question_obj.get("max", max(samples))
        grid = [lo + (hi - lo) * i / 100 for i in range(101)]
        cdf = []
        for x in grid:
            cdf.append(sum(1 for s in samples if s <= x) / len(samples))
        
        result["grid"] = grid
        result["cdf"] = cdf
        result["p10"] = _percentile(samples, 0.10)
        result["p50"] = _percentile(samples, 0.50)
        result["p90"] = _percentile(samples, 0.90)
    
    if return_evidence:
        result["world_summaries"] = world_summaries
    
    return result

def _world_supports_binary(world: Dict, question_obj: Dict) -> bool:
    """Heuristic: does this world support a YES answer? (placeholder)."""
    # Real impl: parse world fields and match to question
    # For now, 50/50 coin flip
    import random
    return random.random() > 0.5

def _world_choice_mc(world: Dict, question_obj: Dict) -> int:
    """Heuristic: which MC option does this world support? (placeholder)."""
    import random
    k = len(question_obj.get("options", []))
    return random.randint(0, k - 1)

def _world_numeric_estimate(world: Dict, question_obj: Dict) -> float:
    """Heuristic: numeric estimate from world. (placeholder)."""
    # Real impl: parse world, extract numeric signal
    # For now, sample from uniform in question range
    import random
    lo = question_obj.get("min", 0)
    hi = question_obj.get("max", 100)
    return random.uniform(lo, hi)

def _percentile(sorted_values: List[float], p: float) -> float:
    """Return p-th percentile from sorted list."""
    if not sorted_values:
        return 0.0
    idx = int(p * len(sorted_values))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]

def collect_world_summaries(worlds: List[Dict]) -> List[str]:
    """Extract summary strings from world dicts (helper)."""
    return [w.get("summary", "") for w in worlds if "summary" in w]