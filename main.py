import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import requests

# Local modules
from mc_worlds import run_mc_worlds, WORLD_PROMPT
from adapters import mc_results_to_metaculus_payload, submit_forecast

# ========== Constants ==========
N_WORLDS_DEFAULT = 30  # for tests
N_WORLDS_TOURNAMENT = 100  # flip to this for production
ASKNEWS_MAX_PER_Q = 8
NEWS_CACHE_TTL_HOURS = 12
CACHE_DIR = Path("cache")
NEWS_CACHE_FILE = CACHE_DIR / "news_cache.json"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openai/gpt-4o-mini"
METACULUS_TOKEN = os.environ.get("METACULUS_TOKEN", "")
ASKNEWS_CLIENT_ID = os.environ.get("ASKNEWS_CLIENT_ID", "")
ASKNEWS_SECRET = os.environ.get("ASKNEWS_SECRET", "")

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
        for qid, text in to_fetch.items():
            facts = _fetch_asknews_single(text, max_per_q)
            results[qid] = facts
            cache[str(qid)] = {
                "timestamp": datetime.utcnow().isoformat(),
                "facts": facts
            }
        _save_news_cache(cache)
    elif to_fetch:
        print("[WARN] AskNews credentials missing; using fallback for uncached questions")
        for qid in to_fetch:
            results[qid] = ["No recent news available; base rates apply."]
    
    return results

def _get_asknews_token():
    """
    Acquire an OAuth token from AskNews using client credentials.
    Returns access_token string or None on failure.
    """
    if not ASKNEWS_CLIENT_ID or not ASKNEWS_SECRET:
        print("[WARN] ASKNEWS_CLIENT_ID/ASKNEWS_SECRET not set")
        return None
    try:
        token_url = "https://auth.asknews.app/oauth2/token"
        data = {
            "client_id": ASKNEWS_CLIENT_ID,
            "client_secret": ASKNEWS_SECRET,
            "grant_type": "client_credentials",
            "scope": "news"
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        resp = requests.post(token_url, data=data, headers=headers, timeout=10)
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

def _fetch_asknews_single(question_text, max_facts=ASKNEWS_MAX_PER_Q):
    """Fetch facts from AskNews for a single question; return list of formatted strings."""
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
    
    valid, err = validate_mc_result(question_obj, mc_result)
    if not valid:
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
    """
    print(f"[TOURNAMENT MODE: {mode}] Starting...")
    
    # TODO: fetch questions from Metaculus tournament API
    # For now, placeholder
    questions = []  # replace with real fetch
    
    if not questions:
        print("[ERROR] No questions fetched. Check Metaculus API integration.")
        return
    
    qid_to_text = {q["id"]: q["title"] + " " + q.get("description", "") for q in questions}
    news = fetch_facts_for_batch(qid_to_text, max_per_q=ASKNEWS_MAX_PER_Q)
    
    skip_set = set()  # dedupe already-forecasted
    
    for q in questions:
        qid = q["id"]
        facts = news.get(qid, [])
        
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
        
        post_forecast_safe(q, aggregate, publish=publish, skip_set=skip_set)
    
    print(f"[TOURNAMENT MODE: {mode}] Complete.")

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