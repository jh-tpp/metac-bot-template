# mc_worlds.py
from typing import List, Dict, Any, Tuple
import json
import datetime as dt

# --- MC smoothing / clamps ---
BINARY_LAPLACE_ALPHA = 1.0   # Beta(1,1) Laplace smoothing
BINARY_LAPLACE_BETA  = 1.0
PROB_FLOOR = 0.01            # final clamp for binary probs
PROB_CEIL  = 0.99

MC_DIRICHLET_ALPHA = 0.5     # add-0.5 to each MC option before normalizing


WORLD_PROMPT = """You are sampling ONE plausible future 'world' consistent with the facts below.
Return ONLY JSON matching the 'output_schema' exactly.

facts (dated, compact). Each line is tagged with a local key and type:
- format: [Qxx|TYPE] YYYY-MM-DD: short fact (source or hint)
- TYPE in {{bin, mc, num, date}}; mc may include k=#
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
        "multiple_choice": {{"option_index": <int>}},  # 0-based
        "numeric": {{"value": <number>}},
        "date": {{"iso_date": "YYYY-MM-DD"}}
      }}
    }}
  ]
}}
- Include exactly one entry per Qxx appearing in facts.
- Keep outputs coherent with the facts; if uncertain, be conservative.
- JSON only, no commentary.
"""

# ---------- helpers (all local so this file has no external deps) ----------

def extract_evidence(worlds, key2id):
    """
    Build per-question evidence buckets from world samples.
    Returns: dict[qid] -> {
        'binary_yes': [summary...],
        'binary_no':  [summary...],
        'mc':         {opt_idx: [summary...]},
        'numeric':    [(value, summary)...],
        'date':       [(iso_date, summary)...],
    }
    """
    ev = {}
    for w in worlds:
        summary = w.get("world_summary", "")
        for item in w.get("per_question", []):
            key = item.get("key")
            qid = key2id.get(key)
            if not qid:
                continue
            d = ev.setdefault(qid, {"binary_yes": [], "binary_no": [], "mc": {}, "numeric": [], "date": []})
            t = item.get("type")
            oc = item.get("outcome", {})
            if t == "binary":
                yes = bool(oc.get("binary", {}).get("yes"))
                (d["binary_yes"] if yes else d["binary_no"]).append(summary)
            elif t == "multiple_choice":
                idx = int(oc.get("multiple_choice", {}).get("option_index", 0))
                d["mc"].setdefault(idx, []).append(summary)
            elif t == "numeric":
                val = float(oc.get("numeric", {}).get("value", 0.0))
                d["numeric"].append((val, summary))
            elif t == "date":
                iso = oc.get("date", {}).get("iso_date")
                d["date"].append((iso, summary))
    return ev


def _make_keymaps(batch_questions):
    id2key, key2id, key_specs = {}, {}, {}
    for i, q in enumerate(batch_questions, start=1):
        key = f"Q{i:02d}"
        qid = str(q["id"])
        qtype = q["type"]
        id2key[qid] = key
        key2id[key] = qid
        spec = {"type": qtype, "k": None, "units": None}
        if qtype == "multiple_choice":
            # accept explicit k from q or infer from q["options"]
            spec["k"] = q.get("k") or (len(q.get("options", [])) if isinstance(q.get("options"), list) else None)
        if qtype == "numeric":
            spec["units"] = q.get("units")
        key_specs[key] = spec
    return id2key, key2id, key_specs

def build_batch_digest(
    batch_questions: List[Dict[str, Any]],
    research: Dict[str, List[str]],
    id2key: Dict[str, str],
    key_specs: Dict[str, dict],
) -> Dict[str, str]:
    """Build the compact 'facts' block for the prompt. No real IDs leak."""
    lines: List[str] = []
    for q in batch_questions:
        qid = str(q["id"])
        key = id2key[qid]
        spec = key_specs[key]
        t = spec["type"]
        tag = {"binary": "bin", "multiple_choice": "mc", "numeric": "num", "date": "date"}[t]
        extra = ""
        if t == "multiple_choice" and spec["k"]:
            extra = f" k={spec['k']}"
        if t == "numeric" and spec["units"]:
            extra = f" units={spec['units']}"
        bullets = research.get(qid, [])[:5] or ["(no recent facts)"]
        for b in bullets:
            lines.append(f"- [{key}|{tag}{extra}] {b}")
    return {"facts": "\n".join(lines[:80])}

def _extract_json(s: str) -> str:
    """Be tolerant if the model wraps JSON in code fences or text."""
    start = s.find("{")
    end = s.rfind("}")
    return s[start:end + 1] if start != -1 and end != -1 else s

def sample_one_world(llm_call, digest: Dict[str, str]) -> Dict[str, Any]:
    out = llm_call(WORLD_PROMPT.format(**digest))
    return json.loads(_extract_json(out))

def aggregate_worlds(
    batch_questions: List[Dict[str, Any]],
    world_samples: List[Dict[str, Any]],
    key2id: Dict[str, str],
    key_specs: Dict[str, dict],
) -> Dict[str, Dict[str, Any]]:
    """Return per-question forecasts keyed by REAL qid strings."""
    by_q: Dict[str, Dict[str, Any]] = {
        key2id[k]: {"type": v["type"], "samples": [], "mc_k": v.get("k")} for k, v in key_specs.items()
    }
    # collect samples
    for w in world_samples:
        for item in w.get("per_question", []):
            key = item.get("key")
            qid = key2id.get(key)
            if not qid:
                continue
            t = by_q[qid]["type"]
            oc = item.get("outcome", {})
            if t == "binary":
                by_q[qid]["samples"].append(1.0 if oc.get("binary", {}).get("yes") else 0.0)
            elif t == "multiple_choice":
                by_q[qid]["samples"].append(int(oc.get("multiple_choice", {}).get("option_index", 0)))
            elif t == "numeric":
                by_q[qid]["samples"].append(float(oc.get("numeric", {}).get("value", 0.0)))
            elif t == "date":
                by_q[qid]["samples"].append(oc.get("date", {}).get("iso_date"))

    # aggregate
    forecasts: Dict[str, Dict[str, Any]] = {}
    for qid, d in by_q.items():
        t = d["type"]
        xs = d["samples"]
        n = max(1, len(xs))
        if t == "binary":
          # Laplace smoothing so 0/n and n/n don't hit 0 or 1
          k = sum(xs)
          alpha = BINARY_LAPLACE_ALPHA
          beta  = BINARY_LAPLACE_BETA
          p = (k + alpha) / (n + alpha + beta)
          p = max(PROB_FLOOR, min(PROB_CEIL, p))
          forecasts[qid] = {"binary": {"p": p}}
        elif t == "multiple_choice":
            k = d["mc_k"] or (max(xs) + 1 if xs else 1)
            counts = [0] * k
            for i in xs:
                if 0 <= i < k:
                    counts[i] += 1
            # Dirichlet smoothing so empty/rare options get >0 mass
            k_opts = k
            counts = [c + MC_DIRICHLET_ALPHA for c in counts]
            total = sum(counts)
            probs = [c/total for c in counts]
            forecasts[qid] = {"multiple_choice": {"probs": probs}}
        elif t == "numeric":
            vals = sorted(xs)
            if not vals:
                vals = [0.0]
            lo, hi = vals[0], vals[-1]
            def ecdf(v): return sum(1 for z in vals if z <= v) / len(vals)
            grid = [lo + (hi - lo) * i / 200.0 for i in range(201)]
            cdf = [min(1.0, max(0.0, ecdf(g))) for g in grid]
            forecasts[qid] = {"numeric": {"grid": grid, "cdf": cdf}}
        elif t == "date":
            if not xs:
                xs = [dt.date.today().isoformat()]
            ords = sorted([dt.date.fromisoformat(s).toordinal() for s in xs])
            def ecdf(o): return sum(1 for z in ords if z <= o) / len(ords)
            lo, hi = ords[0], ords[-1]
            grid = [int(round(lo + (hi - lo) * i / 200.0)) for i in range(201)]
            cdf = [ecdf(g) for g in grid]
            forecasts[qid] = {"date": {"grid_ord": grid, "cdf": cdf}}
    return forecasts

def make_comment(n_worlds: int, drivers: List[str], base_rate: str) -> str:
    d = "; ".join(drivers[:3]) if drivers else "mixed macro/tech drivers"
    br = base_rate or "base rates considered"
    return (
        f"Method: {n_worlds} scenario draws; forecast = empirical frequency/ECDF. "
        f"Key drivers: {d}. Sanity: {br}. Update on major news shocks."
    )

# ---------- exported: run_mc_worlds ----------

def run_mc_worlds(
    open_questions: List[Dict[str, Any]],
    research_by_q: Dict[str, List[str]],
    llm_call,
    n_worlds: int = 3,
    batch_size: int = 12,
    return_evidence: bool = False,
) -> Dict[str, Dict[str, Any]] | tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Batch questions, sample n_worlds per batch, print progress,
    and return forecasts keyed by REAL qid.
    If return_evidence=True, also return per-qid evidence buckets.
    """
    results: Dict[str, Dict[str, Any]] = {}
    evidence_by_q: Dict[str, Any] = {}  # <-- moved outside the loop to accumulate across batches

    total_attempted = 0
    total_success  = 0

    for i in range(0, len(open_questions), batch_size):
        batch = open_questions[i:i + batch_size]
        id2key, key2id, key_specs = _make_keymaps(batch)
        digest = build_batch_digest(batch, research_by_q, id2key, key_specs)
        print("[MC] DIGEST START\n" + digest["facts"] + "\n[MC] DIGEST END")

        worlds = []
        for j in range(n_worlds):
            total_attempted += 1
            try:
                worlds.append(sample_one_world(llm_call, digest))
                total_success += 1
            except Exception as e:
                print(f"[MC][WARN] world {j+1}/{n_worlds} failed: {e}")

        forecasts = aggregate_worlds(batch, worlds, key2id, key_specs)

        # collect + merge evidence for this batch
        ev = extract_evidence(worlds, key2id)
        for qid, buckets in ev.items():
            dst = evidence_by_q.setdefault(
                qid, {"binary_yes": [], "binary_no": [], "mc": {}, "numeric": [], "date": []}
            )
            dst["binary_yes"].extend(buckets["binary_yes"])
            dst["binary_no"].extend(buckets["binary_no"])
            for opt, arr in buckets["mc"].items():
                dst["mc"].setdefault(opt, []).extend(arr)
            dst["numeric"].extend(buckets["numeric"])
            dst["date"].extend(buckets["date"])

        print(f"[MC] Batch {i // batch_size + 1}: {len(worlds)} worlds")
        for q in batch:
            qid = str(q["id"])
            if qid in forecasts:
                print(f"[MC] {id2key[qid]} -> {forecasts[qid]}")
                results[qid] = forecasts[qid]

    print(f"[MC] TOTAL scenarios: {total_success}/{total_attempted} successful")
    return (results, evidence_by_q) if return_evidence else results


