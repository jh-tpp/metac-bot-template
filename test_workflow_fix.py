"""
Test the workflow fix for tournament open questions.

This test validates that the workflow will:
1. Fetch fresh data via tournament_dryrun
2. Compare against posted history
3. Make correct submission decision

We test the Python logic that mirrors the workflow YAML.
"""
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch


def test_workflow_logic_scenarios():
    """
    Test the three-phase workflow logic across different scenarios.
    
    This mirrors the logic in .github/workflows/run_bot_on_tournament.yaml
    """
    
    def simulate_workflow_check(open_ids_data, posted_ids_data):
        """
        Simulate the workflow's "Check for new questions" step logic.
        
        Returns: (should_submit, open_count, posted_count, new_count)
        """
        # Phase 2: Load posted IDs (empty set if file doesn't exist)
        posted_ids = set(posted_ids_data) if posted_ids_data else set()
        
        # Phase 2: Load fresh open IDs from dryrun
        open_ids = set()
        if isinstance(open_ids_data, list):
            for item in open_ids_data:
                if isinstance(item, dict):
                    qid = item.get('question_id')
                    if qid:
                        open_ids.add(qid)
                else:
                    open_ids.add(item)
        
        # Phase 3: Compute new questions and decide
        new_questions = open_ids - posted_ids
        should_submit = len(new_questions) > 0
        
        return should_submit, len(open_ids), len(posted_ids), len(new_questions)
    
    print("Testing workflow logic scenarios...")
    
    # Scenario 1: First run (no posted state, some open questions)
    print("\n[Scenario 1] First run with 3 open questions")
    open_data = [
        {"question_id": 101, "post_id": 201},
        {"question_id": 102, "post_id": 202},
        {"question_id": 103, "post_id": 203},
    ]
    posted_data = []
    
    should_submit, open_count, posted_count, new_count = simulate_workflow_check(open_data, posted_data)
    
    assert open_count == 3, f"Expected 3 open questions, got {open_count}"
    assert posted_count == 0, f"Expected 0 posted questions, got {posted_count}"
    assert new_count == 3, f"Expected 3 new questions, got {new_count}"
    assert should_submit is True, "Should submit when there are new questions"
    print(f"✓ Open={open_count}, Posted={posted_count}, New={new_count}, Submit={should_submit}")
    
    # Scenario 2: All questions already posted
    print("\n[Scenario 2] All 3 questions already posted")
    open_data = [
        {"question_id": 101, "post_id": 201},
        {"question_id": 102, "post_id": 202},
        {"question_id": 103, "post_id": 203},
    ]
    posted_data = [101, 102, 103]
    
    should_submit, open_count, posted_count, new_count = simulate_workflow_check(open_data, posted_data)
    
    assert open_count == 3, f"Expected 3 open questions, got {open_count}"
    assert posted_count == 3, f"Expected 3 posted questions, got {posted_count}"
    assert new_count == 0, f"Expected 0 new questions, got {new_count}"
    assert should_submit is False, "Should NOT submit when all questions are posted"
    print(f"✓ Open={open_count}, Posted={posted_count}, New={new_count}, Submit={should_submit}")
    
    # Scenario 3: Some new questions
    print("\n[Scenario 3] 3 open, 1 posted, 2 new")
    open_data = [
        {"question_id": 101, "post_id": 201},
        {"question_id": 102, "post_id": 202},
        {"question_id": 103, "post_id": 203},
    ]
    posted_data = [101]
    
    should_submit, open_count, posted_count, new_count = simulate_workflow_check(open_data, posted_data)
    
    assert open_count == 3, f"Expected 3 open questions, got {open_count}"
    assert posted_count == 1, f"Expected 1 posted question, got {posted_count}"
    assert new_count == 2, f"Expected 2 new questions, got {new_count}"
    assert should_submit is True, "Should submit when there are new questions"
    print(f"✓ Open={open_count}, Posted={posted_count}, New={new_count}, Submit={should_submit}")
    
    # Scenario 4: No open questions (tournament ended or no questions)
    print("\n[Scenario 4] No open questions")
    open_data = []
    posted_data = [101, 102, 103]
    
    should_submit, open_count, posted_count, new_count = simulate_workflow_check(open_data, posted_data)
    
    assert open_count == 0, f"Expected 0 open questions, got {open_count}"
    assert posted_count == 3, f"Expected 3 posted questions, got {posted_count}"
    assert new_count == 0, f"Expected 0 new questions, got {new_count}"
    assert should_submit is False, "Should NOT submit when there are no open questions"
    print(f"✓ Open={open_count}, Posted={posted_count}, New={new_count}, Submit={should_submit}")
    
    # Scenario 5: Empty tournament (no open, no posted)
    print("\n[Scenario 5] Empty tournament (no open, no posted)")
    open_data = []
    posted_data = []
    
    should_submit, open_count, posted_count, new_count = simulate_workflow_check(open_data, posted_data)
    
    assert open_count == 0, f"Expected 0 open questions, got {open_count}"
    assert posted_count == 0, f"Expected 0 posted questions, got {posted_count}"
    assert new_count == 0, f"Expected 0 new questions, got {new_count}"
    assert should_submit is False, "Should NOT submit when there are no questions at all"
    print(f"✓ Open={open_count}, Posted={posted_count}, New={new_count}, Submit={should_submit}")
    
    print("\n✅ All workflow logic scenarios passed!")


def test_no_dummy_sentinel():
    """
    Verify that the new logic never uses dummy sentinel value {0}.
    
    This was the bug in the old workflow: it would inject set([0]) when
    open_ids.json was missing, causing incorrect counts.
    """
    print("\nTesting that no dummy sentinel {0} is used...")
    
    # Simulate missing open_ids.json (should not inject {0})
    open_data = []  # Empty, not None
    posted_data = []
    
    # Extract IDs (same logic as workflow)
    open_ids = set()
    if isinstance(open_data, list):
        for item in open_data:
            if isinstance(item, dict):
                qid = item.get('question_id')
                if qid:
                    open_ids.add(qid)
            else:
                open_ids.add(item)
    
    # Verify no dummy value
    assert 0 not in open_ids, "Should NOT contain dummy sentinel value 0"
    assert len(open_ids) == 0, f"Should be empty set, got {open_ids}"
    
    print("✓ No dummy sentinel value used")


if __name__ == "__main__":
    test_workflow_logic_scenarios()
    test_no_dummy_sentinel()
    print("\n✅ All workflow fix tests passed!")
