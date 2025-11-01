import argparse
import asyncio
import logging
import os, json
from datetime import date, datetime, timezone, timedelta
from typing import Literal, List, Dict

from forecasting_tools import (
    AskNewsSearcher,
    BinaryQuestion,
    ForecastBot,
    GeneralLlm,
    MetaculusApi,
    MetaculusQuestion,
    MultipleChoiceQuestion,
    NumericDistribution,
    NumericQuestion,
    Percentile,
    BinaryPrediction,
    PredictedOptionList,
    ReasonedPrediction,
    SmartSearcher,
    clean_indents,
    structure_output,
)

logger = logging.getLogger(__name__)

# --- AskNews cache (tiny JSON file, 12h TTL) ---
NEWS_CACHE_PATH = "cache/news_cache.json"
NEWS_TTL_HOURS = 12
pathlib.Path("cache").mkdir(exist_ok=True, parents=True)

def _load_news_cache() -> dict:
    try:
        import json, io
        with io.open(NEWS_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_news_cache(cache: dict) -> None:
    import json, io
    with io.open(NEWS_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def _now_ts() -> float:
    return time.time()

def _fresh(entry: dict) -> bool:
    if not entry or "ts" not in entry: 
        return False
    age_h = (_now_ts() - float(entry["ts"])) / 3600.0
    return age_h < NEWS_TTL_HOURS

def fetch_facts_for_batch(qid_to_text: dict, max_per_q: int = 8) -> dict:
    """
    Returns {qid: [ 'YYYY-MM-DD: headline (url)', ... ]}.
    Uses AskNews if available; caches to cache/news_cache.json; 12h TTL.
    Falls back to a single base-rate note if nothing found.
    """
    cache = _load_news_cache()
    out = {}
    # Try to construct AskNewsSearcher if creds exist
    searcher = None
    try:
        cid = os.environ.get("ASKNEWS_CLIENT_ID")
        sec = os.environ.get("ASKNEWS_SECRET")
        if cid and sec:
            from forecasting_tools import AskNewsSearcher
            searcher = AskNewsSearcher(client_id=cid, client_secret=sec)
    except Exception as e:
        print(f"[NEWS][WARN] Could not init AskNewsSearcher: {e}")

    for qid, qtext in qid_to_text.items():
        if _fresh(cache.get(qid)):
            out[qid] = cache[qid]["facts"][:max_per_q]
            continue

        facts = []
        if searcher:
            try:
                # Be defensive about method name differences across template versions
                results = None
                for meth in ("search_news", "search", "news"):
                    if hasattr(searcher, meth):
                        fn = getattr(searcher, meth)
                        # Prefer very recent first; keep calls cheap
                        results = fn(qtext, hours_back=48, max_results=12)
                        break
                # Normalize a few common shapes
                for r in (results or []):
                    date_iso = (r.get("published_at") or r.get("published") or r.get("date") or
                                datetime.now(timezone.utc).date().isoformat())
                    title = r.get("title") or r.get("headline") or (r.get("summary") or "").split(".")[0]
                    url = r.get("url") or r.get("link")
                    if title:
                        facts.append(f"{date_iso[:10]}: {title}" + (f" ({url})" if url else ""))
            except Exception as e:
                print(f"[NEWS][WARN] qid={qid}: {e}")

        if not facts:
            # Only if truly nothing found (or AskNews not available)
            facts = [f"{datetime.utcnow().date().isoformat()}: no recent news extracted; use question text and base rates"]

        cache[qid] = {"ts": _now_ts(), "facts": facts}
        out[qid] = facts[:max_per_q]

    _save_news_cache(cache)
    return out

# main.py (excerpt)
from mc_worlds import run_mc_worlds

class FallTemplateBot2025(ForecastBot):
    """
    This is a copy of the template bot for Fall 2025 Metaculus AI Tournament.
    """

    _max_concurrent_questions = (
        1  # Set this to whatever works for your search-provider/ai-model rate limits
    )
    _concurrency_limiter = asyncio.Semaphore(_max_concurrent_questions)

    async def run_research(self, question: MetaculusQuestion) -> str:
        async with self._concurrency_limiter:
            research = ""
            researcher = self.get_llm("researcher")

            prompt = clean_indents(
                f"""
                You are an assistant to a superforecaster.
                The superforecaster will give you a question they intend to forecast on.
                To be a great assistant, you generate a concise but detailed rundown of the most relevant news, including if the question would resolve Yes or No based on current information.
                You do not produce forecasts yourself.

                Question:
                {question.question_text}

                This question's outcome will be determined by the specific criteria below:
                {question.resolution_criteria}

                {question.fine_print}
                """
            )

            if isinstance(researcher, GeneralLlm):
                research = await researcher.invoke(prompt)
            elif researcher == "asknews/news-summaries":
                research = await AskNewsSearcher().get_formatted_news_async(
                    question.question_text
                )
            elif researcher == "asknews/deep-research/medium-depth":
                research = await AskNewsSearcher().get_formatted_deep_research(
                    question.question_text,
                    sources=["asknews", "google"],
                    search_depth=2,
                    max_depth=4,
                )
            elif researcher == "asknews/deep-research/high-depth":
                research = await AskNewsSearcher().get_formatted_deep_research(
                    question.question_text,
                    sources=["asknews", "google"],
                    search_depth=4,
                    max_depth=6,
                )
            elif researcher.startswith("smart-searcher"):
                model_name = researcher.removeprefix("smart-searcher/")
                searcher = SmartSearcher(
                    model=model_name,
                    temperature=0,
                    num_searches_to_run=2,
                    num_sites_per_search=10,
                    use_advanced_filters=False,
                )
                research = await searcher.invoke(prompt)
            elif not researcher or researcher == "None":
                research = ""
            else:
                research = await self.get_llm("researcher", "llm").invoke(prompt)
            logger.info(f"Found Research for URL {question.page_url}:\n{research}")
            return research

    async def _run_forecast_on_binary(
        self, question: BinaryQuestion, research: str
    ) -> ReasonedPrediction[float]:
        prompt = clean_indents(
            f"""
            You are a professional forecaster interviewing for a job.

            Your interview question is:
            {question.question_text}

            Question background:
            {question.background_info}


            This question's outcome will be determined by the specific criteria below. These criteria have not yet been satisfied:
            {question.resolution_criteria}

            {question.fine_print}


            Your research assistant says:
            {research}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            Before answering you write:
            (a) The time left until the outcome to the question is known.
            (b) The status quo outcome if nothing changed.
            (c) A brief description of a scenario that results in a No outcome.
            (d) A brief description of a scenario that results in a Yes outcome.

            You write your rationale remembering that good forecasters put extra weight on the status quo outcome since the world changes slowly most of the time.

            The last thing you write is your final answer as: "Probability: ZZ%", 0-100
            """
        )
        reasoning = await self.get_llm("default", "llm").invoke(prompt)
        logger.info(f"Reasoning for URL {question.page_url}: {reasoning}")
        binary_prediction: BinaryPrediction = await structure_output(
            reasoning, BinaryPrediction, model=self.get_llm("parser", "llm")
        )
        decimal_pred = max(0.01, min(0.99, binary_prediction.prediction_in_decimal))

        logger.info(
            f"Forecasted URL {question.page_url} with prediction: {decimal_pred}"
        )
        return ReasonedPrediction(prediction_value=decimal_pred, reasoning=reasoning)

    async def _run_forecast_on_multiple_choice(
        self, question: MultipleChoiceQuestion, research: str
    ) -> ReasonedPrediction[PredictedOptionList]:
        prompt = clean_indents(
            f"""
            You are a professional forecaster interviewing for a job.

            Your interview question is:
            {question.question_text}

            The options are: {question.options}


            Background:
            {question.background_info}

            {question.resolution_criteria}

            {question.fine_print}


            Your research assistant says:
            {research}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            Before answering you write:
            (a) The time left until the outcome to the question is known.
            (b) The status quo outcome if nothing changed.
            (c) A description of an scenario that results in an unexpected outcome.

            You write your rationale remembering that (1) good forecasters put extra weight on the status quo outcome since the world changes slowly most of the time, and (2) good forecasters leave some moderate probability on most options to account for unexpected outcomes.

            The last thing you write is your final probabilities for the N options in this order {question.options} as:
            Option_A: Probability_A
            Option_B: Probability_B
            ...
            Option_N: Probability_N
            """
        )
        parsing_instructions = clean_indents(
            f"""
            Make sure that all option names are one of the following:
            {question.options}
            The text you are parsing may prepend these options with some variation of "Option" which you should remove if not part of the option names I just gave you.
            """
        )
        reasoning = await self.get_llm("default", "llm").invoke(prompt)
        logger.info(f"Reasoning for URL {question.page_url}: {reasoning}")
        predicted_option_list: PredictedOptionList = await structure_output(
            text_to_structure=reasoning,
            output_type=PredictedOptionList,
            model=self.get_llm("parser", "llm"),
            additional_instructions=parsing_instructions,
        )
        logger.info(
            f"Forecasted URL {question.page_url} with prediction: {predicted_option_list}"
        )
        return ReasonedPrediction(
            prediction_value=predicted_option_list, reasoning=reasoning
        )

    async def _run_forecast_on_numeric(
        self, question: NumericQuestion, research: str
    ) -> ReasonedPrediction[NumericDistribution]:
        upper_bound_message, lower_bound_message = (
            self._create_upper_and_lower_bound_messages(question)
        )
        prompt = clean_indents(
            f"""
            You are a professional forecaster interviewing for a job.

            Your interview question is:
            {question.question_text}

            Background:
            {question.background_info}

            {question.resolution_criteria}

            {question.fine_print}

            Units for answer: {question.unit_of_measure if question.unit_of_measure else "Not stated (please infer this)"}

            Your research assistant says:
            {research}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            {lower_bound_message}
            {upper_bound_message}

            Formatting Instructions:
            - Please notice the units requested (e.g. whether you represent a number as 1,000,000 or 1 million).
            - Never use scientific notation.
            - Always start with a smaller number (more negative if negative) and then increase from there

            Before answering you write:
            (a) The time left until the outcome to the question is known.
            (b) The outcome if nothing changed.
            (c) The outcome if the current trend continued.
            (d) The expectations of experts and markets.
            (e) A brief description of an unexpected scenario that results in a low outcome.
            (f) A brief description of an unexpected scenario that results in a high outcome.

            You remind yourself that good forecasters are humble and set wide 90/10 confidence intervals to account for unknown unknowns.

            The last thing you write is your final answer as:
            "
            Percentile 10: XX
            Percentile 20: XX
            Percentile 40: XX
            Percentile 60: XX
            Percentile 80: XX
            Percentile 90: XX
            "
            """
        )
        reasoning = await self.get_llm("default", "llm").invoke(prompt)
        logger.info(f"Reasoning for URL {question.page_url}: {reasoning}")
        percentile_list: list[Percentile] = await structure_output(
            reasoning, list[Percentile], model=self.get_llm("parser", "llm")
        )
        prediction = NumericDistribution.from_question(percentile_list, question)
        logger.info(
            f"Forecasted URL {question.page_url} with prediction: {prediction.declared_percentiles}"
        )
        return ReasonedPrediction(prediction_value=prediction, reasoning=reasoning)

    def _create_upper_and_lower_bound_messages(
        self, question: NumericQuestion
    ) -> tuple[str, str]:
        if question.nominal_upper_bound is not None:
            upper_bound_number = question.nominal_upper_bound
        else:
            upper_bound_number = question.upper_bound
        if question.nominal_lower_bound is not None:
            lower_bound_number = question.nominal_lower_bound
        else:
            lower_bound_number = question.lower_bound

        if question.open_upper_bound:
            upper_bound_message = f"The question creator thinks the number is likely not higher than {upper_bound_number}."
        else:
            upper_bound_message = (
                f"The outcome can not be higher than {upper_bound_number}."
            )

        if question.open_lower_bound:
            lower_bound_message = f"The question creator thinks the number is likely not lower than {lower_bound_number}."
        else:
            lower_bound_message = (
                f"The outcome can not be lower than {lower_bound_number}."
            )
        return upper_bound_message, lower_bound_message

# ---- AskNews -> dated bullets for MC sampler ----
    async def _asknews_bullets_async(qid_to_text: Dict[str, str]) -> Dict[str, List[str]]:
        """
        For each qid, fetch a compact 'latest' news summary and convert it into
        dated bullet strings the MC prompt expects. Returns: {qid: [YYYY-MM-DD: fact, ...]}
        """
        searcher = AskNewsSearcher()
        out: Dict[str, List[str]] = {}
        from datetime import date
        today = date.today().isoformat()

    async def _one(qid: str, question_text: str) -> None:
        # You can swap between news summaries (fast) and deep research (heavier)
        # 1) fast:
        text = await searcher.get_formatted_news_async(question_text)
        # 2) deeper (comment the fast one and uncomment this if you want more detail):
        # text = await searcher.get_formatted_deep_research(
        #     question_text, sources=["asknews", "google"], search_depth=2, max_depth=4
        # )
        # Convert any lines into short dated facts. Keep the first ~5.
        bullets = []
        for raw in (text or "").splitlines():
            s = raw.strip(" -•\t").strip()
            if not s:
                continue
            # make each a dated compact fact. We don't rely on AskNews having dates inline.
            bullets.append(f"{today}: {s}")
            if len(bullets) == 5:
                break
        # fallback if AskNews returned nothing useful
        if not bullets:
            bullets = [f"{today}: no notable updates; use question text and base rates"]
        out[qid] = bullets

    await asyncio.gather(*[_one(qid, qtxt) for qid, qtxt in qid_to_text.items()])
    return out

# ---------- AskNews cache (lightweight) ----------
    ASKNEWS_CACHE_PATH = ".cache/asknews.json"
    
    def _load_asknews_cache() -> Dict[str, dict]:
        try:
            os.makedirs(os.path.dirname(ASKNEWS_CACHE_PATH), exist_ok=True)
            if os.path.exists(ASKNEWS_CACHE_PATH):
                with open(ASKNEWS_CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_asknews_cache(cache: Dict[str, dict]) -> None:
        try:
            os.makedirs(os.path.dirname(ASKNEWS_CACHE_PATH), exist_ok=True)
            with open(ASKNEWS_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    async def asknews_bullets_cached(
        qid_to_text: Dict[str, str],
        stale_days: int = 3,
        max_bullets: int = 5,
        force_refresh: bool = False,
    ) -> Dict[str, List[str]]:
        """
        Returns {qid: [YYYY-MM-DD: fact, ...]} using AskNews only when (a) missing or (b) stale.
        """
        cache = _load_asknews_cache()
        need_fetch: Dict[str, str] = {}
        out: Dict[str, List[str]] = {}
        today = date.today()
        cutoff = today - timedelta(days=stale_days)
    
        for qid, qtxt in qid_to_text.items():
            item = cache.get(qid)
            if not force_refresh and item:
                try:
                    fetched = date.fromisoformat(item["fetched_at"])
                except Exception:
                    fetched = cutoff - timedelta(days=1)
                if fetched >= cutoff and item.get("bullets"):
                    out[qid] = item["bullets"][:max_bullets]
                    continue
            need_fetch[qid] = qtxt
    
        fetched_count = 0
        if need_fetch:
            fresh = await _asknews_bullets_async(need_fetch)  # <- your existing async fetcher
            for qid, bullets in fresh.items():
                cache[qid] = {
                    "fetched_at": today.isoformat(),
                    "bullets": bullets[:max_bullets],
                }
                out[qid] = bullets[:max_bullets]
                fetched_count += 1
            _save_asknews_cache(cache)
    
        hits = len(qid_to_text) - fetched_count
        print(f"[ASKNEWS] fetched {fetched_count}, cache hits {hits}, stale_days={stale_days}, force={force_refresh}")
        return out


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Suppress LiteLLM logging
    litellm_logger = logging.getLogger("LiteLLM")
    litellm_logger.setLevel(logging.WARNING)
    litellm_logger.propagate = False

    parser = argparse.ArgumentParser(
        description="Run the Q1TemplateBot forecasting system"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["tournament", "metaculus_cup", "test_questions"],
        default="tournament",
        help="Specify the run mode (default: tournament)",
    )
    args = parser.parse_args()
    run_mode: Literal["tournament", "metaculus_cup", "test_questions"] = args.mode
    assert run_mode in [
        "tournament",
        "metaculus_cup",
        "test_questions",
    ], "Invalid run mode"
    print(f"RUN_MODE = {run_mode}")

    template_bot = FallTemplateBot2025(
        research_reports_per_question=1,
        predictions_per_research_report=1,
        use_research_summary_to_forecast=False,
        publish_reports_to_metaculus=False,
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=True,
        # llms={  # choose your model names or GeneralLlm llms here, otherwise defaults will be chosen for you
        #     "default": GeneralLlm(
        #         model="openrouter/openai/gpt-4o", # "anthropic/claude-3-5-sonnet-20241022", etc (see docs for litellm)
        #         temperature=0.3,
        #         timeout=40,
        #         allowed_tries=2,
        #     ),
        #     "summarizer": "openai/gpt-4o-mini",
        #     "researcher": "asknews/deep-research/low",
        #     "parser": "openai/gpt-4o-mini",
        # },
    )

    if run_mode == "tournament":
        seasonal_tournament_reports = asyncio.run(
            template_bot.forecast_on_tournament(
                MetaculusApi.CURRENT_AI_COMPETITION_ID, return_exceptions=True
            )
        )
        minibench_reports = asyncio.run(
            template_bot.forecast_on_tournament(
                MetaculusApi.CURRENT_MINIBENCH_ID, return_exceptions=True
            )
        )
        forecast_reports = seasonal_tournament_reports + minibench_reports
    elif run_mode == "metaculus_cup":
        # The Metaculus cup is a good way to test the bot's performance on regularly open questions. You can also use AXC_2025_TOURNAMENT_ID = 32564 or AI_2027_TOURNAMENT_ID = "ai-2027"
        # The Metaculus cup may not be initialized near the beginning of a season (i.e. January, May, September)
        template_bot.skip_previously_forecasted_questions = False
        forecast_reports = asyncio.run(
            template_bot.forecast_on_tournament(
                MetaculusApi.CURRENT_METACULUS_CUP_ID, return_exceptions=True
            )
        )
    elif run_mode == "test_questions_old":
        # Example questions are a good way to test the bot's performance on a single question
        EXAMPLE_QUESTIONS = [
            "https://www.metaculus.com/questions/578/human-extinction-by-2100/",  # Human Extinction - Binary
            #"https://www.metaculus.com/questions/14333/age-of-oldest-human-as-of-2100/",  # Age of Oldest Human - Numeric
           # "https://www.metaculus.com/questions/22427/number-of-new-leading-ai-labs/",  # Number of New Leading AI Labs - Multiple Choice
          #  "https://www.metaculus.com/c/diffusion-community/38880/how-many-us-labor-strikes-due-to-ai-in-2029/",  # Number of US Labor Strikes Due to AI in 2029 - Discrete
        ]
        template_bot.skip_previously_forecasted_questions = False
        questions = [
            MetaculusApi.get_question_by_url(question_url)
            for question_url in EXAMPLE_QUESTIONS
        ]
        forecast_reports = asyncio.run(
            template_bot.forecast_questions(questions, return_exceptions=True)
        )
    elif run_mode == "test_questions":
        # Keep your example set (binary, numeric, MC)
        EXAMPLE_QUESTIONS = [
            "https://www.metaculus.com/questions/578/human-extinction-by-2100/",           # binary
            "https://www.metaculus.com/questions/14333/age-of-oldest-human-as-of-2100/",     # numeric
            "https://www.metaculus.com/questions/22427/number-of-new-leading-ai-labs/",      # multiple choice
        ]
        template_bot.skip_previously_forecasted_questions = False
    
        # Resolve question objects (used for texts, types, etc.)
        questions = [MetaculusApi.get_question_by_url(url) for url in EXAMPLE_QUESTIONS]
    
        # Build the minimal MC input (ids and coarse types)
        def _qtype(q):
            if isinstance(q, BinaryQuestion): return "binary"
            if isinstance(q, MultipleChoiceQuestion): return "multiple_choice"
            return "numeric"  # default
        mc_questions = []
        qid_to_text = {}
        for idx, q in enumerate(questions, start=1):
            # pydantic v2 fields vary; grab an id robustly
            qid = getattr(q, "question_id", None) or getattr(q, "id", None)
            if qid is None:
                url = q.page_url if hasattr(q, "page_url") else EXAMPLE_QUESTIONS[idx-1]
                import re
                m = re.search(r"/questions/(\d+)", url)
                qid = m.group(1) if m else f"T{idx}"
            qid = str(qid)
            mc_questions.append({"id": qid, "type": _qtype(q)})
            # plain text for AskNews
            qtext = getattr(q, "title", None) or getattr(q, "question_text", None) or "Forecasting question"
            qid_to_text[qid] = qtext
    
        # === NEW: fetch dated facts from AskNews with cache (or a single fallback line) ===
        research_by_q = fetch_facts_for_batch(qid_to_text, max_per_q=8)
    
        # Run MC on this batch
        from mc_worlds import run_mc_worlds, collect_world_summaries
        N_WORLDS = 30
        results, evidence = run_mc_worlds(
            open_questions=mc_questions,
            research_by_q=research_by_q,
            llm_call=llm_call,
            n_worlds=N_WORLDS,
            batch_size=12,
            return_evidence=True,
        )
    
        # Persist raw outputs for inspection
        import json, io
        with io.open("mc_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
        # Synthesize short, question-specific reasons from the world summaries (not per-world)
        def synth_reason(qtext: str, worlds: list, mc_fore: dict) -> str:
            ws = collect_world_summaries(worlds)
            subset = ws[:12] if len(ws) > 12 else ws
            if not subset:
                subset = ["A baseline world with no major recent shocks; outcomes depend on usual mechanisms."]
            summaries_block = "\n".join("- " + s.replace("\n", " ").strip() for s in subset)
            # small, cheap prompt that references THIS question
            prm = f"""
            You are writing a short rationale for a Metaculus forecast on ONE question.
            
            Question:
            {qtext}
            
            Sampled world summaries (evidence):
            {summaries_block}
            
            Monte Carlo aggregate (for context):
            {json.dumps(mc_fore)[:800]}
            
            Write 3–5 *specific* bullet points that explain the forecast for THIS question.
            Use only the evidence above (no outside facts). Name concrete drivers (e.g., “policy timeline”, “tech milestone”, “base rate X”).
            Avoid boilerplate and generic phrases. No “will adjust later”.
            """
            import json as _json, urllib.request as _rq
            api_key = os.environ["OPENROUTER_API_KEY"]
            payload = {
                "model": "openrouter/openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prm}],
                "temperature": 0.2,
                "max_tokens": 250,
            }
            req = _rq.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=_json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "X-Title": "Metaculus MC rationale",
                },
            )
            with _rq.urlopen(req, timeout=60) as resp:
                body = _json.loads(resp.read().decode("utf-8"))
            txt = body["choices"][0]["message"]["content"].strip()
            # Keep only bullets and trim
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip().startswith(("-", "•", "*"))]
            if not lines:
                lines = [txt]
            return "\n".join(lines[:5])
    
        # Build reasons per question from the *same* worlds used for results
        reasons_lines = []
        for q in mc_questions:
            qid = q["id"]; qtext = qid_to_text[qid]
            worlds_for_q = evidence.get(qid, {}).get("binary_yes", []) + evidence.get(qid, {}).get("binary_no", [])
            # If we didn't track per-world text above, reuse all worlds by passing them from results aggregation call
            # (run_mc_worlds returns 'evidence' with per-question buckets; we only need the world summaries)
            # For simplicity, just reuse all worlds we sampled: collect from evidence buckets (already populated)
            bullets = synth_reason(qtext, worlds=evidence.get(qid, {}).get("numeric", []) or [], mc_fore=results.get(qid, {}))
            # If numeric bucket is empty (common), regenerate using the binary_yes/no summaries we collected
            if not bullets.strip() or "drivers synthesized" in bullets.lower():
                # fallback: use any summaries we captured for this q
                from mc_worlds import collect_world_summaries
                # Reconstruct a list of summaries from all buckets we stored (we put summaries into binary_yes/no)
                summaries = evidence.get(qid, {}).get("binary_yes", []) + evidence.get(qid, {}).get("binary_no", [])
                bullets = synth_reason(qtext, worlds=[{"world_summary": s} for s in summaries] or [], mc_fore=results.get(qid, {}))
            reasons_lines.append(f"[MC][REASON] Q{qid}:\n{bullets}\n")
    
        with open("mc_reasons.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(reasons_lines))
    
        print("[MC] wrote mc_results.json")
        print("[MC] wrote mc_reasons.txt")
        print("[MC] SENTINEL: end of test batch.")

    
    try:
        template_bot.log_report_summary(forecast_reports)
    except NameError:
        pass
