import argparse
import asyncio
import logging
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
from mc_worlds import build_batch_digest, sample_one_world, aggregate_worlds, make_comment

class FallTemplateBot2025(ForecastBot):
    """
    This is a copy of the template bot for Fall 2025 Metaculus AI Tournament.
    This bot is what is used by Metaculus in our benchmark, but is also provided as a template for new bot makers.
    This template is given as-is, and though we have covered most test cases
    in forecasting-tools it may be worth double checking key components locally.

    Main changes since Q2:
    - An LLM now parses the final forecast output (rather than programmatic parsing)
    - Added resolution criteria and fine print explicitly to the research prompt
    - Previously in the prompt, nothing about upper/lower bound was shown when the bounds were open. Now a suggestion is made when this is the case.
    - Support for nominal bounds was added (i.e. when there are discrete questions and normal upper/lower bounds are not as intuitive)

    The main entry point of this bot is `forecast_on_tournament` in the parent class.
    See the script at the bottom of the file for more details on how to run the bot.
    Ignoring the finer details, the general flow is:
    - Load questions from Metaculus
    - For each question
        - Execute run_research a number of times equal to research_reports_per_question
        - Execute respective run_forecast function `predictions_per_research_report * research_reports_per_question` times
        - Aggregate the predictions
        - Submit prediction (if publish_reports_to_metaculus is True)
    - Return a list of ForecastReport objects

    Only the research and forecast functions need to be implemented in ForecastBot subclasses,
    though you may want to override other ones.
    In this example, you can change the prompts to be whatever you want since,
    structure_output uses an LLMto intelligently reformat the output into the needed structure.

    By default (i.e. 'tournament' mode), when you run this script, it will forecast on any open questions for the
    MiniBench and Seasonal AIB tournaments. If you want to forecast on only one or the other, you can remove one
    of them from the 'tournament' mode code at the bottom of the file.

    You can experiment with what models work best with your bot by using the `llms` parameter when initializing the bot.
    You can initialize the bot with any number of models. For example,
    ```python
    my_bot = MyBot(
        ...
        llms={  # choose your model names or GeneralLlm llms here, otherwise defaults will be chosen for you
            "default": GeneralLlm(
                model="openrouter/openai/gpt-4o", # "anthropic/claude-3-5-sonnet-20241022", etc (see docs for litellm)
                temperature=0.3,
                timeout=40,
                allowed_tries=2,
            ),
            "summarizer": "openai/gpt-4o-mini",
            "researcher": "asknews/deep-research/low",
            "parser": "openai/gpt-4o-mini",
        },
    )
    ```

    Then you can access the model in custom functions like this:
    ```python
    research_strategy = self.get_llm("researcher", "model_name"
    if research_strategy == "asknews/deep-research/low":
        ...
    # OR
    summarizer = await self.get_llm("summarizer", "model_name").invoke(prompt)
    # OR
    reasoning = await self.get_llm("default", "llm").invoke(prompt)
    ```

    If you end up having trouble with rate limits and want to try a more sophisticated rate limiter try:
    ```python
    from forecasting_tools import RefreshingBucketRateLimiter
    rate_limiter = RefreshingBucketRateLimiter(
        capacity=2,
        refresh_rate=1,
    ) # Allows 1 request per second on average with a burst of 2 requests initially. Set this as a class variable
    await self.rate_limiter.wait_till_able_to_acquire_resources(1) # 1 because it's consuming 1 request (use more if you are adding a token limit)
    ```
    Additionally OpenRouter has large rate limits immediately on account creation
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

        def qid_from_url(u: str) -> str:
            import re
            m = re.search(r"/questions/(\d+)(?:/|$)", u)
            return m.group(1)
        
        def mc_option_count(q_obj) -> int | None:
            # Try attributes
            for attr in ("options", "choices", "answer_options", "options_text"):
                v = getattr(q_obj, attr, None)
                if isinstance(v, list):
                    return len(v)
            # Try pydantic dump
            try:
                d = q_obj.model_dump()
                for k in ("options", "choices", "answer_options", "options_text"):
                    v = d.get(k)
                    if isinstance(v, list):
                        return len(v)
            except Exception:
                pass
            return None
            
        # 1) Use one known-binary test question
        # TEST_URL = "https://www.metaculus.com/questions/578/human-extinction-by-2100/"
        # EXAMPLE_QUESTIONS = [TEST_URL]
        EXAMPLES = [
            ("https://www.metaculus.com/questions/578/human-extinction-by-2100/",            "binary"),          # BIN
            ("https://www.metaculus.com/questions/14333/age-of-oldest-human-as-of-2100/",    "numeric"),         # NUM
            ("https://www.metaculus.com/questions/22427/number-of-new-leading-ai-labs/",     "multiple_choice"), # MC
        ]
        template_bot.skip_previously_forecasted_questions = False
    
        # 2) Resolve the question (optional, helps confirm the URL works)
        questions = [MetaculusApi.get_question_by_url(u) for (u, _) in EXAMPLES]
    
        # 3) Parse qids from URLs
        import re
        def qid_from_url(u: str) -> str:
            m = re.search(r"/questions/(\d+)(?:/|$)", u)
            if not m:
                raise SystemExit(f"Could not parse qid from URL: {u}")
            return m.group(1)
        
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
            # return list of option strings if present
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
            return None
        
        mc_questions = []
        for (u, t), obj in zip(EXAMPLES, questions):
            entry = {"id": qid_from_url(u), "type": t, "title": qtitle(obj)}
            if t == "multiple_choice":
                opts = mc_options_text(obj)
                if opts:
                    entry["options"] = opts
                    entry["k"] = len(opts)
            mc_questions.append(entry)
        
        # Minimal neutral facts; do NOT mention “sampler” or prompts.
        from datetime import date
        today = date.today().isoformat()
        research_by_q = {q["id"]: [f"{today}: no notable updates; rely on question text and base rates"]
                         for q in mc_questions}
    
        # 5) number of draws
        N_WORLDS = 30
    
        # 6) OpenRouter call (explicit; no template internals)
        import os, json, time, random, urllib.request, urllib.error

        FALLBACK_MODELS = [
            "openai/gpt-4o-mini",          # first choice
            "openrouter/auto",             # router fallback
            "google/gemini-1.5-flash",     # cheap/fast fallback
        ]
        MAX_RETRIES = 4  # per model
        BACKOFF_CAP = 10.0
        
        def llm_call(prompt: str) -> str:
            api_key = os.environ["OPENROUTER_API_KEY"]
        
            def try_once(model: str):
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Reply with a single valid JSON object. No preface, no code fences."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "top_p": 1,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 800,
                    "seed": 12345,  # some models ignore it; harmless
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
                return content[s:e+1] if s != -1 and e != -1 else content
        
            for model in FALLBACK_MODELS:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        return try_once(model)
                    except urllib.error.HTTPError as e:
                        code = e.code
                        msg = e.read().decode("utf-8", "ignore")
                        print(f"[MC][LLM] HTTP {code} on {model} attempt {attempt}: {msg[:200]}")
                        # Only retry on transient codes
                        if code not in (429, 500, 502, 503, 504):
                            raise
                    except urllib.error.URLError as e:
                        print(f"[MC][LLM] URL error on {model} attempt {attempt}: {getattr(e, 'reason', e)}")
                    # backoff with jitter
                    sleep_s = min(2 ** attempt, BACKOFF_CAP) + random.random()
                    time.sleep(sleep_s)
                print(f"[MC][LLM] model fallback: switching from {model}")
            raise RuntimeError("All OpenRouter model fallbacks exhausted")

    
        # 7) Run MC and stop (no posting in test mode)
        from mc_worlds import run_mc_worlds
        import json

        try:
            mc_results, mc_evidence = run_mc_worlds(
                open_questions=mc_questions,
                research_by_q=research_by_q,
                llm_call=llm_call,
                n_worlds=N_WORLDS,
                batch_size=12,
                return_evidence=True,
            )

            def _clip(s: str, n: int = 160) -> str:
                s = (s or "").strip().replace("\n", " ")
                return (s[:n] + "…") if len(s) > n else s
            
            def _sample(lst, k):
                return lst[:k] if len(lst) <= k else lst[:k]
            
            def synth_reason(qtype: str, qid: str, forecast: dict, evidence: dict, n_worlds: int) -> str:
                # Prefer per-world rationales (they mention the actual question)
                rationale_snips = (evidence.get("rationales") or [])[:6]
                if not rationale_snips:
                    # fallback: use world summaries for the modal outcome
                    if qtype == "binary":
                        yes = evidence.get("binary_yes", [])
                        no  = evidence.get("binary_no", [])
                        rationale_snips = (yes if len(yes) >= len(no) else no)[:6]
                    elif qtype == "multiple_choice":
                        mc = evidence.get("mc", {})
                        if mc:
                            top = max(mc.keys(), key=lambda k: len(mc[k]))
                            rationale_snips = mc[top][:6]
                    else:
                        rationale_snips = [s for _, s in (evidence.get("numeric") or [])][:6]
            
                # One tiny summarization call per question, into 3 bullets.
                # Our llm_call expects JSON; ask for {"bullets":[...]}.
                joined = "\n- ".join(rationale_snips)
                ask = (
                    "You are writing a compact rationale for a forecast.\n"
                    "Source snippets:\n- " + joined + "\n\n"
                    "Write EXACTLY three short bullets (plain language) summarizing the most common drivers and one caveat.\n"
                    "Output JSON only as {\"bullets\":[\"...\",\"...\",\"...\"]}. No meta, no mention of prompts or samplers."
                )
                import json as _json
                try:
                    resp = llm_call(ask)
                    obj = _json.loads(resp)
                    bullets = obj.get("bullets") or []
                    bullets = [b.strip("• ").strip() for b in bullets if isinstance(b, str) and b.strip()]
                    if len(bullets) >= 3:
                        return "• " + "\n• ".join(bullets[:3])
                except Exception:
                    pass
                # Fallback: compress first 3 snippets
                return "• " + "\n• ".join([s[:140] + ("…" if len(s) > 140 else "") for s in rationale_snips[:3]])

            
                # Use the same LLM call (cheap: small prompt)
                import json as _json
                data = llm_call(prompt)
                # Model returns a JSON object or plain text; accept either.
                try:
                    obj = _json.loads(data)
                    text = obj.get("rationale") or obj.get("bullets") or obj.get("text") or ""
                    if text.strip():
                        return text.strip()
                except Exception:
                    pass
                return data.strip()
            
            # Print every result (works for 1 or many questions)
            for q in mc_questions:
                qid_i = q["id"]
                print(f"[MC] Result Q{qid_i}:", mc_results.get(qid_i))
        
            # Save artifact so you (and I) can inspect exact JSON
            with open("mc_results.json", "w") as f:
                json.dump(mc_results, f, indent=2)
            print("[MC] wrote mc_results.json")
        
            # --- Optional: generate a short reasoning blurb per question (printed only) ---
            def _median_from_cdf(grid, cdf):
                for x, y in zip(grid, cdf):
                    if y >= 0.5:
                        return x
                return grid[-1]
        
            def _p10_p90_from_cdf(grid, cdf):
                p10 = next((x for x, y in zip(grid, cdf) if y >= 0.10), grid[0])
                p90 = next((x for x, y in zip(grid, cdf) if y >= 0.90), grid[-1])
                return p10, p90
        
            def build_reasoning(qtype, forecast, n_worlds):
                # 3–4 short lines; enough to satisfy the tournament requirement
                if qtype == "binary":
                    p = forecast["binary"]["p"]
                    return (
                        f"Method: {n_worlds} scenario draws; p = {p:.2f} from empirical frequency.\n"
                        f"Context: dated fact digest; conservative when uncertain.\n"
                        f"Updates: will adjust on major news."
                    )
                if qtype == "multiple_choice":
                    probs = forecast["multiple_choice"]["probs"]
                    top = max(range(len(probs)), key=lambda i: probs[i]) if probs else 0
                    return (
                        f"Method: {n_worlds} draws; option probs from empirical frequency.\n"
                        f"Top option: {top} @ {probs[top]:.2f}; vector (truncated): {probs[:5]}.\n"
                        f"Updates: will adjust on major news."
                    )
                if qtype == "numeric":
                    grid, cdf = forecast["numeric"]["grid"], forecast["numeric"]["cdf"]
                    med = _median_from_cdf(grid, cdf)
                    p10, p90 = _p10_p90_from_cdf(grid, cdf)
                    return (
                        f"Method: {n_worlds} draws; ECDF → CDF on a test grid.\n"
                        f"Median ≈ {med:.2f}; 10–90% ≈ [{p10:.2f}, {p90:.2f}].\n"
                        f"Updates: will adjust on major news."
                    )
                if qtype == "date":
                    # If you return {"date":{"grid_ord":[...],"cdf":[...]}} in tests
                    return (
                        f"Method: {n_worlds} draws; ECDF on ordinal-date grid.\n"
                        f"Updates: will adjust on major news."
                    )
                return "Method: scenario draws; empirical aggregation."
        
            for q in mc_questions:
                qid_i, qtype_i = q["id"], q["type"]
                fore_i = mc_results.get(qid_i)
                if not fore_i:
                    continue
                print(f"[MC][REASON] Q{qid_i}:\n{build_reasoning(qtype_i, fore_i, N_WORLDS)}")
                reasons = {}
                for q in mc_questions:
                    qid_i, qtype_i = q["id"], q["type"]
                    fore_i = mc_results.get(qid_i)
                    evid_i = mc_evidence.get(qid_i, {})
                    if not fore_i:
                        continue
                    txt = synth_reason(qtype_i, qid_i, fore_i, evid_i, N_WORLDS)
                    reasons[qid_i] = txt
                    print(f"[MC][REASON] Q{qid_i}:\n{txt}\n")
                
                with open("mc_reasons.txt", "w") as f:
                    for qid_i, txt in reasons.items():
                        f.write(f"Q{qid_i}\n{txt}\n\n")
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
