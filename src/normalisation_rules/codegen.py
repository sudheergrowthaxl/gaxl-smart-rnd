"""Generate executable Python normalisers from rule descriptions using LLM."""

import json
import re
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from normalisation_rules.config import PROJECT_ROOT, GENERATED_NORMALISERS_JSON

CODEGEN_SYSTEM = """You are a Python code generator for data normalisation. Given an attribute name and a list of normalisation rule descriptions (natural language), output a single Python function that implements those rules.

Requirements:
- Function signature: def normalise(value, row=None):
  - value: the current cell value (str, int, float, or None). It may be None or NaN for missing data.
  - row: optional dict-like (e.g. pandas Series) of the full row; use for conditional rules that reference other columns (e.g. "if frame width < 50").
- Return the normalised value (str or number). For missing/None/NaN input, return the value as-is or None.
- Use only: standard library (re, str, int, float), and optionally pandas as pd (e.g. pd.isna). No file I/O, no network, no system calls.
- Apply the rules in the order given. Keep the code short and safe.
- Output ONLY the Python function code, no markdown fences, no explanation. Start with "def normalise(value, row=None):" and end with the function body indented.
"""


def _build_codegen_prompt(attribute: str, rule_descriptions: list[str]) -> str:
    lines = [
        f"Attribute: {attribute}",
        "",
        "Rule descriptions (apply in order):",
    ]
    for i, desc in enumerate(rule_descriptions, 1):
        if desc:
            lines.append(f"  {i}. {desc}")
    lines.extend([
        "",
        "Output the Python function only (def normalise(value, row=None): ...):",
    ])
    return "\n".join(lines)


def generate_normaliser_code(
    attribute: str,
    rule_descriptions: list[str],
    llm: Any,
) -> str:
    """Use LLM to generate Python code for one attribute. Returns the full function source."""
    prompt = _build_codegen_prompt(attribute, [r.get("Rule description", "") if isinstance(r, dict) else r for r in rule_descriptions])
    messages = [
        SystemMessage(content=CODEGEN_SYSTEM),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    content = (getattr(response, "content", None) or str(response)).strip()
    # Strip markdown code block if present
    if content.startswith("```"):
        content = re.sub(r"^```\w*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)
    return content.strip()


def compile_normaliser(code: str, attribute: str) -> Callable[[Any, Any], Any]:
    """Compile the generated code into a callable in a restricted namespace. On exception, returns original value."""
    restricted = {
        "re": re,
        "pd": __import__("pandas"),
        "math": __import__("math"),
        "str": str,
        "int": int,
        "float": float,
        "len": len,
        "None": None,
        "True": True,
        "False": False,
        "isinstance": isinstance,
        "round": round,
        "min": min,
        "max": max,
        "abs": abs,
    }
    try:
        exec(code, restricted)
        normalise_fn = restricted.get("normalise")
        if not callable(normalise_fn):
            raise ValueError("Generated code did not define 'normalise'")
    except Exception as e:
        raise ValueError(f"Invalid generated code for {attribute}: {e}") from e

    def safe_normalise(value: Any, row: Any = None) -> Any:
        try:
            import pandas as pd
            if pd.isna(value):
                value = None
            return normalise_fn(value, row)
        except Exception:
            return value

    return safe_normalise


def save_generated_code(attribute_to_code: dict[str, str], path: Path | None = None) -> None:
    """Persist generated code to a JSON file (attribute -> code string) for --skip-generate."""
    path = path or GENERATED_NORMALISERS_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(attribute_to_code, f, indent=2)


def load_generated_code(path: Path | None = None) -> dict[str, str]:
    """Load previously generated code from JSON."""
    path = path or GENERATED_NORMALISERS_JSON
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
