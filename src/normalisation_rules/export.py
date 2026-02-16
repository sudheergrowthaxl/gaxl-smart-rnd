"""Export derived rules to Excel or text."""

from __future__ import annotations

from pathlib import Path


def _parse_rule_line(line: str) -> tuple[str, str, str, str] | None:
    """Parse a tab-separated rule line into (Entity, Attribute, Normalization, Rule description)."""
    line = line.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) >= 4:
        return (parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip())
    if len(parts) == 1 and (line.startswith("Contactors") or "Normalization" in line):
        # Malformed: put whole line in Rule description
        return ("", "", "Normalization", line)
    if len(parts) == 3:
        return (parts[0].strip(), parts[1].strip(), parts[2].strip(), "")
    return None


def write_rules_to_excel(rules_with_ref: list[tuple[str, str]], path: Path) -> None:
    """Write (rule_line, reference) pairs to an Excel file with columns Entity, Attribute, Normalization, Rule description, Reference."""
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Normalisation Rules"

    headers = ["Entity", "Attribute", "Normalization", "Rule description", "Reference"]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)

    row = 2
    for line, reference in rules_with_ref:
        parsed = _parse_rule_line(line)
        if parsed is None:
            continue
        entity, attr, norm, desc = parsed
        ws.cell(row=row, column=1, value=entity)
        ws.cell(row=row, column=2, value=attr)
        ws.cell(row=row, column=3, value=norm)
        ws.cell(row=row, column=4, value=desc)
        ws.cell(row=row, column=5, value=reference)
        row += 1

    # Column widths for readability
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 80
    ws.column_dimensions["E"].width = 40

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_rules_to_text(rules_with_ref: list[tuple[str, str]], path: Path) -> None:
    """Write (rule_line, reference) pairs to a plain text file (one rule per line, tab-separated, with Reference as 5th column)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{line}\t{reference}" for line, reference in rules_with_ref]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_rules_from_excel(path: Path) -> list[dict]:
    """Load rules from an existing Excel file into a list of dicts."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rules: list[dict] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        rules.append({
            "entity": str(row[0] or "").strip(),
            "attribute": str(row[1] or "").strip(),
            "normalization": str(row[2] or "").strip(),
            "description": str(row[3] or "").strip(),
            "reference": str(row[4] or "").strip() if len(row) > 4 else "",
        })
    wb.close()
    return rules


def write_validated_rules_to_excel(validated_rules: list[dict], path: Path) -> None:
    """Write validated rules to Excel with original columns + Validation + Validation Notes."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Validated Normalisation Rules"

    headers = [
        "Entity", "Attribute", "Normalization", "Rule description",
        "Reference", "Validation", "Validation Notes",
    ]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)

    # Conditional fills for validation status
    fill_valid = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    fill_invalid = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    fill_review = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    status_fills = {"Valid": fill_valid, "Invalid": fill_invalid, "Needs Review": fill_review}

    for row_idx, rule in enumerate(validated_rules, start=2):
        ws.cell(row=row_idx, column=1, value=rule.get("entity", ""))
        ws.cell(row=row_idx, column=2, value=rule.get("attribute", ""))
        ws.cell(row=row_idx, column=3, value=rule.get("normalization", ""))
        ws.cell(row=row_idx, column=4, value=rule.get("description", ""))
        ws.cell(row=row_idx, column=5, value=rule.get("reference", ""))

        status = rule.get("validation", "")
        status_cell = ws.cell(row=row_idx, column=6, value=status)
        if status in status_fills:
            status_cell.fill = status_fills[status]

        ws.cell(row=row_idx, column=7, value=rule.get("validation_notes", ""))

    # Column widths
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 80
    ws.column_dimensions["E"].width = 40
    ws.column_dimensions["F"].width = 16
    ws.column_dimensions["G"].width = 80

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def load_validated_rules_from_excel(path: Path) -> list[dict]:
    """Load validated rules (with Validation + Validation Notes columns) from Excel."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rules: list[dict] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        rule = {
            "entity": str(row[0] or "").strip(),
            "attribute": str(row[1] or "").strip(),
            "normalization": str(row[2] or "").strip(),
            "description": str(row[3] or "").strip(),
            "reference": str(row[4] or "").strip() if len(row) > 4 else "",
        }
        if len(row) > 5 and row[5]:
            rule["validation"] = str(row[5]).strip()
        if len(row) > 6 and row[6]:
            rule["validation_notes"] = str(row[6]).strip()
        rules.append(rule)
    wb.close()
    return rules


def write_few_shot_rules_to_excel(rules: list[dict], path: Path) -> None:
    """Write rules with few-shot examples to Excel with original columns + Few-shot Examples."""
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rules with Few-shot Examples"

    # Detect which columns exist in the input data
    has_validation = any(r.get("validation") for r in rules)
    headers = ["Entity", "Attribute", "Normalization", "Rule description", "Reference"]
    if has_validation:
        headers.extend(["Validation", "Validation Notes"])
    headers.append("Few-shot Examples")

    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)

    for row_idx, rule in enumerate(rules, start=2):
        col = 1
        ws.cell(row=row_idx, column=col, value=rule.get("entity", "")); col += 1
        ws.cell(row=row_idx, column=col, value=rule.get("attribute", "")); col += 1
        ws.cell(row=row_idx, column=col, value=rule.get("normalization", "")); col += 1
        ws.cell(row=row_idx, column=col, value=rule.get("description", "")); col += 1
        ws.cell(row=row_idx, column=col, value=rule.get("reference", "")); col += 1
        if has_validation:
            ws.cell(row=row_idx, column=col, value=rule.get("validation", "")); col += 1
            ws.cell(row=row_idx, column=col, value=rule.get("validation_notes", "")); col += 1
        ws.cell(row=row_idx, column=col, value=rule.get("few_shot_examples", ""))

    # Column widths
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 80
    ws.column_dimensions["E"].width = 40
    if has_validation:
        ws.column_dimensions["F"].width = 16
        ws.column_dimensions["G"].width = 80
        ws.column_dimensions["H"].width = 100
    else:
        ws.column_dimensions["F"].width = 100

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
