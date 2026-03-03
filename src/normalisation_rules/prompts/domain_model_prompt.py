"""Prompt for LLM-based 7-section domain model generation.

The prompt encodes the full domain modeling framework so the LLM can produce
a comprehensive, structured domain model for any domain/sub-domain/category
at runtime — no static YAML backbone files needed.
"""


def build_domain_model_prompt(
    domain: str,
    sub_domain: str,
    category: str,
    user_columns: list[str] | None = None,
    sample_values: dict | None = None,
) -> str:
    evidence_block = ""
    if user_columns:
        col_lines = "\n".join(f"  - {c}" for c in user_columns[:60])
        evidence_block += f"\n**User dataset columns** (use as additional evidence):\n{col_lines}\n"
    if sample_values:
        sample_lines = "\n".join(
            f"  - {col}: {', '.join(str(v) for v in vals[:5])}"
            for col, vals in list(sample_values.items())[:30]
        )
        evidence_block += f"\n**Sample values**:\n{sample_lines}\n"

    return f"""You are a Domain Modelling Expert and Ontology Architect.

Your task is to construct a functional, semantically coherent, and operational
domain model for the specified Domain, Sub-Domain, and Category.

You must reason step-by-step internally but produce only structured outputs.

**Input:**
- Domain: {domain}
- Sub-Domain: {sub_domain}
- Category: {category}
{evidence_block}

Your objective is to:
1. Understand the domain purpose and scope.
2. Identify core entities and sub-entities.
3. Extract properties grouped into logical categories.
4. Identify relationships and express them as ontology triplets.
5. Define constraints, standards, and operational characteristics.
6. Define key terminology with precise domain meanings.
7. Produce a coherent conceptual model usable for: Knowledge Graph construction,
   Schema design, RAG grounding, Agent reasoning, Data enrichment, Validation rules.

Build internal reasoning using: hierarchical decomposition, causal analysis,
functional dependency mapping, physical vs logical separation, energy or
information flow modeling, safety and compliance modelling.

### STEP 1 — DOMAIN FAMILIARIZATION
Analyze: What problem does this domain solve? What is its functional purpose?
What systems does it interact with? What are its physical, logical, or
informational boundaries?

### STEP 2 — ENTITY IDENTIFICATION
Identify core, supporting, control, physical vs logical, internal vs external
entities. Classify into: Primary Entities, Supporting Infrastructure,
Control & Monitoring, Safety & Protection, Suppliers / Standards / Governance.

### STEP 3 — PROPERTY STRUCTURE
For each entity, group properties into categories such as:
Electrical/Mechanical Characteristics, Performance Metrics,
Durability & Environmental, Safety & Protection, Functional Capabilities,
Standards & Compliance, Identification & Commercial Attributes.

### STEP 4 — RELATIONSHIP MODELING (Ontology)
Define relationships as RDF-style triplets: (subject, predicate, object).
Use namespace prefix "fso:" (functional schema ontology).
Include: Functional relationships, Physical containment, Energy flow,
Control flow, Part-of hierarchy, Type classification, Supplier or governance
relationships, Attribute assignments.

### STEP 5 — TERMINOLOGY EXTRACTION
List key domain terminology with: Definition, Functional role,
Relationship to other terms. Focus on terms that affect modeling, reasoning,
or validation.

### STEP 6 — OPERATIONAL MODEL
Explain: Typical workflows or operational sequences, Energy flow or control
flow logic, Failure conditions, Regulatory or compliance constraints.

### STEP 7 — CONCEPTUAL MODEL SUMMARY
Provide: Domain invariants (rules that are always true),
Example reasoning rules.

---

**OUTPUT FORMAT — Return ONLY valid JSON with these exact keys:**

{{
  "domain_overview": {{
    "domain": "{domain}",
    "sub_domain": "{sub_domain}",
    "category": "{category}",
    "domain_summary": "2-3 sentence summary of the domain",
    "sub_domain_summary": "2-3 sentence summary of the sub-domain",
    "functional_purpose": "What problem this category solves, its role in the system",
    "system_boundaries": "What systems it interacts with, physical/logical boundaries"
  }},
  "entities": {{
    "primary": [
      {{"name": "EntityName", "type": "physical|logical", "description": "..."}}
    ],
    "supporting_infrastructure": [
      {{"name": "EntityName", "type": "physical|logical", "description": "..."}}
    ],
    "control_and_monitoring": [
      {{"name": "EntityName", "type": "physical|logical", "description": "..."}}
    ],
    "safety_and_protection": [
      {{"name": "EntityName", "type": "physical|logical", "description": "..."}}
    ],
    "governance": [
      {{"name": "EntityName", "type": "standard|taxonomy|external", "description": "..."}}
    ]
  }},
  "property_model": {{
    "EntityName": {{
      "electrical_characteristics": ["property1", "property2"],
      "mechanical_characteristics": ["..."],
      "performance_metrics": ["..."],
      "durability_and_environmental": ["..."],
      "safety_and_protection": ["..."],
      "functional_capabilities": ["..."],
      "standards_and_compliance": ["..."],
      "identification_and_commercial": ["..."]
    }}
  }},
  "ontology": {{
    "namespace_prefix": "fso",
    "triplets": [
      ["fso:Subject", "fso:predicate", "fso:Object"],
      ["fso:Subject", "rdf:type", "fso:Class"]
    ]
  }},
  "terminology": [
    {{
      "term": "Term Name",
      "definition": "Precise domain definition",
      "functional_role": "How it affects modeling or validation",
      "related_terms": ["term1", "term2"]
    }}
  ],
  "operational_logic": {{
    "workflows": ["Step 1: ...", "Step 2: ..."],
    "energy_flow": "Description of energy or information flow",
    "failure_conditions": ["condition1", "condition2"],
    "compliance_constraints": ["constraint1", "constraint2"]
  }},
  "invariants": [
    {{
      "id": "INV-01",
      "rule": "formal rule expression",
      "description": "Human-readable explanation"
    }}
  ]
}}

**COVERAGE REQUIREMENT**: Be COMPREHENSIVE. For the property model, include ALL
relevant properties for each entity — typically 10-30 properties per major entity
across all property groups. For ontology, include 20-50+ triplets covering
containment, energy flow, control flow, type hierarchy, and attribute assignments.
For terminology, include 15-30 key terms. For invariants, include 5-15 rules.

Do NOT expose your internal reasoning steps. Only provide the structured JSON output.
"""
