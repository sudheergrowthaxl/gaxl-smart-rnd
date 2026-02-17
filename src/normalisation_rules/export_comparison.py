"""Write comparison workbook: Before, After, Comparison, and optional Python_Expressions."""

from pathlib import Path

import pandas as pd

# Excel row limit (openpyxl / xlsx): 1,048,576 rows including header
EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_DATA_ROWS = EXCEL_MAX_ROWS - 1


def write_comparison_workbook(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    df_comparison: pd.DataFrame,
    path: Path,
    attribute_to_code: dict[str, str] | None = None,
) -> None:
    """Write one Excel workbook with sheets Before, After, Comparison, and optionally Python_Expressions.
    Comparison sheet is capped at Excel max rows; if truncated, an Info sheet is added."""
    path.parent.mkdir(parents=True, exist_ok=True)
    comparison_truncated = False
    comparison_total = len(df_comparison)
    if comparison_total > EXCEL_MAX_DATA_ROWS:
        df_comparison = df_comparison.head(EXCEL_MAX_DATA_ROWS)
        comparison_truncated = True
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if comparison_truncated:
            info_df = pd.DataFrame([
                {"Note": f"Comparison sheet truncated to {EXCEL_MAX_DATA_ROWS} rows (total changes: {comparison_total})."},
            ])
            info_df.to_excel(writer, sheet_name="Info", index=False)
        df_before.to_excel(writer, sheet_name="Before", index=True)
        df_after.to_excel(writer, sheet_name="After", index=True)
        df_comparison.to_excel(writer, sheet_name="Comparison", index=False)
        if attribute_to_code:
            code_df = pd.DataFrame([
                {"Attribute": attr, "Python_code": code}
                for attr, code in attribute_to_code.items()
            ])
            code_df.to_excel(writer, sheet_name="Python_Expressions", index=False)
    return None
