import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any

# Simplified WORLD_PROMPT without intrusive schema blocks
WORLD_PROMPT = """You are a geopolitical and macroeconomic analyst making a forecast.

Use Tetlockian forecasting discipline:
- Start with the outside view and base rates
- Consider alternative hypotheses and common biases
- Set explicit assumptions internally
- Be conservative under uncertainty

Analyze the question and facts below, then provide your forecast."""

def run_mc_worlds(question_obj: Dict, context_facts: List[str], n_worlds: int = 30, return_evidence: bool = False, trace=None) -> Dict[str, Any]:
    """
    Run Monte-Carlo sampling with simplified world prompt construction.
    
    Args:
        question_obj: Metaculus question dict (minimal: id, type, title, description, url, options?)
        context_facts: list of news facts
        n_worlds: number of MC samples
        return_evidence: if True, return world_summaries for rationale synthesis
        trace: Optional DiagnosticTrace for saving diagnostics
    
    Returns:
        dict with 'p' (binary), 'probs' (MC), or 'cdf'/'grid' (numeric),
        plus optionally 'world_summaries' if return_evidence=True
    """
    from main import llm_call, OPENROUTER_DEBUG_ENABLED, CACHE_DIR, _diag_save  # import here to avoid circular dependency
    from pathlib import Path
    
    qtype = question_obj.get("type", "").lower()
    qid = question_obj.get("id", "unknown")
    qtitle = question_obj.get("title", "")
    qdesc = question_obj.get("description", "")
    options = question_obj.get("options", [])
    
    # Build base world prompt (WORLD_PROMPT + question + facts)
    base_prompt = WORLD_PROMPT.strip() + "\n\n"
    base_prompt += f"Question: {qtitle}\n\n"
    if qdesc:
        base_prompt += f"Description: {qdesc}\n\n"
    
    # Add recent facts
    base_prompt += "Recent facts:\n"
    for fact in context_facts[:5]:  # cap at 5 to keep prompt short
        fact_truncated = fact if len(fact) <= 200 else fact[:197] + "..."
        base_prompt += f"- {fact_truncated}\n"
    
    # Add optional JSON hint based on WORLD_JSON_HINT_ENABLED config
    hint_enabled = os.environ.get("WORLD_JSON_HINT_ENABLED", "true").lower() in ("true", "1", "yes", "y", "on", "t")
    
    full_prompt = base_prompt
    if hint_enabled:
        full_prompt += "\n"
        if qtype == "binary":
            full_prompt += 'Output JSON: {"answer": true} or {"answer": false}'
        elif qtype == "multiple_choice":
            full_prompt += 'Output JSON: {"scores": {"Option1": number, "Option2": number, ...}}'
        elif qtype == "numeric":
            full_prompt += 'Output JSON: {"value": number}'
    
    # Collect world results
    world_results = []
    world_summaries = []
    
    for i in range(n_worlds):
        try:
            # Save prompt to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    prompt_file = CACHE_DIR / f"debug_world_q{qid}_{i}_prompt.txt"
                    with open(prompt_file, "w", encoding="utf-8") as f:
                        f.write(full_prompt)
                    print(f"[MC DEBUG] Saved world {i} prompt: {prompt_file}", flush=True)
                except Exception as e:
                    print(f"[ERROR] Failed to save world {i} prompt: {e}", flush=True)
            
            # Call LLM
            result = llm_call(full_prompt, max_tokens=200, temperature=0.7, trace=trace)
            
            # Parse output
            parsed, summary = _parse_world_output(qtype, result, options)
            
            if parsed is not None:
                world_results.append(parsed)
                world_summaries.append(f"World {i+1}: {summary}")
                print(f"[WORLD] Q{qid} world {i+1}/{n_worlds} parse=OK", flush=True)
            else:
                print(f"[WORLD] Q{qid} world {i+1}/{n_worlds} parse=FAIL", flush=True)
                
        except Exception as e:
            print(f"[WORLD] Q{qid} world {i+1}/{n_worlds} parse=FAIL ({e})", flush=True)
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
    
    if not world_results:
        raise RuntimeError(f"No valid worlds generated for Q{qid}")
    
    # Aggregate results by type
    if qtype == "binary":
        aggregate = _aggregate_binary(world_results)
    elif qtype == "multiple_choice":
        aggregate = _aggregate_multiple_choice(world_results, options)
    elif qtype == "numeric":
        aggregate = _aggregate_numeric(world_results)
    else:
        raise ValueError(f"Unsupported question type: {qtype}")
    
    # Save diagnostics
    if trace:
        try:
            aggregate_input = {
                "n_worlds": len(world_results),
                "world_results": world_results
            }
            _diag_save(trace, "20_aggregate_input", aggregate_input, redact=False)
            _diag_save(trace, "21_aggregate_output", aggregate, redact=False)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate diagnostics: {e}", flush=True)
    
    if return_evidence:
        aggregate["world_summaries"] = world_summaries
    
    return aggregate


def _parse_world_output(qtype: str, raw_content_dict: Dict, options: List = None) -> tuple:
    """
    Parse world output with lenient fallbacks.
    
    Args:
        qtype: Question type ('binary', 'multiple_choice', 'numeric')
        raw_content_dict: Raw dict from LLM
        options: List of option dicts (for multiple_choice)
    
    Returns:
        Tuple (parsed_value, summary_string) or (None, None) on failure
    """
    try:
        if qtype == "binary":
            # Try {"answer": true/false}
            if "answer" in raw_content_dict:
                answer = raw_content_dict["answer"]
                if isinstance(answer, bool):
                    return answer, "YES" if answer else "NO"
                # Fallback: parse string "true"/"false" or "True"/"False"
                if isinstance(answer, str):
                    if answer.lower() in ("true", "yes", "1"):
                        return True, "YES"
                    elif answer.lower() in ("false", "no", "0"):
                        return False, "NO"
            print(f"[WARN] Binary parse failed: {raw_content_dict}", flush=True)
            return None, None
        
        elif qtype == "multiple_choice":
            # Try {"scores": {"Opt1": num, ...}}
            if "scores" in raw_content_dict:
                scores_dict = raw_content_dict["scores"]
            else:
                # Fallback: raw numbers at top level {"Opt1": 3, ...}
                scores_dict = raw_content_dict
            
            if not isinstance(scores_dict, dict):
                print(f"[WARN] MC parse failed: expected dict, got {type(scores_dict)}", flush=True)
                return None, None
            
            # Extract option names
            option_names = []
            for i, opt in enumerate(options):
                if isinstance(opt, str):
                    option_names.append(opt)
                elif isinstance(opt, dict):
                    option_names.append(opt.get("name", f"Option{i}"))
                else:
                    option_names.append(f"Option{i}")
            
            # Parse scores in order
            scores = []
            for name in option_names:
                score = scores_dict.get(name, 0)
                try:
                    scores.append(float(score))
                except (ValueError, TypeError):
                    scores.append(0.0)
            
            if not option_names or all(s == 0 for s in scores):
                print(f"[WARN] MC parse got all zeros or no options: {scores_dict}", flush=True)
                return None, None
            
            max_idx = scores.index(max(scores))
            summary = f"{option_names[max_idx]} (score: {scores[max_idx]:.1f})"
            return scores, summary
        
        elif qtype == "numeric":
            # Try {"value": number}
            if "value" in raw_content_dict:
                value = raw_content_dict["value"]
            else:
                # Fallback: raw number as string or number at top level
                # Try to extract first numeric value
                for v in raw_content_dict.values():
                    if isinstance(v, (int, float)):
                        value = v
                        break
                    elif isinstance(v, str):
                        try:
                            value = float(v)
                            break
                        except ValueError:
                            pass
                else:
                    print(f"[WARN] Numeric parse failed: {raw_content_dict}", flush=True)
                    return None, None
            
            try:
                val = float(value)
                return val, f"{val}"
            except (ValueError, TypeError):
                print(f"[WARN] Numeric parse failed to convert: {value}", flush=True)
                return None, None
    
    except Exception as e:
        print(f"[WARN] Parse exception: {e}", flush=True)
        return None, None


def _aggregate_binary(world_results: List[bool]) -> Dict:
    """Aggregate binary world results."""
    p = sum(1 for a in world_results if a) / len(world_results)
    # Clamp to [0.01, 0.99]
    p = max(0.01, min(0.99, p))
    return {"p": p}


def _aggregate_multiple_choice(world_results: List[List[float]], options: List) -> Dict:
    """Aggregate multiple choice world results."""
    if not world_results:
        raise RuntimeError("No valid MC worlds")
    
    k = len(world_results[0])
    avg_scores = [0.0] * k
    for scores in world_results:
        for i in range(k):
            avg_scores[i] += scores[i]
    avg_scores = [s / len(world_results) for s in avg_scores]
    
    # Normalize to probabilities
    total_score = sum(avg_scores)
    if total_score > 0:
        probs = [s / total_score for s in avg_scores]
    else:
        # Fallback to uniform if all scores are 0
        probs = [1.0 / k] * k
    
    return {"probs": probs}


def _aggregate_numeric(world_results: List[float]) -> Dict:
    """Aggregate numeric world results."""
    if not world_results:
        raise RuntimeError("No valid numeric worlds")
    
    values = sorted(world_results)
    lo = min(values)
    hi = max(values)
    
    # Add small padding to ensure all values are within grid
    range_padding = (hi - lo) * 0.05 if hi > lo else 1.0
    lo = lo - range_padding
    hi = hi + range_padding
    
    # Create grid
    grid = [lo + (hi - lo) * i / 100 for i in range(101)]
    
    # Compute CDF
    cdf = []
    for x in grid:
        cdf.append(sum(1 for v in values if v <= x) / len(values))
    
    # Compute percentiles
    p10 = _percentile(values, 0.10)
    p50 = _percentile(values, 0.50)
    p90 = _percentile(values, 0.90)
    
    return {
        "grid": grid,
        "cdf": cdf,
        "p10": p10,
        "p50": p50,
        "p90": p90
    }


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
