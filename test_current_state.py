"""Test current state to understand the issue"""
import requests
import json

# Test questions from the problem statement
test_qids = [578, 14333, 22427]

METACULUS_API_BASE = "https://www.metaculus.com/api2/questions/"

for qid in test_qids:
    print(f"\n{'='*70}")
    print(f"Testing Q{qid}")
    print('='*70)
    
    try:
        url = f"{METACULUS_API_BASE}{qid}/"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        # Check top-level keys
        print(f"Top-level keys: {list(data.keys())[:10]}")
        
        # Check if 'question' key exists
        if 'question' in data:
            print("✓ 'question' key found at top level")
            q = data['question']
            print(f"  Keys in nested 'question': {list(q.keys())[:10]}")
            
            # Check for possibilities/possibility
            if 'possibilities' in q:
                print(f"  ✓ 'possibilities' found in nested question")
                poss = q['possibilities']
                if isinstance(poss, dict):
                    print(f"    Type: {poss.get('type', 'N/A')}")
                    print(f"    Keys: {list(poss.keys())}")
                elif isinstance(poss, list):
                    print(f"    List of {len(poss)} items")
                    if poss:
                        print(f"    First item type: {poss[0].get('type', 'N/A') if isinstance(poss[0], dict) else 'N/A'}")
            elif 'possibility' in q:
                print(f"  ✓ 'possibility' found in nested question")
                poss = q['possibility']
                print(f"    Type: {poss.get('type', 'N/A') if isinstance(poss, dict) else 'N/A'}")
            else:
                print("  ✗ Neither 'possibilities' nor 'possibility' found in nested question")
        else:
            print("✗ No 'question' key at top level")
            
        # Check top-level possibility/possibilities
        if 'possibilities' in data:
            print("  'possibilities' found at TOP level")
        if 'possibility' in data:
            print("  'possibility' found at TOP level")
            
    except Exception as e:
        print(f"ERROR: {e}")

print("\n" + "="*70)
print("Test complete")
