# keying.py
from typing import List, Dict, Any, Tuple

def make_keymaps(batch_questions: List[Dict[str, Any]]) -> Tuple[Dict[str,str], Dict[str,str], Dict[str,dict]]:
    """
    Returns:
      id2key: {real_id -> 'Q01'}
      key2id: {'Q01' -> real_id}
      key_specs: {'Q01': {'type':'binary'|'multiple_choice'|'numeric'|'date', 'k':int|None, 'units':str|None}}
    """
    id2key, key2id, key_specs = {}, {}, {}
    for i, q in enumerate(batch_questions, start=1):
        key = f"Q{i:02d}"
        qid = str(q["id"])
        id2key[qid] = key
        key2id[key] = qid
        qtype = q["type"]
        spec = {"type": qtype, "k": None, "units": None}
        if qtype == "multiple_choice":
            spec["k"] = len(q.get("options", [])) or None
        if qtype == "numeric":
            spec["units"] = q.get("units")
        key_specs[key] = spec
    return id2key, key2id, key_specs
