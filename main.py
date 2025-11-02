import os
import sys
import json
import argparse
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

# Retry configuration for HTTP requests
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]

# Error detection keys
ERROR_KEY_REQUEST = "_request_error"
ERROR_KEY_PARSE = "_parse_error"

# Type inference constants
FALLBACK_TYPE_FIELDS = ["type", "possibility_type", "prediction_type", "question_type", "value_type", "outcome_type"]
BINARY_TYPE_VARIANTS = ["binary", "bool", "boolean"]
MULTIPLE_CHOICE_TYPE_VARIANTS = ["one_of", "categorical", "multiple_choice", "multiplechoice", "mc"]
NUMERIC_TYPE_VARIANTS = ["continuous", "float", "integer", "number", "numeric", "linear", "log", "date", "discrete"]

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openai/gpt-4o-mini"
METACULUS_TOKEN = os.environ.get("METACULUS_TOKEN", "")
ASKNEWS_CLIENT_ID = os.environ.get("ASKNEWS_CLIENT_ID", "")
ASKNEWS_SECRET = os.environ.get("ASKNEWS_SECRET", "")

# Project-based tournament targeting (AIB Fall 2025)
METACULUS_PROJECT_ID = os.environ.get("METACULUS_PROJECT_ID", "32813")
METACULUS_PROJECT_SLUG = os.environ.get("METACULUS_PROJECT_SLUG", "fall-aib-2025")
METACULUS_CONTEST_SLUG = os.environ.get("METACULUS_CONTEST_SLUG", "fall-aib")

# ========== HTTP Session and Retry ==========
def _build_http_session():
    """
    Build a requests.Session with retry logic for robustness.
    
    Returns:
        requests.Session configured with retry and headers
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_FORCELIST,
        allowed_methods=["GET", "POST", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "metac-bot-template/1.0",
        "Accept": "application/json"
    })
    return session

# ========== Diagnostic Utilities ==========
def _dprint(msg):
    """Print message with immediate flush for GitHub Actions visibility."""
    print(msg, flush=True)

def _write_debug_files(prefix, raw_text, parsed_obj):
    """
    Write debug artifacts: raw response and parsed JSON.
    
    Args:
        prefix: filename prefix (e.g., "debug_q_578_attempt1")
        raw_text: raw response text/body
        parsed_obj: parsed object (dict or other JSON-serializable)
    """
    try:
        # Write raw text
        raw_file = f"{prefix}_raw.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(raw_text)
        _dprint(f"[DEBUG] Wrote {raw_file}")
        
        # Write parsed JSON
        json_file = f"{prefix}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(parsed_obj, f, indent=2)
        _dprint(f"[DEBUG] Wrote {json_file}")
    except Exception as e:
        _dprint(f"[ERROR] Failed to write debug files for {prefix}: {e}")

def _debug_log_fetch(qid, label, resp, raw_text, parsed_obj, request_url, request_params, request_headers):
    """
    Log comprehensive request/response diagnostics.
    
    Args:
        qid: Question ID
        label: Label for this attempt (e.g., "attempt1")
        resp: requests.Response object
        raw_text: raw response body text
        parsed_obj: parsed response dict
        request_url: request URL
        request_params: request params dict
        request_headers: request headers dict
    """
    _dprint(f"\n{'='*80}")
    _dprint(f"[DEBUG] Question {qid} - {label}")
    _dprint(f"{'='*80}")
    
    # Request details
    _dprint(f"[REQUEST]")
    _dprint(f"  URL: {request_url}")
    _dprint(f"  Params: {request_params}")
    # Safe headers allowlist (exclude all auth-related headers)
    safe_header_keys = ["user-agent", "accept", "accept-encoding", "content-type", "connection"]
    safe_headers = {k: v for k, v in request_headers.items() if k.lower() in safe_header_keys}
    _dprint(f"  Headers: {safe_headers}")
    
    # Response details
    _dprint(f"[RESPONSE]")
    _dprint(f"  Final URL: {resp.url}")
    _dprint(f"  Status: {resp.status_code} {resp.reason}")
    _dprint(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
    _dprint(f"  Content-Length: {resp.headers.get('content-length', 'N/A')}")
    _dprint(f"  Encoding: {resp.encoding}")
    _dprint(f"  Redirects: {len(resp.history)} redirect(s)")
    
    # Body snippet (first 2KB)
    _dprint(f"[BODY SNIPPET] First 2KB:")
    snippet = raw_text[:2048]
    _dprint(snippet)
    if len(raw_text) > 2048:
        _dprint(f"... ({len(raw_text) - 2048} more bytes)")
    
    # Parsed object keys
    _dprint(f"[PARSED OBJECT]")
    if isinstance(parsed_obj, dict):
        _dprint(f"  Top-level keys: {list(parsed_obj.keys())}")
        
        # Check possibility/possibilities fields
        possibility = parsed_obj.get("possibility")
        possibilities = parsed_obj.get("possibilities")
        
        if possibility:
            _dprint(f"  'possibility' present: type={type(possibility).__name__}")
            if isinstance(possibility, dict):
                _dprint(f"    possibility keys: {list(possibility.keys())}")
                poss_type = possibility.get("type")
                if poss_type:
                    _dprint(f"    possibility.type: {repr(poss_type)}")
        else:
            _dprint(f"  'possibility' absent")
        
        if possibilities:
            _dprint(f"  'possibilities' present: type={type(possibilities).__name__}")
            if isinstance(possibilities, dict):
                _dprint(f"    possibilities keys: {list(possibilities.keys())}")
                poss_type = possibilities.get("type")
                if poss_type:
                    _dprint(f"    possibilities.type: {repr(poss_type)}")
        else:
            _dprint(f"  'possibilities' absent")
        
        # Check fallback type fields
        fallback_fields = ["type", "possibility_type", "prediction_type", "question_type", "value_type", "outcome_type"]
        _dprint(f"  Fallback type fields:")
        for field in fallback_fields:
            val = parsed_obj.get(field)
            if val is not None:
                _dprint(f"    {field}: {repr(val)}")
    else:
        _dprint(f"  Parsed object is not a dict: {type(parsed_obj).__name__}")
    
    _dprint(f"{'='*80}\n")

# ========== Robust Per-ID Hydration ==========
def _request_with_logging(sess, url, params, qid, label):
    """
    Perform GET request with comprehensive logging and artifact writing.
    
    Args:
        sess: requests.Session
        url: request URL
        params: query parameters dict
        qid: Question ID
        label: Label for this attempt (e.g., "attempt1")
    
    Returns:
        dict: Parsed response or minimal parse-error dict
    """
    try:
        resp = sess.get(url, params=params, timeout=20)
        resp.raise_for_status()
        raw_text = resp.text
        
        # Try to parse JSON
        try:
            parsed_obj = resp.json()
        except Exception as parse_err:
            _dprint(f"[ERROR] Failed to parse JSON for Q{qid} {label}: {parse_err}")
            parsed_obj = {ERROR_KEY_PARSE: str(parse_err), "_raw_snippet": raw_text[:500]}
        
        # Log comprehensive diagnostics
        _debug_log_fetch(qid, label, resp, raw_text, parsed_obj, url, params, sess.headers)
        
        # Write debug files
        prefix = f"debug_q_{qid}_{label}"
        _write_debug_files(prefix, raw_text, parsed_obj)
        
        return parsed_obj
        
    except requests.exceptions.RequestException as e:
        _dprint(f"[ERROR] Request failed for Q{qid} {label}: {e}")
        error_dict = {ERROR_KEY_REQUEST: str(e), "id": qid}
        
        # Try to get response details if available
        if hasattr(e, "response") and e.response is not None:
            try:
                raw_text = e.response.text
                error_dict["_status_code"] = e.response.status_code
                error_dict["_raw_snippet"] = raw_text[:500]
                
                # Still log what we have
                _debug_log_fetch(qid, label, e.response, raw_text, error_dict, url, params, sess.headers)
                
                # Write debug files even for errors
                prefix = f"debug_q_{qid}_{label}"
                _write_debug_files(prefix, raw_text, error_dict)
            except Exception:
                pass
        
        return error_dict

def _hydrate_single_question(sess, qid):
    """
    Hydrate a single question with multiple API variant attempts.
    
    Tries four URL/param variants in order and merges fields into one object.
    
    Args:
        sess: requests.Session
        qid: Question ID
    
    Returns:
        dict: Merged question data with best available fields
    """
    _dprint(f"\n[HYDRATE] Starting multi-attempt hydration for Q{qid}")
    
    base_url = METACULUS_API_BASE
    
    # Define four attempts with different URL/param combinations
    attempts = [
        {
            "url": f"{base_url}{qid}/",
            "params": {
                "expand": "possibility",
                "fields": "id,title,description,type,possibility,options"
            },
            "label": "attempt1_expand_fields"
        },
        {
            "url": f"{base_url}{qid}/",
            "params": {},
            "label": "attempt2_plain_slash"
        },
        {
            "url": f"{base_url}{qid}",
            "params": {
                "expand": "possibility",
                "fields": "id,title,description,type,possibility,options"
            },
            "label": "attempt3_expand_fields_no_slash"
        },
        {
            "url": f"{base_url}{qid}",
            "params": {},
            "label": "attempt4_plain_no_slash"
        }
    ]
    
    # Collect results from all attempts
    results = []
    for attempt in attempts:
        _dprint(f"[HYDRATE] Q{qid} - {attempt['label']}: {attempt['url']} {attempt['params']}")
        result = _request_with_logging(sess, attempt["url"], attempt["params"], qid, attempt["label"])
        results.append(result)
    
    # Merge results: start with empty dict and overlay fields from each attempt
    merged = {"id": qid}
    
    for i, result in enumerate(results):
        if isinstance(result, dict) and not result.get(ERROR_KEY_REQUEST) and not result.get(ERROR_KEY_PARSE):
            # Valid result, merge fields
            for key, value in result.items():
                if key not in merged or merged.get(key) is None or (key == "possibility" and value):
                    merged[key] = value
    
    # Log merged keys
    _dprint(f"[HYDRATE] Q{qid} - Merged keys: {list(merged.keys())}")
    
    # Check for possibility in merged
    if "possibility" in merged:
        poss = merged["possibility"]
        if isinstance(poss, dict):
            _dprint(f"[HYDRATE] Q{qid} - Merged possibility keys: {list(poss.keys())}")
            if "type" in poss:
                _dprint(f"[HYDRATE] Q{qid} - Merged possibility.type: {repr(poss['type'])}")
    
    # Write final merged result
    prefix = f"debug_q_{qid}_final"
    merged_json = json.dumps(merged, indent=2)
    _write_debug_files(prefix, merged_json, merged)
    
    _dprint(f"[HYDRATE] Completed multi-attempt hydration for Q{qid}\n")
    
    return merged

# ========== Tournament Question Fetcher ==========
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
    Inspects q.get("possibility"), q.get("possibilities"), and falls back to legacy keys.
    
    Args:
        q: Question dict from Metaculus API2
    
    Returns:
        Tuple (qtype, extra) where:
        - qtype: str in {"binary", "numeric", "multiple_choice", "unknown"}
        - extra: dict with optional keys:
            - "options": list[str] for multiple_choice
            - "numeric_bounds": dict with min, max, unit, scale for numeric
    """
    extra = {}
    
    # Check multiple sources for type in priority order
    possibility = q.get("possibility", {})
    possibilities = q.get("possibilities", {})
    
    # Try to get type from various sources
    poss_type = ""
    candidates_tried = []
    
    # Priority 1: possibility.type
    if possibility and isinstance(possibility, dict):
        poss_type = possibility.get("type", "").lower()
        if poss_type:
            candidates_tried.append(f"possibility.type={repr(poss_type)}")
    
    # Priority 2: possibilities.type
    if not poss_type and possibilities and isinstance(possibilities, dict):
        poss_type = possibilities.get("type", "").lower()
        if poss_type:
            candidates_tried.append(f"possibilities.type={repr(poss_type)}")
    
    # Priority 3: top-level type
    if not poss_type:
        poss_type = q.get("type", "").lower()
        if poss_type:
            candidates_tried.append(f"type={repr(poss_type)}")
    
    # Priority 4+: legacy/fallback fields
    for field in FALLBACK_TYPE_FIELDS[1:]:  # Skip "type" as we already checked it
        if not poss_type:
            poss_type = q.get(field, "").lower()
            if poss_type:
                candidates_tried.append(f"{field}={repr(poss_type)}")
    
    # Normalize possibility.type values to canonical types
    # Binary types
    if poss_type in BINARY_TYPE_VARIANTS:
        qtype = "binary"
    # Multiple choice types
    elif poss_type in MULTIPLE_CHOICE_TYPE_VARIANTS:
        qtype = "multiple_choice"
        
        # Extract options from possibility or possibilities
        options_data = []
        if possibility and isinstance(possibility, dict):
            options_data = possibility.get("options", [])
        if not options_data and possibilities and isinstance(possibilities, dict):
            options_data = possibilities.get("options", [])
        if not options_data:
            options_data = q.get("options", [])
        
        options = []
        for i, opt in enumerate(options_data):
            if isinstance(opt, dict):
                # Try keys: name, label, title
                name = opt.get("name") or opt.get("label") or opt.get("title") or f"opt_{i}"
                options.append(name)
            elif isinstance(opt, str):
                options.append(opt)
            else:
                options.append(f"opt_{i}")
        extra["options"] = options
        
    # Numeric types (extended variants)
    elif poss_type in NUMERIC_TYPE_VARIANTS:
        qtype = "numeric"
        
        # Extract numeric bounds - try multiple field names from both possibility and possibilities
        numeric_bounds = {}
        
        # Try possibility first
        if possibility and isinstance(possibility, dict):
            # Try possibility.range
            if "range" in possibility and isinstance(possibility["range"], (list, tuple)) and len(possibility["range"]) >= 2:
                numeric_bounds["min"] = possibility["range"][0]
                numeric_bounds["max"] = possibility["range"][1]
            # Try possibility.bounds
            elif "bounds" in possibility and isinstance(possibility["bounds"], (list, tuple)) and len(possibility["bounds"]) >= 2:
                numeric_bounds["min"] = possibility["bounds"][0]
                numeric_bounds["max"] = possibility["bounds"][1]
            # Try direct min/max in possibility
            else:
                if "min" in possibility:
                    numeric_bounds["min"] = possibility["min"]
                if "max" in possibility:
                    numeric_bounds["max"] = possibility["max"]
            
            # Extract unit and scale from possibility
            if "unit" in possibility:
                numeric_bounds["unit"] = possibility["unit"]
            if "scale" in possibility:
                numeric_bounds["scale"] = possibility["scale"]
        
        # Try possibilities if no bounds found yet
        if not numeric_bounds and possibilities and isinstance(possibilities, dict):
            # Try possibilities.range
            if "range" in possibilities and isinstance(possibilities["range"], (list, tuple)) and len(possibilities["range"]) >= 2:
                numeric_bounds["min"] = possibilities["range"][0]
                numeric_bounds["max"] = possibilities["range"][1]
            # Try possibilities.bounds
            elif "bounds" in possibilities and isinstance(possibilities["bounds"], (list, tuple)) and len(possibilities["bounds"]) >= 2:
                numeric_bounds["min"] = possibilities["bounds"][0]
                numeric_bounds["max"] = possibilities["bounds"][1]
        
        # Fallback to legacy keys at top level
        if not numeric_bounds:
            if "numerical_range" in q and isinstance(q["numerical_range"], (list, tuple)) and len(q["numerical_range"]) >= 2:
                numeric_bounds["min"] = q["numerical_range"][0]
                numeric_bounds["max"] = q["numerical_range"][1]
            elif "range_min" in q and "range_max" in q:
                numeric_bounds["min"] = q["range_min"]
                numeric_bounds["max"] = q["range_max"]
        
        if numeric_bounds:
            extra["numeric_bounds"] = numeric_bounds
    else:
        # Unknown type - log what we tried
        qtype = "unknown"
        _dprint(f"[WARN] Could not infer question type. Candidates tried: {candidates_tried}")
        
        # Log keys present in possibility/possibilities for debugging
        if possibility and isinstance(possibility, dict):
            _dprint(f"  possibility keys: {list(possibility.keys())}")
        if possibilities and isinstance(possibilities, dict):
            _dprint(f"  possibilities keys: {list(possibilities.keys())}")
    
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
        
        # Identify questions missing 'possibility' field and hydrate them
        questions_to_hydrate = []
        for q in raw_questions:
            if not q.get("possibility"):
                questions_to_hydrate.append(q.get("id"))
        
        if questions_to_hydrate:
            print(f"[INFO] Hydrating possibility for {len(questions_to_hydrate)} questions (per-ID fetch)...")
            for qid in questions_to_hydrate:
                try:
                    hydrate_url = f"{METACULUS_API_BASE}{qid}/?expand=possibility"
                    hydrate_resp = requests.get(hydrate_url, timeout=15)
                    hydrate_resp.raise_for_status()
                    hydrated_data = hydrate_resp.json()
                    
                    # Find the question in raw_questions and update its possibility field
                    for q in raw_questions:
                        if q.get("id") == qid:
                            q["possibility"] = hydrated_data.get("possibility", {})
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
                poss = q.get("possibility", {})
                poss_type = poss.get("type", "") if poss else ""
                raw_type = q.get("type", "")
                type_source = poss_type if poss_type else (raw_type if raw_type else "unknown")
                print(f"[SKIP] Unsupported question type for Q{qid}: '{type_source}'")
                skipped_count += 1
                continue
            
            # Extract title and description
            title = q.get("title") or q.get("name", "")
            description = q.get("description", "")
            
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
def _hydrate_possibility(qid, timeout=20):
    """
    Fetch a single question from Metaculus API with possibility field.
    
    Args:
        qid: Question ID
        timeout: Request timeout in seconds
    
    Returns:
        Question dict or None on failure
    """
    try:
        url = f"{METACULUS_API_BASE}{qid}/?expand=possibility"
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch question {qid}: {e}")
        return None

def run_live_test():
    """
    Live test on three long-lived Metaculus questions (578, 14333, 22427).
    Uses multi-attempt hydration with comprehensive diagnostics and artifact writing.
    """
    _dprint("[LIVE TEST] Starting with comprehensive diagnostics...")
    
    # Test question IDs
    test_qids = [578, 14333, 22427]  # binary, numeric, multiple_choice
    
    # Build HTTP session with retry logic
    sess = _build_http_session()
    _dprint(f"[LIVE TEST] Built HTTP session with retry logic")
    
    # Hydrate questions with multi-attempt strategy
    raw_questions = []
    for qid in test_qids:
        _dprint(f"\n[LIVE TEST] Hydrating question {qid}...")
        merged_q = _hydrate_single_question(sess, qid)
        raw_questions.append(merged_q)
    
    if not raw_questions:
        _dprint("[ERROR] No questions hydrated. Aborting live test.")
        return
    
    _dprint(f"\n[LIVE TEST] Successfully hydrated {len(raw_questions)} questions")
    
    # Normalize questions with broadened type inference
    questions = []
    for q in raw_questions:
        qid = q.get("id")
        if not qid:
            _dprint(f"[WARN] Skipping question without ID")
            continue
        
        _dprint(f"\n[NORMALIZE] Q{qid} - Starting normalization")
        _dprint(f"[NORMALIZE] Q{qid} - Merged keys: {list(q.keys())}")
        
        # Log presence of fallback type fields
        _dprint(f"[NORMALIZE] Q{qid} - Fallback type fields present:")
        for field in FALLBACK_TYPE_FIELDS:
            val = q.get(field)
            if val is not None:
                _dprint(f"  {field}: {repr(val)}")
        
        # Infer type with broadened logic
        qtype, extra = _infer_qtype_and_fields(q)
        
        if qtype == "unknown":
            _dprint(f"[SKIP] Q{qid} - Unknown type after broadened inference")
            _dprint(f"[SKIP] Q{qid} - This question will be skipped but debug artifacts are available")
            continue
        
        _dprint(f"[NORMALIZE] Q{qid} - Inferred type: {qtype}")
        _dprint(f"[NORMALIZE] Q{qid} - Extra fields: {extra}")
        
        title = q.get("title") or q.get("name", "")
        description = q.get("description", "")
        
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
            _dprint(f"[NORMALIZE] Q{qid} - Multiple choice with {len(options)} options")
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
            _dprint(f"[NORMALIZE] Q{qid} - Numeric bounds: {numeric_bounds}")
        
        questions.append(normalized)
        _dprint(f"[NORMALIZE] Q{qid} - Successfully normalized\n")
    
    if not questions:
        _dprint("\n[ERROR] Zero questions normalized successfully!")
        _dprint("[ERROR] Please review debug artifacts:")
        _dprint("  - debug_q_*_attempt*_raw.txt (raw API responses)")
        _dprint("  - debug_q_*_attempt*.json (parsed JSON)")
        _dprint("  - debug_q_*_final.json (merged results)")
        return
    
    _dprint(f"\n[LIVE TEST] Successfully normalized {len(questions)} questions. Proceeding with pipeline...")
    
    # Fetch AskNews facts
    qid_to_text = {q["id"]: q["title"] + " " + q.get("description", "") for q in questions}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    
    # Run pipeline
    all_results = []
    all_reasons = []
    
    for q in questions:
        qid = q["id"]
        facts = news.get(qid, [])
        
        _dprint(f"\n[PIPELINE] Processing Q{qid}: {q['title']}")
        _dprint(f"  Type: {q['type']}")
        _dprint(f"  AskNews facts: {len(facts)}")
        
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
    
    # Write artifacts
    with open("mc_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    _dprint("[LIVE TEST] Wrote mc_results.json")
    
    with open("mc_reasons.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_reasons))
    _dprint("[LIVE TEST] Wrote mc_reasons.txt")
    
    _dprint("\n[LIVE TEST] Complete!")
    _dprint(f"  Processed: {len(questions)} questions")
    _dprint(f"  Artifacts: mc_results.json, mc_reasons.txt")
    _dprint(f"  Debug files: debug_q_*_*.txt, debug_q_*.json")

def run_submit_smoke_test(test_qid, publish=False):
    """
    Submit smoke test for a single question ID.
    
    Args:
        test_qid: Metaculus question ID to test (int)
        publish: If True, actually submit forecast; otherwise just dry-run
    """
    _dprint(f"[SUBMIT SMOKE TEST] Starting for Q{test_qid} (publish={publish})...")
    
    # Create session and fetch question with multi-attempt hydration
    _dprint(f"[INFO] Fetching question {test_qid}...")
    sess = _build_http_session()
    q = _hydrate_single_question(sess, test_qid)
    
    if not q or not q.get("id"):
        _dprint(f"[ERROR] Could not fetch question {test_qid}. Aborting.")
        return
    
    # Normalize question
    qid = q.get("id")
    qtype, extra = _infer_qtype_and_fields(q)
    
    if qtype == "unknown":
        _dprint(f"[ERROR] Unknown question type for Q{qid}. Aborting.")
        return
    
    _dprint(f"[INFO] Q{qid} inferred type: {qtype}")
    
    title = q.get("title") or q.get("name", "")
    description = q.get("description", "")
    
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
    
    _dprint(f"[INFO] Processing Q{qid}: {title}")
    _dprint(f"  Type: {qtype}")
    _dprint(f"  AskNews facts: {len(facts)}")
    
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
        _dprint(f"[INFO] Attempting to submit forecast for Q{qid}...")
        success = post_forecast_safe(normalized, aggregate, publish=True)
        
        if success:
            _dprint(f"[SUCCESS] Posted forecast for Q{qid}")
            with open("posted_ids.json", "w", encoding="utf-8") as f:
                json.dump([qid], f, indent=2)
            _dprint("[INFO] Wrote posted_ids.json")
        else:
            _dprint(f"[ERROR] Failed to post forecast for Q{qid}")
    else:
        _dprint(f"[DRYRUN] Would post forecast for Q{qid}")
    
    _dprint(f"[SUBMIT SMOKE TEST] Complete. Artifacts: mc_results.json, mc_reasons.txt" + 
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
        required=True,
        help="Run mode"
    )
    args = parser.parse_args()
    
    if args.mode == "test_questions":
        run_test_mode()
    elif args.mode == "tournament_dryrun":
        run_tournament(mode="dryrun", publish=False)
    elif args.mode == "tournament_submit":
        run_tournament(mode="submit", publish=True)

if __name__ == "__main__":
    main()
