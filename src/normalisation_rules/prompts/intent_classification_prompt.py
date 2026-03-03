"""Prompt for LLM-powered conversational intent classification."""


def build_intent_classification_prompt(
    user_message: str,
    session_context: dict,
) -> str:
    """Classify user intent from natural language and extract parameters.

    The session_context dict contains:
      - category: current detected category or None
      - has_data: whether a dataset is loaded
      - has_attributes: whether attribute resolution has run
      - derived_rules_columns: list of columns with cached rules
      - has_hierarchy: whether hierarchy has been resolved
      - cached_views: list of view types already projected
      - recent_messages: last 3-5 messages for conversational context
    """
    cat = session_context.get("category") or "(none)"
    has_data = session_context.get("has_data", False)
    has_attrs = session_context.get("has_attributes", False)
    rules_cols = session_context.get("derived_rules_columns", [])
    has_hier = session_context.get("has_hierarchy", False)
    cached_views = session_context.get("cached_views", [])
    recent = session_context.get("recent_messages", [])

    recent_block = ""
    if recent:
        recent_block = "\n".join(
            f"  {m['role']}: {m['content'][:400]}" for m in recent[-10:]
        )

    rules_block = ", ".join(rules_cols) if rules_cols else "(none yet)"
    views_block = ", ".join(cached_views) if cached_views else "(none yet)"

    return f"""You are the intent classifier for Schema Builder, an opinionated AI schema
architect that produces deployable product data schemas for industrial equipment.
The agent makes concrete schema decisions grounded in standards and expert knowledge.

**Current session state:**
- Dataset loaded: {has_data}
- Detected category: {cat}
- Attribute resolution done: {has_attrs}
- Columns with normalisation rules: {rules_block}
- Hierarchy resolved: {has_hier}
- View projections cached: {views_block}

**Recent conversation:**
{recent_block or "  (start of conversation)"}

**User's latest message:**
"{user_message}"

**Task**: Classify the user's intent into exactly ONE of these categories and extract
any relevant parameters.

**Intents:**

- `schema_advice` — user asks a SCHEMA DESIGN question requiring an opinionated decision:
  splitting/merging attributes, data types, regex patterns, naming conventions, cardinality,
  variant logic, relationships, constraints, enumerations, classes, shapes, abstract
  representations, or any "should I...?" or "how to model...?" question about schema.
  Examples: "should I split Type into separate attributes?", "what regex for part numbers?",
  "what data type should voltage be?", "is this variant-defining or descriptive?",
  "how to model the relationship between current and voltage?", "what naming convention?",
  "should this be an enum or free text?", "what SHACL shape?", "how to represent in RDF?",
  "what attributes should a contactor schema have?", "what's the ideal schema for relays?"
  Params: {{"attribute": "attribute name mentioned or null", "question": "the design question"}}

- `resolve_attributes` — user explicitly asks to resolve / build / generate canonical
  attributes or the canonical attribute schema for the loaded dataset or category.
  Examples: "resolve attributes", "build the canonical schema", "generate attributes",
  "what are the relevant attributes?", "show me possible attributes", "attribute resolution",
  "find canonical attributes", "run attribute resolver"
  Params: {{}}

- `domain_setup` — user is providing domain/sub-domain/category information in response
  to the system asking for it, or proactively specifying their domain context.
  Examples: "domain is industrial component, sub-domain electrical equipment, category contactors",
  "the category is relays", "I'm working with limit switches in electrical equipment",
  "industrial component > electrical > circuit breakers"
  Params: {{"domain": "domain name or empty", "sub_domain": "sub-domain name or empty", "category": "category name or empty"}}

- `normalize` — user wants to derive normalisation rules for one or more columns.
  Examples: "normalize voltage", "run rules for current rating", "clean up poles",
  "normalise all columns"
  Params: {{"column": "column name or null if not specified"}}

- `hierarchy` — user wants hierarchy / taxonomy / classification path resolution.
  Examples: "show hierarchy", "UNSPSC path", "classify this category", "taxonomy",
  "show supply chain taxonomy", "supply chain hierarchy", "ERP classification",
  "show ecommerce taxonomy", "selling path", "channel navigation",
  "show all taxonomy views", "all hierarchies"
  Params: {{"view_type": "general|supply_chain|ecommerce|all"}}
  Rules for view_type:
  - Default is "general" (when user just says "hierarchy" or "taxonomy")
  - "supply_chain" when user mentions supply chain, ERP, procurement, sourcing
  - "ecommerce" when user mentions ecommerce, selling, channel, commerce, navigation
  - "all" when user says "all views", "all taxonomies", "show all", "complete hierarchy"

- `multi_view` — user wants data projected into a business lens / view.
  Examples: "show supply chain view", "ERP lens", "ecommerce perspective", "analytical view"
  Params: {{"view_type": "supply_chain|ecommerce|analytical", "source": "rules|attributes"}}

- `show_attributes` — user wants to see already-resolved canonical attributes / schema.
  Examples: "show attributes", "list the schema", "canonical attributes"
  Params: {{}}

- `show_rules` — user wants to see previously derived normalisation rules.
  Examples: "show rules", "what rules exist", "rules for voltage"
  Params: {{"column": "column name or null for all"}}

- `change_category` — user wants to override the detected category.
  Examples: "change category to relays", "this is actually limit switches"
  Params: {{"new_category": "category name or null"}}

- `upload` — user wants to upload a file.
  Params: {{}}

- `download` — user wants to download / export results.
  Examples: "download", "export csv", "save results"
  Params: {{"what": "rules|attributes|hierarchy|schema|profiling|all"}}

- `explain` — user wants an explanation of WHY a decision was made.
  Examples: "why is rated voltage variant-defining?", "explain the recommendations"
  Params: {{"topic": "what they want explained"}}

- `general` — anything else: greetings, capabilities questions, domain knowledge,
  general conversation, questions about the system.
  Examples: "what can you do?", "hello", "tell me about contactors", "what features
  do you have?", "how does this system work?"
  Params: {{"question": "the user's question"}}

**Classification Rules:**
- `resolve_attributes` when user explicitly asks to resolve, generate, or build attributes.
  This is different from `show_attributes` which just displays already-resolved attributes.
- `domain_setup` when user is providing domain context information.
- `schema_advice` takes PRIORITY over `general` when the user asks about data modeling,
  schema design, splitting/merging attributes, data types, regex, naming, relationships,
  constraints, or abstract representations.
- `schema_advice` also applies to questions like "what attributes should X have?" when
  no dataset is loaded (the system can answer from domain knowledge).
- If no dataset is loaded and the user asks about normalisation/hierarchy, classify as
  `general` (the system will answer from knowledge) unless they specifically say "upload".
- "show supply chain view" or "ERP lens" → multi_view with view_type=supply_chain
- "ecommerce view" or "selling perspective" → multi_view with view_type=ecommerce
- "analytical view" or "reporting lens" → multi_view with view_type=analytical

**Output ONLY valid JSON:**
{{
  "intent": "one of the intent names above",
  "params": {{}},
  "confidence": 0.0,
  "response_hint": "brief description of what the user wants"
}}
"""
