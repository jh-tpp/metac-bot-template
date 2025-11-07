import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any

# Keep WORLD_PROMPT intact (per requirements)
WORLD_PROMPT = """You are a geopolitical and macroeconomic analyst. You are generating ONE plausible sample of a future "world" consistent with the metadata and facts below.
Return exactly one JSON object. No markdown, no comments, no trailing commas.

Schema (all keys required):
{
  "world_summary": "string, 180–200 words describing the world dynamics that jointly drive the outcomes below, plain English, concise.",
  "per_question": [
    {
      "key": "Q01",
      "type": "binary|multiple_choice|numeric",
      "outcome": {
        "binary": { "yes": true },
        "multiple_choice": { "option_index": 0 },
        "numeric": { "value": 12.3 }
      }
    }
  ]
}

Superforecaster discipline:
- Tetlockian technique: start with the outside view and base rates; consider alt. hypotheses and common biases; set explicit assumptions internally (do not output them).
- Coherence: outcomes must be mutually consistent, causally linked to drivers in the summary.
- Causal model: before filling JSON, internally build a causal model that ties drivers → outcomes over the same world.

Rules:
- Include exactly one entry in "per_question" for each question key present in FACTS.
- Match each entry’s "type" to the fact tag (bin, mc, num).
- For multiple_choice, "option_index" must be in [0, k-1] (k may appear in the fact tag, e.g., "mc k=6").
- For numeric, choose a single plausible value for this world.
- Be conservative under uncertainty; keep all outputs consistent with FACTS.
- Output PURE JSON only (no prose, no code fences).

FACTS:
{facts}
"""

def run_mc_worlds(question_obj: Dict, context_facts: List[str], n_worlds: int = 30, return_evidence: bool = False, trace=None) -> Dict[str, Any]:
    """
    Run Monte-Carlo sampling of joint worlds, aggregate forecasts.
    
    Args:
        question_obj: Metaculus question dict
        context_facts: list of news facts
        n_worlds: number of MC samples
        return_evidence: if True, return world_summaries for rationale synthesis
        trace: Optional DiagnosticTrace for saving diagnostics
    
    Returns:
        dict with 'p' (binary), 'probs' (MC), or 'cdf'/'grid' (numeric),
        plus optionally 'world_summaries' if return_evidence=True
    """
    from main import llm_call, parse_numeric_bounds, OPENROUTER_DEBUG_ENABLED, CACHE_DIR, _diag_save  # import here to avoid circular dependency
    from pathlib import Path
    
    qtype = question_obj.get("type", "").lower()
    qid = question_obj.get("id", "unknown")
    
    # Parse bounds for numeric questions
    bounds = None
    if "numeric" in qtype or "continuous" in qtype:
        bounds = parse_numeric_bounds(question_obj, trace=trace)
    
    # Sample worlds
    worlds = []
    for i in range(n_worlds):
        try:
            # Build prompt with token limit
            prompt =  WORLD_PROMPT + f"\n\nContext (recent news):\n"
            # Include top-k facts (k<=5) to reduce generic summaries, truncate to avoid token bloat
            for fact in context_facts[:5]:  # cap at 5 to keep prompt short
                # Truncate long facts to ~200 chars
                fact_truncated = fact if len(fact) <= 200 else fact[:197] + "..."
                prompt += f"- {fact_truncated}\n"
            prompt += f"\nQuestion to consider: {question_obj['title']}\n"
            
            # For numeric questions, add bounds constraint to prompt
            if bounds:
                min_bound, max_bound = bounds
                prompt += f"\nIMPORTANT: When providing numeric estimates, all values MUST be within the range [{min_bound}, {max_bound}].\n"
            
            # Save prompt to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    prompt_file = CACHE_DIR / f"debug_world_q{qid}_{i}_prompt.txt"
                    with open(prompt_file, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"[MC DEBUG] Saved world {i} prompt: {prompt_file}", flush=True)
                except Exception as e:
                    print(f"[ERROR] Failed to save world {i} prompt: {e}", flush=True)
            
            world = llm_call(prompt, max_tokens=800, temperature=0.7, trace=trace)
            worlds.append(world)
        except Exception as e:
            print(f"[WARN] World {i+1} failed: {e}")
            
            # Save error to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    error_file = CACHE_DIR / f"debug_world_q{qid}_{i}_error.txt"
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(f"Error in world {i} generation:\n{str(e)}\n")
                        import traceback
                        f.write(f"\nTraceback:\n{traceback.format_exc()}")
                    print(f"[MC DEBUG] Saved world {i} error: {error_file}", flush=True)
                except Exception as save_err:
                    print(f"[ERROR] Failed to save world {i} error: {save_err}", flush=True)
    
    if not worlds:
        raise RuntimeError("No valid worlds generated")
    
    # Collect summaries
    world_summaries = [w.get("summary", "") for w in worlds if "summary" in w]
    
    # Save aggregate input diagnostics (before aggregation)
    if trace:
        try:
            aggregate_input = {
                "n_worlds": len(worlds),
                "worlds": worlds,
                "world_summaries": world_summaries
            }
            _diag_save(trace, "20_aggregate_input", aggregate_input, redact=False)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate input diagnostics: {e}", flush=True)
    
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
            val = _world_numeric_estimate(w, question_obj, bounds)
            if val is not None:
                samples.append(val)
        
        if not samples:
            raise ValueError("No numeric samples generated")
        
        samples.sort()
        
        # Build CDF on fixed grid using bounds
        if bounds:
            min_bound, max_bound = bounds
            lo = min_bound
            hi = max_bound
        else:
            lo = question_obj.get("min", min(samples))
            hi = question_obj.get("max", max(samples))
        
        # Clamp samples to bounds if needed (safety)
        samples = [max(lo, min(hi, s)) for s in samples]
        samples.sort()
        
        grid = [lo + (hi - lo) * i / 100 for i in range(101)]
        cdf = []
        for x in grid:
            cdf.append(sum(1 for s in samples if s <= x) / len(samples))
        
        result["grid"] = grid
        result["cdf"] = cdf
        result["p10"] = _percentile(samples, 0.10)
        result["p50"] = _percentile(samples, 0.50)
        result["p90"] = _percentile(samples, 0.90)
        
        # Validate bounds
        if bounds:
            min_bound, max_bound = bounds
            grid_min = min(grid)
            grid_max = max(grid)
            
            # Check if grid exceeds bounds (should not happen with our logic above)
            if grid_min < min_bound or grid_max > max_bound:
                print(f"[REJECT] numeric grid beyond bounds [{min_bound}, {max_bound}]: min={grid_min}, max={grid_max}")
                # Already clamped samples, so grid should be ok now
            
            # Check percentiles
            for pname, pval in [("p10", result["p10"]), ("p50", result["p50"]), ("p90", result["p90"])]:
                if pval < min_bound or pval > max_bound:
                    print(f"[REJECT] {pname}={pval} outside bounds [{min_bound}, {max_bound}]")
    
    # Save aggregate output diagnostics (after aggregation)
    if trace:
        try:
            _diag_save(trace, "21_aggregate_output", result, redact=False)
            
            # Check for previous aggregate output and create diff
            import os
            prev_file = os.path.join(trace.dir, "21_aggregate_output.json")
            if os.path.exists(prev_file):
                try:
                    import json
                    with open(prev_file, "r", encoding="utf-8") as f:
                        prev_result = json.load(f)
                    trace.diff("aggregate_output", prev_result, result)
                except Exception as diff_err:
                    print(f"[WARN] Failed to create aggregate diff: {diff_err}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate output diagnostics: {e}", flush=True)
    
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

def _world_numeric_estimate(world: Dict, question_obj: Dict, bounds=None) -> float:
    """Heuristic: numeric estimate from world. (placeholder)."""
    # Real impl: parse world, extract numeric signal
    # For now, sample from uniform in question range
    import random
    
    if bounds:
        lo, hi = bounds
    else:
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
