import argparse
import asyncio
import logging
import json
from datetime import datetime
from typing import Literal

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
        # ---------------------- Config: 3 example questions ----------------------
        EXAMPLES = [
            ("https://www.metaculus.com/questions/578/human-extinction-by-2100/",            "binary"),
            ("https://www.metaculus.com/questions/14333/age-of-oldest-human-as-of-2100/",    "numeric"),
            ("https://www.metaculus.com/questions/22427/number-of-new-leading-ai-labs/",     "multiple_choice"),
        ]
        template_bot.skip_previously_forecasted_questions = False
    
        # ---------------------- Resolve objects (optional sanity) ----------------
        questions = [MetaculusApi.get_question_by_url(u) for (u, _) in EXAMPLES]
    
        # ---------------------- Helpers to extract id/title/options --------------
        def qid_from_url(u: str) -> str:
            import re
            m = re.search(r"/questions/(\d+)(?:/|$)", u)
            if not m:
                raise SystemExit(f"Could not parse qid from URL: {u}")
            return m.group(1)
    
        def qtitle(q_obj) -> str:
            for attr in ("title", "name", "question_title"):
                v = getattr(q_obj, attr, None)
                if v:
                    return str(v)
            try:
                d = q_obj.model_dump()
                for k in ("title", "name", "question_title"):
                    if d.get(k):
                        return str(d[k])
            except Exception:
                pass
            return ""
    
        def mc_options_text(q_obj):
            for attr in ("options", "choices", "answer_options", "options_text"):
                v = getattr(q_obj, attr, None)
                if isinstance(v, list) and v and isinstance(v[0], str):
                    return v
            try:
                d = q_obj.model_dump()
                for k in ("options", "choices", "answer_options", "options_text"):
                    v = d.get(k)
                    if isinstance(v, list) and v and isinstance(v[0], str):
                        return v
            except Exception:
                pass
            return []
    
        # ---------------------- Build compact MC input questions -----------------
        mc_questions = []
        meta_by_q = {}
        for (u, t), obj in zip(EXAMPLES, questions):
            qid = qid_from_url(u)
            title = qtitle(obj)
            entry = {"id": qid, "type": t, "title": title}
            meta = {"title": title}
            if t == "multiple_choice":
                opts = mc_options_text(obj)
                entry["options"] = opts
                entry["k"] = len(opts) if opts else None
                meta["options"] = opts
            mc_questions.append(entry)
            meta_by_q[qid] = meta
    
        # ---------------------- Neutral “facts” per question ---------------------
        from datetime import date
        today = date.today().isoformat()
        research_by_q = {
            q["id"]: [f"{today}: no notable updates; use question text and base rates"]
            for q in mc_questions
        }
    
        # ---------------------- World sampling config ----------------------------
        N_WORLDS = 30
    
        # ---------------------- LLM call for world sampling ----------------------
        import os, json, time, random, urllib.request, urllib.error
    
        FALLBACK_MODELS = [
            "openai/gpt-4o-mini",
            "openrouter/auto",
            "google/gemini-1.5-flash",
        ]
        MAX_RETRIES = 4
        BACKOFF_CAP = 10.0
    
        def llm_call(prompt: str) -> str:
            api_key = os.environ["OPENROUTER_API_KEY"]
    
            def try_once(model: str):
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Reply with a single valid JSON object. No preface, no code fences, no meta."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "top_p": 1,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 900,
                    "seed": 12345,
                }
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=json.dumps(data).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://github.com/jh-tpp/metac-bot-template",
                        "X-Title": "Metaculus MC test",
                    },
                )
                with urllib.request.urlopen(req, timeout=90) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                s, e = content.find("{"), content.rfind("}")
                return content[s:e + 1] if s != -1 and e != -1 else content
    
            for model in FALLBACK_MODELS:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        return try_once(model)
                    except urllib.error.HTTPError as e:
                        code = e.code
                        msg = e.read().decode("utf-8", "ignore")
                        print(f"[MC][LLM] HTTP {code} on {model} attempt {attempt}: {msg[:160]}")
                        if code not in (429, 500, 502, 503, 504):
                            raise
                    except urllib.error.URLError as e:
                        print(f"[MC][LLM] URL error on {model} attempt {attempt}: {getattr(e, 'reason', e)}")
                    time.sleep(min(2 ** attempt, BACKOFF_CAP) + random.random())
                print(f"[MC][LLM] model fallback: switching from {model}")
            raise RuntimeError("All OpenRouter model fallbacks exhausted")
    
        # ---------------------- Run worlds and aggregate -------------------------
        try:
            mc_results, world_summaries = run_mc_worlds(
                open_questions=mc_questions,
                research_by_q=research_by_q,
                llm_call=llm_call,
                n_worlds=N_WORLDS,
                batch_size=12,
                return_summaries=True,   # <— matches mc_worlds.py
            )
    
            # Save forecasts for inspection (CI artifact step expects this)
            with open("mc_results.json", "w") as f:
                json.dump(mc_results, f, indent=2)
            print("[MC] wrote mc_results.json")
    
            # ------------------ One cheap synth pass for question rationales ------
            def synth_reasons_batch(world_summaries, mc_questions, meta_by_q, forecasts, n_worlds, llm_call):
                # limit token use
                subset = world_summaries[:12] if len(world_summaries) > 12 else world_summaries
                summaries_block = "\n".join(f"- {s.replace('\n', ' ').strip()}" for s in subset)
    
                # compact question lines w/ forecasts
                qlines = []
                for q in mc_questions:
                    qid, qtype = q["id"], q["type"]
                    title = meta_by_q[qid]["title"]
                    line = {"qid": qid, "type": qtype, "title": title}
                    f = forecasts.get(qid, {})
                    if qtype == "binary":
                        line["forecast"] = {"p_yes": f.get("binary", {}).get("p")}
                    elif qtype == "multiple_choice":
                        probs = f.get("multiple_choice", {}).get("probs", [])
                        opts  = q.get("options", [])
                        top_i = max(range(len(probs)), key=lambda i: probs[i]) if probs else 0
                        top_n = opts[top_i] if 0 <= top_i < len(opts) else f"option {top_i}"
                        line["forecast"] = {"k": len(probs), "top_index": top_i, "top_name": top_n, "top_p": probs[top_i] if probs else None}
                    elif qtype == "numeric":
                        grid = f.get("numeric", {}).get("grid", [])
                        cdf  = f.get("numeric", {}).get("cdf", [])
                        def pct(p):
                            return next((vx for vx, y in zip(grid, cdf) if y >= p), grid[-1] if grid else None)
                        if grid and cdf:
                            line["forecast"] = {"p10": pct(0.10), "median": pct(0.50), "p90": pct(0.90)}
                    qlines.append(line)
    
                import json as _json
                prompt = (
                    "Write short, question-specific rationales using the sampled world summaries.\n"
                    "Rules:\n"
                    "1) Address EACH question separately; do not reuse the same bullets across questions.\n"
                    "2) Use concrete drivers implied by the summaries; no meta (no mention of prompts/JSON/samplers).\n"
                    "3) Return JSON ONLY as {\"reasons\": {qid: [\"b1\",\"b2\",\"b3\"], ...}} with 2–3 bullets per question.\n\n"
                    "SAMPLED WORLD SUMMARIES (subset):\n"
                    f"{summaries_block}\n\n"
                    "QUESTIONS AND CURRENT FORECASTS:\n"
                    f"{_json.dumps(qlines, ensure_ascii=False)}"
                )
    
                resp = llm_call(prompt)
                try:
                    obj = _json.loads(resp)
                except Exception:
                    return {}
                raw = obj.get("reasons", {})
                clean = {}
                for qid, arr in raw.items():
                    if not isinstance(arr, list):
                        continue
                    bullets = []
                    seen = set()
                    for b in arr:
                        s = str(b).strip().lstrip("• ").strip()
                        if not s or s.lower().startswith("global tensions"):
                            # light de-dup and remove overly generic boilerplate we saw earlier
                            continue
                        if s in seen:
                            continue
                        seen.add(s)
                        bullets.append(s)
                        if len(bullets) == 3:
                            break
                    if bullets:
                        clean[qid] = bullets
                return clean
    
            reason_map = synth_reasons_batch(world_summaries, mc_questions, meta_by_q, mc_results, N_WORLDS, llm_call)
    
            # Write reasons file (one block per qid)
            with open("mc_reasons.txt", "w") as f:
                for q in mc_questions:
                    qid = q["id"]
                    bullets = reason_map.get(qid, [])
                    txt = ("• " + "\n• ".join(bullets)) if bullets else "• Drivers synthesized from sampled worlds and base rates."
                    print(f"[MC][REASON] Q{qid}:\n{txt}\n")
                    f.write(f"Q{qid}\n{txt}\n\n")
            print("[MC] wrote mc_reasons.txt")
    
            print("[MC] SENTINEL: end of test batch.")
            raise SystemExit(0)
    
        except Exception as e:
            print(f"[MC] Error: {e}")
            raise SystemExit(1)


    try:
        template_bot.log_report_summary(forecast_reports)
    except NameError:
        pass
