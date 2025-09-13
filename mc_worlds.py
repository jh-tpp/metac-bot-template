# mc_worlds.py
from typing import List, Dict, Any
import json, math, datetime as dt, textwrap

WORLD_PROMPT = """You are sampling ONE plausible future 'world' consistent with the facts below.
Return ONLY JSON matching the 'output_schema' exactly.

facts (dated, compact). Each line is tagged with a local key and type:
- format: [Qxx|TYPE] YYYY-MM-DD: short fact (source or hint)
- TYPE in {bin, mc, num, date}; mc may include k=#
{facts}

output_schema (strict):
{{
  "world_summary": "100-150 word narrative of the world dynamics",
  "per_question": [
    {{
      "key": "Qxx",
      "type": "binary|multiple_choice|numeric|date",
      "outcome": {{
        "binary": {{"yes": true/false}},
        "multiple_choice": {{"option_index": <int>}},  // 0-based
        "numeric": {{"value": <number>}},              // units from facts tag
        "date": {{"iso_date": "YYYY-MM-DD"}}
      }}
    }}
  ]
}}
- Include exactly one entry per Qxx appearing in facts.
- Keep outputs coherent with the facts; if uncertain, be conservative.
- JSON only, no commentary.
"""

def build_batch_digest(batch_questions: List[Dict[str, Any]],
                       research: Dict[str, List[str]],
                       id2key: Dict[str,str],
                       key_specs: Dict[str,dict]) -> Dict[str, str]:
    """
    research[qid] -> list of short fact bullets (already trimmed).
    Produces facts like: "- [Q03|mc k=4] 2025-09-12: … (src)"
    """
    lines = []
    for q in batch_questions:
        qid = str(q["id"]); key = id2key[qid]; spec = key_specs[key]
        t = spec["type"]
        tag = {"binary":"bin","multiple_choice":"mc","numeric":"num","date":"date"}[t]
        extra = ""
        if t == "multiple_choice" and spec["k"]:
            extra = f" k={spec['k']}"
        if t == "numeric" and spec["units"]:
            extra = f" units={spec['units']}"
        for b in (research.get(qid, [])[:5] or ["(no recent facts)"]):
            # Expect bullets already like "2025-09-11: text (url)" — ok if not perfect.
            lines.append(f"- [{key}|{tag}{extra}] {b}")
    facts = "\n".join(lines[:80])  # keep prompt lean
    return {"facts": facts}

def sample_one_world(llm_call, digest: Dict[str, str]) -> Dict[str, Any]:
    # llm_call(prompt: str) -> str  (JSON string)
    out = llm_call(WORLD_PROMPT.format(**digest))
    return json.loads(out)

def aggregate_worlds(batch_questions: List[Dict[str, Any]],
                     world_samples: List[Dict[str, Any]],
                     key2id: Dict[str,str],
                     key_specs: Dict[str,dict]) -> Dict[str, Dict[str, Any]]:
    by_q = {key2id[k]: {"type": v["type"], "samples": [], "mc_k": v.get("k")} for k,v in key_specs.items()}
    for w in world_samples:
        for item in w["per_question"]:
            key = item["key"]
            qid = key2id.get(key)
            if not qid: continue
            t = by_q[qid]["type"]
            oc = item["outcome"]
            if t == "binary":
                by_q[qid]["samples"].append(1.0 if oc["binary"]["yes"] else 0.0)
            elif t == "multiple_choice":
                by_q[qid]["samples"].append(int(oc["multiple_choice"]["option_index"]))
            elif t == "numeric":
                by_q[qid]["samples"].append(float(oc["numeric"]["value"]))
            elif t == "date":
                by_q[qid]["samples"].append(oc["date"]["iso_date"])

    forecasts = {}
    for qid, d in by_q.items():
        t = d["type"]; xs = d["samples"]; n = max(1, len(xs))
        if t == "binary":
            p = sum(xs)/n
            forecasts[qid] = {"binary": {"p": max(0.001, min(0.999, p))}}
        elif t == "multiple_choice":
            k = d["mc_k"] or (max(xs)+1 if xs else 1)
            counts = [0]*k
            for i in xs: 
                if 0 <= i < k: counts[i]+=1
            probs = [c/n for c in counts]
            forecasts[qid] = {"multiple_choice": {"probs": probs}}
        elif t == "numeric":
            vals = sorted(xs)
            lo, hi = (vals[0], vals[-1]) if vals else (0.0, 1.0)
            def ecdf(v): 
                return 0.0 if not vals else sum(1 for z in vals if z <= v)/n
            grid = [lo + (hi-lo)*i/200.0 for i in range(201)]
            cdf = [min(1.0, max(0.0, ecdf(g))) for g in grid]
            forecasts[qid] = {"numeric": {"grid": grid, "cdf": cdf}}
        elif t == "date":
            ords = sorted([dt.date.fromisoformat(s).toordinal() for s in xs]) if xs else [dt.date.today().toordinal()]
            def ecdf(o): return sum(1 for z in ords if z <= o)/n
            lo, hi = ords[0], ords[-1]
            grid = [int(round(lo + (hi-lo)*i/200.0)) for i in range(201)]
            cdf = [ecdf(g) for g in grid]
            forecasts[qid] = {"date": {"grid_ord": grid, "cdf": cdf}}
    return forecasts

def make_comment(n_worlds:int, drivers:List[str], base_rate:str) -> str:
    d = "; ".join(drivers[:3]) if drivers else "mixed macro/tech drivers"
    br = base_rate or "base rates considered"
    return (f"Method: {n_worlds} scenario draws; forecast = empirical frequency/ECDF. "
            f"Key drivers: {d}. Sanity: {br}. Update on major news shocks.")
