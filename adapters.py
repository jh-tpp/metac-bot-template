# adapters.py
from typing import Dict, Any, List
import datetime as dt

def _ecdf_on_grid(samples: List[float], grid: List[float]) -> List[float]:
    if not samples:
        return [0.0]*len(grid)
    xs = sorted(samples)
    n = len(xs)
    out = []
    j = 0
    for x in grid:
        while j < n and xs[j] <= x:
            j += 1
        out.append(j / n)
    return out

def _dates_to_ord(ds: List[str]) -> List[int]:
    return [dt.date.fromisoformat(s).toordinal() for s in ds]

def to_submission_payload(q_meta: Dict[str, Any], mc_fore: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a dict ready for submit(). We keep names generic; you’ll match them
    to the template’s expected keys where submit happens.
    q_meta should include type and (for continuous) a 201-point grid from the question.
    """
    qtype = q_meta["type"]

    if qtype == "binary":
        p = float(mc_fore["binary"]["p"])
        return {"kind": "binary", "p": max(0.001, min(0.999, p))}

    if qtype == "multiple_choice":
        probs = list(mc_fore["multiple_choice"]["probs"])
        # normalize & pad/trim to k options from metadata
        k = len(q_meta.get("options", [])) or len(probs)
        probs = probs[:k] + [0.0]*max(0, k - len(probs))
        s = sum(probs) or 1.0
        probs = [x/s for x in probs]
        return {"kind": "multiple_choice", "probs": probs}

    if qtype in ("numeric", "date"):
        # Use the question’s official 201-point grid from metadata
        grid = q_meta.get("grid")  # list of 201 floats for numeric; for date often epoch days/ISO
        if grid is None:
            raise ValueError(f"No 201-point grid in q_meta for {q_meta.get('id')}")
        if qtype == "numeric":
            samples = mc_fore.get("numeric", {}).get("samples")  # if you stored raw samples
            if samples is None:
                # or map from our placeholder grid/cdf if that’s what you logged
                samples = mc_fore["numeric"].get("raw_samples", [])
            cdf = _ecdf_on_grid(samples, grid)
            return {"kind": "continuous", "x": grid, "y": cdf}
        else:
            # date: map ISO samples to ordinals to compare with grid (ordinals or epoch-days)
            samples_iso = mc_fore.get("date", {}).get("samples", [])
            samples_ord = _dates_to_ord(samples_iso)
            # If grid is ISO strings, convert to ordinals; if numeric days, leave as is
            if isinstance(grid[0], str):
                grid_ord = _dates_to_ord(grid)
            else:
                grid_ord = grid
            cdf = _ecdf_on_grid(samples_ord, grid_ord)
            return {"kind": "continuous", "x": grid, "y": cdf}

    raise ValueError(f"Unknown question type: {qtype}")
