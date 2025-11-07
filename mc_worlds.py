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
    Run Monte-Carlo sampling with per-type LLM schemas and simple aggregation.
    
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
    
    # Build context string from facts
    context_str = "Recent news:\n"
    for fact in context_facts[:5]:  # cap at 5 to keep prompt short
        fact_truncated = fact if len(fact) <= 200 else fact[:197] + "..."
        context_str += f"- {fact_truncated}\n"
    
    # Per-type schema and parsing
    if qtype == "binary":
        return _run_binary_worlds(qid, qtitle, qdesc, context_str, n_worlds, return_evidence, trace)
    elif qtype == "multiple_choice":
        options = question_obj.get("options", [])
        return _run_multiple_choice_worlds(qid, qtitle, qdesc, context_str, options, n_worlds, return_evidence, trace)
    elif qtype == "numeric":
        return _run_numeric_worlds(qid, qtitle, qdesc, context_str, question_obj, n_worlds, return_evidence, trace)
    else:
        raise ValueError(f"Unsupported question type: {qtype}")


def _run_binary_worlds(qid, qtitle, qdesc, context_str, n_worlds, return_evidence, trace):
    """
    Binary questions: Request {"answer": true|false}, compute probability as mean of booleans.
    """
    from main import llm_call, OPENROUTER_DEBUG_ENABLED, CACHE_DIR, _diag_save
    from pathlib import Path
    
    # Build system message with strict schema
    system_msg = """You are a superforecaster. Respond with ONLY JSON in this exact format:
{"answer": true}
or
{"answer": false}

No other keys, no markdown, no explanations. Just the JSON object."""
    
    # Build user message with question and facts
    user_msg = f"""Question: {qtitle}

{qdesc}

{context_str}

Based on your analysis, will this happen? Respond with ONLY JSON: {{"answer": true}} or {{"answer": false}}"""
    
    # Collect world results
    answers = []
    world_summaries = []
    
    for i in range(n_worlds):
        try:
            # Combine system and user messages into a single prompt
            prompt = f"{system_msg}\n\n{user_msg}"
            
            # Save prompt to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    prompt_file = CACHE_DIR / f"debug_binary_world_q{qid}_{i}_prompt.txt"
                    with open(prompt_file, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"[MC DEBUG] Saved binary world {i} prompt: {prompt_file}", flush=True)
                except Exception as e:
                    print(f"[ERROR] Failed to save world {i} prompt: {e}", flush=True)
            
            result = llm_call(prompt, max_tokens=50, temperature=0.7, trace=trace)
            
            # Parse answer
            answer = result.get("answer")
            if isinstance(answer, bool):
                answers.append(answer)
                world_summaries.append(f"World {i+1}: {'YES' if answer else 'NO'}")
            else:
                print(f"[WARN] Binary world {i+1} returned non-boolean answer: {answer}", flush=True)
                
        except Exception as e:
            print(f"[WARN] Binary world {i+1} failed: {e}", flush=True)
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    error_file = CACHE_DIR / f"debug_binary_world_q{qid}_{i}_error.txt"
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(f"Error in binary world {i} generation:\n{str(e)}\n")
                        import traceback
                        f.write(f"\nTraceback:\n{traceback.format_exc()}")
                    print(f"[MC DEBUG] Saved binary world {i} error: {error_file}", flush=True)
                except Exception as save_err:
                    print(f"[ERROR] Failed to save world {i} error: {save_err}", flush=True)
    
    if not answers:
        raise RuntimeError("No valid binary worlds generated")
    
    # Compute probability as mean of booleans
    p = sum(1 for a in answers if a) / len(answers)
    
    # Clamp to [0.01, 0.99]
    p = max(0.01, min(0.99, p))
    
    result = {"p": p}
    
    # Save diagnostics
    if trace:
        try:
            aggregate_input = {
                "n_worlds": len(answers),
                "answers": answers
            }
            _diag_save(trace, "20_aggregate_input", aggregate_input, redact=False)
            _diag_save(trace, "21_aggregate_output", result, redact=False)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate diagnostics: {e}", flush=True)
    
    if return_evidence:
        result["world_summaries"] = world_summaries
    
    return result


def _run_multiple_choice_worlds(qid, qtitle, qdesc, context_str, options, n_worlds, return_evidence, trace):
    """
    Multiple choice: Request {"scores": {"option1": score, ...}}, normalize to probabilities.
    """
    from main import llm_call, OPENROUTER_DEBUG_ENABLED, CACHE_DIR, _diag_save
    from pathlib import Path
    
    if not options:
        raise ValueError("Multiple choice question has no options")
    
    # Extract option names
    option_names = [opt if isinstance(opt, str) else opt.get("name", f"Option {i+1}") for i, opt in enumerate(options)]
    
    # Build system message with strict schema
    system_msg = f"""You are a superforecaster. Respond with ONLY JSON in this exact format:
{{"scores": {{{", ".join(f'"{name}": <number>' for name in option_names)}}}}}

Assign a score (0-100) to each option based on likelihood. Higher score = more likely.
No other keys, no markdown, no explanations. Just the JSON object."""
    
    # Build user message with question and facts
    options_str = "\n".join(f"- {name}" for name in option_names)
    user_msg = f"""Question: {qtitle}

{qdesc}

Options:
{options_str}

{context_str}

Based on your analysis, assign scores (0-100) to each option. Respond with ONLY JSON: {{"scores": {{...}}}}"""
    
    # Collect world results
    world_scores = []
    world_summaries = []
    
    for i in range(n_worlds):
        try:
            # Combine system and user messages into a single prompt
            prompt = f"{system_msg}\n\n{user_msg}"
            
            # Save prompt to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    prompt_file = CACHE_DIR / f"debug_mc_world_q{qid}_{i}_prompt.txt"
                    with open(prompt_file, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"[MC DEBUG] Saved MC world {i} prompt: {prompt_file}", flush=True)
                except Exception as e:
                    print(f"[ERROR] Failed to save world {i} prompt: {e}", flush=True)
            
            result = llm_call(prompt, max_tokens=200, temperature=0.7, trace=trace)
            
            # Parse scores
            scores_dict = result.get("scores", {})
            if isinstance(scores_dict, dict):
                # Extract scores in option order
                scores = []
                for name in option_names:
                    score = scores_dict.get(name, 0)
                    try:
                        scores.append(float(score))
                    except (ValueError, TypeError):
                        scores.append(0.0)
                
                world_scores.append(scores)
                
                # Create summary
                max_idx = scores.index(max(scores)) if scores else 0
                world_summaries.append(f"World {i+1}: {option_names[max_idx]} (score: {scores[max_idx]:.1f})")
            else:
                print(f"[WARN] MC world {i+1} returned invalid scores: {scores_dict}", flush=True)
                
        except Exception as e:
            print(f"[WARN] MC world {i+1} failed: {e}", flush=True)
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    error_file = CACHE_DIR / f"debug_mc_world_q{qid}_{i}_error.txt"
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(f"Error in MC world {i} generation:\n{str(e)}\n")
                        import traceback
                        f.write(f"\nTraceback:\n{traceback.format_exc()}")
                    print(f"[MC DEBUG] Saved MC world {i} error: {error_file}", flush=True)
                except Exception as save_err:
                    print(f"[ERROR] Failed to save world {i} error: {save_err}", flush=True)
    
    if not world_scores:
        raise RuntimeError("No valid MC worlds generated")
    
    # Average scores across worlds
    k = len(option_names)
    avg_scores = [0.0] * k
    for scores in world_scores:
        for i in range(k):
            avg_scores[i] += scores[i]
    avg_scores = [s / len(world_scores) for s in avg_scores]
    
    # Normalize to probabilities
    total_score = sum(avg_scores)
    if total_score > 0:
        probs = [s / total_score for s in avg_scores]
    else:
        # Fallback to uniform if all scores are 0
        probs = [1.0 / k] * k
    
    result = {"probs": probs}
    
    # Save diagnostics
    if trace:
        try:
            aggregate_input = {
                "n_worlds": len(world_scores),
                "world_scores": world_scores,
                "option_names": option_names
            }
            _diag_save(trace, "20_aggregate_input", aggregate_input, redact=False)
            _diag_save(trace, "21_aggregate_output", result, redact=False)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate diagnostics: {e}", flush=True)
    
    if return_evidence:
        result["world_summaries"] = world_summaries
    
    return result


def _run_numeric_worlds(qid, qtitle, qdesc, context_str, question_obj, n_worlds, return_evidence, trace):
    """
    Numeric questions: Request {"value": number}, average values directly without normalization.
    """
    from main import llm_call, OPENROUTER_DEBUG_ENABLED, CACHE_DIR, _diag_save
    from pathlib import Path
    
    # Build system message with strict schema
    system_msg = """You are a superforecaster. Respond with ONLY JSON in this exact format:
{"value": <number>}

Provide your best point estimate as a single numeric value.
No other keys, no markdown, no explanations. Just the JSON object."""
    
    # Build user message with question and facts
    user_msg = f"""Question: {qtitle}

{qdesc}

{context_str}

Based on your analysis, what is your best point estimate? Respond with ONLY JSON: {{"value": <number>}}"""
    
    # Collect world results
    values = []
    world_summaries = []
    
    for i in range(n_worlds):
        try:
            # Combine system and user messages into a single prompt
            prompt = f"{system_msg}\n\n{user_msg}"
            
            # Save prompt to debug file if debug is enabled
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    prompt_file = CACHE_DIR / f"debug_numeric_world_q{qid}_{i}_prompt.txt"
                    with open(prompt_file, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"[MC DEBUG] Saved numeric world {i} prompt: {prompt_file}", flush=True)
                except Exception as e:
                    print(f"[ERROR] Failed to save world {i} prompt: {e}", flush=True)
            
            result = llm_call(prompt, max_tokens=50, temperature=0.7, trace=trace)
            
            # Parse value
            value = result.get("value")
            try:
                val = float(value)
                values.append(val)
                world_summaries.append(f"World {i+1}: {val}")
            except (ValueError, TypeError):
                print(f"[WARN] Numeric world {i+1} returned non-numeric value: {value}", flush=True)
                
        except Exception as e:
            print(f"[WARN] Numeric world {i+1} failed: {e}", flush=True)
            if OPENROUTER_DEBUG_ENABLED:
                try:
                    CACHE_DIR.mkdir(exist_ok=True)
                    error_file = CACHE_DIR / f"debug_numeric_world_q{qid}_{i}_error.txt"
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(f"Error in numeric world {i} generation:\n{str(e)}\n")
                        import traceback
                        f.write(f"\nTraceback:\n{traceback.format_exc()}")
                    print(f"[MC DEBUG] Saved numeric world {i} error: {error_file}", flush=True)
                except Exception as save_err:
                    print(f"[ERROR] Failed to save world {i} error: {save_err}", flush=True)
    
    if not values:
        raise RuntimeError("No valid numeric worlds generated")
    
    # Average values directly (no normalization/clamping)
    values.sort()
    
    # Build CDF on fixed grid
    # Use question bounds if available, otherwise infer from samples
    min_val = question_obj.get("min")
    max_val = question_obj.get("max")
    
    if min_val is not None and max_val is not None:
        try:
            lo = float(min_val)
            hi = float(max_val)
        except (ValueError, TypeError):
            # If bounds are not numeric (e.g., date strings), infer from samples
            lo = min(values)
            hi = max(values)
    else:
        lo = min(values)
        hi = max(values)
    
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
    
    result = {
        "grid": grid,
        "cdf": cdf,
        "p10": p10,
        "p50": p50,
        "p90": p90
    }
    
    # Save diagnostics
    if trace:
        try:
            aggregate_input = {
                "n_worlds": len(values),
                "values": values,
                "sorted_values": sorted(values)
            }
            _diag_save(trace, "20_aggregate_input", aggregate_input, redact=False)
            _diag_save(trace, "21_aggregate_output", result, redact=False)
        except Exception as e:
            print(f"[WARN] Failed to save aggregate diagnostics: {e}", flush=True)
    
    if return_evidence:
        result["world_summaries"] = world_summaries
    
    return result


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
