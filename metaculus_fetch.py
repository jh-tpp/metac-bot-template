"""
Unified, resilient fetch module for Metaculus questions/posts.

Resolves 403 errors by adding Authorization header when METACULUS_TOKEN is present.
Prefers /api/posts/{post_id}/, falls back to /api/posts/{question_id}/, then /api/questions/{question_id}/.
Includes light retries and optional HTTP logging via http_logging.
"""
import os
import time
import requests
from typing import Optional, Dict, Any
from http_logging import (
    print_http_request,
    print_http_response,
    prepare_request_artifact,
    prepare_response_artifact,
    save_http_artifacts,
)

API_BASE = "https://www.metaculus.com/api"
TOKEN = os.getenv("METACULUS_TOKEN")

COMMON_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "metac-bot-template/1.1",
}
if TOKEN:
    COMMON_HEADERS["Authorization"] = f"Token {TOKEN}"


class FetchError(RuntimeError):
    """Raised when fetch operations fail after retries."""
    pass


def _attempt_get(url: str, params=None, max_retries=2, backoff=1.5) -> requests.Response:
    """
    Attempt HTTP GET with retries for transient errors.
    
    Args:
        url: Full URL to fetch
        params: Query parameters dict
        max_retries: Maximum number of retry attempts (default: 2)
        backoff: Backoff multiplier for retry delays (default: 1.5)
    
    Returns:
        requests.Response object
    
    Raises:
        requests.RequestException: On network errors after retries
        FetchError: On persistent failures
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        print_http_request(method="GET", url=url, headers=COMMON_HEADERS, params=params, timeout=30)
        req_art = prepare_request_artifact(method="GET", url=url, params=params, timeout=30)
        try:
            resp = requests.get(url, headers=COMMON_HEADERS, params=params, timeout=30)
            print_http_response(resp)
            resp_art = prepare_response_artifact(resp)
            save_http_artifacts(f"fetch_{url.rsplit('/', 1)[-1]}", req_art, resp_art)
            
            # Retry on specific transient errors
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt < max_retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(backoff * (attempt + 1))
    
    if last_exc:
        raise last_exc
    raise FetchError(f"Failed to GET {url}")


def fetch_post(post_id: int) -> Dict[str, Any]:
    """
    Fetch a Metaculus post by ID.
    
    Args:
        post_id: Metaculus post ID
    
    Returns:
        Post dict (includes 'question' field for question posts)
    
    Raises:
        FetchError: If fetch fails or returns non-OK status
    """
    url = f"{API_BASE}/posts/{post_id}/"
    resp = _attempt_get(url)
    if not resp.ok:
        raise FetchError(f"POST {post_id} fetch failed {resp.status_code}")
    return resp.json()


def fetch_question(question_id: int) -> Dict[str, Any]:
    """
    Fetch a Metaculus question by ID.
    
    Args:
        question_id: Metaculus question ID
    
    Returns:
        Question dict
    
    Raises:
        FetchError: If fetch fails or returns non-OK status
    """
    url = f"{API_BASE}/questions/{question_id}/"
    resp = _attempt_get(url)
    if not resp.ok:
        raise FetchError(f"QUESTION {question_id} fetch failed {resp.status_code}")
    return resp.json()


def fetch_question_with_fallback(
    question_id: int, post_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetch question data with resilient fallback paths.
    
    Preferred path: /posts/{post_id}/ (if given) -> returns 'question' field.
    Fallback paths:
      1. If post_id is None, try /posts/{question_id}/ (often post_id==question_id)
      2. Then /questions/{question_id}/
    
    Args:
        question_id: Metaculus question ID
        post_id: Optional Metaculus post ID
    
    Returns:
        Post-like dict containing 'question' field
    
    Raises:
        FetchError: If all fetch paths fail
    """
    errors = []
    
    # Try post_id if provided
    if post_id is not None:
        try:
            post = fetch_post(post_id)
            if "question" in post:
                return post
        except Exception as e:
            errors.append(f"post {post_id}: {e}")
    
    # Try post endpoint with question_id (often post_id==question_id)
    try:
        post = fetch_post(question_id)
        if "question" in post:
            return post
    except Exception as e:
        errors.append(f"post==question_id {question_id}: {e}")
    
    # Try question endpoint as last resort
    try:
        q = fetch_question(question_id)
        return {"id": question_id, "question": q}
    except Exception as e:
        errors.append(f"question endpoint {question_id}: {e}")
        raise FetchError(
            f"All fetch paths failed for Q{question_id}: {' | '.join(errors)}"
        )
