# Simple Metaculus forecasting bot
This repository contains a simple bot meant to get you started with creating your own bot for the AI Forecasting Tournament. Go to https://www.metaculus.com/aib/ for more info and tournament rules (this should link to the "Getting Started" section of our [resources](https://www.metaculus.com/notebooks/38928/ai-benchmark-resources/#GettingStarted:~:text=AI%20Forecasting%20Benchmark%3F-,Getting%20Started,-We%27ve%20published%20a) page).

In this project are 2 files:
- **main.py**: Our recommended template option that uses [forecasting-tools](https://github.com/Metaculus/forecasting-tools) package to handle a lot of stuff in the background for you (such as API calls). We will update the package, thus allowing you to gain new features with minimal changes to your code.
- **main_with_no_framework.py**: A copy of main.py but implemented with minimal dependencies. Useful if you want a more custom approach.

Join the conversation about bot creation, get support, and follow updates on the [Metaculus Discord](https://discord.com/invite/NJgCC2nDfh) 'build a forecasting bot' channel.

## Quick start -> Fork and use Github Actions
The easiest way to use this repo is to fork it, enable github workflow/actions, and then set repository secrets. Then your bot will run every 30min, pick up new questions, and forecast on them. Automation is handled in the `.github/workflows/` folder. The `daily_run_simple_bot.yaml` file runs the simple bot every 30min and will skip questions it has already forecasted on.

1) **Fork the repository**: Go to the [repository](https://github.com/Metaculus/metac-bot-template) and click 'fork'.
2) **Set secrets**: Go to `Settings -> Secrets and variables -> Actions -> New repository secret` and set API keys/Tokens as secrets. You will want to set your METACULUS_TOKEN and an OPENROUTER_API_KEY (or whatever LLM/search providers you plan to use). This will be used to post questions to Metaculus. Make sure to copy the name of these variables exactly (including all caps).
   - You can create a METACULUS_TOKEN at https://metaculus.com/aib. If you get confused, please see the instructions on our [resources](https://www.metaculus.com/notebooks/38928/ai-benchmark-resources/#creating-your-bot-account-and-metaculus-token) page.
   - You can get an OPENROUTER_API_KEY with free credits by filling out this [form](https://forms.gle/aQdYMq9Pisrf1v7d8). If you don't want to wait or want to use more models than we provide, you can also make your own API key on OpenRouter's [website](https://openrouter.ai/). First, make an account, then go to your profile, then go to "keys", and then make a key.
   - Other LLM and Search providers should work out of the box (such as OPENAI_API_KEY, PERPLEXITY_API_KEY, ASKNEWS_SECRET, etc), though we recommend OpenRouter to start.
4) **Enable Actions**: Go to 'Actions' then click 'Enable'. Then go to the 'Regularly forecast new questions' workflow, and click 'Enable'. To test if the workflow is working, click 'Run workflow', choose the main branch, then click the green 'Run workflow' button. This will check for new questions and forecast only on ones it has not yet successfully forecast on.

The bot should just work as is at this point. You can disable the workflow by clicking `Actions > Regularly forecast new questions > Triple dots > disable workflow`

## API Keys
Instructions for getting your METACULUS_TOKEN, OPENROUTER_API_KEY, or optional search provider API keys (AskNews, Exa, Perplexity, etc) are listed on the "Getting Started" section of the [resources](https://www.metaculus.com/notebooks/38928/ai-benchmark-resources/#GettingStarted:~:text=AI%20Forecasting%20Benchmark%3F-,Getting%20Started,-We%27ve%20published%20a) page.

## Disabling AskNews (optional)
The bot supports an `ASKNEWS_ENABLED` environment variable to completely disable AskNews calls while keeping the bot fully functional. **AskNews is disabled by default.** This is useful for:
- Testing without AskNews credentials
- Reducing API costs
- Using alternative research providers (EXA, Perplexity)
- Debugging forecast logic without network calls

### Usage
Set the `ASKNEWS_ENABLED` environment variable to enable or disable AskNews:

**In `.env` file:**
```bash
# Enable AskNews (must also set ASKNEWS_CLIENT_ID and ASKNEWS_SECRET)
ASKNEWS_ENABLED=true

# Disable AskNews (default)
ASKNEWS_ENABLED=false
```

**In GitHub Actions secrets:**
Add a repository secret named `ASKNEWS_ENABLED` with value `true` to enable, or `false` (or leave unset) to disable.

**Accepted values:**
- To enable: `true`, `1`, `yes`, `y`, `on`, `t`
- To disable (default): `false`, `0`, `no`, `n`, `off`, `f` (or leave unset)

### Behavior when disabled
- **All AskNews network requests are skipped** (no token acquisition, no API calls)
- `fetch_facts_for_batch()` returns empty fact lists (`[]`) for all questions
- The bot continues to run normally in all modes (test, tournament, live-test)
- Alternative research providers (EXA, Perplexity) are still used if configured
- No errors or exceptions are raised

**Note:** Even if `ASKNEWS_CLIENT_ID` and `ASKNEWS_SECRET` are set, when `ASKNEWS_ENABLED=false` (or unset), AskNews is completely bypassed.

## OpenRouter Debug Mode (optional)
The bot supports an `OPENROUTER_DEBUG` environment variable to enable verbose logging and artifact saving for OpenRouter API calls. **Debug mode is disabled by default.** This is useful for:
- Diagnosing empty LLM responses or JSON parse failures
- Understanding rate limiting and quota issues
- Correlating world generation errors with specific prompts
- Inspecting request/response details for troubleshooting

### Usage
Set the `OPENROUTER_DEBUG` environment variable to enable or disable debug mode:

**In `.env` file:**
```bash
# Enable debug mode
OPENROUTER_DEBUG=true

# Disable debug mode (default)
OPENROUTER_DEBUG=false
```

**In GitHub Actions secrets:**
Add a repository secret named `OPENROUTER_DEBUG` with value `true` to enable, or `false` (or leave unset) to disable.

**Accepted values:**
- To enable: `true`, `1`, `yes`, `y`, `on`, `t`
- To disable (default): `false`, `0`, `no`, `n`, `off`, `f` (or leave unset)

### Behavior when enabled
When `OPENROUTER_DEBUG=true`, the bot will:
- **Log detailed request information** before each OpenRouter call:
  - URL, model, temperature, max_tokens
  - Prompt length and first ~1000 characters
- **Log detailed response information** after each OpenRouter call:
  - HTTP status code
  - Selected response headers (x-request-id, x-ratelimit-*, etc.)
- **Save debug artifacts** to the `cache/` directory:
  - `cache/debug_llm_*_request.json` - Request details (Authorization header stripped for security)
  - `cache/debug_llm_*_response.json` - Full response body and headers
  - `cache/debug_world_q{qid}_{i}_prompt.txt` - World generation prompts (in mc_worlds)
  - `cache/debug_world_q{qid}_{i}_error.txt` - Error details when world generation fails
- **Include detailed error messages** for:
  - Empty content responses (includes truncated response JSON)
  - JSON parse failures (includes raw content snippet)
  - Unexpected response shapes (includes response structure)

### Security note
All saved artifacts automatically strip the `Authorization` header to prevent secrets from being written to disk. Debug logs printed to console do not include API keys.

### Behavior when disabled
When `OPENROUTER_DEBUG=false` (default), the bot operates normally without verbose logging or artifact saving. Only errors are logged as usual.

## OpenRouter Model Override (optional)
The bot allows you to override the default OpenRouter model via the `OPENROUTER_MODEL` environment variable. **The default model is `openai/gpt-5-nano`** which provides better JSON mode reliability than earlier models.

### Usage
Set the `OPENROUTER_MODEL` environment variable to specify which model to use:

**In `.env` file:**
```bash
# Use default model (gpt-5-nano)
OPENROUTER_MODEL=openai/gpt-5-nano
```

**In GitHub Actions secrets:**
Add a repository secret named `OPENROUTER_MODEL` with your preferred model name (e.g., `openai/gpt-5-nano`).

### Special handling for gpt-5-* models
When using gpt-5-* models (e.g., `openai/gpt-5-nano`), the bot automatically includes `reasoning: {effort: minimal}` in API requests to suppress the reasoning channel. This prevents empty content responses in JSON mode. You can also force this behavior for other models using `OPENROUTER_DISABLE_REASONING=true`.

## OpenRouter Reasoning Disable (optional)
For models that support a reasoning channel (e.g., gpt-5-*), you can explicitly disable it using `OPENROUTER_DISABLE_REASONING`. **This is automatically enabled for gpt-5-\* models** to prevent empty content in JSON mode.

### Usage
**In `.env` file:**
```bash
# Force disable reasoning for all models
OPENROUTER_DISABLE_REASONING=true

# Use automatic detection (default)
OPENROUTER_DISABLE_REASONING=false
```

**Accepted values:**
- To enable: `true`, `1`, `yes`, `y`, `on`, `t`
- To disable (default): `false`, `0`, `no`, `n`, `off`, `f` (or leave unset)

## World JSON Hint (optional)
The bot supports a `WORLD_JSON_HINT_ENABLED` environment variable to control whether a minimal JSON format hint is appended to world prompts. **JSON hints are enabled by default.** This provides a lightweight way to guide the LLM on the expected output format without intrusive "You are a superforecaster" system messages or complex schema blocks.

### Usage
Set the `WORLD_JSON_HINT_ENABLED` environment variable to enable or disable JSON format hints:

**In `.env` file:**
```bash
# Enable JSON hints (default)
WORLD_JSON_HINT_ENABLED=true

# Disable JSON hints (raw world prompt only)
WORLD_JSON_HINT_ENABLED=false
```

**In GitHub Actions secrets:**
Add a repository secret named `WORLD_JSON_HINT_ENABLED` with value `true` to enable (default), or `false` to disable.

**Accepted values:**
- To enable (default): `true`, `1`, `yes`, `y`, `on`, `t` (or leave unset)
- To disable: `false`, `0`, `no`, `n`, `off`, `f`

### Behavior when enabled
When `WORLD_JSON_HINT_ENABLED=true` (default), the bot appends a minimal one-line JSON format hint to world prompts:
- **Binary**: `Output JSON: {"answer": true} or {"answer": false}`
- **Multiple choice**: `Output JSON: {"scores": {"Option1": number, "Option2": number, ...}}`
- **Numeric**: `Output JSON: {"value": number}`

These hints are appended after the question, description, and recent facts. The base world prompt focuses on forecasting discipline without prescriptive schema instructions.

### Behavior when disabled
When `WORLD_JSON_HINT_ENABLED=false`, no JSON format hint is appended. The LLM receives only the simplified world prompt (Tetlockian forecasting discipline) plus question context and facts. This gives you complete control over prompting without editing code.

### Simplified Prompting Architecture
The world prompt system has been simplified to remove intrusive elements:
- ❌ Removed "You are a superforecaster" system role messages
- ❌ Removed multi-line strict JSON schema blocks
- ✅ Simplified base prompt focuses on forecasting methodology (Tetlockian techniques, base rates, bias consideration)
- ✅ Minimal per-type JSON hints (optional, controlled by config)
- ✅ Lenient parsing with robust fallbacks for common output variations
- ✅ Per-world logging: `[WORLD] Q{qid} world {i+1}/{n} parse=OK/FAIL`

This architecture provides flexibility while maintaining reliability. The unified `run_mc_worlds` function handles all question types (binary, multiple_choice, numeric) with consistent logic.

## World Max Tokens (optional)
The bot supports a `WORLD_MAX_TOKENS` environment variable to control the maximum number of tokens for world generation LLM calls. **The default is 700 tokens.** This ensures that world summaries (~180-200 words) plus JSON fields can be generated without truncation.

### Usage
Set the `WORLD_MAX_TOKENS` environment variable to configure the token limit:

**In `.env` file:**
```bash
# Set custom max tokens for world generation (default 700)
WORLD_MAX_TOKENS=700

# Increase if you see truncated JSON or "finish_reason=length" errors
WORLD_MAX_TOKENS=1000
```

**In GitHub Actions secrets:**
Add a repository secret named `WORLD_MAX_TOKENS` with your desired token limit (e.g., `700`).

### When to adjust
- **Increase** if you observe:
  - JSON parse errors due to unterminated strings
  - `finish_reason=length` in logs (response truncated)
  - `parse=FAIL` messages for world generation
- **Decrease** if you want to:
  - Reduce API costs
  - Force more concise world summaries

### Default value rationale
The default of 700 tokens allows:
- ~180-200 word world_summary (as requested in prompts)
- JSON structure overhead (`{"world_summary": "...", "answer": ...}`)
- Reasonable buffer for LLM formatting variations

Previous default of 200 tokens was insufficient, causing mid-JSON truncation errors.

## Diagnostics (optional)
The bot supports comprehensive per-question diagnostic tracing via the `DIAGNOSTICS_ENABLED` environment variable. **Diagnostics are enabled by default.** This feature saves detailed JSON artifacts for each question throughout the forecasting pipeline, making it trivial to see exactly what was sent to the LLM, what was received, and how each downstream step transformed the data.

### Usage
Set the `DIAGNOSTICS_ENABLED` environment variable to enable or disable diagnostic tracing:

**In `.env` file:**
```bash
# Enable diagnostics (default)
DIAGNOSTICS_ENABLED=true

# Disable diagnostics
DIAGNOSTICS_ENABLED=false

# Optionally specify custom trace directory (default: cache/trace)
DIAGNOSTICS_TRACE_DIR=my_custom_trace_dir
```

**In GitHub Actions secrets:**
Add a repository secret named `DIAGNOSTICS_ENABLED` with value `true` to enable (default), or `false` to disable.

**Accepted values:**
- To enable (default): `true`, `1`, `yes`, `y`, `on`, `t` (or leave unset)
- To disable: `false`, `0`, `no`, `n`, `off`, `f`

### Behavior when enabled
When `DIAGNOSTICS_ENABLED=true` (default), the bot will:
- **Create per-question trace directories** at `cache/trace/q{qid}/{run_id}/` (run_id is a UTC timestamp)
- **Save diagnostic artifacts** at each pipeline stage:
  - `00_raw_question.json` - Raw question object from Metaculus API
  - `01_normalized.json` - Normalized question with type inference and bounds extraction
  - `02_bounds_after_parse.json` - Parsed numeric bounds with type information (for numeric questions)
  - `02b_bounds_clamp.json` - Bounds clamping details if values were out of range
  - `10_llm_request_{n}.json` - LLM request details for each call (Authorization header redacted)
  - `11_llm_response_{n}.json` - Raw LLM response for each call
  - `12_parsed_output_{n}.json` - Parsed model output with parse warnings if any
  - `20_aggregate_input.json` - All worlds/forecasts before aggregation with their weights
  - `21_aggregate_output.json` - Aggregated forecast result
  - `diffs/diff_aggregate_output.json` - Diff of aggregate output vs previous run (if exists)
  - `30_submission_payload.json` - Forecast submission payload (Authorization header redacted)
  - `31_submission_response.json` - Submission response from Metaculus API
- **Upload trace artifacts** to GitHub Actions (available as downloadable `trace` artifact)
- **Automatically redact** Authorization headers and API keys in all saved artifacts

### Security note
All diagnostic artifacts automatically strip sensitive headers (`Authorization`, `api_key`, etc.) to prevent secrets from being written to disk or uploaded to GitHub Actions.

### Behavior when disabled
When `DIAGNOSTICS_ENABLED=false`, diagnostic tracing is completely bypassed. The bot operates normally without saving per-question trace artifacts. The existing `OPENROUTER_DEBUG` behavior is independent and continues to work as before.

## World Date Override (optional)
The bot can use an explicit date for world generation scenarios via the `WORLD_DATE` environment variable. By default, the bot infers the date from the question text (looking for years) or uses `current_year + 5`.

### Usage
**In `.env` file:**
```bash
# Force a specific date for all world scenarios
WORLD_DATE=2030-07-01
```

**Format:** `YYYY-MM-DD`

**Behavior:**
- If `WORLD_DATE` is set, all world scenarios use this exact date
- If not set, the bot searches for years (YYYY) in the question title/description
- If a year is found in range [current_year, 2100], uses `YYYY-07-01`
- Otherwise, defaults to `(current_year + 5)-01-01`

## Changing the Github automation
You can change which file is run in the GitHub automation by either changing the content of `main.py` to the contents of `main_with_no_framwork.py` (or another script) or by chaging all references to `main.py` to another script in `.github/workflows/run_bot_on_tournament.yaml` and related files.

## Editing in GitHub UI
Remember that you can edit a bot non locally by clicking on a file in Github, and then clicking the 'Edit this file' button. Whether you develop locally or not, when making edits, attempt to do things that you think others have not tried, as this will help further innovation in the field more than doing something that has already been done. Feel free to ask about what has or has not been tried in the Discord.

## Single Question Submission Workflow
You can manually test forecasts on individual Metaculus questions using the "Submit Single Question" workflow. This is useful for:
- Testing your bot on specific questions without running the full tournament
- Debugging forecast generation for particular question types
- Dry-run testing before actual submission

### Using the GitHub Actions Workflow
1. Go to the "Actions" tab in your repository
2. Select "Submit Single Question" from the workflow list
3. Click "Run workflow"
4. Fill in the inputs:
   - **qid** (required): The Metaculus question ID (e.g., 578)
   - **worlds** (optional): Number of MC worlds to generate (default: 100)
   - **publish** (optional): Check to actually submit the forecast to Metaculus (default: false for dry-run)
5. Click "Run workflow" to start

The workflow will:
- Fetch the question from Metaculus
- Classify the question type (binary, multiple_choice, or numeric)
- Generate MC worlds and aggregate forecasts
- Upload artifacts including:
  - `submit_smoke_payload.json` - The forecast payload (always created)
  - `mc_results.json` - Full forecast results
  - `mc_reasons.txt` - Reasoning bullets
  - `trace/` - Diagnostic traces (if diagnostics enabled)
  - `posted_ids.json` - Posted question IDs (only if publish=true)

### Using the CLI locally
You can also run single question forecasts from the command line:

**Dry-run mode (recommended for testing):**
```bash
poetry run python main.py --mode submit_smoke_test --qid 578 --worlds 100
```

**Actually submit the forecast:**
```bash
poetry run python main.py --mode submit_smoke_test --qid 578 --worlds 100 --publish
```

**Using environment variables:**
```bash
export QID=578
export WORLDS=100
export PUBLISH=true
poetry run python main.py --mode submit_smoke_test
```

The single question mode respects all existing environment variables (OPENROUTER_API_KEY, ASKNEWS_ENABLED, DIAGNOSTICS_ENABLED, etc.) and produces the same output artifacts as the workflow.

## Run/Edit the bot locally
Clone the repository. Find your terminal and run the following commands:
```bash
git clone https://github.com/Metaculus/metac-bot-template.git
```

If you forked the repository first, you have to replace the url in the `git clone` command with the url to your fork. Just go to your forked repository and copy the URL from the address bar in the browser.

### Installing dependencies
Make sure you have python and [poetry](https://python-poetry.org/docs/#installing-with-pipx) installed (poetry is a python package manager).

If you don't have poetry installed, run the below:
```bash
sudo apt update -y
sudo apt install -y pipx
pipx install poetry

# Optional
poetry config virtualenvs.in-project true
```

Inside the terminal, go to the directory you cloned the repository into and run the following command:
```bash
poetry install
```
to install all required dependencies.

### Setting environment variables

Running the bot requires various environment variables. If you run the bot locally, the easiest way to set them is to create a file called `.env` in the root directory of the repository (copy the `.env.template`).

### Running the bot

To test the simple bot, execute the following command in your terminal:
```bash
poetry run python main.py --mode test_questions
```
Make sure to set the environment variables as described above and to set the parameters in the code to your liking. In particular, to submit predictions, make sure that `submit_predictions` is set to `True` (it is set to `True` by default in main.py).

## Early Benchmarking
Provided in this project is an example of how to benchmark your bot's forecasts against the community prediction for questions on Metaculus. Running `community_benchmark.py` will run versions of your bot defined by you (e.g. with different LLMs or research paths) and score them on how close they are to the community prediction using expected baseline score (a proper score assuming the community prediction is the true probability). You will want to edit the file to choose which bot configurations you want to test and how many questions you want to test on. Any class inheriting from `forecasting-tools.Forecastbot` can be passed into the benchmarker. As of March 28, 2025 the benchmarker only works with binary questions.

To run a benchmark:
`poetry run python community_benchmark.py --mode run`

To run a custom benchmark (e.g. remove background info from questions to test retrieval):
`poetry run python community_benchmark.py --mode custom`

To view a UI showing your scores, statistical error bars, and your bot's reasoning:
`poetry run streamlit run community_benchmark.py`

See more information in the benchmarking section of the [forecasting-tools repo](https://github.com/Metaculus/forecasting-tools?tab=readme-ov-file#benchmarking)


## Example usage of /news and /deepnews:
If you are using AskNews, here is some useful example code.
```python
from asknews_sdk import AsyncAskNewsSDK
import asyncio

"""
More information available here:
https://docs.asknews.app/en/news
https://docs.asknews.app/en/deepnews

Installation:
pip install asknews
"""

client_id = ""
client_secret = ""

ask = AsyncAskNewsSDK(
    client_id=client_id,
    client_secret=client_secret,
    scopes=["chat", "news", "stories", "analytics"],
)

# /news endpoint example
async def search_news(query):

  hot_response = await ask.news.search_news(
      query=query, # your natural language query
      n_articles=5, # control the number of articles to include in the context
      return_type="both",
      strategy="latest news" # enforces looking at the latest news only
  )

  print(hot_response.as_string)

  # get context from the "historical" database that contains a news archive going back to 2023
  historical_response = await ask.news.search_news(
      query=query,
      n_articles=10,
      return_type="both",
      strategy="news knowledge" # looks for relevant news within the past 60 days
  )

  print(historical_response.as_string)

# /deepnews endpoint example:
async def deep_research(
    query, sources, model, search_depth=2, max_depth=2
):

    response = await ask.chat.get_deep_news(
        messages=[{"role": "user", "content": query}],
        search_depth=search_depth,
        max_depth=max_depth,
        sources=sources,
        stream=False,
        return_sources=False,
        model=model,
        inline_citations="numbered"
    )

    print(response)


if __name__ == "__main__":
    query = "What is the TAM of the global market for electric vehicles in 2025? With your final report, please report the TAM in USD using the tags <TAM> ... </TAM>"

    sources = ["asknews"]
    model = "deepseek-basic"
    search_depth = 2
    max_depth = 2
    asyncio.run(
        deep_research(
            query, sources, model, search_depth, max_depth
        )
    )

    asyncio.run(search_news(query))
```

Some tips for DeepNews:

You will get tags in your response, including:

<think> </think>
<asknews_search> </asknews_search>
<final_response> </final_response>

These tags are likely useful for extracting the pieces that you need for your pipeline. For example, if you don't want to include all the thinking/searching, you could just extract <final_response> </final_response>


## Ideas for bot improvements
Below are some ideas for making a novel bot.
- Finetuned LLM on Metaculus Data: Create an optimized prompt (using DSPY or a similar toolset) and/or a fine-tuned LLM using all past Metaculus data. The thought is that this will train the LLM to be well-calibrated on real-life questions. Consider knowledge cutoffs and data leakage from search providers.
- Dataset explorer: Create a tool that can find if there are datasets or graphs related to a question online, download them if they exist, and then run data science on them to answer a question.
- Question decomposer: A tool that takes a complex question and breaks it down into simpler questions to answer those instead
- Meta-Forecast Researcher: A tool that searches all major prediction markets, prediction aggregators, and possibly thought leaders to find relevant forecasts, and then combines them into an assessment for the current question (see [Metaforecast](https://metaforecast.org/)).
- Base rate researcher: Create a tool to find accurate base rates. There is an experimental version [here](https://forecasting-tools.streamlit.app/base-rate-generator) in [forecasting-tools](https://github.com/Metaculus/forecasting-tools) that works 50% of the time.
- Key factors researcher: Improve our experimental [key factors researcher](https://forecasting-tools.streamlit.app/key-factors) to find higher significance key factors for a given question.
- Monte Carlo Simulations: Experiment with combining some tools to run effective Monte Carlo simulations. This could include experimenting with combining Squiggle with the question decomposer.
- Adding personality diversity, LLM diversity, and other variations: Have GPT come up with a number of different ‘expert personalities’ or 'world-models' that it runs the forecasting bot with and then aggregates the median. Additionally, run the bot on different LLMs and see if the median of different LLMs improves the forecast. Finally, try simulating up to hundreds of personalities/LLM combinations to create large, diverse crowds. Each individual could have a backstory, thinking process, biases they are resistant to, etc. This will ideally improve accuracy and give more useful bot reasoning outputs to help humans reading the output consider things from multiple angles.
- Worldbuilding: Have GPT world build different future scenarios and then forecast all the different parts of those scenarios. It would then choose the most likely future world. In addition to a forecast, descriptions of future ‘worlds’ are created. This can take inspiration from Feinman paths.
- Consistency Forecasting: Forecast many tangential questions all at once (in a single prompt) and prompts for consistency rules.
- Extremize & Calibrate Predictions: Using the historical performance of a bot, adjust forecasts to be better calibrated. For instance, if predictions of 30% from the bot actually happen 40% of the time, then transform predictions of 30% to 40%.
- Assigning points to evidence: Starting with some ideas from a [blog post from Ozzie Gooen](https://forum.effectivealtruism.org/posts/mrAZFnEjsQAQPJvLh/using-points-to-rate-different-kinds-of-evidence), you could experiment with assigning ‘points’ to major types of evidence and having GPT categorize the evidence it finds related to a forecast so that the ‘total points’ can be calculated. This can then be turned into a forecast, and potentially optimized using machine learning on past Metaculus data.
- Search provider benchmark: Run bots using different combinations of search providers (e.g. Google, Bing, Exa.ai, Tavily, AskNews, Perplexity, etc) and search filters (e.g. only recent data, sites with a certain search rank, etc) and see if any specific one is better than others, or if using multiple of them makes a difference.
- Timeline researcher: Make a tool that can take a niche topic and make a timeline for all major and minor events relevant to that topic.
- Research Tools: Utilize the ComputerUse and DataAnalyzer tool from forecasting-tools for advanced analysis and to find/analyze datasets.
