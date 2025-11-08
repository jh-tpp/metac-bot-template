"""
Official Posts API for fetching tournament data from Metaculus.

Uses the /api/posts/ endpoint per the official template to fetch open questions
from the Fall 2025 AIB tournament by slug, and returns (question_id, post_id) pairs.

IMPORTANT: Tournament Hardcoding
-------------------------------
This module enforces the use of the Fall 2025 AIB tournament (slug: "fall-aib-2025")
to ensure stability and prevent accidental environment variable overrides that could
cause incorrect tournament IDs (e.g., 3512) to be used in production.

The tournament is hardcoded and CANNOT be overridden via environment variables or
function parameters in production code paths. This prevents configuration errors
and ensures all forecasts are submitted to the correct tournament.
"""
import os
import requests
from typing import List, Tuple, Dict, Any

API_BASE_URL = "https://www.metaculus.com/api"
METACULUS_TOKEN = os.getenv("METACULUS_TOKEN")

# Hardcoded Fall 2025 AIB tournament slug - DO NOT override via environment variables
# This ensures all production forecasts target the correct tournament
FALL_2025_AIB_TOURNAMENT = "fall-aib-2025"

AUTH_HEADERS = {"Authorization": f"Token {METACULUS_TOKEN}"} if METACULUS_TOKEN else {}


def list_posts_from_tournament(
    tournament_id: int | str = None,
    offset: int = 0,
    count: int = 50,
) -> Dict[str, Any]:
    """
    Fetch posts from a Metaculus tournament using /api/posts/ endpoint.
    
    IMPORTANT: The tournament is hardcoded to Fall 2025 AIB ("fall-aib-2025").
    The tournament_id parameter is ignored and exists only for backward compatibility.
    
    Args:
        tournament_id: IGNORED - kept for backward compatibility only
        offset: Pagination offset (default: 0)
        count: Number of posts to fetch (default: 50, max: 100)
    
    Returns:
        Response dict with 'results' list of posts
    
    Raises:
        RuntimeError: If request fails
    """
    # Always use hardcoded tournament - ignore parameter
    actual_tournament = FALL_2025_AIB_TOURNAMENT
    
    params = {
        "limit": count,
        "offset": offset,
        "order_by": "-hotness",
        "forecast_type": ",".join(["binary", "multiple_choice", "numeric", "discrete"]),
        "tournaments": [actual_tournament],
        "statuses": "open",
        "include_description": "true",
    }
    url = f"{API_BASE_URL}/posts/"
    resp = requests.get(url, headers=AUTH_HEADERS, params=params, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to list posts: {resp.status_code} {resp.text}"
        )
    return resp.json()


def get_open_question_ids_from_tournament(
    tournament_id: int | str = None,
) -> List[Tuple[int, int]]:
    """
    Get list of (question_id, post_id) tuples for open questions in a tournament.
    
    IMPORTANT: The tournament is hardcoded to Fall 2025 AIB ("fall-aib-2025").
    The tournament_id parameter is ignored and exists only for backward compatibility.
    
    Args:
        tournament_id: IGNORED - kept for backward compatibility only
    
    Returns:
        List of (question_id, post_id) tuples from Fall 2025 AIB tournament
    """
    # Always use hardcoded tournament - ignore parameter
    posts = list_posts_from_tournament()
    pairs: List[Tuple[int, int]] = []
    for post in posts.get("results", []):
        q = post.get("question")
        if q and q.get("status") == "open":
            pairs.append((q["id"], post["id"]))
    return pairs


def get_post_details(post_id: int) -> Dict[str, Any]:
    """
    Fetch detailed information for a specific post.
    
    Args:
        post_id: Metaculus post ID
    
    Returns:
        Post dict with full details
    
    Raises:
        RuntimeError: If request fails
    """
    url = f"{API_BASE_URL}/posts/{post_id}/"
    resp = requests.get(url, headers=AUTH_HEADERS, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to get post details {post_id}: {resp.status_code} {resp.text}"
        )
    return resp.json()
