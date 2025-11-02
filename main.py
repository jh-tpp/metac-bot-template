import os
import sys
import json
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Local modules
from mc_worlds import run_mc_worlds, WORLD_PROMPT
from adapters import mc_results_to_metaculus_payload, submit_forecast

# ========== Constants ==========
N_WORLDS_DEFAULT = 30  # for tests
N_WORLDS_TOURNAMENT = 100  # flip to this for production
ASKNEWS_MAX_PER_Q = 8
NEWS_CACHE_TTL_HOURS = 168
CACHE_DIR = Path("cache")
NEWS_CACHE_FILE = CACHE_DIR / "news_cache.json"
METACULUS_API_BASE = "https://www.metaculus.com/api2/questions/"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openai/gpt-4o-mini"
METACULUS_TOKEN = os.environ.get("METACULUS_TOKEN", "")
ASKNEWS_CLIENT_ID = os.environ.get("ASKNEWS_CLIENT_ID", "")
ASKNEWS_SECRET = os.environ.get("ASKNEWS_SECRET", "")

# Project-based tournament targeting (AIB Fall 2025)
METACULUS_PROJECT_ID = os.environ.get("METACULUS_PROJECT_ID", "32813")
METACULUS_PROJECT_SLUG = os.environ.get("METACULUS_PROJECT_SLUG", "fall-aib-2025")
METACULUS_CONTEST_SLUG = os.environ.get("METACULUS_CONTEST_SLUG", "fall-aib")

# ========== Diagnostic Helpers ==========
def _write_debug_files(prefix, raw_text, parsed_obj):
    """
    Write debug artifacts: raw response text and parsed JSON.
    
    Args:
        prefix: Filename prefix (e.g., 'debug_q_578_att1')
        raw_text: Raw response body as string
        parsed_obj: Parsed response as dict
    """
    try:
        # Write raw text
        raw_file = f"{prefix}_raw.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(raw_text)
        print(f"[DEBUG] Wrote raw response to {raw_file}", flush=True)
        
        # Write parsed JSON
        json_file = f"{prefix}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(parsed_obj, f, indent=2, ensure_ascii=False)
        print(f"[DEBUG] Wrote parsed response to {json_file}", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to write debug files for {prefix}: {e}", flush=True)
        traceback.print_exc()

def _debug_log_fetch(qid, label, resp, raw_text, parsed_obj, request_url, request_params):
    """
    Log comprehensive fetch diagnostics.
    
    Args:
        qid: Question ID
        label: Human-readable label for this attempt
        resp: requests.Response object
        raw_text: Raw response body
        parsed_obj: Parsed response dict
        request_url: Request URL
        request_params: Request parameters dict
    """
    print(f"\n{'='*60}", flush=True)
    print(f"[DEBUG FETCH] Q{qid} - {label}", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Request URL: {request_url}", flush=True)
    print(f"Request params: {request_params}", flush=True)
    print(f"Response status: {resp.status_code} {resp.reason}", flush=True)
    
    # Log response headers
    print(f"Response headers:", flush=True)
    for key, value in resp.headers.items():
        print(f"  {key}: {value}", flush=True)
    
    # Log content info
    content_length = len(raw_text)
    print(f"Content-Length: {content_length} bytes", flush=True)
    print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}", flush=True)
    print(f"Encoding: {resp.encoding}", flush=True)
    
    # Log first 2KB of body
    snippet = raw_text[:2048]
    print(f"\nFirst 2KB of response body:", flush=True)
    print(snippet, flush=True)
    if content_length > 2048:
        print(f"... (truncated, {content_length - 2048} more bytes)", flush=True)
    
    # Log top-level keys
    if isinstance(parsed_obj, dict):
        print(f"\nTop-level keys: {list(parsed_obj.keys())}", flush=True)
        
        # Pivot into core question object for nested inspection
        core = _get_core_question(parsed_obj)
        if core is not parsed_obj:
            print(f"  Core (nested question) keys: {list(core.keys())}", flush=True)
        
        # Check for possibility/possibilities in core
        if "possibility" in core:
            poss = core["possibility"]
            poss_type = poss.get("type", "N/A") if isinstance(poss, dict) else "N/A"
            print(f"  core.possibility present: type={poss_type}", flush=True)
            if isinstance(poss, dict):
                print(f"  core.possibility keys: {list(poss.keys())}", flush=True)
        else:
            print(f"  core.possibility: NOT PRESENT", flush=True)
        
        if "possibilities" in core:
            poss_list = core["possibilities"]
            print(f"  core.possibilities present: {type(poss_list)}, length={len(poss_list) if isinstance(poss_list, (list, tuple)) else 'N/A'}", flush=True)
            if isinstance(poss_list, list) and len(poss_list) > 0 and isinstance(poss_list[0], dict):
                print(f"  core.possibilities[0] keys: {list(poss_list[0].keys())}", flush=True)
        else:
            print(f"  core.possibilities: NOT PRESENT", flush=True)
        
        # Check for fallback type fields in core
        fallback_fields = ["type", "possibility_type", "prediction_type", "question_type", "value_type", "outcome_type"]
        print(f"  Core fallback type fields:", flush=True)
        for field in fallback_fields:
            if field in core:
                print(f"    {field}: {core[field]}", flush=True)
    else:
        print(f"\nParsed response is not a dict: {type(parsed_obj)}", flush=True)
    
    print(f"{'='*60}\n", flush=True)

# ========== Tournament Question Fetcher ==========
def _get_core_question(raw):
    """
    Get the core question object, pivoting into nested 'question' key if present.
    
    Args:
        raw: Question dict from Metaculus API (may be top-level or nested under 'question')
    
    Returns:
        Core question dict (the nested object if present, otherwise raw, or empty dict if None)
    """
    if not raw:
        return {}
    core = raw.get("question", raw)
    return core if core else {}

def _normalize_question_type(raw_type):
    """
    Normalize a question type string to canonical format.
    
    Args:
        raw_type: Raw type string from Metaculus API
    
    Returns:
        Canonical type ('binary', 'multiple_choice', 'numeric') or empty string if unmappable
    """
    if not raw_type:
        return ""
    
    # Type normalization mapping
    type_mapping = {
        "binary": "binary",
        "multiple_choice": "multiple_choice",
        "multiplechoice": "multiple_choice",
        "mc": "multiple_choice",
        "numeric": "numeric",
        "numerical": "numeric",
        "continuous": "numeric",
        "date": "numeric",  # dates can be treated as numeric
    }
    
    # Normalize: lowercase and remove hyphens/underscores
    normalized_key = raw_type.lower().replace("-", "").replace("_", "")
    return type_mapping.get(normalized_key, "")

def _infer_qtype_and_fields(q):
    """
    Infer question type and extract relevant fields from Metaculus API2 question object.
    Pivots into nested 'question' key if present, then inspects possibilities/possibility.
    
    Args:
        q: Question dict from Metaculus API2 (may be nested under 'question' key)
    
    Returns:
        Tuple (qtype, extra) where:
        - qtype: str in {"binary", "numeric", "multiple_choice", "unknown"}
        - extra: dict with optional keys:
            - "options": list[str] for multiple_choice
            - "numeric_bounds": dict with min, max, unit, scale for numeric
    """
    extra = {}
    
    # Pivot into core question object
    core = _get_core_question(q)
    qid = core.get("id") or q.get("id", "?")
    
    # Get possibilities/possibility from core (defensive for both singular/plural)
    poss = core.get("possibilities") or core.get("possibility") or {}
    
    # Determine type from possibilities/possibility or fallback to core.type
    ptype = ""
    if isinstance(poss, dict):
        ptype = (poss.get("type") or "").strip().lower()
    elif isinstance(poss, list) and len(poss) > 0 and isinstance(poss[0], dict):
        ptype = (poss[0].get("type") or "").strip().lower()
    
    # Fallback to core.type if ptype not found
    if not ptype:
        ptype = (core.get("type") or "").strip().lower()
    
    # Map types per Metaculus v2 semantics
    if ptype in ["binary", "bool", "boolean"]:
        qtype = "binary"
    
    elif ptype in ["discrete"]:
        # discrete → multiple_choice
        qtype = "multiple_choice"
        # Extract option names from poss.outcomes[].name|label or core.options
        options = []
        
        # Try poss.outcomes
        if isinstance(poss, dict) and "outcomes" in poss:
            outcomes = poss["outcomes"]
            if isinstance(outcomes, list):
                for outcome in outcomes:
                    if isinstance(outcome, dict):
                        name = outcome.get("name") or outcome.get("label") or ""
                        if name:
                            options.append(name)
        
        # Fallback to core.options
        if not options and "options" in core:
            options_data = core["options"]
            if isinstance(options_data, list):
                for opt in options_data:
                    if isinstance(opt, dict):
                        name = opt.get("name") or opt.get("label") or opt.get("title") or ""
                        if name:
                            options.append(name)
                    elif isinstance(opt, str):
                        options.append(opt)
        
        extra["options"] = options
    
    elif ptype in ["continuous"]:
        # continuous → numeric
        qtype = "numeric"
        # Extract bounds from poss.range or poss.min/max
        numeric_bounds = {}
        
        if isinstance(poss, dict):
            # Try poss.range
            if "range" in poss:
                poss_range = poss["range"]
                if isinstance(poss_range, (list, tuple)) and len(poss_range) >= 2:
                    numeric_bounds["min"] = poss_range[0]
                    numeric_bounds["max"] = poss_range[1]
            # Try poss.min/max
            if not numeric_bounds:
                if "min" in poss:
                    numeric_bounds["min"] = poss["min"]
                if "max" in poss:
                    numeric_bounds["max"] = poss["max"]
            
            # Extract unit and scale
            if "unit" in poss:
                numeric_bounds["unit"] = poss["unit"]
            if "scale" in poss:
                numeric_bounds["scale"] = poss["scale"]
        
        if numeric_bounds:
            extra["numeric_bounds"] = numeric_bounds
    
    else:
        # Fallback inference: check for outcomes or range/min/max
        qtype = "unknown"
        
        # If outcomes present → multiple_choice
        if isinstance(poss, dict) and "outcomes" in poss:
            outcomes = poss["outcomes"]
            if isinstance(outcomes, list) and len(outcomes) > 0:
                qtype = "multiple_choice"
                options = []
                for outcome in outcomes:
                    if isinstance(outcome, dict):
                        name = outcome.get("name") or outcome.get("label") or ""
                        if name:
                            options.append(name)
                extra["options"] = options
        
        # Elif range/min/max present → numeric
        elif isinstance(poss, dict) and ("range" in poss or "min" in poss or "max" in poss):
            qtype = "numeric"
            numeric_bounds = {}
            if "range" in poss:
                poss_range = poss["range"]
                if isinstance(poss_range, (list, tuple)) and len(poss_range) >= 2:
                    numeric_bounds["min"] = poss_range[0]
                    numeric_bounds["max"] = poss_range[1]
            if not numeric_bounds:
                if "min" in poss:
                    numeric_bounds["min"] = poss["min"]
                if "max" in poss:
                    numeric_bounds["max"] = poss["max"]
            if numeric_bounds:
                extra["numeric_bounds"] = numeric_bounds
        
        # Log diagnostics for unknown types
        if qtype == "unknown":
            core_poss_type = (core.get("possibilities") or core.get("possibility") or {})
            if isinstance(core_poss_type, dict):
                core_poss_type = core_poss_type.get("type")
            elif isinstance(core_poss_type, list) and len(core_poss_type) > 0:
                core_poss_type = core_poss_type[0].get("type") if isinstance(core_poss_type[0], dict) else None
            else:
                core_poss_type = None
            
            print(f"[INFER UNKNOWN] Q{qid}: Could not infer type. ptype='{ptype}', core_poss_type={core_poss_type}", flush=True)
            
            # Log keys in core and poss for investigation
            print(f"[INFER UNKNOWN] Q{qid}: core keys: {list(core.keys())}", flush=True)
            if isinstance(poss, dict):
                print(f"[INFER UNKNOWN] Q{qid}: poss keys: {list(poss.keys())}", flush=True)
            elif isinstance(poss, list) and len(poss) > 0:
                print(f"[INFER UNKNOWN] Q{qid}: poss is list of length {len(poss)}", flush=True)
                if isinstance(poss[0], dict):
                    print(f"[INFER UNKNOWN] Q{qid}: poss[0] keys: {list(poss[0].keys())}", flush=True)
    
    return (qtype, extra)

def fetch_tournament_questions(contest_slug=None, project_id=None, project_slug=None):
    """
    Fetch open questions from a Metaculus project or contest.
    
    Args:
        contest_slug: Contest slug to filter by (legacy fallback)
        project_id: Project ID to filter by (preferred, defaults to METACULUS_PROJECT_ID)
        project_slug: Project slug to filter by (alternative, defaults to METACULUS_PROJECT_SLUG)
    
    Returns:
        List of question dicts normalized for pipeline
    """
    from typing import List, Dict, Any
    
    # Prioritize project-based targeting with safe fallbacks
    if project_id is None:
        project_id = METACULUS_PROJECT_ID
    if project_slug is None:
        project_slug = METACULUS_PROJECT_SLUG
    if contest_slug is None:
        contest_slug = METACULUS_CONTEST_SLUG
    
    url = METACULUS_API_BASE
    
    # Try project ID first, then project slug, then contest slug fallback
    if project_id:
        filter_str = f"project:{project_id}"
        filter_desc = f"project:{project_id}"
    elif project_slug:
        filter_str = f"project:{project_slug}"
        filter_desc = f"project:{project_slug}"
    else:
        filter_str = f"contest:{contest_slug}"
        filter_desc = f"contest:{contest_slug}"
    
    params = {
        "search": filter_str,
        "status": "open",
        "limit": 1000,
        "order_by": "-activity",
        "expand": "possibility",
        "fields": "id,title,description,possibility"
    }
    
    try:
        print(f"[INFO] Fetching tournament questions with filter: {filter_desc}")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        raw_questions = data.get("results", [])
        print(f"[INFO] Fetched {len(raw_questions)} questions from Metaculus API")
        
        # Identify questions missing 'possibility'/'possibilities' field and hydrate them
        questions_to_hydrate = []
        for q in raw_questions:
            core = _get_core_question(q)
            if not core.get("possibility") and not core.get("possibilities"):
                questions_to_hydrate.append(q.get("id"))
        
        if questions_to_hydrate:
            print(f"[INFO] Hydrating possibility for {len(questions_to_hydrate)} questions (per-ID fetch)...")
            for qid in questions_to_hydrate:
                try:
                    # Call detail endpoint without expand/fields to get native v2 structure
                    hydrate_url = f"{METACULUS_API_BASE}{qid}/"
                    hydrate_resp = requests.get(hydrate_url, timeout=15)
                    hydrate_resp.raise_for_status()
                    hydrated_data = hydrate_resp.json()
                    
                    # Find the question in raw_questions and update it
                    for q in raw_questions:
                        if q.get("id") == qid:
                            # If hydrated_data has a nested 'question' key, use that
                            hydrated_core = hydrated_data.get("question")
                            if hydrated_core:
                                q["question"] = hydrated_core
                            else:
                                # Otherwise merge the whole hydrated_data as core
                                # This handles the case where detail returns flat structure
                                for key in ["possibility", "possibilities", "type", "title", "description"]:
                                    if key in hydrated_data:
                                        q[key] = hydrated_data[key]
                            break
                except Exception as e:
                    print(f"[WARN] Failed to hydrate question {qid}: {e}")
        
        # Debug smoke-print: show sample of first 5 questions
        print(f"[DEBUG] Sample of first {min(5, len(raw_questions))} questions:")
        for i, q in enumerate(raw_questions[:5]):
            qid = q.get("id", "?")
            poss = q.get("possibility", {})
            poss_type = poss.get("type", "") if poss else ""
            q_type = q.get("type", "")
            print(f"  ({qid}, {repr(poss_type)}, {repr(q_type)})")
        
        # Normalize to pipeline format
        questions = []
        skipped_count = 0
        
        for q in raw_questions:
            qid = q.get("id")
            if not qid:
                continue
            
            # Use new helper to infer question type and extract fields
            qtype, extra = _infer_qtype_and_fields(q)
            
            if qtype == "unknown":
                # Unknown/unmappable type - skip question with explicit source info
                core = _get_core_question(q)
                poss = core.get("possibilities") or core.get("possibility") or {}
                poss_type = poss.get("type", "") if isinstance(poss, dict) else ""
                raw_type = core.get("type", "")
                type_source = poss_type if poss_type else (raw_type if raw_type else "unknown")
                print(f"[SKIP] Unsupported question type for Q{qid}: '{type_source}'")
                skipped_count += 1
                continue
            
            # Extract title and description from core
            core = _get_core_question(q)
            title = core.get("title") or q.get("title") or ""
            description = core.get("description") or q.get("description") or ""
            
            # Build normalized question
            normalized = {
                "id": qid,
                "type": qtype,
                "title": title,
                "description": description,
                "url": f"https://www.metaculus.com/questions/{qid}/"
            }
            
            # Handle multiple choice options
            if qtype == "multiple_choice":
                options = extra.get("options", [])
                normalized["options"] = [{"name": name} for name in options]
            else:
                normalized["options"] = []
            
            # Handle numeric bounds
            if qtype == "numeric":
                numeric_bounds = extra.get("numeric_bounds", {})
                if "min" in numeric_bounds:
                    try:
                        normalized["min"] = float(numeric_bounds["min"])
                    except (ValueError, TypeError):
                        # For date strings, keep as-is (will be handled by downstream code)
                        normalized["min"] = numeric_bounds["min"]
                if "max" in numeric_bounds:
                    try:
                        normalized["max"] = float(numeric_bounds["max"])
                    except (ValueError, TypeError):
                        # For date strings, keep as-is (will be handled by downstream code)
                        normalized["max"] = numeric_bounds["max"]
            
            questions.append(normalized)
        
        print(f"[INFO] Summary: Fetched {len(raw_questions)}, Normalized {len(questions)}, Skipped {skipped_count}")
        return questions
        
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", "N/A")
        try:
            detail = e.response.text[:400]
        except Exception:
            detail = str(e)
        print(f"[ERROR] Failed to fetch tournament questions (HTTP {status}): {detail}")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to fetch tournament questions: {e}")
        return []

# ========== AskNews Cache Helpers ==========
def _load_news_cache():
    """Load news cache from disk; return empty dict if missing or corrupt."""
    if not NEWS_CACHE_FILE.exists():
        return {}
    try:
        with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load news cache: {e}")
        return {}

def _save_news_cache(cache):
    """Save news cache to disk."""
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Could not save news cache: {e}")

def _is_fresh(entry, ttl_hours=NEWS_CACHE_TTL_HOURS):
    """Check if cache entry is fresh (< ttl_hours old)."""
    try:
        ts = datetime.fromisoformat(entry["timestamp"])
        age = datetime.utcnow() - ts
        return age < timedelta(hours=ttl_hours)
    except:
        return False

def fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q):
    """
    Fetch AskNews facts for a batch of questions.
    
    Args:
        qid_to_text: dict of question_id -> question_text
        max_per_q: max facts per question
    
    Returns:
        dict of question_id -> list of "YYYY-MM-DD: headline (url)" strings
    """
    cache = _load_news_cache()
    results = {}
    to_fetch = {}
    
    # Check cache first
    for qid, text in qid_to_text.items():
        cache_key = str(qid)
        if cache_key in cache and _is_fresh(cache[cache_key]):
            results[qid] = cache[cache_key]["facts"]
            print(f"[INFO] Using cached news for question {qid}")
        else:
            to_fetch[qid] = text
    
    # Fetch missing/stale
    if to_fetch and ASKNEWS_CLIENT_ID and ASKNEWS_SECRET:
        print(f"[INFO] Fetching AskNews for {len(to_fetch)} questions...")
        # Acquire token once for the entire batch
        token = _get_asknews_token()
        if token:
            print(f"[INFO] Using single OAuth token for batch of {len(to_fetch)} questions")
            for qid, text in to_fetch.items():
                facts = _fetch_asknews_single(text, max_per_q, token=token)
                results[qid] = facts
                cache[str(qid)] = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "facts": facts
                }
            _save_news_cache(cache)
        else:
            # Token acquisition failed, fall back to base-rate for all uncached
            print("[WARN] AskNews token acquisition failed; using fallback for uncached questions")
            for qid in to_fetch:
                results[qid] = ["No recent news available; base rates apply."]
    elif to_fetch:
        print("[WARN] AskNews credentials missing; using fallback for uncached questions")
        for qid in to_fetch:
            results[qid] = ["No recent news available; base rates apply."]
    
    return results

def _get_asknews_token():
    """
    Acquire an OAuth token from AskNews using client credentials with HTTP Basic auth.
    Returns access_token string or None on failure.
    """
    if not ASKNEWS_CLIENT_ID or not ASKNEWS_SECRET:
        print("[WARN] ASKNEWS_CLIENT_ID/ASKNEWS_SECRET not set")
        return None
    try:
        token_url = "https://auth.asknews.app/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "scope": "news"
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        # Use HTTP Basic auth (client_secret_basic) instead of client_secret_post
        resp = requests.post(
            token_url, 
            data=data, 
            auth=(ASKNEWS_CLIENT_ID, ASKNEWS_SECRET),
            headers=headers, 
            timeout=10
        )
        resp.raise_for_status()
        body = resp.json()
        token = body.get("access_token")
        if not token:
            print(f"[ERROR] AskNews token response missing access_token: {body}")
            return None
        return token
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text if hasattr(e.response, "text") else str(e)
        print(f"[ERROR] AskNews OAuth HTTP error {e.response.status_code}: {detail}")
        return None
    except Exception as e:
        print(f"[ERROR] AskNews OAuth failed: {e}")
        return None

def _fetch_asknews_single(question_text, max_facts=ASKNEWS_MAX_PER_Q, token=None):
    """Fetch facts from AskNews for a single question; return list of formatted strings."""
    if token is None:
        token = _get_asknews_token()
    if not token:
        # Authentication failed; return base-rate fallback
        return ["AskNews unavailable; base rates only."]
    try:
        url = "https://api.asknews.app/v1/news/search"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        params = {
            "query": question_text,
            "n_articles": max_facts,
            "method": "kw",
            "return_type": "dicts"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])
        facts = []
        for art in articles[:max_facts]:
            pub_date = art.get("pub_date", "")[:10]
            headline = art.get("headline", "Untitled")
            link = art.get("article_url", "") or art.get("link", "")
            facts.append(f"{pub_date}: {headline} ({link})")
        if not facts:
            facts = ["No recent news found; relying on base rates."]
        return facts
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", "N/A")
        try:
            snippet = e.response.text[:400]
        except Exception:
            snippet = str(e)
        print(f"[ERROR] AskNews HTTP {status}: {snippet}")
        return ["AskNews unavailable; base rates only."]
    except Exception as e:
        print(f"[ERROR] AskNews fetch failed: {e}")
        return ["AskNews unavailable; base rates only."]

# ========== Hardened LLM Call ==========
def llm_call(prompt, max_tokens=1500, temperature=0.3):
    """
    Call OpenRouter with JSON mode, strip fences, return parsed dict.
    Raises RuntimeError with diagnostics on HTTP failures.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # helpful diagnostic headers (optional)
        "Referer": "https://github.com/jh-tpp/metac-bot-template",
        "X-Client": "metac-bot-template"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # parse body if possible to include helpful diagnostic text
        try:
            body = e.response.json()
        except Exception:
            body = e.response.text if hasattr(e.response, "text") else str(e)
        raise RuntimeError(
            f"OpenRouter API HTTP {getattr(e.response, 'status_code', 'N/A')}: {body}\n"
            "Check OPENROUTER_API_KEY, model accessibility, and account quota. "
            "Model setting not modified by this patch."
        )
    except Exception as e:
        raise RuntimeError(f"OpenRouter request failed: {e}")

    resp_json = resp.json()
    # defensive navigation
    try:
        raw = resp_json["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"Unexpected OpenRouter response shape: {resp_json}")

    # Strip markdown fences if present
    if isinstance(raw, str) and raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON from LLM response: {e}\nRaw response: {raw}")

# ========== Rationale Synthesizer ==========
def synthesize_rationale(question_text, world_summaries, aggregate_forecast, max_worlds=12):
    """
    Produce 3-5 bullet rationale by summarizing world_summaries.
    
    Args:
        question_text: str
        world_summaries: list of str (world summary texts)
        aggregate_forecast: dict with 'p' or 'probs' or 'cdf'
        max_worlds: cap summaries to avoid huge prompts
    
    Returns:
        list of bullet strings (no boilerplate)
    """
    summaries_subset = world_summaries[:max_worlds]
    
    # Format aggregate
    if "p" in aggregate_forecast:
        agg_str = f"Binary probability: {aggregate_forecast['p']:.2f}"
    elif "probs" in aggregate_forecast:
        probs = aggregate_forecast["probs"]
        agg_str = f"Multiple-choice probabilities: {probs}"
    elif "cdf" in aggregate_forecast:
        p10 = aggregate_forecast.get("p10", "?")
        p50 = aggregate_forecast.get("p50", "?")
        p90 = aggregate_forecast.get("p90", "?")
        agg_str = f"Numeric forecast (p10/p50/p90): {p10}/{p50}/{p90}"
    else:
        agg_str = "Forecast available"
    
    prompt = f"""
    You are a forecasting analyst. Given these Monte-Carlo world summaries and the aggregate forecast, produce 3-5 specific, evidence-based bullet points explaining the reasoning. Do NOT include boilerplate like \"will adjust later\" or \"subject to change\".

    Question: {question_text}

    Aggregate Forecast: {agg_str}

    World Summaries (sample of {len(summaries_subset)}):
    {chr(10).join(f"- {s}" for s in summaries_subset)}

    Return JSON: {{"bullets": ["bullet1", "bullet2", ...]}}
    """
    try:
        result = llm_call(prompt, max_tokens=800, temperature=0.3)
        bullets = result.get("bullets", [])
        return bullets[:5]  # cap at 5
    except Exception as e:
        print(f"[ERROR] Rationale synthesis failed: {e}")
        return ["Could not synthesize rationale due to LLM error."]

# ========== Numeric Bounds Parser ==========
def parse_numeric_bounds(question_obj):
    """
    Parse numeric bounds from question metadata or description.
    
    Args:
        question_obj: Metaculus question dict
    
    Returns:
        (min_val, max_val) tuple or None if not found
    """
    # First try question metadata
    if "min" in question_obj and "max" in question_obj:
        try:
            min_val = float(question_obj["min"])
            max_val = float(question_obj["max"])
            return (min_val, max_val)
        except (ValueError, TypeError):
            pass
    
    # Fallback to regex parsing of description
    import re
    desc = question_obj.get("description", "")
    if not desc:
        return None
    
    # Pattern: "Range: <min> to <max>" (handles negatives and decimals)
    pattern = r'Range:\s*([-+]?\d+(?:\.\d+)?)\s*to\s*([-+]?\d+(?:\.\d+)?)'
    match = re.search(pattern, desc, re.IGNORECASE)
    if match:
        try:
            min_val = float(match.group(1))
            max_val = float(match.group(2))
            return (min_val, max_val)
        except (ValueError, TypeError):
            pass
    
    return None

def correct_numeric_bounds(result, bounds):
    """
    Attempt to correct numeric result to fit within bounds.
    
    Args:
        result: dict with grid, cdf, p10, p50, p90
        bounds: (min_bound, max_bound) tuple
    
    Returns:
        (corrected_result, success) tuple
    """
    if not bounds:
        return result, True
    
    min_bound, max_bound = bounds
    grid = result.get("grid", [])
    cdf = result.get("cdf", [])
    
    if not grid or not cdf:
        return result, False
    
    # Check if correction is needed
    needs_correction = False
    if min(grid) < min_bound or max(grid) > max_bound:
        needs_correction = True
    
    for pname in ["p10", "p50", "p90"]:
        pval = result.get(pname)
        if pval is not None and (pval < min_bound or pval > max_bound):
            needs_correction = True
    
    if not needs_correction:
        return result, True
    
    # Attempt correction: clamp grid and percentiles
    print(f"[INFO] Attempting bounded correction: clamping to [{min_bound}, {max_bound}]")
    
    corrected = result.copy()
    
    # Clamp grid
    corrected["grid"] = [max(min_bound, min(max_bound, x)) for x in grid]
    
    # Re-check CDF monotonicity (may be affected by clamping)
    # If grid values collapsed, we need to deduplicate and rebuild CDF
    unique_grid = []
    unique_cdf = []
    for i, x in enumerate(corrected["grid"]):
        if not unique_grid or x > unique_grid[-1]:
            unique_grid.append(x)
            unique_cdf.append(cdf[i])
        elif x == unique_grid[-1]:
            # Update CDF to max if duplicate grid point
            unique_cdf[-1] = max(unique_cdf[-1], cdf[i])
    
    corrected["grid"] = unique_grid
    corrected["cdf"] = unique_cdf
    
    # Clamp percentiles
    for pname in ["p10", "p50", "p90"]:
        if pname in corrected:
            corrected[pname] = max(min_bound, min(max_bound, corrected[pname]))
    
    return corrected, True

# ========== Validation ==========
def validate_mc_result(question_obj, result):
    """
    Validate MC result against question type.
    
    Returns: (bool, error_msg)
    """
    qtype = question_obj.get("type", "").lower()
    
    if "binary" in qtype:
        p = result.get("p")
        if p is None:
            return False, "Binary result missing 'p'"
        if not (0.01 <= p <= 0.99):
            return False, f"Binary p={p} out of [0.01, 0.99]"
    
    elif "multiple" in qtype or "mc" in qtype:
        probs = result.get("probs")
        if not probs:
            return False, "MC result missing 'probs'"
        
        # Infer k from question
        k = len(question_obj.get("options", []))
        if k == 0:
            return False, "Cannot infer k from question options"
        
        if len(probs) != k:
            return False, f"MC probs length {len(probs)} != k={k}"
        
        total = sum(probs)
        if abs(total - 1.0) > 1e-6:
            return False, f"MC probs sum to {total}, not 1.0"
        
        if any(p < 0 or p > 1 for p in probs):
            return False, "MC probs contain values outside [0,1]"
    
    elif "numeric" in qtype or "continuous" in qtype:
        cdf = result.get("cdf")
        grid = result.get("grid")
        if not cdf or not grid:
            return False, "Numeric result missing 'cdf' or 'grid'"
        
        if len(cdf) != len(grid):
            return False, f"CDF length {len(cdf)} != grid length {len(grid)}"
        
        if any(c < 0 or c > 1 for c in cdf):
            return False, "CDF contains values outside [0,1]"
        
        # Check monotone
        for i in range(1, len(cdf)):
            if cdf[i] < cdf[i-1]:
                return False, f"CDF not monotone at index {i}"
        
        # Check bounds if available
        bounds = parse_numeric_bounds(question_obj)
        if bounds:
            min_bound, max_bound = bounds
            
            # Check grid bounds
            grid_min = min(grid)
            grid_max = max(grid)
            if grid_min < min_bound:
                return False, f"Grid min {grid_min} < bound {min_bound}"
            if grid_max > max_bound:
                return False, f"Grid max {grid_max} > bound {max_bound}"
            
            # Check p10/p50/p90 if present
            for pname in ["p10", "p50", "p90"]:
                pval = result.get(pname)
                if pval is not None:
                    if pval < min_bound or pval > max_bound:
                        return False, f"{pname}={pval} outside bounds [{min_bound}, {max_bound}]"
    
    return True, ""

# ========== Forecast Submission (with guardrails) ==========
def post_forecast_safe(question_obj, mc_result, publish=False, skip_set=None):
    """
    Post forecast if all checks pass.
    
    Args:
        question_obj: Metaculus question dict
        mc_result: dict with 'p' or 'probs' or 'cdf'/'grid', plus 'reasoning'
        publish: bool, actually POST or just dry-run
        skip_set: set of qids already forecasted (optional)
    
    Returns:
        bool success
    """
    qid = question_obj.get("id")
    if skip_set and qid in skip_set:
        print(f"[SKIP] Question {qid} already forecasted (dedupe).")
        return False
    
    if question_obj.get("resolution") is not None:
        print(f"[SKIP] Question {qid} already resolved.")
        return False
    
    # Defensive skip: verify question type is supported before processing
    qtype = question_obj.get("type", "").lower()
    supported_types = ["binary", "multiple_choice", "numeric"]
    if qtype not in supported_types:
        print(f"[SKIP] Skipping post for Q{qid}: unsupported type '{qtype}'")
        return False
    
    valid, err = validate_mc_result(question_obj, mc_result)
    if not valid:
        # For numeric questions with bounds, try correction
        qtype = question_obj.get("type", "").lower()
        if "numeric" in qtype or "continuous" in qtype:
            bounds = parse_numeric_bounds(question_obj)
            if bounds:
                print(f"[WARN] Initial validation failed for Q{qid}: {err}")
                mc_result, success = correct_numeric_bounds(mc_result, bounds)
                if success:
                    # Re-validate after correction
                    valid, err = validate_mc_result(question_obj, mc_result)
                    if valid:
                        print(f"[INFO] Correction successful for Q{qid}")
                    else:
                        print(f"[ERROR] Correction failed for Q{qid}: {err}")
                        return False
                else:
                    print(f"[ERROR] Could not correct Q{qid}")
                    return False
            else:
                print(f"[ERROR] Validation failed for Q{qid}: {err}")
                return False
        else:
            print(f"[ERROR] Validation failed for Q{qid}: {err}")
            return False
    
    payload = mc_results_to_metaculus_payload(question_obj, mc_result)
    
    if not publish:
        print(f"[DRYRUN] Would post to Q{qid}: {payload}")
        return True
    
    try:
        submit_forecast(qid, payload, METACULUS_TOKEN)
        print(f"[SUCCESS] Posted forecast for Q{qid}")
        if skip_set is not None:
            skip_set.add(qid)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to post Q{qid}: {e}")
        return False

# ========== Live Test & Smoke Test Helpers ==========
def _create_session_with_retry():
    """
    Create a requests session with retry logic.
    
    Returns:
        requests.Session with retry adapter
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def _hydrate_question_with_diagnostics(qid):
    """
    Fetch a single question from Metaculus API with comprehensive diagnostics.
    Tries multiple URL and parameter variants, logging each attempt.
    
    Args:
        qid: Question ID
    
    Returns:
        Merged question dict or None on failure
    """
    print(f"\n[HYDRATE] Starting comprehensive fetch for Q{qid}", flush=True)
    
    session = _create_session_with_retry()
    headers = {
        "Accept": "application/json",
        "User-Agent": "metac-bot-template/1.0"
    }
    
    # Try multiple variants in order
    attempts = [
        {
            "label": "attempt 1: with trailing slash, expand=possibility, fields",
            "url": f"{METACULUS_API_BASE}{qid}/",
            "params": {
                "expand": "possibility",
                "fields": "id,title,description,type,possibility,options"
            }
        },
        {
            "label": "attempt 2: with trailing slash, plain detail",
            "url": f"{METACULUS_API_BASE}{qid}/",
            "params": {}
        },
        {
            "label": "attempt 3: no trailing slash, expand=possibility, fields",
            "url": f"{METACULUS_API_BASE}{qid}",
            "params": {
                "expand": "possibility",
                "fields": "id,title,description,type,possibility,options"
            }
        },
        {
            "label": "attempt 4: no trailing slash, plain detail",
            "url": f"{METACULUS_API_BASE}{qid}",
            "params": {}
        }
    ]
    
    merged_data = None
    
    for i, attempt in enumerate(attempts, 1):
        label = attempt["label"]
        url = attempt["url"]
        params = attempt["params"]
        
        print(f"\n[HYDRATE] Q{qid} - {label}", flush=True)
        print(f"  Request headers: {headers}", flush=True)
        
        try:
            resp = session.get(url, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            
            raw_text = resp.text
            parsed_obj = resp.json()
            
            # Log comprehensive diagnostics
            _debug_log_fetch(qid, label, resp, raw_text, parsed_obj, url, params)
            
            # Write debug files
            prefix = f"debug_q_{qid}_att{i}"
            _write_debug_files(prefix, raw_text, parsed_obj)
            
            # Merge into working object
            if merged_data is None:
                merged_data = parsed_obj
            else:
                # If parsed_obj has a nested 'question', merge its contents
                if "question" in parsed_obj and isinstance(parsed_obj["question"], dict):
                    nested_q = parsed_obj["question"]
                    # Merge nested question into merged_data's question (or create it)
                    if "question" not in merged_data or not isinstance(merged_data["question"], dict):
                        merged_data["question"] = {}
                    merged_data["question"].update(nested_q)
                    print(f"[HYDRATE] Q{qid} - Merged nested question from {label}", flush=True)
                
                # Also merge top-level possibility/possibilities if present
                if "possibility" in parsed_obj and parsed_obj["possibility"]:
                    merged_data["possibility"] = parsed_obj["possibility"]
                    print(f"[HYDRATE] Q{qid} - Merged possibility from {label}", flush=True)
                
                if "possibilities" in parsed_obj and parsed_obj["possibilities"]:
                    merged_data["possibilities"] = parsed_obj["possibilities"]
                    print(f"[HYDRATE] Q{qid} - Merged possibilities from {label}", flush=True)
                
                # Merge top-level type fields
                for field in ["type", "title", "description", "possibility_type", "prediction_type", "question_type", "value_type", "outcome_type"]:
                    if field in parsed_obj and parsed_obj[field]:
                        merged_data[field] = parsed_obj[field]
                        print(f"[HYDRATE] Q{qid} - Merged {field} from {label}", flush=True)
            
            print(f"[HYDRATE] Q{qid} - {label} SUCCESS", flush=True)
            
        except requests.exceptions.HTTPError as e:
            print(f"[HYDRATE] Q{qid} - {label} FAILED: HTTP {e.response.status_code}", flush=True)
            traceback.print_exc()
        except requests.exceptions.Timeout as e:
            print(f"[HYDRATE] Q{qid} - {label} FAILED: Timeout", flush=True)
            traceback.print_exc()
        except Exception as e:
            print(f"[HYDRATE] Q{qid} - {label} FAILED: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
    
    # Write final merged object
    if merged_data:
        print(f"\n[HYDRATE] Q{qid} - Writing final merged object", flush=True)
        final_prefix = f"debug_q_{qid}_final"
        try:
            final_file = f"{final_prefix}.json"
            with open(final_file, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, indent=2, ensure_ascii=False)
            print(f"[HYDRATE] Q{qid} - Wrote final merged object to {final_file}", flush=True)
            print(f"[HYDRATE] Q{qid} - Final top-level keys: {list(merged_data.keys())}", flush=True)
        except Exception as e:
            print(f"[ERROR] Failed to write final merged object for Q{qid}: {e}", flush=True)
            traceback.print_exc()
    else:
        print(f"[HYDRATE] Q{qid} - FAILED: No successful fetches", flush=True)
    
    return merged_data

def run_live_test():
    """
    Live test on three long-lived Metaculus questions (578, 14333, 22427).
    Fetches questions, runs pipeline, writes artifacts. Never submits.
    """
    print("[LIVE TEST] Starting...", flush=True)
    print(f"[LIVE TEST] Python version: {sys.version}", flush=True)
    print(f"[LIVE TEST] Requests version: {requests.__version__}", flush=True)
    
    # Fetch three long-lived questions with comprehensive diagnostics
    test_qids = [578, 14333, 22427]  # binary, numeric, multiple_choice
    raw_questions = []
    
    for qid in test_qids:
        print(f"\n{'#'*70}", flush=True)
        print(f"[LIVE TEST] Starting fetch for question {qid}", flush=True)
        print(f"{'#'*70}", flush=True)
        
        q = _hydrate_question_with_diagnostics(qid)
        if q:
            raw_questions.append(q)
            print(f"[LIVE TEST] Successfully fetched Q{qid}", flush=True)
        else:
            print(f"[WARN] Could not fetch question {qid}, skipping", flush=True)
    
    if not raw_questions:
        print("[ERROR] No questions fetched. Check debug artifacts in current directory:", flush=True)
        print("  - debug_q_*_raw.txt (raw response bodies)", flush=True)
        print("  - debug_q_*.json (parsed response objects)", flush=True)
        print("  - debug_q_{id}_final.json (final merged objects)", flush=True)
        return
    
    # Normalize questions
    print(f"\n[LIVE TEST] Normalizing {len(raw_questions)} fetched questions...", flush=True)
    questions = []
    for q in raw_questions:
        qid = q.get("id")
        if not qid:
            continue
        
        qtype, extra = _infer_qtype_and_fields(q)
        
        if qtype == "unknown":
            print(f"[SKIP] Unknown type for Q{qid} - check debug artifacts", flush=True)
            continue
        
        print(f"[INFO] Q{qid} inferred type: {qtype}", flush=True)
        
        # Extract title and description from core
        core = _get_core_question(q)
        title = core.get("title") or q.get("title") or ""
        description = core.get("description") or q.get("description") or ""
        
        normalized = {
            "id": qid,
            "type": qtype,
            "title": title,
            "description": description,
            "url": f"https://www.metaculus.com/questions/{qid}/"
        }
        
        if qtype == "multiple_choice":
            options = extra.get("options", [])
            normalized["options"] = [{"name": name} for name in options]
            print(f"[INFO] Q{qid} options: {[opt['name'] for opt in normalized['options']]}", flush=True)
        else:
            normalized["options"] = []
        
        if qtype == "numeric":
            numeric_bounds = extra.get("numeric_bounds", {})
            if "min" in numeric_bounds:
                try:
                    normalized["min"] = float(numeric_bounds["min"])
                except (ValueError, TypeError):
                    normalized["min"] = numeric_bounds["min"]
            if "max" in numeric_bounds:
                try:
                    normalized["max"] = float(numeric_bounds["max"])
                except (ValueError, TypeError):
                    normalized["max"] = numeric_bounds["max"]
            if "min" in normalized and "max" in normalized:
                print(f"[INFO] Q{qid} numeric bounds: [{normalized['min']}, {normalized['max']}]", flush=True)
        
        questions.append(normalized)
    
    if not questions:
        print("[ERROR] Zero questions normalized. Check debug artifacts:", flush=True)
        print("  - debug_q_*_raw.txt (raw response bodies)", flush=True)
        print("  - debug_q_*.json (parsed response objects)", flush=True)
        print("  - debug_q_{id}_final.json (final merged objects)", flush=True)
        return
    
    print(f"\n[LIVE TEST] Successfully normalized {len(questions)} questions", flush=True)
    
    # Fetch AskNews facts
    print(f"\n[LIVE TEST] Fetching AskNews facts...", flush=True)
    qid_to_text = {q["id"]: q["title"] + " " + q.get("description", "") for q in questions}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    
    # Run pipeline
    all_results = []
    all_reasons = []
    
    for q in questions:
        qid = q["id"]
        facts = news.get(qid, [])
        
        print(f"\n{'='*60}", flush=True)
        print(f"[INFO] Processing Q{qid}: {q['title']}", flush=True)
        print(f"  Type: {q['type']}", flush=True)
        print(f"  AskNews facts: {len(facts)}", flush=True)
        print(f"{'='*60}", flush=True)
        
        mc_out = run_mc_worlds(
            question_obj=q,
            context_facts=facts,
            n_worlds=N_WORLDS_DEFAULT,
            return_evidence=True
        )
        
        world_summaries = mc_out.pop("world_summaries", [])
        aggregate = mc_out
        bullets = synthesize_rationale(q["title"], world_summaries, aggregate)
        aggregate["reasoning"] = bullets
        
        all_results.append({
            "question_id": qid,
            "question_title": q["title"],
            "forecast": aggregate
        })
        
        all_reasons.append(f"Q{qid}: {q['title']}")
        for b in bullets:
            all_reasons.append(f"  • {b}")
        all_reasons.append("")
        
        print(f"[INFO] Q{qid} processing complete", flush=True)
    
    # Write artifacts
    print(f"\n[LIVE TEST] Writing output artifacts...", flush=True)
    with open("mc_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"[LIVE TEST] Wrote mc_results.json", flush=True)
    
    with open("mc_reasons.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_reasons))
    print(f"[LIVE TEST] Wrote mc_reasons.txt", flush=True)
    
    print("\n[LIVE TEST] Complete. Artifacts:", flush=True)
    print("  - mc_results.json (forecast results)", flush=True)
    print("  - mc_reasons.txt (reasoning)", flush=True)
    print("  - debug_q_*_raw.txt (raw API responses)", flush=True)
    print("  - debug_q_*.json (parsed API responses)", flush=True)
    print("  - debug_q_{id}_final.json (final merged objects)", flush=True)

def run_submit_smoke_test(test_qid, publish=False):
    """
    Submit smoke test for a single question ID.
    
    Args:
        test_qid: Metaculus question ID to test (int)
        publish: If True, actually submit forecast; otherwise just dry-run
    """
    print(f"[SUBMIT SMOKE TEST] Starting for Q{test_qid} (publish={publish})...", flush=True)
    
    # Fetch question
    print(f"[INFO] Fetching question {test_qid}...", flush=True)
    q = _hydrate_question_with_diagnostics(test_qid)
    
    if not q:
        print(f"[ERROR] Could not fetch question {test_qid}. Aborting.", flush=True)
        return
    
    # Normalize question
    qid = q.get("id")
    qtype, extra = _infer_qtype_and_fields(q)
    
    if qtype == "unknown":
        print(f"[ERROR] Unknown question type for Q{qid}. Aborting.", flush=True)
        return
    
    print(f"[INFO] Q{qid} inferred type: {qtype}", flush=True)
    
    # Extract title and description from core
    core = _get_core_question(q)
    title = core.get("title") or q.get("title") or ""
    description = core.get("description") or q.get("description") or ""
    
    normalized = {
        "id": qid,
        "type": qtype,
        "title": title,
        "description": description,
        "url": f"https://www.metaculus.com/questions/{qid}/"
    }
    
    if qtype == "multiple_choice":
        options = extra.get("options", [])
        normalized["options"] = [{"name": name} for name in options]
    else:
        normalized["options"] = []
    
    if qtype == "numeric":
        numeric_bounds = extra.get("numeric_bounds", {})
        if "min" in numeric_bounds:
            try:
                normalized["min"] = float(numeric_bounds["min"])
            except (ValueError, TypeError):
                normalized["min"] = numeric_bounds["min"]
        if "max" in numeric_bounds:
            try:
                normalized["max"] = float(numeric_bounds["max"])
            except (ValueError, TypeError):
                normalized["max"] = numeric_bounds["max"]
    
    # Fetch AskNews facts
    qid_to_text = {qid: title + " " + description}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    facts = news.get(qid, [])
    
    print(f"[INFO] Processing Q{qid}: {title}")
    print(f"  Type: {qtype}")
    print(f"  AskNews facts: {len(facts)}")
    
    # Run pipeline
    mc_out = run_mc_worlds(
        question_obj=normalized,
        context_facts=facts,
        n_worlds=N_WORLDS_DEFAULT,
        return_evidence=True
    )
    
    world_summaries = mc_out.pop("world_summaries", [])
    aggregate = mc_out
    bullets = synthesize_rationale(title, world_summaries, aggregate)
    aggregate["reasoning"] = bullets
    
    # Write artifacts
    result = {
        "question_id": qid,
        "question_title": title,
        "forecast": aggregate
    }
    
    with open("mc_results.json", "w", encoding="utf-8") as f:
        json.dump([result], f, indent=2, ensure_ascii=False)
    
    reasons = [f"Q{qid}: {title}"]
    for b in bullets:
        reasons.append(f"  • {b}")
    
    with open("mc_reasons.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(reasons))
    
    # Attempt submission if publish=True
    if publish:
        print(f"[INFO] Attempting to submit forecast for Q{qid}...")
        success = post_forecast_safe(normalized, aggregate, publish=True)
        
        if success:
            print(f"[SUCCESS] Posted forecast for Q{qid}")
            with open("posted_ids.json", "w", encoding="utf-8") as f:
                json.dump([qid], f, indent=2)
            print("[INFO] Wrote posted_ids.json")
        else:
            print(f"[ERROR] Failed to post forecast for Q{qid}")
    else:
        print(f"[DRYRUN] Would post forecast for Q{qid}")
    
    print(f"[SUBMIT SMOKE TEST] Complete. Artifacts: mc_results.json, mc_reasons.txt" + 
          (", posted_ids.json" if publish else ""))

# ========== Test Mode ==========
def run_test_mode():
    """
    Fetch 3 example questions, run MC with AskNews, write artifacts.
    """
    print("[TEST MODE] Starting...")
    
    # Fixture: 3 example questions (replace with real Metaculus API call if available)
    test_questions = [
        {
            "id": 12345,
            "type": "binary",
            "title": "Will AGI be developed by 2030?",
            "description": "Resolution criteria: ...",
            "options": []
        },
        {
            "id": 12346,
            "type": "multiple_choice",
            "title": "Which company will lead AI in 2026?",
            "description": "Options: Google, OpenAI, Anthropic, Meta",
            "options": [
                {"name": "Google"},
                {"name": "OpenAI"},
                {"name": "Anthropic"},
                {"name": "Meta"}
            ]
        },
        {
            "id": 12347,
            "type": "numeric",
            "title": "US GDP growth in 2025 (%)?",
            "description": "Range: -5 to 10",
            "options": []
        }
    ]
    
    # Fetch AskNews facts
    qid_to_text = {q["id"]: q["title"] + " " + q["description"] for q in test_questions}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    
    # Run MC worlds
    all_results = []
    all_reasons = []
    
    for q in test_questions:
        qid = q["id"]
        facts = news.get(qid, [])
        
        print(f"\n[INFO] Processing Q{qid}: {q['title']}")
        print(f"  AskNews facts: {len(facts)}")
        
        # Detect and print bounds for numeric questions
        qtype = q.get("type", "").lower()
        if "numeric" in qtype or "continuous" in qtype:
            bounds = parse_numeric_bounds(q)
            if bounds:
                print(f"  Detected numeric bounds: [{bounds[0]}, {bounds[1]}]")
            else:
                print(f"  No numeric bounds detected")
        
        # Build context
        context = f"Question: {q['title']}\n\nDescription: {q['description']}\n\n"
        context += "Recent News:\n" + "\n".join(f"- {f}" for f in facts)
        
        # Run MC
        mc_out = run_mc_worlds(
            question_obj=q,
            context_facts=facts,
            n_worlds=N_WORLDS_DEFAULT,
            return_evidence=True
        )
        
        # Synthesize rationale
        world_summaries = mc_out.get("world_summaries", [])
        aggregate = {k: v for k, v in mc_out.items() if k != "world_summaries"}
        bullets = synthesize_rationale(q["title"], world_summaries, aggregate)
        
        mc_out["reasoning"] = bullets
        all_results.append({
            "question_id": qid,
            "question_title": q["title"],
            "forecast": mc_out
        })
        
        all_reasons.append(f"Q{qid}: {q['title']}")
        for b in bullets:
            all_reasons.append(f"  • {b}")
        all_reasons.append("")
    
    # Write artifacts
    with open("mc_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    with open("mc_reasons.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_reasons))
    
    print("\n[TEST MODE] Complete. Artifacts: mc_results.json, mc_reasons.txt")

# ========== Tournament Modes ==========
def run_tournament(mode="dryrun", publish=False):
    """
    Fetch tournament questions, run MC, post (if publish=True).
    Writes state files: open_ids.json (dryrun), posted_ids.json (submit).
    """
    print(f"[TOURNAMENT MODE: {mode}] Starting...")
    
    # Fetch questions from Metaculus tournament API
    questions = fetch_tournament_questions()
    
    if not questions:
        print("[ERROR] No questions fetched. Check Metaculus API integration.")
        return
    
    # Write open_ids.json in dryrun mode
    open_ids = [q["id"] for q in questions]
    if mode == "dryrun":
        with open("open_ids.json", "w", encoding="utf-8") as f:
            json.dump(open_ids, f, indent=2)
        print(f"[INFO] Wrote {len(open_ids)} open question IDs to open_ids.json")
    
    qid_to_text = {q["id"]: q["title"] + " " + q.get("description", "") for q in questions}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    
    skip_set = set()  # dedupe already-forecasted
    all_results = []
    all_reasons = []
    posted_ids = []  # track successfully posted IDs for submit mode
    
    for q in questions:
        qid = q["id"]
        facts = news.get(qid, [])
        
        print(f"\n[INFO] Processing Q{qid}: {q['title']}")
        
        mc_out = run_mc_worlds(
            question_obj=q,
            context_facts=facts,
            n_worlds=N_WORLDS_DEFAULT,  # flip to N_WORLDS_TOURNAMENT for production
            return_evidence=True
        )
        
        world_summaries = mc_out.pop("world_summaries", [])
        aggregate = mc_out
        bullets = synthesize_rationale(q["title"], world_summaries, aggregate)
        aggregate["reasoning"] = bullets
        
        # Store results for artifacts
        all_results.append({
            "question_id": qid,
            "question_title": q["title"],
            "forecast": aggregate
        })
        
        all_reasons.append(f"Q{qid}: {q['title']}")
        for b in bullets:
            all_reasons.append(f"  • {b}")
        all_reasons.append("")
        
        success = post_forecast_safe(q, aggregate, publish=publish, skip_set=skip_set)
        if success and publish:
            posted_ids.append(qid)
    
    # Write posted_ids.json in submit mode
    if mode == "submit" and publish:
        with open("posted_ids.json", "w", encoding="utf-8") as f:
            json.dump(posted_ids, f, indent=2)
        print(f"[INFO] Wrote {len(posted_ids)} posted question IDs to posted_ids.json")
    
    # Write artifacts
    with open("mc_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    with open("mc_reasons.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_reasons))
    
    print(f"[TOURNAMENT MODE: {mode}] Complete. Artifacts: mc_results.json, mc_reasons.txt")

# ========== Main CLI ==========
def main():
    parser = argparse.ArgumentParser(description="Metaculus MC Bot")
    parser.add_argument(
        "--mode",
        choices=["test_questions", "tournament_dryrun", "tournament_submit"],
        help="Run mode (deprecated, use specific flags instead)"
    )
    parser.add_argument(
        "--live-test",
        action="store_true",
        help="Run live test on questions 578, 14333, 22427"
    )
    parser.add_argument(
        "--submit-smoke-test",
        type=int,
        metavar="QID",
        help="Submit smoke test for a single question ID"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually submit forecasts (use with --submit-smoke-test)"
    )
    args = parser.parse_args()
    
    # Handle new flags first
    if args.live_test:
        run_live_test()
    elif args.submit_smoke_test is not None:
        run_submit_smoke_test(args.submit_smoke_test, publish=args.publish)
    # Fall back to mode-based dispatch for backwards compatibility
    elif args.mode:
        if args.mode == "test_questions":
            run_test_mode()
        elif args.mode == "tournament_dryrun":
            run_tournament(mode="dryrun", publish=False)
        elif args.mode == "tournament_submit":
            run_tournament(mode="submit", publish=True)
    else:
        parser.error("Must specify either --mode, --live-test, or --submit-smoke-test")

if __name__ == "__main__":
    main()
