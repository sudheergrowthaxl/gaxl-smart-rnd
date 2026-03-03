"""Load, profile, and persist datasets for the normalisation pipeline.

Every new dataset is profiled (column statistics, distinct values, semantic
types) and the result is saved as a JSON file inside the ``data/`` folder.
All downstream pipelines (attribute resolution, normalisation rules,
hierarchy) load from this persisted profiling JSON rather than re-reading
the raw file.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Any

import pandas as pd

from normalisation_rules.config import DATA_DIR

SKIP_SEMANTIC_TYPES = {"Empty/NA", "ID", "Constant"}
MAX_VALUES_PER_ATTR = 50


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Profile every column in a DataFrame.

    Returns a dict keyed by column name, each containing:
        datatype, semantic_type, missing_percentage, range,
        distinct_count, total_count, distinct_values (list of {value, count}).
    """
    profiling: dict[str, Any] = {}
    for col in df.columns:
        series = df[col]
        total = len(series)
        missing = int(series.isna().sum())
        missing_pct = round(missing / total * 100, 2) if total > 0 else 0.0

        non_null = series.dropna()
        dtype = str(series.dtype)
        distinct = non_null.nunique()

        semantic = _infer_semantic_type(non_null, col, distinct, total)

        vc = non_null.value_counts().head(MAX_VALUES_PER_ATTR)
        distinct_values = [
            {"value": str(v), "count": int(c)} for v, c in vc.items()
        ]

        val_range = None
        if pd.api.types.is_numeric_dtype(series) and len(non_null) > 0:
            val_range = f"{non_null.min()} - {non_null.max()}"

        profiling[col] = {
            "datatype": dtype,
            "semantic_type": semantic,
            "missing_percentage": missing_pct,
            "range": val_range,
            "distinct_count": distinct,
            "total_count": total,
            "distinct_values": distinct_values,
        }

    return profiling


def profile_and_save(
    df: pd.DataFrame,
    dataset_name: str,
    category: str,
) -> tuple[dict[str, Any], Path]:
    """Profile a DataFrame and persist the result as JSON in the data/ folder.

    The output file is named: ``data/{safe_name}_profiling_{timestamp}.json``
    and also includes metadata (original filename, category, row/column counts,
    profiled_at timestamp).

    Returns:
        (profiling_dict, output_path)
    """
    profiling = profile_dataframe(df)

    # Build enriched output
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output = {
        "_meta": {
            "dataset_name": dataset_name,
            "category": category,
            "rows": len(df),
            "columns": len(df.columns),
            "profiled_at": ts,
        },
        "profiling": profiling,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(dataset_name)
    ts_file = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = DATA_DIR / f"{safe_name}_profiling_{ts_file}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return profiling, out_path


def _safe_filename(name: str) -> str:
    """Strip extension and replace non-alphanumeric chars."""
    stem = Path(name).stem
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)


# ---------------------------------------------------------------------------
# Loading persisted profiling
# ---------------------------------------------------------------------------

def load_profiling_json(path: Path | str) -> dict[str, Any]:
    """Load a profiling JSON file.

    Supports both the enriched format (with ``_meta`` + ``profiling`` keys)
    and the legacy flat format (column name -> stats dict).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "profiling" in data and "_meta" in data:
        return data["profiling"]
    return data


def load_profiling_with_meta(path: Path | str) -> dict[str, Any]:
    """Load a profiling JSON including the full metadata envelope."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_latest_profiling(dataset_name: str | None = None) -> Path | None:
    """Find the most recent profiling JSON in the data/ folder.

    If *dataset_name* is provided, only files matching that dataset are
    considered.  Otherwise the newest file overall is returned.
    """
    if not DATA_DIR.exists():
        return None

    pattern = "*_profiling_*.json"
    if dataset_name:
        safe = _safe_filename(dataset_name)
        pattern = f"{safe}_profiling_*.json"

    candidates = sorted(DATA_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Generic dataset loading (from raw file -> DataFrame)
# ---------------------------------------------------------------------------

def load_dataset_as_dataframe(path: str | Path) -> pd.DataFrame:
    """Load any Excel / CSV / JSON file into a pandas DataFrame."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported file format: {ext}")


def load_generic_dataset(path: str | Path) -> dict[str, Any]:
    """Load any Excel/CSV/JSON file and return its profiling dict.

    Convenience wrapper: ``load_dataset_as_dataframe`` + ``profile_dataframe``.
    """
    df = load_dataset_as_dataframe(path)
    return profile_dataframe(df)


# ---------------------------------------------------------------------------
# Semantic type inference
# ---------------------------------------------------------------------------

def _infer_semantic_type(series: pd.Series, col_name: str, distinct: int, total: int) -> str:
    if len(series) == 0:
        return "Empty/NA"
    if distinct <= 1:
        return "Constant"
    if distinct > total * 0.9 and series.dtype == object:
        return "ID"
    if pd.api.types.is_numeric_dtype(series):
        return "Numeric"
    if series.dtype == object and distinct <= total * 0.5:
        return "Categorical"
    return "Text"


# ---------------------------------------------------------------------------
# Attribute extraction for rule derivation
# ---------------------------------------------------------------------------

def _get_values_for_attr(attr_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = attr_data.get("distinct_values") or attr_data.get("top_values") or []
    if not isinstance(raw, list):
        return []
    return raw[:MAX_VALUES_PER_ATTR]


def _is_useful_for_rules(attr_name: str, attr_data: dict[str, Any]) -> bool:
    semantic = (attr_data.get("semantic_type") or "").strip()
    if semantic in SKIP_SEMANTIC_TYPES:
        return False
    values = _get_values_for_attr(attr_data)
    return len(values) > 0


def extract_attributes_for_rules(
    profiling: dict[str, Any],
    *,
    priority_attributes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract attribute summaries for rule derivation from a profiling dict."""
    if priority_attributes is None:
        priority_attributes = set()

    result = []
    for attr_name, attr_data in profiling.items():
        if not isinstance(attr_data, dict):
            continue
        if not _is_useful_for_rules(attr_name, attr_data):
            continue
        values = _get_values_for_attr(attr_data)
        result.append({
            "name": attr_name,
            "datatype": attr_data.get("datatype"),
            "semantic_type": attr_data.get("semantic_type"),
            "missing_percentage": attr_data.get("missing_percentage"),
            "range": attr_data.get("range"),
            "values": values,
        })

    def order_key(a: dict) -> tuple[int, str]:
        name = a["name"]
        return (0, name) if name in priority_attributes else (1, name)

    result.sort(key=order_key)
    return result
