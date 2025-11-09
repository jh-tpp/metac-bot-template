"""
Test pagination functionality in metaculus_posts.py
"""
import os
import sys
from unittest.mock import Mock, patch

print("="*70)
print("PAGINATION TEST: list_posts_from_tournament_all")
print("="*70)

# Set up environment
os.environ['OPENROUTER_API_KEY'] = 'test_key'
os.environ['METACULUS_TOKEN'] = 'test_token'

from metaculus_posts import list_posts_from_tournament_all

print("\nTest 1: Single page (< page_size results)")
print("-" * 60)

# Mock response with 30 posts (less than page_size of 50)
single_page_data = {
    "results": [{"id": i, "status": "open"} for i in range(30)]
}

with patch('metaculus_posts.list_posts_from_tournament') as mock_list:
    mock_list.return_value = single_page_data
    
    posts = list_posts_from_tournament_all(page_size=50, max_pages=40)
    
    # Should have called once and returned 30 posts
    assert mock_list.call_count == 1, f"Should call once for single page, called {mock_list.call_count}"
    assert len(posts) == 30, f"Should return 30 posts, got {len(posts)}"
    print(f"  ✓ Single page: {len(posts)} posts, {mock_list.call_count} API call")

print("\nTest 2: Multiple pages (exactly 2 pages)")
print("-" * 60)

# Mock responses for 2 pages
page1_data = {
    "results": [{"id": i, "status": "open"} for i in range(50)]
}
page2_data = {
    "results": [{"id": i+50, "status": "open"} for i in range(25)]
}

with patch('metaculus_posts.list_posts_from_tournament') as mock_list:
    # Return different data on each call
    mock_list.side_effect = [page1_data, page2_data]
    
    posts = list_posts_from_tournament_all(page_size=50, max_pages=40)
    
    # Should have called twice and returned 75 posts
    assert mock_list.call_count == 2, f"Should call twice for 2 pages, called {mock_list.call_count}"
    assert len(posts) == 75, f"Should return 75 posts, got {len(posts)}"
    
    # Verify offset parameters
    calls = mock_list.call_args_list
    assert calls[0][1]['offset'] == 0, "First call should have offset=0"
    assert calls[1][1]['offset'] == 50, "Second call should have offset=50"
    print(f"  ✓ Multiple pages: {len(posts)} posts, {mock_list.call_count} API calls")
    print(f"  ✓ Offset parameters: 0, 50")

print("\nTest 3: Max pages limit")
print("-" * 60)

# Mock responses that would go beyond max_pages
full_page_data = {
    "results": [{"id": i, "status": "open"} for i in range(50)]
}

with patch('metaculus_posts.list_posts_from_tournament') as mock_list:
    # Always return full page (would continue indefinitely)
    mock_list.return_value = full_page_data
    
    posts = list_posts_from_tournament_all(page_size=50, max_pages=3)
    
    # Should stop at max_pages
    assert mock_list.call_count == 3, f"Should stop at max_pages=3, called {mock_list.call_count}"
    assert len(posts) == 150, f"Should return 150 posts (3*50), got {len(posts)}"
    print(f"  ✓ Respects max_pages limit: {mock_list.call_count} calls, {len(posts)} posts")

print("\nTest 4: Empty first page")
print("-" * 60)

empty_data = {"results": []}

with patch('metaculus_posts.list_posts_from_tournament') as mock_list:
    mock_list.return_value = empty_data
    
    posts = list_posts_from_tournament_all(page_size=50, max_pages=40)
    
    # Should call once and return empty list
    assert mock_list.call_count == 1, f"Should call once for empty page, called {mock_list.call_count}"
    assert len(posts) == 0, f"Should return 0 posts, got {len(posts)}"
    print(f"  ✓ Empty results: {len(posts)} posts, {mock_list.call_count} API call")

print("\nTest 5: API error on second page")
print("-" * 60)

page1_ok = {"results": [{"id": i, "status": "open"} for i in range(50)]}

with patch('metaculus_posts.list_posts_from_tournament') as mock_list:
    # First call succeeds, second raises error
    mock_list.side_effect = [page1_ok, RuntimeError("API error")]
    
    posts = list_posts_from_tournament_all(page_size=50, max_pages=40)
    
    # Should return first page data and stop gracefully
    assert mock_list.call_count == 2, f"Should call twice (second fails), called {mock_list.call_count}"
    assert len(posts) == 50, f"Should return 50 posts from first page, got {len(posts)}"
    print(f"  ✓ Graceful error handling: {len(posts)} posts from first page")

print("\n" + "="*70)
print("✅ ALL PAGINATION TESTS PASSED")
print("="*70)
print("\nSummary:")
print("  ✓ Single page fetching works correctly")
print("  ✓ Multi-page pagination accumulates results")
print("  ✓ Offset parameters increment correctly")
print("  ✓ max_pages limit is respected")
print("  ✓ Empty results handled gracefully")
print("  ✓ API errors handled gracefully")
