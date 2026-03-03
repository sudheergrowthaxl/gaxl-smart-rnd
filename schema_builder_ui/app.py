"""Schema Builder V0 — AI-Powered Schema Architect.

Produces deployable, opinionated product data schemas by applying expert
knowledge consistently and at scale.  A schema is successful not because it
reflects the current state of the data, but because it reflects what the data
SHOULD look like to support the intended business outcome.

The agent is expert in product data modeling, opinionated about best practices,
consistent in how rules are applied, grounded in industry-recognized standards,
and honest about tradeoffs and constraints.

Chat is always available — users can ask schema questions even before uploading
a file.  Once a dataset is loaded the agent becomes context-aware and makes
concrete, defensible schema decisions.
"""

import io
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from normalisation_rules.config import (
    get_openai_client,
    get_categories_from_docx,
    get_manufacturers_for_category,
    get_domain_model_context,
    get_domain_invariants_summary,
    PROJECT_ROOT,
)
from normalisation_rules.domain_model_generator import (
    generate_domain_model,
    detect_domain_overview,
)


# ===================================================================
#  Session Logger — traces every step to a single file
# ===================================================================

_LOGS_DIR = PROJECT_ROOT / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _get_session_log_path() -> Path:
    if "session_log_path" not in st.session_state:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.session_log_path = str(_LOGS_DIR / f"session_{ts}.log")
    return Path(st.session_state.session_log_path)


def _log(stage: str, message: str, level: str = "INFO"):
    """Append a timestamped, stage-tagged entry to the session log file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    path = _get_session_log_path()
    line = f"[{ts}] [{level}] [{stage}] {message}\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _log_block(stage: str, title: str, body: str, level: str = "INFO"):
    """Log a multi-line block with a clear separator."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    path = _get_session_log_path()
    sep = "=" * 72
    block = (
        f"\n{sep}\n"
        f"[{ts}] [{level}] [{stage}] {title}\n"
        f"{'-' * 72}\n"
        f"{body}\n"
        f"{sep}\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception:
        pass


def _log_session_state(stage: str):
    """Snapshot current session state for debugging."""
    state = {
        "file_name": st.session_state.file_name,
        "domain": st.session_state.domain,
        "sub_domain": st.session_state.sub_domain,
        "category": st.session_state.category,
        "category_confidence": st.session_state.category_confidence,
        "has_domain_model": st.session_state.domain_model is not None,
        "domain_model_path": st.session_state.domain_model_path,
        "awaiting_domain_confirm": st.session_state.awaiting_domain_confirm,
        "has_df": st.session_state.df is not None,
        "df_shape": list(st.session_state.df.shape) if st.session_state.df is not None else None,
        "profiling_columns": len(st.session_state.profiling) if st.session_state.profiling else 0,
        "profiling_path": st.session_state.profiling_path,
        "canonical_attributes_count": len((st.session_state.canonical_attributes or {}).get("backbone", [])),
        "has_schema_report": st.session_state.schema_report is not None and bool(st.session_state.schema_report),
        "derived_rules_columns": list(st.session_state.derived_rules.keys()),
        "has_hierarchy": st.session_state.hierarchy_result is not None,
        "view_projections": list(st.session_state.view_projections.keys()),
        "auto_pipeline_done": st.session_state.auto_pipeline_done,
        "message_count": len(st.session_state.messages),
    }
    _log_block(stage, "SESSION STATE SNAPSHOT", json.dumps(state, indent=2, default=str))

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Schema Builder — AI Schema Architect",
    page_icon="🧠",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar — config, upload, status, downloads
# ---------------------------------------------------------------------------
st.sidebar.title("🧠 Schema Builder")

with st.sidebar.expander("🔑 API Keys", expanded=False):
    api_key_openai = st.text_input("OpenAI API Key", type="password", key="k_oai")
    api_key_tavily = st.text_input("Tavily API Key", type="password", key="k_tav")
    if api_key_openai:
        os.environ["OPENAI_API_KEY"] = api_key_openai
    if api_key_tavily:
        os.environ["TAVILY_API_KEY"] = api_key_tavily

st.sidebar.markdown("---")
st.sidebar.markdown("**📂 Upload Dataset**")
uploaded = st.sidebar.file_uploader(
    "Excel, CSV, or JSON",
    type=["xlsx", "csv", "json"],
    key="uploader_widget",
    label_visibility="collapsed",
)

if st.sidebar.button("🔄 New Session", use_container_width=True):
    _log("SESSION", "User pressed 'New Session' — clearing all state")
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_log("SESSION", "Streamlit page rendered (session state init)")

_DEFAULTS = {
    "messages": [],
    "df": None,
    "file_name": None,
    # Domain resolution
    "domain": None,
    "sub_domain": None,
    "category": None,
    "category_confidence": None,
    "category_reasoning": None,
    "domain_model": None,
    "domain_model_path": None,
    "awaiting_domain_confirm": False,
    "detected_domain_info": None,
    # Data processing
    "column_mapping": None,
    "profiling": None,
    "profiling_path": None,
    "canonical_attributes": None,
    "schema_report": None,
    "derived_rules": {},
    "hierarchy_result": None,
    "view_projections": {},
    "auto_pipeline_done": False,
    "pending_upload": False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ===================================================================
#  SYSTEM PROMPT — Schema Architect persona
# ===================================================================

_SCHEMA_ARCHITECT_SYSTEM = """You are **Schema Builder**, an opinionated AI schema architect
that produces deployable product data schemas for industrial electrical equipment.

YOUR CORE IDENTITY:
You are NOT a general-purpose assistant or data analyst.  You are an expert practitioner
who makes concrete, defensible schema decisions — the same way a senior data architect
with 20 years of product data experience would.

You exist because schema expertise is scarce, expensive, slow to apply, and difficult
to replicate.  You embed that expertise into every response.

YOUR ROLE:
• Expert in product data modeling and specific product categories
• Opinionated about best practices — you RECOMMEND, not merely describe options
• Consistent in how rules are applied across decisions
• Grounded in industry-recognized standards (IEC, ISO, UNSPSC, eClass, GPC)
• Honest about tradeoffs and constraints

KNOWLEDGE AUTHORITY (highest to lowest — higher overrides lower when they conflict):
1. Category-specific knowledge (expected attributes, variant logic, known enums)
2. Product domain knowledge (variant modeling, attribute roles, UoM, channel reqs)
3. Data architecture knowledge (canonical forms, cardinality, controlled vocabularies)
4. Reference knowledge (terminology, synonyms, public standards)
5. Observed data — informs decisions but NEVER overrides schema intent

SCHEMA COVERS:
• Product categories and hierarchies (taxonomy, UNSPSC, eClass, custom)
• Attributes and canonical meanings (structural roles: identity, variant-defining,
  descriptive, contextual; intrinsic vs extrinsic)
• Naming conventions (canonical naming, abbreviation policies)
• Data types, constraints, units of measure, regex patterns, format masks
• Cardinality and variant logic (single vs multi-value, variant-defining vs descriptive)
• Enumerations aligned to industry and channel expectations
• Product relationships (co-determined, conditional, constraining dependencies)
• Abstract representations (SHACL shapes, OWL classes, property graphs, ER/UML)
• Normalisation rules (value cleaning, mapping, unit conversion, synonym resolution)

HOW YOU RESPOND:
1. **Be opinionated** — state your recommendation clearly, then explain why.
   Do NOT present a menu of equal options.  Give your best advice.
2. **Structure decisions explicitly** — when making a schema decision, state:
   - **Decision**: what you recommend
   - **Rationale**: why (functional purpose, standards, downstream impact)
   - **Alternatives considered**: what was rejected and why
   - **Tradeoffs**: what is gained and what is sacrificed
3. **Define target state** — schema describes what data SHOULD look like, not what
   it currently looks like.  Observed data is evidence, not truth.
4. **Be concrete** — give specific names, types, regex patterns, enum values, units.
   Not "consider using an enumeration" but "use enumeration: {AC-1, AC-2, AC-3, AC-4,
   DC-1, DC-3, DC-5} per IEC 60947-4-1".
5. **Explain deviations** — if reality forces compromise from best practice, say so
   explicitly.  Deviations must be intentional and explainable.
6. **Reference standards** — cite IEC, ISO, NEMA, UNSPSC, eClass where relevant.
7. **Keep responses focused** — 3-10 sentences unless the user asks for detail.
   Use markdown tables and code blocks for clarity.

When NO dataset is loaded, answer from your expert knowledge about product data schemas.
When a dataset IS loaded, reference actual columns, profiling, and canonical attributes
to give specific, grounded advice about THAT data.
"""


# ===================================================================
#  Conversion helpers (for downloads)
# ===================================================================

def _backbone_to_df(backbone: list[dict]) -> pd.DataFrame:
    rows = []
    for a in backbone:
        conf = a.get("confidence", {})
        deps = a.get("dependencies", [])
        deps_str = "; ".join(f"{d.get('attribute', '?')} ({d.get('type', '?')})" for d in deps) if deps else ""
        unit = a.get("unit")
        unit_str = unit.get("base_unit", "") if isinstance(unit, dict) else ""
        sources = a.get("sources", [])
        rows.append({
            "Name": a.get("name", ""),
            "Structural Role": a.get("structural_role", ""),
            "Data Type": a.get("data_type", ""),
            "Intrinsic": a.get("intrinsic", ""),
            "Unit": unit_str,
            "Dependencies": deps_str,
            "Confidence": conf.get("composite", ""),
            "Rationale": a.get("rationale", ""),
            "Sources": ", ".join(sources) if isinstance(sources, list) else str(sources),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _rules_to_df(derived_rules: dict[str, list[str]]) -> pd.DataFrame:
    rows = []
    for col, rules in derived_rules.items():
        for r in rules:
            parts = r.split("\t")
            if len(parts) >= 4:
                rows.append({"Entity": parts[0], "Attribute": parts[1], "Type": parts[2], "Rule": parts[3]})
            else:
                rows.append({"Entity": "", "Attribute": col, "Type": "Normalization", "Rule": r})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _hierarchy_to_df(result: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Category": st.session_state.category,
        "General Hierarchy": result.get("global_generalized_hierarchy_path") or result.get("recommended_path", ""),
        "Supply Chain Path": result.get("recommended_path") or result.get("supply_chain_recommended_path", ""),
        "Ecommerce Path": result.get("ecommerce_recommended_path", ""),
        "UNSPSC Code": result.get("unspsc_code", ""),
        "Supply Chain Reason": result.get("supply_chain_reason", ""),
        "Ecommerce Reason": result.get("ecommerce_reason", ""),
        "Confidence": result.get("confidence", ""),
    }])


def _df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ===================================================================
#  Chat helpers
# ===================================================================

def _add(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def _render_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def _find_column(name: str) -> str | None:
    if st.session_state.df is None:
        return None
    cols = list(st.session_state.df.columns)
    name_l = name.strip().lower()
    for c in cols:
        if name_l == c.lower():
            return c
    for c in cols:
        if name_l in c.lower():
            return c
    if name.strip().isdigit():
        idx = int(name.strip()) - 1
        if 0 <= idx < len(cols):
            return cols[idx]
    return None


def _build_session_context_block() -> str:
    """Build a comprehensive context string from session state for LLM prompts."""
    parts = []
    cat = st.session_state.category
    profiling = st.session_state.profiling or {}
    attrs = st.session_state.canonical_attributes or {}
    backbone = attrs.get("backbone", [])
    report = st.session_state.schema_report or {}
    rules = st.session_state.derived_rules
    hier = st.session_state.hierarchy_result

    dm = st.session_state.domain_model
    if st.session_state.domain:
        parts.append(f"Domain: {st.session_state.domain} > {st.session_state.sub_domain} > {cat}")
    if dm:
        dm_ctx = get_domain_model_context(dm)
        if dm_ctx:
            parts.append(f"Domain Model:\n{dm_ctx}")
    if st.session_state.file_name:
        parts.append(f"Dataset: {st.session_state.file_name}")
    if cat:
        parts.append(f"Category: {cat} (confidence: {st.session_state.category_confidence or '?'})")
    if profiling:
        col_summaries = []
        for col, s in list(profiling.items())[:40]:
            sem = s.get("semantic_type", "")
            miss = s.get("missing_percentage", 0)
            dist = s.get("distinct_count", 0)
            top = s.get("distinct_values", [])[:3]
            top_str = ", ".join(str(v.get("value", v) if isinstance(v, dict) else v) for v in top)
            col_summaries.append(f"  {col} | {sem} | missing={miss}% | distinct={dist} | samples: {top_str}")
        parts.append(f"User columns ({len(profiling)} total, with profiling):\n" + "\n".join(col_summaries))
    if backbone:
        attr_lines = []
        for a in backbone[:60]:
            role = a.get("structural_role", "")
            dtype = a.get("data_type", "")
            conf = a.get("confidence", {}).get("composite", "?")
            attr_lines.append(f"  {a.get('name','')} | role={role} | type={dtype} | conf={conf}")
        remaining = len(backbone) - 60
        if remaining > 0:
            attr_lines.append(f"  ... and {remaining} more attributes")
        parts.append(f"Canonical attributes ({len(backbone)}):\n" + "\n".join(attr_lines))
    if report.get("target_state_summary"):
        parts.append(f"Target state: {report['target_state_summary']}")
    if report.get("schema_completeness_pct"):
        parts.append(f"Schema completeness: {report['schema_completeness_pct']}%")
    if report.get("missing_attributes"):
        miss_items = [f"{m['name']} ({m.get('criticality','')})" for m in report["missing_attributes"][:15]]
        parts.append(f"Missing attributes: {', '.join(miss_items)}")
    if report.get("schema_decisions"):
        dec_items = [f"{d.get('type','')}: {d.get('decision','')}" for d in report["schema_decisions"][:8]]
        parts.append(f"Schema decisions made:\n" + "\n".join(f"  - {d}" for d in dec_items))
    if report.get("data_quality_issues"):
        dq = [f"{i['column']}: {i['issue']}" for i in report["data_quality_issues"][:5]]
        parts.append(f"Data quality issues: {'; '.join(dq)}")
    if rules:
        rules_detail = []
        for col, col_rules in rules.items():
            rules_detail.append(f"  {col}: {len(col_rules)} rules")
        parts.append(f"Normalisation rules derived ({len(rules)} columns):\n" + "\n".join(rules_detail))
    if hier:
        global_path = hier.get("global_generalized_hierarchy_path") or hier.get("recommended_path", "")
        sc_path = hier.get("recommended_path") or hier.get("supply_chain_recommended_path", "")
        ec_path = hier.get("ecommerce_recommended_path", "")
        parts.append(
            f"Hierarchy resolved:\n"
            f"  General: {global_path}\n"
            f"  Supply Chain: {sc_path}\n"
            f"  Ecommerce: {ec_path}\n"
            f"  UNSPSC: {hier.get('unspsc_code', 'N/A')}"
        )
    return "\n".join(parts) if parts else "(No dataset loaded yet)"


# ===================================================================
#  LLM-powered schema health report
# ===================================================================

def _generate_schema_report(profiling: dict, canonical_attrs: dict, category: str) -> dict:
    backbone = canonical_attrs.get("backbone", [])
    profiling_summary = ""
    for col, stats in profiling.items():
        sem = stats.get("semantic_type", "")
        miss = stats.get("missing_percentage", 0)
        dist = stats.get("distinct_count", 0)
        profiling_summary += f"  - {col} | type={sem} | missing={miss}% | distinct={dist}\n"

    canonical_summary = ""
    for a in backbone:
        conf = a.get("confidence", {}).get("composite", "?")
        role = a.get("structural_role", "")
        dtype = a.get("data_type", "")
        canonical_summary += f"  - {a.get('name','')} | role={role} | type={dtype} | conf={conf}\n"

    prompt = f"""You are an opinionated product data schema architect producing a
DEPLOYABLE schema assessment.

Schema defines what GOOD looks like — the target state data must achieve.
Observed data is evidence, not truth.  Your job is to define the target and
measure the gap.

**Category**: {category}
**User's current columns**:
{profiling_summary}

**Canonical (target) schema for {category}**:
{canonical_summary}

Produce a schema assessment as JSON.  For every decision, be OPINIONATED:

1. **column_mapping** — map each user column to its canonical attribute.
   If a column should be SPLIT (e.g., "Dimensions" → Height, Width, Depth),
   say so.  If a column name is wrong, map it to the correct canonical name.

2. **present_attributes** — canonical attributes already covered.

3. **missing_attributes** — canonical attributes NOT present.  For each:
   - criticality: critical (identity/variant-defining), important (contextual),
     nice-to-have (descriptive)
   - reason: WHY this matters for buying, selling, or moving the product
   - impact: what breaks downstream without this attribute

4. **data_quality_issues** — columns with quality problems.

5. **schema_decisions** — 5-8 concrete schema decisions you are making:
   - Each decision has: type (split|merge|rename|retype|add_enum|add_constraint|
     add_relation|set_cardinality|set_variant_role), action, rationale,
     alternatives_rejected, tradeoff.
   Example: "Split 'Contact Configuration' into 'NO Contacts' (integer) and
   'NC Contacts' (integer) — needed for variant logic; alternative was keeping
   composite but that prevents filtering."

6. **naming_conventions** — specific naming fixes with the canonical form.

7. **type_and_validation** — for key attributes: recommended type, unit, regex,
   enum value-set, cardinality (single/multi).

8. **target_state_summary** — 2-3 sentences describing what the IDEAL schema
   looks like for this category, independent of current data state.

**Output ONLY valid JSON:**
{{
  "column_mapping": [{{"user_column": "...", "canonical_attribute": "...", "match_quality": "exact|partial|none", "action": "keep|rename|split|merge"}}],
  "present_attributes": ["..."],
  "missing_attributes": [{{"name": "...", "role": "...", "criticality": "critical|important|nice-to-have", "reason": "...", "impact": "..."}}],
  "data_quality_issues": [{{"column": "...", "issue": "...", "severity": "high|medium|low"}}],
  "schema_decisions": [{{"type": "...", "decision": "...", "rationale": "...", "alternatives_rejected": "...", "tradeoff": "..."}}],
  "naming_conventions": [{{"current": "...", "canonical": "...", "reason": "..."}}],
  "type_and_validation": [{{"attribute": "...", "type": "...", "unit": "...", "regex": "...", "enum_values": [], "cardinality": "single|multi"}}],
  "schema_completeness_pct": 0,
  "target_state_summary": "..."
}}
"""
    _log("LLM/REPORT", f"Sending schema report prompt ({len(prompt)} chars) for category '{category}'")
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.15,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        usage = response.usage
        _log("LLM/REPORT", f"Report received: {len(raw)} chars, tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
        return json.loads(raw)
    except Exception as e:
        _log("LLM/REPORT", f"Schema report FAILED: {e}", level="ERROR")
        return {"error": str(e), "summary": f"Report generation failed: {e}"}


def _format_schema_report(report: dict) -> str:
    lines = []

    # Target state summary
    target = report.get("target_state_summary", "")
    if target:
        lines.append(f"**Target State**: {target}\n")

    completeness = report.get("schema_completeness_pct", 0)
    if completeness:
        bar_filled = int(completeness / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        lines.append(f"**Schema Completeness**: `{bar}` **{completeness}%**\n")

    # Present attributes (compact)
    present = report.get("present_attributes", [])
    if present:
        lines.append(f"**Present** ({len(present)}): " + ", ".join(f"`{a}`" for a in present) + "\n")

    # Missing attributes with impact
    missing = report.get("missing_attributes", [])
    if missing:
        critical = [m for m in missing if m.get("criticality") == "critical"]
        important = [m for m in missing if m.get("criticality") == "important"]
        nice = [m for m in missing if m.get("criticality") == "nice-to-have"]
        lines.append(f"**Missing** ({len(missing)}):")
        if critical:
            for m in critical:
                impact = f" | Impact: {m['impact']}" if m.get("impact") else ""
                lines.append(f"- 🔴 **{m['name']}** — {m.get('reason', '')}{impact}")
        if important:
            for m in important:
                lines.append(f"- 🟡 **{m['name']}** — {m.get('reason', '')}")
        if nice:
            lines.append(f"- 🟢 {len(nice)} descriptive attributes (nice-to-have)")
        lines.append("")

    # Schema decisions (the core of the report)
    decisions = report.get("schema_decisions", [])
    if decisions:
        lines.append("**Schema Decisions**:")
        for d in decisions:
            dtype = d.get("type", "")
            icon = {"split": "✂️", "merge": "🔗", "rename": "🏷️", "retype": "🔢",
                    "add_enum": "📋", "add_constraint": "📏", "add_relation": "🔗",
                    "set_cardinality": "🔢", "set_variant_role": "🔧"}.get(dtype, "💡")
            lines.append(f"- {icon} **{d.get('decision', '')}**")
            if d.get("rationale"):
                lines.append(f"  *Rationale*: {d['rationale']}")
            if d.get("alternatives_rejected"):
                lines.append(f"  *Rejected*: {d['alternatives_rejected']}")
            if d.get("tradeoff"):
                lines.append(f"  *Tradeoff*: {d['tradeoff']}")
        lines.append("")

    # Naming conventions
    naming = report.get("naming_conventions", [])
    if naming:
        lines.append("**Naming Fixes**:")
        for n in naming[:6]:
            lines.append(f"- `{n.get('current', '')}` → `{n.get('canonical', '')}` — *{n.get('reason', '')}*")
        lines.append("")

    # Type & validation
    type_recs = report.get("type_and_validation", [])
    if type_recs:
        lines.append("**Type & Validation**:")
        for t in type_recs[:6]:
            parts = [f"**{t.get('attribute', '')}**"]
            if t.get("type"):
                parts.append(f"type=`{t['type']}`")
            if t.get("unit"):
                parts.append(f"unit=`{t['unit']}`")
            if t.get("cardinality"):
                parts.append(f"cardinality=`{t['cardinality']}`")
            if t.get("regex"):
                parts.append(f"regex=`{t['regex']}`")
            if t.get("enum_values"):
                vals = t["enum_values"][:5]
                parts.append(f"enum={vals}")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    # Data quality
    dq = report.get("data_quality_issues", [])
    if dq:
        lines.append(f"**Data Quality** ({len(dq)} issues):")
        for issue in dq[:5]:
            sev = issue.get("severity", "")
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
            lines.append(f"- {icon} `{issue.get('column', '')}` — {issue.get('issue', '')}")
        lines.append("")

    return "\n".join(lines)


# ===================================================================
#  Smart schema-aware LLM response
# ===================================================================

def _smart_response(user_message: str) -> str:
    context_block = _build_session_context_block()
    _log("LLM/SMART", f"Generating smart response for: {user_message[:200]}")
    _log_block("LLM/SMART", "SESSION CONTEXT SENT TO LLM", context_block[:2000])

    system = _SCHEMA_ARCHITECT_SYSTEM + f"""

**Current session context:**
{context_block}
"""
    client = get_openai_client()
    try:
        messages = [{"role": "system", "content": system}]
        for m in st.session_state.messages[-14:]:
            messages.append({"role": m["role"], "content": m["content"][:1200]})
        messages.append({"role": "user", "content": user_message})

        _log("LLM/SMART", f"Sending {len(messages)} messages to gpt-4o-mini (system + {len(messages)-2} history + user)")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.25,
            max_tokens=1500,
        )
        content = response.choices[0].message.content or "I'm not sure how to help with that."
        usage = response.usage
        _log_block("LLM/SMART", "LLM RESPONSE",
                   f"Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}\n\n{content[:1500]}")
        return content
    except Exception as e:
        _log("LLM/SMART", f"LLM call FAILED: {e}", level="ERROR")
        return f"Error: {e}"


def _schema_advice_response(user_message: str, params: dict) -> str:
    """Handle schema design questions with structured, defensible decisions."""
    context_block = _build_session_context_block()
    attr_name = params.get("attribute", "")

    attr_detail = ""
    if attr_name:
        profiling = st.session_state.profiling or {}
        matched = _find_column(attr_name)
        if matched and matched in profiling:
            s = profiling[matched]
            vals = s.get("distinct_values", [])[:20]
            val_str = ", ".join(str(v.get("value", v) if isinstance(v, dict) else v) for v in vals)
            attr_detail = (
                f"\n**Observed data for `{matched}`:**\n"
                f"  semantic_type={s.get('semantic_type','')}\n"
                f"  datatype={s.get('datatype','')}\n"
                f"  distinct={s.get('distinct_count','')}\n"
                f"  missing={s.get('missing_percentage','')}%\n"
                f"  sample values: {val_str}\n"
            )

        backbone = (st.session_state.canonical_attributes or {}).get("backbone", [])
        for a in backbone:
            if a.get("name", "").lower() == attr_name.lower():
                deps = a.get("dependencies", [])
                deps_str = ", ".join(f"{d.get('attribute','')} ({d.get('type','')})" for d in deps) if deps else "none"
                attr_detail += (
                    f"\n**Canonical definition:**\n"
                    f"  role={a.get('structural_role','')}\n"
                    f"  data_type={a.get('data_type','')}\n"
                    f"  intrinsic={a.get('intrinsic','')}\n"
                    f"  dependencies={deps_str}\n"
                    f"  rationale={a.get('rationale','')}\n"
                )
                break

    _log("LLM/SCHEMA_ADVICE", f"Schema advice for: {user_message[:200]}")
    if attr_detail:
        _log_block("LLM/SCHEMA_ADVICE", "ATTRIBUTE DETAIL", attr_detail)

    system = _SCHEMA_ARCHITECT_SYSTEM + f"""

**Session context:**
{context_block}
{attr_detail}

The user is asking a SCHEMA DESIGN question.  You must respond with a DECISION,
not a discussion of options.  Structure your response as:

**Decision**: [Your concrete recommendation]
**Rationale**: [Why — citing functional purpose, standards, downstream impact]
**Alternatives rejected**: [What you considered and dismissed, with brief reason]
**Tradeoff**: [What is gained vs. sacrificed]

Then provide the specific implementation detail:
- If splitting: exact sub-attribute names, types, units
- If typing: exact type, unit, regex pattern, enum value-set
- If naming: exact canonical name and reasoning
- If cardinality: single vs multi, with variant logic impact
- If relationship: type (co-determined/conditional/constraining) and how to model it

If the attribute has observed data, analyze the sample values to ground your decision.
If no data is loaded, reason from category-specific and product domain knowledge.
Observed data informs but NEVER overrides schema intent.
"""
    client = get_openai_client()
    try:
        messages = [{"role": "system", "content": system}]
        for m in st.session_state.messages[-14:]:
            messages.append({"role": m["role"], "content": m["content"][:1200]})
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=1500,
        )
        content = response.choices[0].message.content or "I'm not sure about that."
        usage = response.usage
        _log_block("LLM/SCHEMA_ADVICE", "LLM RESPONSE",
                   f"Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}\n\n{content[:1500]}")
        return content
    except Exception as e:
        _log("LLM/SCHEMA_ADVICE", f"LLM call FAILED: {e}", level="ERROR")
        return f"Error: {e}"


# ===================================================================
#  Intent classification
# ===================================================================

def _classify_intent(user_message: str) -> dict:
    from normalisation_rules.prompts.intent_classification_prompt import (
        build_intent_classification_prompt,
    )
    session_context = {
        "category": st.session_state.category,
        "has_data": st.session_state.df is not None,
        "has_attributes": st.session_state.canonical_attributes is not None,
        "derived_rules_columns": list(st.session_state.derived_rules.keys()),
        "has_hierarchy": st.session_state.hierarchy_result is not None,
        "cached_views": list(st.session_state.view_projections.keys()),
        "recent_messages": st.session_state.messages[-10:],
    }
    _log_block("INTENT", "CLASSIFYING INTENT",
               f"User message: {user_message}\n"
               f"Session context: {json.dumps({k: v for k, v in session_context.items() if k != 'recent_messages'}, default=str)}")
    prompt = build_intent_classification_prompt(user_message, session_context)
    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
        _log_block("INTENT", "INTENT RESULT",
                   f"Intent: {result.get('intent')}\n"
                   f"Confidence: {result.get('confidence')}\n"
                   f"Params: {json.dumps(result.get('params', {}))}\n"
                   f"Hint: {result.get('response_hint', '')}")
        return result
    except Exception as exc:
        _log(f"INTENT", f"Intent classification FAILED: {exc}", level="ERROR")
        return {"intent": "general", "params": {"question": user_message}, "confidence": 0.5}


# ===================================================================
#  Auto-pipeline
# ===================================================================

def _run_slim_pipeline(domain: str, sub_domain: str, category: str):
    """Slim pipeline: generate domain model, strip prefixes, profile.

    Attribute resolution and schema report are on-demand only.
    """
    df = st.session_state.df
    filename = st.session_state.file_name

    _log_block("PIPELINE", "SLIM-PIPELINE START",
               f"File: {filename}\nDomain: {domain} > {sub_domain} > {category}\n"
               f"Shape: {df.shape}\nColumns: {list(df.columns)}")

    with st.status("🔍 Analyzing your data...", expanded=True) as status:
        # --- Step 1: Generate domain model ---
        st.write(f"**Step 1/3** — Generating domain model for **{category}**...")
        _log("PIPELINE/DOMAIN_MODEL", f"Generating 7-section domain model for {domain} > {sub_domain} > {category}")

        columns = list(df.columns)
        sample_vals: dict[str, list[str]] = {}
        for c in columns:
            sample_vals[c] = df[c].dropna().head(5).astype(str).tolist()

        try:
            dm, dm_path = generate_domain_model(
                domain=domain, sub_domain=sub_domain, category=category,
                user_columns=columns, sample_values=sample_vals,
            )
            st.session_state.domain_model = dm
            st.session_state.domain_model_path = str(dm_path)
            entity_count = sum(len(v) for v in dm.get("entities", {}).values() if isinstance(v, list))
            prop_count = sum(
                sum(len(p) for p in groups.values() if isinstance(p, list))
                for groups in dm.get("property_model", {}).values()
            )
            triplet_count = len(dm.get("ontology", {}).get("triplets", []))
            _log_block("PIPELINE/DOMAIN_MODEL", "DOMAIN MODEL GENERATED",
                       f"Entities: {entity_count}, Properties: {prop_count}, Triplets: {triplet_count}\n"
                       f"Saved to: {dm_path}")
            st.write(f"  → Domain model: {entity_count} entities, {prop_count} properties, {triplet_count} ontology triplets")
        except Exception as exc:
            _log("PIPELINE/DOMAIN_MODEL", f"Domain model generation FAILED: {exc}", level="ERROR")
            st.session_state.domain_model = {}
            st.session_state.domain_model_path = None
            st.write(f"  → Domain model error: {exc}")

        # --- Step 2: Prefix stripping ---
        st.write("**Step 2/3** — Cleaning column names...")
        _log("PIPELINE/PREFIX", f"Starting prefix stripping for category '{category}'")
        from normalisation_rules.prefix_stripper import strip_column_prefixes
        cleaned_df, mapping = strip_column_prefixes(df, category)
        st.session_state.df = cleaned_df
        st.session_state.column_mapping = mapping
        changed = {k: v for k, v in mapping.items() if k != v}
        if changed:
            _log_block("PIPELINE/PREFIX", f"PREFIX CHANGES ({len(changed)})",
                       "\n".join(f"  {k} → {v}" for k, v in changed.items()))
            st.write(f"  → Cleaned {len(changed)} column prefixes")
        else:
            _log("PIPELINE/PREFIX", "No prefix changes needed")

        # --- Step 3: Profiling ---
        st.write("**Step 3/3** — Profiling dataset...")
        _log("PIPELINE/PROFILE", f"Profiling {len(cleaned_df.columns)} columns, {len(cleaned_df)} rows")
        from normalisation_rules.data_loader import profile_and_save
        profiling, profiling_path = profile_and_save(cleaned_df, filename, category)
        st.session_state.profiling = profiling
        st.session_state.profiling_path = str(profiling_path)
        _log_block("PIPELINE/PROFILE", f"PROFILING COMPLETE ({len(profiling)} columns)",
                   f"Saved to: {profiling_path}")
        st.write(f"  → {len(profiling)} columns profiled")

        status.update(label="✅ Analysis complete", state="complete")

    _log_session_state("PIPELINE/DONE")
    st.session_state.auto_pipeline_done = True

    entity_count = sum(len(v) for v in (st.session_state.domain_model or {}).get("entities", {}).values() if isinstance(v, list))
    prop_count = sum(
        sum(len(p) for p in groups.values() if isinstance(p, list))
        for groups in (st.session_state.domain_model or {}).get("property_model", {}).values()
    )
    triplet_count = len((st.session_state.domain_model or {}).get("ontology", {}).get("triplets", []))

    lines = [
        f"Analysis of **{filename}** is complete.\n",
        f"**Domain**: {domain} > {sub_domain} > {category}",
        f"**Domain Model**: {entity_count} entities, {prop_count} properties, {triplet_count} ontology triplets",
    ]
    if changed:
        lines.append(f"**Cleaned**: {len(changed)} column prefixes stripped")
    lines.append(f"**Profiled**: {len(profiling)} columns\n")
    lines.append("---\n")
    lines.append(
        "You can now ask me to:\n"
        "- *\"Resolve attributes\"* — build the canonical attribute schema\n"
        "- *\"Normalize [column]\"* — derive normalisation rules for a column\n"
        "- *\"Show hierarchy\"* — recommend taxonomy classification\n"
        "- *\"Should I split the Type attribute?\"* — schema design questions\n"
        "- *\"What naming conventions should I use?\"*\n"
        "- *\"Download results\"*"
    )
    _add("assistant", "\n".join(lines))


def _run_attribute_resolution():
    """Run attribute resolution on demand."""
    cat = st.session_state.category
    profiling = st.session_state.profiling or {}
    dm = st.session_state.domain_model

    _log("HANDLER/ATTR_RESOLVE", f"Running attribute resolution for '{cat}'")
    with st.status(f"Resolving canonical schema for **{cat}**...", expanded=True) as status:
        from normalisation_rules.attribute_resolver.resolver import standardize_attributes
        try:
            result, rows, run_log = standardize_attributes(
                category=cat,
                profiling_data=profiling,
                output_dir=str(PROJECT_ROOT),
                domain_model=dm,
            )
            backbone = result.get("backbone", [])
            st.session_state.canonical_attributes = result
            _log_block("HANDLER/ATTR_RESOLVE", f"ATTRIBUTES RESOLVED ({len(backbone)})",
                       f"Log: {run_log}")
            status.update(label=f"✅ {len(backbone)} attributes resolved", state="complete")
        except Exception as exc:
            _log("HANDLER/ATTR_RESOLVE", f"FAILED: {exc}\n{traceback.format_exc()}", level="ERROR")
            st.session_state.canonical_attributes = {"backbone": [], "lenses": {}, "error": str(exc)}
            status.update(label="Error", state="error")

    # Generate schema health report too
    if st.session_state.canonical_attributes and st.session_state.canonical_attributes.get("backbone"):
        _log("HANDLER/ATTR_RESOLVE", "Generating schema health report")
        report = _generate_schema_report(profiling, st.session_state.canonical_attributes, cat)
        st.session_state.schema_report = report


def _handle_domain_confirm(user_message: str) -> str:
    """Handle user response to domain confirmation question."""
    info = st.session_state.detected_domain_info or {}
    msg_lower = user_message.strip().lower()

    if msg_lower in ("yes", "y", "correct", "that's correct", "looks good", "proceed", "confirm", "ok", "yep", "yeah"):
        domain = info.get("domain", "Unknown")
        sub_domain = info.get("sub_domain", "Unknown")
        category = info.get("category", "Unknown")
    else:
        _log("DOMAIN_CONFIRM", f"User correcting domain: {user_message}")
        correction = _parse_domain_correction(user_message, info)
        domain = correction.get("domain", info.get("domain", "Unknown"))
        sub_domain = correction.get("sub_domain", info.get("sub_domain", "Unknown"))
        category = correction.get("category", info.get("category", "Unknown"))

    st.session_state.domain = domain
    st.session_state.sub_domain = sub_domain
    st.session_state.category = category
    st.session_state.awaiting_domain_confirm = False
    _log_block("DOMAIN_CONFIRM", "DOMAIN CONFIRMED",
               f"Domain: {domain}\nSub-Domain: {sub_domain}\nCategory: {category}")

    _run_slim_pipeline(domain, sub_domain, category)
    return ""


def _parse_domain_correction(user_message: str, current_info: dict) -> dict:
    """Use LLM to parse user corrections to detected domain info."""
    prompt = f"""The system detected these domain values from uploaded data:
- Domain: {current_info.get('domain', 'Unknown')}
- Sub-Domain: {current_info.get('sub_domain', 'Unknown')}
- Category: {current_info.get('category', 'Unknown')}

The user responded with corrections: "{user_message}"

Extract the corrected values. If the user only corrected some fields, keep the
original values for the unchanged fields.

Output ONLY valid JSON:
{{"domain": "...", "sub_domain": "...", "category": "..."}}
"""
    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return current_info


# ===================================================================
#  Intent handlers → (text, download_key | None)
# ===================================================================

def _handle_normalize(params: dict) -> tuple[str, str | None]:
    _log("HANDLER/NORMALIZE", f"Params: {json.dumps(params, default=str)}")
    if st.session_state.df is None:
        _log("HANDLER/NORMALIZE", "No data loaded — returning early")
        return "Upload a dataset first so I can normalize its columns.", None

    col_name = params.get("column")
    if not col_name:
        _log("HANDLER/NORMALIZE", "No column specified — listing normalisable columns")
        profiling = st.session_state.profiling or {}
        cols = [c for c, s in profiling.items() if s.get("semantic_type") not in ("ID", "Constant", "Empty/NA")]
        return (
            "Which column? Your normalisable columns:\n\n"
            + "\n".join(f"- `{c}` ({profiling.get(c, {}).get('semantic_type', '')})" for c in cols),
            None,
        )

    matched = _find_column(col_name)
    if not matched:
        _log("HANDLER/NORMALIZE", f"Column '{col_name}' not found in dataset", level="WARN")
        return f"No column matching \"{col_name}\". Check the exact name.", None

    cat = st.session_state.category
    if matched in st.session_state.derived_rules:
        _log("HANDLER/NORMALIZE", f"Returning cached rules for '{matched}'")
        rules = st.session_state.derived_rules[matched]
        return f"**Rules for `{matched}`** (cached):\n\n" + "\n".join(f"- {r}" for r in rules), "rules"

    _log("HANDLER/NORMALIZE", f"Deriving new rules for '{matched}' in category '{cat}'")
    with st.status(f"Deriving rules for **{matched}**...", expanded=True) as status:
        from normalisation_rules.models import get_llm
        from normalisation_rules.graph import run_for_attribute

        profiling = st.session_state.profiling
        if profiling and matched in profiling:
            col_stats = profiling[matched]
            attr = {
                "name": matched,
                "datatype": col_stats.get("datatype", ""),
                "semantic_type": col_stats.get("semantic_type", ""),
                "missing_percentage": col_stats.get("missing_percentage", 0),
                "range": col_stats.get("range"),
                "values": col_stats.get("distinct_values", []),
            }
        else:
            df = st.session_state.df
            series = df[matched].dropna()
            vc = series.value_counts().head(50)
            attr = {
                "name": matched, "datatype": str(df[matched].dtype),
                "semantic_type": "Categorical" if series.nunique() < len(series) * 0.5 else "Text",
                "missing_percentage": round(df[matched].isna().sum() / len(df) * 100, 2),
                "range": None,
                "values": [{"value": str(v), "count": int(c)} for v, c in vc.items()],
            }
        try:
            llm = get_llm(provider="openai")
            _log("HANDLER/NORMALIZE", f"Calling run_for_attribute: attr={attr['name']}, category={cat}, tavily={bool(os.getenv('TAVILY_API_KEY'))}")
            rules, curated = run_for_attribute(
                llm=llm, attribute=attr, few_shot_examples="", category=cat,
                use_tavily=bool(os.getenv("TAVILY_API_KEY")),
            )
            st.session_state.derived_rules[matched] = rules
            status.update(label=f"✅ {matched}", state="complete")
            _log_block("HANDLER/NORMALIZE", f"RULES DERIVED ({len(rules)})",
                       "\n".join(f"  {r}" for r in rules) if rules else "(no rules)")
            if rules:
                return f"**Normalisation rules for `{matched}`:**\n\n" + "\n".join(f"- {r}" for r in rules), "rules"
            return f"No rules could be derived for **{matched}**.", None
        except Exception as exc:
            status.update(label="Error", state="error")
            _log("HANDLER/NORMALIZE", f"Rule derivation FAILED: {exc}\n{traceback.format_exc()}", level="ERROR")
            return f"Error: {exc}", None


def _format_hierarchy_global(rec: dict, cat: str) -> str:
    """Format the global/general hierarchy taxonomy (shown first)."""
    global_path = (
        rec.get("global_generalized_hierarchy_path")
        or rec.get("recommended_path")
        or rec.get("supply_chain_recommended_path", "N/A")
    )
    unspsc = rec.get("unspsc_code", "N/A")
    lines = [
        f"**General Taxonomy for {cat}**\n",
        f"**Hierarchy**: `{global_path}`",
        f"**UNSPSC Code**: `{unspsc}`\n",
        "---\n",
        "Would you like to see **specialized taxonomy views** as well?\n",
        "- *\"Show supply chain taxonomy\"* — ERP/procurement classification path",
        "- *\"Show ecommerce taxonomy\"* — selling/channel navigation path",
        "- *\"Show all taxonomy views\"* — both at once",
    ]
    return "\n".join(lines)


def _format_hierarchy_supply_chain(rec: dict, cat: str) -> str:
    sc_path = rec.get("recommended_path") or rec.get("supply_chain_recommended_path", "N/A")
    sc_reason = rec.get("supply_chain_reason", "")
    return (
        f"**Supply Chain Taxonomy for {cat}**\n\n"
        f"**Path**: `{sc_path}`\n\n"
        f"*Rationale*: {sc_reason}"
    )


def _format_hierarchy_ecommerce(rec: dict, cat: str) -> str:
    ec_path = rec.get("ecommerce_recommended_path", "N/A")
    ec_reason = rec.get("ecommerce_reason", "")
    return (
        f"**Ecommerce Taxonomy for {cat}**\n\n"
        f"**Path**: `{ec_path}`\n\n"
        f"*Rationale*: {ec_reason}"
    )


def _format_hierarchy_all(rec: dict, cat: str) -> str:
    global_path = (
        rec.get("global_generalized_hierarchy_path")
        or rec.get("recommended_path")
        or rec.get("supply_chain_recommended_path", "N/A")
    )
    sc_path = rec.get("recommended_path") or rec.get("supply_chain_recommended_path", "N/A")
    ec_path = rec.get("ecommerce_recommended_path", "N/A")
    unspsc = rec.get("unspsc_code", "N/A")
    return (
        f"**Complete Taxonomy for {cat}**\n\n"
        f"| View | Path |\n|---|---|\n"
        f"| **General** | `{global_path}` |\n"
        f"| **Supply Chain** | `{sc_path}` |\n"
        f"| **Ecommerce** | `{ec_path}` |\n"
        f"| **UNSPSC** | `{unspsc}` |\n\n"
        f"*Supply chain rationale*: {rec.get('supply_chain_reason', '')}\n\n"
        f"*Ecommerce rationale*: {rec.get('ecommerce_reason', '')}"
    )


def _handle_hierarchy(params: dict) -> tuple[str, str | None]:
    _log("HANDLER/HIERARCHY", f"Params: {json.dumps(params, default=str)}")
    if st.session_state.df is None:
        _log("HANDLER/HIERARCHY", "No data loaded — returning early")
        return "Upload a dataset first so I can resolve hierarchy paths.", None

    cat = st.session_state.category
    view = params.get("view_type", "general")

    if st.session_state.hierarchy_result:
        _log("HANDLER/HIERARCHY", f"Returning cached hierarchy (view={view})")
        r = st.session_state.hierarchy_result
        if view == "supply_chain":
            return _format_hierarchy_supply_chain(r, cat), "hierarchy"
        elif view == "ecommerce":
            return _format_hierarchy_ecommerce(r, cat), "hierarchy"
        elif view == "all":
            return _format_hierarchy_all(r, cat), "hierarchy"
        else:
            return _format_hierarchy_global(r, cat), "hierarchy"

    _log("HANDLER/HIERARCHY", f"Resolving hierarchy for category '{cat}'")
    with st.status(f"Resolving hierarchy for **{cat}**...", expanded=True) as status:
        from normalisation_rules.hierarchy.resolver import standardize_hierarchy
        df = pd.DataFrame({"category": [cat]})
        dm = st.session_state.domain_model
        try:
            _, json_records = standardize_hierarchy(df, "category", domain_model=dm)
            rec = json_records[0] if json_records else {}
            st.session_state.hierarchy_result = rec
            _log_block("HANDLER/HIERARCHY", "HIERARCHY RESOLVED", json.dumps(rec, indent=2, default=str)[:3000])
            status.update(label="✅ Hierarchy", state="complete")
            return _format_hierarchy_global(rec, cat), "hierarchy"
        except Exception as exc:
            _log("HANDLER/HIERARCHY", f"Hierarchy FAILED: {exc}\n{traceback.format_exc()}", level="ERROR")
            status.update(label="Error", state="error")
            return f"Error: {exc}", None


def _handle_multi_view(params: dict) -> tuple[str, str | None]:
    if st.session_state.df is None:
        return "Upload a dataset first.", None
    view_type = params.get("view_type", "supply_chain")
    cat = st.session_state.category

    if view_type in st.session_state.view_projections:
        return _format_view(st.session_state.view_projections[view_type], view_type), f"view_{view_type}"

    source = params.get("source", "attributes")
    if source == "rules" and st.session_state.derived_rules:
        all_rules = [r for rules in st.session_state.derived_rules.values() for r in rules]
        if all_rules:
            with st.status(f"Projecting into {view_type.replace('_',' ')} view...") as status:
                from normalisation_rules.graph import project_rules_to_views
                result = project_rules_to_views(all_rules, cat, view_type)
                st.session_state.view_projections[view_type] = result
                status.update(label="✅ Done", state="complete")
            return _format_view(result, view_type), f"view_{view_type}"

    attrs = st.session_state.canonical_attributes or {}
    lens_data = attrs.get("lenses", {}).get(view_type, [])
    if lens_data:
        result = {"view_type": view_type, "projected": lens_data}
        st.session_state.view_projections[view_type] = result
        return _format_view(result, view_type), f"view_{view_type}"

    return f"No data for {view_type.replace('_',' ')} view yet.", None


def _format_view(result: dict, view_type: str) -> str:
    label = view_type.replace("_", " ").title()
    lines = [f"**{label} View:**\n"]
    if "projected_rules" in result:
        for pr in result["projected_rules"]:
            lines.append(f"- [{pr.get('relevance','')}] {pr.get('rule','')}")
    elif "projected" in result:
        for item in result["projected"]:
            lines.append(f"- **{item.get('name','') if isinstance(item,dict) else item}**")
    return "\n".join(lines)


def _handle_show_attributes(params: dict) -> tuple[str, str | None]:
    attrs = st.session_state.canonical_attributes
    if not attrs or not attrs.get("backbone"):
        if st.session_state.df is not None and st.session_state.category:
            _run_attribute_resolution()
            attrs = st.session_state.canonical_attributes
            if not attrs or not attrs.get("backbone"):
                return "Attribute resolution did not produce results. Please try again.", None
        else:
            return "Upload a dataset first, then ask me to resolve attributes.", None
    backbone = attrs["backbone"]
    lines = [f"**Canonical Schema — {st.session_state.category}** ({len(backbone)} attributes):\n"]
    lines.append("| # | Attribute | Role | Type | Confidence |")
    lines.append("|---|-----------|------|------|------------|")
    for i, a in enumerate(backbone, 1):
        conf = a.get("confidence", {}).get("composite", "?")
        lines.append(f"| {i} | **{a.get('name','')}** | {a.get('structural_role','')} | {a.get('data_type','')} | {conf} |")

    report = st.session_state.schema_report
    if report and not report.get("error"):
        lines.append("\n---")
        lines.append(_format_schema_report(report))
    return "\n".join(lines), "attributes"


def _handle_show_rules(params: dict) -> tuple[str, str | None]:
    rules = st.session_state.derived_rules
    col = params.get("column")
    if not rules:
        return "No rules yet. Ask me to *\"normalize [column]\"* to derive them.", None
    if col:
        matched = _find_column(col)
        if matched and matched in rules:
            return f"**Rules for `{matched}`:**\n\n" + "\n".join(f"- {r}" for r in rules[matched]), "rules"
        return f"No rules for \"{col}\".", None
    lines = ["**All normalisation rules:**\n"]
    for col_name, col_rules in rules.items():
        lines.append(f"**`{col_name}`:**")
        for r in col_rules:
            lines.append(f"  - {r}")
    return "\n".join(lines), "rules"


def _handle_resolve_attributes(params: dict) -> tuple[str, str | None]:
    """Explicitly resolve canonical attributes on user demand."""
    if st.session_state.df is None:
        return "Upload a dataset first so I can resolve attributes for it.", None
    if not st.session_state.category:
        return "I need to know the product category first. Please confirm the domain detection or tell me the category.", None
    _run_attribute_resolution()
    return _handle_show_attributes(params)


def _handle_change_category(params: dict) -> tuple[str, str | None]:
    new_cat = params.get("new_category")
    if not new_cat:
        cats = get_categories_from_docx()
        if cats:
            return "Which category?\n\n" + "\n".join(f"- {c}" for c in cats[:20]), None
        return "Type the category name.", None
    st.session_state.category = new_cat
    st.session_state.domain_model = None
    st.session_state.domain_model_path = None
    for key in ("profiling", "profiling_path", "canonical_attributes", "schema_report"):
        st.session_state[key] = None
    st.session_state.derived_rules = {}
    st.session_state.hierarchy_result = None
    st.session_state.view_projections = {}
    st.session_state.auto_pipeline_done = False
    return f"Category changed to **{new_cat}**. Re-running analysis...", None


def _handle_download(params: dict) -> tuple[str, str | None]:
    available = []
    if st.session_state.domain_model:
        available.append("domain model")
    if st.session_state.canonical_attributes and st.session_state.canonical_attributes.get("backbone"):
        available.append("attributes")
    if st.session_state.derived_rules:
        available.append("rules")
    if st.session_state.hierarchy_result:
        available.append("hierarchy")
    if st.session_state.profiling:
        available.append("profiling")
    if st.session_state.schema_report:
        available.append("schema report")
    if not available:
        return "Nothing to download yet.", None
    return "**Downloads** (buttons below + sidebar):\n\n" + "\n".join(f"- {a.title()}" for a in available), "all"


def _handle_schema_advice(params: dict, user_message: str) -> tuple[str, str | None]:
    return _schema_advice_response(user_message, params), None


def _handle_explain(params: dict) -> tuple[str, str | None]:
    return _smart_response(params.get("topic", "explain the reasoning")), None


def _handle_general(params: dict, user_message: str) -> tuple[str, str | None]:
    return _smart_response(user_message or params.get("question", "")), None


# ===================================================================
#  Render download buttons
# ===================================================================

def _render_download_buttons(download_key: str):
    cat = (st.session_state.category or "data").replace(" ", "_")
    cols = st.columns(4)

    if download_key in ("domain_model", "all"):
        dm = st.session_state.domain_model
        if dm:
            cols[0].download_button("🧠 Domain Model JSON",
                json.dumps(dm, indent=2, ensure_ascii=False).encode("utf-8"),
                f"{cat}_domain_model.json", "application/json", key=f"dl_dm_{download_key}")

    if download_key in ("attributes", "all"):
        attrs = st.session_state.canonical_attributes
        if attrs and attrs.get("backbone"):
            df_attr = _backbone_to_df(attrs["backbone"])
            if not df_attr.empty:
                cols[1].download_button("📊 Attributes CSV", _df_to_csv_bytes(df_attr),
                    f"{cat}_attributes.csv", "text/csv", key=f"dl_ac_{download_key}")
                cols[2].download_button("📊 Attributes Excel", _df_to_excel_bytes(df_attr),
                    f"{cat}_attributes.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_ax_{download_key}")

    if download_key in ("rules", "all"):
        rules = st.session_state.derived_rules
        if rules:
            df_rules = _rules_to_df(rules)
            if not df_rules.empty:
                cols[3].download_button("📋 Rules CSV", _df_to_csv_bytes(df_rules),
                    f"{cat}_rules.csv", "text/csv", key=f"dl_rc_{download_key}")

    if download_key in ("hierarchy", "all"):
        hier = st.session_state.hierarchy_result
        if hier:
            cols[0].download_button("🗂️ Hierarchy CSV", _df_to_csv_bytes(_hierarchy_to_df(hier)),
                f"{cat}_hierarchy.csv", "text/csv", key=f"dl_hc_{download_key}")

    if download_key in ("profiling", "all"):
        if st.session_state.profiling:
            cols[1].download_button("📈 Profiling JSON",
                json.dumps(st.session_state.profiling, indent=2, ensure_ascii=False).encode("utf-8"),
                f"{cat}_profiling.json", "application/json", key=f"dl_pj_{download_key}")

    if download_key in ("schema report", "all"):
        if st.session_state.schema_report:
            cols[2].download_button("📝 Schema Report",
                json.dumps(st.session_state.schema_report, indent=2, ensure_ascii=False).encode("utf-8"),
                f"{cat}_schema_report.json", "application/json", key=f"dl_sr_{download_key}")


# ===================================================================
#  Seed greeting
# ===================================================================
if not st.session_state.messages:
    _log("SESSION", "New session — displaying seed greeting")
    _add("assistant",
         "**Schema Builder** — opinionated AI schema architect for product data.\n\n"
         "I produce deployable, defensible product data schemas grounded in industry "
         "standards.  I don't just describe your data — I define what it *should* "
         "look like to support buying, selling, and moving products.\n\n"
         "**Ask me anything right now** — no dataset required:\n"
         "- *\"What attributes should a contactor schema have?\"*\n"
         "- *\"Should I split 'Type' into sub-attributes?\"*\n"
         "- *\"What regex should Part Number follow?\"*\n"
         "- *\"What's the difference between variant-defining and descriptive?\"*\n"
         "- *\"How should I model the relationship between current and voltage?\"*\n\n"
         "Or **upload a dataset** (sidebar) and I'll build the canonical target schema, "
         "identify gaps, and make concrete schema decisions with full rationale.")


# ===================================================================
#  Render chat history
# ===================================================================
_render_history()

# ===================================================================
#  Handle file upload (from sidebar)
# ===================================================================
if uploaded is not None and st.session_state.df is None:
    _log("UPLOAD", f"File received: {uploaded.name} ({uploaded.size} bytes)")
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        elif uploaded.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded)
        else:
            df = pd.read_json(uploaded)
        st.session_state.df = df
        st.session_state.file_name = uploaded.name
        _log_block("UPLOAD", "FILE LOADED",
                   f"Name: {uploaded.name}\nRows: {len(df)}\nColumns: {len(df.columns)}\n"
                   f"Column names: {list(df.columns)}\nDtypes:\n{df.dtypes.to_string()}")
        _add("user", f"I uploaded **{uploaded.name}**.")

        # Auto-detect domain/sub-domain/category
        _log("UPLOAD/DETECT", "Auto-detecting domain overview from data...")
        columns = list(df.columns)
        sample_vals: dict[str, list[str]] = {}
        for c in columns:
            sample_vals[c] = df[c].dropna().head(5).astype(str).tolist()

        from normalisation_rules.category_detector import detect_category
        cat_result = detect_category(df, uploaded.name)
        detected_cat = cat_result.get("category", "Unknown")

        overview = detect_domain_overview(
            columns=columns,
            sample_values=sample_vals,
            filename=uploaded.name,
            detected_category=detected_cat,
        )
        _log_block("UPLOAD/DETECT", "DOMAIN OVERVIEW DETECTED", json.dumps(overview, indent=2))

        st.session_state.detected_domain_info = overview
        st.session_state.awaiting_domain_confirm = True
        st.session_state.category_confidence = overview.get("confidence", cat_result.get("confidence", 0))
        st.session_state.category_reasoning = overview.get("reasoning", cat_result.get("reasoning", ""))

        domain_str = overview.get("domain", "Unknown")
        sub_domain_str = overview.get("sub_domain", "Unknown")
        category_str = overview.get("category", detected_cat)

        confirm_msg = (
            f"**{uploaded.name}** — {len(df):,} rows x {len(df.columns)} columns.\n\n"
            f"I detected the following from your data:\n"
            f"- **Domain**: {domain_str}\n"
            f"- **Sub-Domain**: {sub_domain_str}\n"
            f"- **Category**: {category_str}\n"
            f"- **Confidence**: {overview.get('confidence', 0):.0%}\n\n"
            f"_{overview.get('reasoning', '')}_\n\n"
            f"**Is this correct?** Reply *\"yes\"* to proceed, or tell me the correct "
            f"domain/sub-domain/category values."
        )
        _add("assistant", confirm_msg)
        st.rerun()
    except Exception as exc:
        _log("UPLOAD", f"File load FAILED: {exc}", level="ERROR")
        _add("assistant", f"Could not read that file: `{exc}`")
        st.rerun()

# Show compact preview if data loaded
if st.session_state.df is not None:
    with st.expander(f"📄 {st.session_state.file_name} — {len(st.session_state.df):,} rows x {len(st.session_state.df.columns)} cols", expanded=False):
        st.dataframe(st.session_state.df.head(5), use_container_width=True, height=180)

# ===================================================================
#  Sidebar status & downloads (only when data loaded)
# ===================================================================
if st.session_state.category or st.session_state.domain:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 Session**")
    if st.session_state.domain:
        st.sidebar.markdown(f"Domain: **{st.session_state.domain}**")
        st.sidebar.markdown(f"Sub-Domain: **{st.session_state.sub_domain}**")
    if st.session_state.category:
        st.sidebar.markdown(f"Category: **{st.session_state.category}**")
    if st.session_state.domain_model:
        _ec = sum(len(v) for v in st.session_state.domain_model.get("entities", {}).values() if isinstance(v, list))
        st.sidebar.markdown(f"Domain Model: **{_ec}** entities")
    if st.session_state.canonical_attributes:
        bb = st.session_state.canonical_attributes.get("backbone", [])
        st.sidebar.markdown(f"Schema: **{len(bb)}** attributes")
    if st.session_state.schema_report:
        comp = st.session_state.schema_report.get("schema_completeness_pct", "?")
        st.sidebar.markdown(f"Completeness: **{comp}%**")
    if st.session_state.derived_rules:
        st.sidebar.markdown(f"Normalised: **{len(st.session_state.derived_rules)}** cols")
    if st.session_state.hierarchy_result:
        st.sidebar.markdown("Hierarchy: ✅")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**📥 Downloads**")
    _cat = (st.session_state.category or "data").replace(" ", "_")
    _any_dl = False

    if st.session_state.domain_model and st.session_state.domain_model_path:
        _any_dl = True
        st.sidebar.download_button("Domain Model (JSON)",
            json.dumps(st.session_state.domain_model, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{_cat}_domain_model.json", "application/json", key="sb_dm")

    attrs = st.session_state.canonical_attributes
    if attrs and attrs.get("backbone"):
        _any_dl = True
        df_a = _backbone_to_df(attrs["backbone"])
        if not df_a.empty:
            st.sidebar.download_button("Attributes (CSV)", _df_to_csv_bytes(df_a),
                f"{_cat}_attributes.csv", "text/csv", key="sb_ac")
            st.sidebar.download_button("Attributes (JSON)",
                json.dumps(attrs, indent=2, ensure_ascii=False).encode("utf-8"),
                f"{_cat}_attributes.json", "application/json", key="sb_aj")

    if st.session_state.derived_rules:
        _any_dl = True
        df_r = _rules_to_df(st.session_state.derived_rules)
        if not df_r.empty:
            st.sidebar.download_button("Rules (CSV)", _df_to_csv_bytes(df_r),
                f"{_cat}_rules.csv", "text/csv", key="sb_rc")

    if st.session_state.hierarchy_result:
        _any_dl = True
        st.sidebar.download_button("Hierarchy (CSV)",
            _df_to_csv_bytes(_hierarchy_to_df(st.session_state.hierarchy_result)),
            f"{_cat}_hierarchy.csv", "text/csv", key="sb_hc")

    if st.session_state.profiling:
        _any_dl = True
        st.sidebar.download_button("Profiling (JSON)",
            json.dumps(st.session_state.profiling, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{_cat}_profiling.json", "application/json", key="sb_pj")

    if st.session_state.schema_report and not st.session_state.schema_report.get("error"):
        _any_dl = True
        st.sidebar.download_button("Schema Report (JSON)",
            json.dumps(st.session_state.schema_report, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{_cat}_schema_report.json", "application/json", key="sb_sr")

    if not _any_dl:
        st.sidebar.caption("No results yet.")

# Log file download
st.sidebar.markdown("---")
st.sidebar.markdown("**📜 Session Log**")
_log_path = _get_session_log_path()
if _log_path.exists():
    st.sidebar.download_button(
        "Download Session Log",
        _log_path.read_bytes(),
        _log_path.name,
        "text/plain",
        key="sb_log",
    )
    st.sidebar.caption(f"`{_log_path.name}`")

# ===================================================================
#  Chat input — ALWAYS visible
# ===================================================================
if prompt := st.chat_input("Ask me about schema design, attributes, naming, rules..."):
    _log_block("CHAT", "USER MESSAGE", prompt)
    _add("user", prompt)

    with st.chat_message("user"):
        st.markdown(prompt)

    # --- Handle domain confirmation flow ---
    if st.session_state.awaiting_domain_confirm:
        _log("CHAT/ROUTE", "Awaiting domain confirmation — routing to confirmation handler")
        with st.chat_message("assistant"):
            _handle_domain_confirm(prompt)
        st.rerun()

    with st.chat_message("assistant"):
        has_data = st.session_state.df is not None
        has_domain_model = st.session_state.domain_model is not None
        _log("CHAT/ROUTE", f"has_data={has_data}, has_domain_model={has_domain_model} — classifying intent...")

        intent_result = _classify_intent(prompt)
        intent = intent_result.get("intent", "general")
        params = intent_result.get("params", {})
        confidence = intent_result.get("confidence", 0)

        # Conversational domain resolution: if user asks schema questions
        # but there's no domain model and no data, ask for domain info
        needs_domain = intent in (
            "normalize", "hierarchy", "multi_view", "show_attributes",
            "resolve_attributes", "show_rules", "schema_advice",
        )
        if not has_data and not has_domain_model and needs_domain:
            _log("CHAT/ROUTE", f"Intent '{intent}' needs domain context but none available — asking for domain info")
            response_text = (
                "To give you the best schema advice, I need to understand your domain context.\n\n"
                "Could you tell me:\n"
                "1. **Domain** — e.g., Industrial Component, Consumer Electronics, Automotive Parts\n"
                "2. **Sub-Domain** — e.g., Electrical Equipment, Mechanical Components, Pneumatic Systems\n"
                "3. **Category** — e.g., Contactors, Circuit Breakers, Limit Switches, Relays\n\n"
                "Or simply upload a dataset and I'll auto-detect these for you."
            )
            download_key = None
        elif intent == "domain_setup":
            _log("CHAT/ROUTE", "Handling domain_setup intent")
            domain = params.get("domain", "")
            sub_domain = params.get("sub_domain", "")
            category = params.get("category", "")
            if domain and sub_domain and category:
                st.session_state.domain = domain
                st.session_state.sub_domain = sub_domain
                st.session_state.category = category
                _log("CHAT/ROUTE", f"Generating domain model for {domain} > {sub_domain} > {category}")
                try:
                    dm, dm_path = generate_domain_model(
                        domain=domain, sub_domain=sub_domain, category=category,
                    )
                    st.session_state.domain_model = dm
                    st.session_state.domain_model_path = str(dm_path)
                    entity_count = sum(len(v) for v in dm.get("entities", {}).values() if isinstance(v, list))
                    prop_count = sum(
                        sum(len(p) for p in g.values() if isinstance(p, list))
                        for g in dm.get("property_model", {}).values()
                    )
                    response_text = (
                        f"Domain model generated for **{domain} > {sub_domain} > {category}**.\n\n"
                        f"- **Entities**: {entity_count}\n"
                        f"- **Properties**: {prop_count}\n"
                        f"- **Ontology triplets**: {len(dm.get('ontology', {}).get('triplets', []))}\n"
                        f"- **Invariants**: {len(dm.get('invariants', []))}\n\n"
                        f"I'm now ready to answer schema questions about {category}. "
                        f"Upload a dataset for data-grounded advice, or ask away!"
                    )
                except Exception as exc:
                    response_text = f"Failed to generate domain model: {exc}"
                download_key = None
            else:
                missing = []
                if not domain:
                    missing.append("domain")
                if not sub_domain:
                    missing.append("sub-domain")
                if not category:
                    missing.append("category")
                response_text = (
                    f"I still need the following: **{', '.join(missing)}**.\n\n"
                    f"For example: *Domain: Industrial Component, Sub-Domain: Electrical Equipment, Category: Contactors*"
                )
                download_key = None
        elif not has_data and intent in ("normalize", "show_rules", "download", "change_category"):
            _log("CHAT/ROUTE", f"Intent '{intent}' requires uploaded data → falling back to smart_response")
            response_text = _smart_response(prompt)
            download_key = None
        else:
            _log("CHAT/ROUTE", f"Routing to handler: intent={intent}, confidence={confidence}, params={json.dumps(params, default=str)}")
            handlers = {
                "normalize": lambda p: _handle_normalize(p),
                "hierarchy": lambda p: _handle_hierarchy(p),
                "multi_view": lambda p: _handle_multi_view(p),
                "show_attributes": lambda p: _handle_show_attributes(p),
                "resolve_attributes": lambda p: _handle_resolve_attributes(p),
                "show_rules": lambda p: _handle_show_rules(p),
                "change_category": lambda p: _handle_change_category(p),
                "download": lambda p: _handle_download(p),
                "schema_advice": lambda p: _handle_schema_advice(p, prompt),
                "explain": lambda p: _handle_explain(p),
                "upload": lambda p: ("Upload your file using the **sidebar uploader** on the left.", None),
                "general": lambda p: _handle_general(p, prompt),
            }
            handler = handlers.get(intent, lambda p: _handle_general(p, prompt))
            response_text, download_key = handler(params)

        _log_block("CHAT", "ASSISTANT RESPONSE",
                   f"Intent: {intent} | Confidence: {confidence} | Download key: {download_key}\n"
                   f"Response length: {len(response_text)} chars\n\n{response_text[:2000]}")

        st.markdown(response_text)

        if download_key:
            st.markdown("---")
            _render_download_buttons(download_key)
            _log("CHAT", f"Rendered download buttons for key='{download_key}'")

    _add("assistant", response_text)

    if intent == "change_category" and params.get("new_category"):
        _log("CHAT", f"Category change to '{params['new_category']}' — triggering rerun")
        st.rerun()
