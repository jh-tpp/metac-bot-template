"""
Official Posts API for fetching tournament data from Metaculus.

Uses the /api/posts/ endpoint per the official template to fetch open questions
from the Fall 2025 AIB tournament by slug, and returns (question_id, post_id) pairs.
"""
import os
import requests
from typing import List, Tuple, Dict, Any

API_BASE_URL = "https://www.metaculus.com/api"
METACULUS_TOKEN = os.getenv("METACULUS_TOKEN")
FALL_2025_AIB_TOURNAMENT = "fall-aib-2025"

AUTH_HEADERS = {"Authorization": f"Token {METACULUS_TOKEN}"} if METACULUS_TOKEN else {}


def list_posts_from_tournament(
    tournament_id: int | str = FALL_2025_AIB_TOURNAMENT,
    offset: int = 0,
    count: int = 50,
) -> Dict[str, Any]:
    """
    Fetch posts from a Metaculus tournament using /api/posts/ endpoint.
    
    Args:
        tournament_id: Tournament ID (int) or slug (str). Defaults to Fall 2025 AIB slug.
        offset: Pagination offset (default: 0)
        count: Number of posts to fetch (default: 50, max: 100)
    
    Returns:
        Response dict with 'results' list of posts
    
    Raises:
        RuntimeError: If request fails
    """
    params = {
        "limit": count,
        "offset": offset,
        "order_by": "-hotness",
        "forecast_type": ",".join(["binary", "multiple_choice", "numeric", "discrete"]),
        "tournaments": [tournament_id],
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
    tournament_id: int | str = FALL_2025_AIB_TOURNAMENT,
) -> List[Tuple[int, int]]:
    """
    Get list of (question_id, post_id) tuples for open questions in a tournament.
    
    Args:
        tournament_id: Tournament ID (int) or slug (str). Defaults to Fall 2025 AIB slug.
    
    Returns:
        List of (question_id, post_id) tuples
    """
    posts = list_posts_from_tournament(tournament_id=tournament_id)
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
