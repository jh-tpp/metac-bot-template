import json
import os
import shutil
from datetime import datetime
from typing import Any, Optional

REDACT_KEYS = {"authorization", "api_key", "x-api-key", "x-openai-api-key"}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in REDACT_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


class DiagnosticTrace:
    def __init__(self, qid: Optional[int], run_id: Optional[str] = None, base_dir: str = None):
        base_dir = base_dir or os.environ.get("DIAGNOSTICS_TRACE_DIR", "cache/trace")
        self.qid = qid
        self.run_id = run_id or datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        self.dir = os.path.join(base_dir, f"q{qid or 'unknown'}", self.run_id)
        _ensure_dir(self.dir)

    def save(self, stage: str, obj: Any, redact: bool = True) -> str:
        path = os.path.join(self.dir, f"{stage}.json")
        # Ensure parent directory exists (for subdirectories like diffs/)
        _ensure_dir(os.path.dirname(path))
        to_write = _redact(obj) if redact else obj
        with open(path, "w", encoding="utf-8") as f:
            json.dump(to_write, f, indent=2, ensure_ascii=False)
        return path

    def copy_from(self, stage: str, src_path: str):
        if not os.path.exists(src_path):
            return
        dst = os.path.join(self.dir, f"{stage}{os.path.splitext(src_path)[1]}")
        shutil.copyfile(src_path, dst)

    def diff(self, stage: str, old_obj: Any, new_obj: Any) -> str:
        diff_obj = {
            "stage": stage,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "changes": {
                "before": _redact(old_obj),
                "after": _redact(new_obj),
            },
        }
        return self.save(f"diffs/diff_{stage}", diff_obj, redact=False)
