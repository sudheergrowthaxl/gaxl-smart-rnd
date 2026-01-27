"""
Data-Driven Rules Generator
Generates data quality rules from profiling statistics enhanced with domain knowledge.
Follows the exact format from Rules_Format.txt
"""

import json
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import yaml
import re

# Paths
BASE_DIR = Path(r"C:\Users\Sudheer\OneDrive\SMART\Industry_Ontology")
PROFILING_FILE = BASE_DIR / "data" / "input" / "profiling" / "python_profiling 3.json"
SHAPE_CONFIG = BASE_DIR / "config" / "shape_constraints.yaml"
OUTPUT_FILE = BASE_DIR / "data" / "output" / "Data_Quality_Rules_v2.xlsx"

# Domain knowledge mappings
DOMAIN_KNOWLEDGE = {
    # Voltage attributes - IEC 60038 standard values
    "voltage": {
        "standard_values": [24, 48, 110, 120, 220, 230, 240, 380, 400, 415, 440, 480, 500, 690],
        "range": (12, 1000),
        "unit": "V",
        "standard": "IEC 60038"
    },
    "control_voltage": {
        "standard_values": [24, 48, 110, 120, 220, 230, 240],
        "range": (12, 400),
        "unit": "V"
    },
    # Current - IEC 60947-4-1
    "current": {
        "standard_values": [6, 9, 12, 16, 25, 32, 40, 50, 65, 80, 95, 115, 145, 170, 205, 250, 300, 400, 500, 630, 800, 1000, 1250, 1600, 2050],
        "range": (0.1, 5000),
        "unit": "A",
        "standard": "IEC 60947-4-1"
    },
    # Frequency
    "frequency": {
        "standard_values": [50, 60],
        "range": (45, 65),
        "unit": "Hz"
    },
    # IP Rating - IEC 60529
    "ip_rating": {
        "standard_values": ["IP00", "IP20", "IP40", "IP54", "IP55", "IP65", "IP66", "IP67"],
        "pattern": r"IP[0-6][0-9X]",
        "standard": "IEC 60529"
    },
    # Temperature
    "temperature": {
        "range": (-40, 85),
        "operating_range": (-25, 70),
        "unit": "C"
    },
    # Utilization Category - IEC 60947-4-1
    "utilization_category": {
        "standard_values": ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5a", "AC-5b", "AC-6a", "AC-6b", "AC-7a", "AC-7b", "AC-8a", "AC-8b", "DC-1", "DC-3", "DC-5"],
        "standard": "IEC 60947-4-1"
    },
    # Poles
    "poles": {
        "standard_values": [1, 2, 3, 4],
        "range": (1, 4)
    },
    # Horsepower
    "horsepower": {
        "range": (0.25, 1000),
        "unit": "HP"
    }
}

# Attribute to domain mapping
ATTRIBUTE_DOMAIN_MAP = {
    "zz_Control Voltage": "control_voltage",
    "zz_Supply Voltage": "voltage",
    "zz_Operating Voltage": "voltage",
    "zz_Operating Voltage Range": "voltage",
    "zz_Load Voltage": "voltage",
    "zz_Maximum Voltage": "voltage",
    "zz_Voltage Range": "voltage",
    "zz_Voltage Rating": "voltage",
    "zz_Current Rating": "current",
    "zz_Current, Ratings": "current",
    "zz_Continuous Current": "current",
    "zz_Load Current": "current",
    "zz_Surge Current": "current",
    "zz_Contact Current Rating": "current",
    "zz_Contact Rating": "current",
    "zz_Frequency": "frequency",
    "zz_IP Rating": "ip_rating",
    "zz_Ambient Temperature": "temperature",
    "zz_Maximum Ambient Temperature": "temperature",
    "zz_Minimum Ambient Temperature": "temperature",
    "zz_Operating Temperature": "temperature",
    "zz_Maximum Operating Temperature": "temperature",
    "zz_Minimum Operating Temperature": "temperature",
    "zz_Temperature Range": "temperature",
    "zz_Number of Poles": "poles",
    "zz_Horsepower Rating": "horsepower",
}

# Normalization patterns - common variations to standardize
NORMALIZATION_PATTERNS = {
    "voltage": [
        ('"{value}VAC", "{value} V AC", "{value}V~"', '"{value} V AC"'),
        ('"{value}VDC", "{value} V DC"', '"{value} V DC"'),
    ],
    "current": [
        ('"{value} Amps", "{value}A", "{value} A"', '"{value} A"'),
    ],
    "frequency": [
        ('"{value}Hz", "{value} Hz", "{value}HZ"', '"{value} Hz"'),
    ],
    "poles": [
        ('"3P", "3 Pole", "Three Pole", "3-Pole"', '"3"'),
        ('"1 + Shunt"', '"1", move "Shunt" to zz_Special Features'),
    ],
    "ip_rating": [
        ('"IP 20", "ip20", "IP-20"', '"IP20"'),
    ],
    "auxiliary_contact": [
        ('"1 NO + 1 NC", "1NO/1NC", "1N.O.+1N.C."', '"1NO+1NC"'),
    ],
    "mounting": [
        ('"On Rail", "35mm rail", "DIN 35", "TS35"', '"DIN Rail"'),
        ('"Screw mount", "Bolt mount", "Surface mount"', '"Panel Mount"'),
    ],
    "phase": [
        ('"Single phase", "1P", "1-phase", "1 Ph"', '"1 Phase"'),
        ('"Three phase", "3P", "3-phase", "3 Ph"', '"3 Phase"'),
    ],
}

def load_profiling_data():
    """Load profiling statistics from JSON file."""
    with open(PROFILING_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_shape_constraints():
    """Load shape constraints configuration."""
    with open(SHAPE_CONFIG, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_category_from_attribute(attr_name: str, profiling_data: dict) -> str:
    """Determine category based on attribute and profiling data."""
    # Check RS Product Category for hints
    rs_category = profiling_data.get("RS Product Category", {})
    top_values = rs_category.get("top_values", [])

    if top_values:
        category_str = top_values[0].get("value", "")
        if "Contactors" in category_str:
            return "Contactors"
        elif "Relay" in category_str:
            return "Relays"
        elif "Limit Switch" in category_str:
            return "Limit Switches"

    # Default to Contactors based on the profiling data
    return "Contactors"

def derive_completeness_rules(attr_name: str, attr_stats: dict, config: dict, category: str) -> list:
    """Derive completeness rules based on missing percentage thresholds."""
    rules = []
    missing_pct = attr_stats.get("missing_percentage", 0)
    thresholds = config.get("shape_constraints", {}).get("completeness", {})

    mandatory_threshold = thresholds.get("mandatory_threshold", 5.0)
    expected_threshold = thresholds.get("expected_threshold", 20.0)
    conditional_threshold = thresholds.get("conditional_threshold", 70.0)

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name", "MaterialNumber"]:
        return rules

    if missing_pct == 100.0:
        rules.append((category, attr_name, "Validation", f"Dead field - 100% missing, consider removing from schema"))
    elif missing_pct < mandatory_threshold:
        rules.append((category, attr_name, "Validation", f"Mandatory field - must not be empty (currently {100-missing_pct:.1f}% populated)"))
    elif missing_pct < expected_threshold:
        rules.append((category, attr_name, "Validation", f"Expected field - should be populated ({100-missing_pct:.1f}% currently have values)"))

    return rules

def derive_validation_rules(attr_name: str, attr_stats: dict, config: dict, category: str) -> list:
    """Derive validation rules based on data type, range, and domain knowledge."""
    rules = []
    datatype = attr_stats.get("datatype", "")
    range_vals = attr_stats.get("range", [None, None])
    top_values = attr_stats.get("top_values", [])

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name"]:
        return rules

    # Get domain knowledge if available
    domain = ATTRIBUTE_DOMAIN_MAP.get(attr_name)
    domain_info = DOMAIN_KNOWLEDGE.get(domain, {}) if domain else {}

    # Data type validation
    if datatype == "Numeric" and range_vals and range_vals[0] is not None:
        min_val, max_val = range_vals
        if domain_info:
            # Use domain knowledge for range
            std_range = domain_info.get("range")
            unit = domain_info.get("unit", "")
            standard = domain_info.get("standard", "")
            if std_range:
                rule_text = f"Value must be between {std_range[0]} and {std_range[1]}"
                if unit:
                    rule_text += f" {unit}"
                if standard:
                    rule_text += f" per {standard}"
                rules.append((category, attr_name, "Validation", rule_text))
        else:
            # Use data-driven range
            if min_val != max_val:
                rules.append((category, attr_name, "Validation", f"Data shows range {min_val} to {max_val}"))

    # Enumeration validation for categorical attributes
    if datatype == "Categorical" and top_values:
        values = [v.get("value") for v in top_values if v.get("value")]
        if len(values) <= 10 and len(values) >= 2:
            # Check if we have domain standard values
            if domain_info and "standard_values" in domain_info:
                std_vals = domain_info["standard_values"]
                std_vals_str = ", ".join(str(v) for v in std_vals[:8])
                if len(std_vals) > 8:
                    std_vals_str += f" (and {len(std_vals)-8} more)"
                rules.append((category, attr_name, "Validation", f"Must be one of standard values: {std_vals_str}"))
            else:
                vals_str = ", ".join(f'"{v}"' for v in values[:5])
                if len(values) > 5:
                    vals_str += f" (and {len(values)-5} more)"
                rules.append((category, attr_name, "Validation", f"Expected values include: {vals_str}"))

    # Pattern validation for specific attributes
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append((category, attr_name, "Validation", "Must match pattern IP[0-6][0-9] per IEC 60529"))

    if "UPC" in attr_name:
        rules.append((category, attr_name, "Validation", "Must be valid 12-digit UPC-A or 13-digit EAN with valid check digit"))

    if "Frequency" in attr_name:
        rules.append((category, attr_name, "Validation", "Must be 50 Hz, 60 Hz, or \"50/60 Hz\""))

    if "Phase" in attr_name and "Number" not in attr_name:
        rules.append((category, attr_name, "Validation", "Must be \"1 Phase\" or \"3 Phase\""))

    if "Number of Poles" in attr_name:
        rules.append((category, attr_name, "Validation", "Must be integer between 1 and 4"))

    if "Contact" in attr_name and ("Configuration" in attr_name or "Form" in attr_name):
        rules.append((category, attr_name, "Validation", "Must specify NO (Normally Open) and/or NC (Normally Closed) count"))

    if "Auxiliary Contact" in attr_name:
        rules.append((category, attr_name, "Validation", "Format must match pattern: [0-9]+NO(\\+[0-9]+NC)?"))

    if "Horsepower" in attr_name:
        rules.append((category, attr_name, "Validation", "Must be positive numeric value, correlate with voltage and phase"))

    if "Wire Size" in attr_name:
        rules.append((category, attr_name, "Validation", "AWG values: 22-4/0 or metric mm² values"))

    if "Temperature" in attr_name:
        if "Storage" in attr_name:
            rules.append((category, attr_name, "Validation", "Must be within -40°C to +85°C"))
        elif "Operating" in attr_name or "Ambient" in attr_name:
            rules.append((category, attr_name, "Validation", "Must be within -25°C to +70°C per IEC 60947-1"))

    # Text length validation
    if "80 Character" in attr_name:
        rules.append((category, attr_name, "Validation", "Must not exceed 80 characters"))

    return rules

def derive_normalization_rules(attr_name: str, attr_stats: dict, category: str) -> list:
    """Derive normalization rules based on top values and domain patterns."""
    rules = []
    top_values = attr_stats.get("top_values", [])

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name", "MaterialNumber"]:
        return rules

    # Voltage normalization
    if "Voltage" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"230VAC\", \"230 V AC\", \"230V~\" normalize to \"230 V AC\""))
        rules.append((category, attr_name, "Normalization", "Include voltage type suffix: \"V AC\" or \"V DC\""))

    # Current normalization
    if "Current" in attr_name and "Rating" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"6 Amps\", \"6A\", \"6 A\" normalize to \"6 A\""))

    # Frequency normalization
    if "Frequency" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"50Hz\", \"50 Hz\", \"50HZ\" normalize to \"50 Hz\""))

    # Poles normalization
    if "Number of Poles" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"3P\", \"3 Pole\", \"Three Pole\" normalize to \"3\""))
        rules.append((category, attr_name, "Normalization", "\"1 + Shunt\" normalize to \"1\", move \"Shunt\" to zz_Special Features"))

    # Mounting type normalization
    if "Mounting" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"On Rail\", \"35mm rail\", \"DIN 35\" normalize to \"DIN Rail\""))
        rules.append((category, attr_name, "Normalization", "\"Screw mount\", \"Bolt mount\", \"Surface mount\" normalize to \"Panel Mount\""))

    # Phase normalization
    if attr_name == "zz_Phase":
        rules.append((category, attr_name, "Normalization", "\"Single phase\", \"1P\", \"1-phase\" normalize to \"1 Phase\""))
        rules.append((category, attr_name, "Normalization", "\"Three phase\", \"3P\", \"3-phase\" normalize to \"3 Phase\""))

    # Auxiliary contact normalization
    if "Auxiliary Contact" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"1 NO + 1 NC\", \"1NO/1NC\", \"1N.O.+1N.C.\" normalize to \"1NO+1NC\""))

    # IP Rating normalization
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"IP 20\", \"ip20\", \"IP-20\" normalize to \"IP20\""))

    # Temperature normalization
    if "Temperature" in attr_name and "Range" not in attr_name:
        rules.append((category, attr_name, "Normalization", "Express as range: \"-25°C to +55°C\""))

    # Horsepower normalization
    if "Horsepower" in attr_name:
        rules.append((category, attr_name, "Normalization", "Express as \"X HP\" not \"X hp\" or \"X horsepower\""))

    # Wire size normalization
    if "Wire Size" in attr_name:
        rules.append((category, attr_name, "Normalization", "Express range as \"14-8 AWG\" or \"2.5-10 mm²\""))

    # Dimensions normalization
    if "Dimensions" in attr_name:
        rules.append((category, attr_name, "Normalization", "Use format \"H x W x D mm\" with spaces around x"))

    # Weight normalization
    if "Weight" in attr_name:
        rules.append((category, attr_name, "Normalization", "Express in kg for values >= 1kg, otherwise in grams"))

    # Series normalization - based on top values
    if "Series" in attr_name and top_values:
        series_values = [v.get("value", "") for v in top_values if v.get("value")]
        # Look for known series patterns
        known_series = ["TeSys D", "TeSys Deca", "AF Series", "XT Series", "A-Line"]
        for series in known_series:
            if any(series.lower() in str(v).lower() for v in series_values):
                base = series.split()[0] if " " in series else series
                rules.append((category, attr_name, "Normalization", f"\"{base}D\", \"{base} D\", \"{base.lower()}-d\" normalize to \"{series}\""))
                break

    # Vendor name normalization
    if "VendorName" in attr_name:
        rules.append((category, attr_name, "Normalization", "\"ABB Ltd\", \"ABB Inc\", \"ABB\" normalize to \"ABB\""))
        rules.append((category, attr_name, "Normalization", "\"Schneider Electric\", \"Schneider\" normalize to \"Schneider Electric\""))

    return rules

def derive_default_rules(attr_name: str, attr_stats: dict, category: str) -> list:
    """Derive default value rules for missing data."""
    rules = []
    missing_pct = attr_stats.get("missing_percentage", 0)

    # Skip if mostly empty or system fields
    if missing_pct > 80 or attr_name.startswith("_"):
        return rules

    # Frequency default
    if "Frequency" in attr_name:
        rules.append((category, attr_name, "Default", "If AC voltage specified without frequency, default to \"50/60 Hz\""))

    # Ambient temperature default
    if "Ambient Temperature" in attr_name:
        rules.append((category, attr_name, "Default", "If not specified, default to \"40°C max\""))

    # IP Rating default
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append((category, attr_name, "Default", "If terminal cover present and no rating, default to \"IP20\""))

    # Control voltage frequency
    if "Control Voltage" in attr_name:
        rules.append((category, attr_name, "Default", "If AC and frequency missing, default to \"50/60 Hz\""))

    return rules

def generate_rules(profiling_data: dict, config: dict) -> list:
    """Generate all rules from profiling data."""
    all_rules = []

    # Determine base category
    base_category = get_category_from_attribute("", profiling_data)

    # Process each attribute
    for attr_name, attr_stats in profiling_data.items():
        if not isinstance(attr_stats, dict):
            continue

        category = base_category

        # Derive rules
        all_rules.extend(derive_completeness_rules(attr_name, attr_stats, config, category))
        all_rules.extend(derive_validation_rules(attr_name, attr_stats, config, category))
        all_rules.extend(derive_normalization_rules(attr_name, attr_stats, category))
        all_rules.extend(derive_default_rules(attr_name, attr_stats, category))

    return all_rules

def export_to_excel(rules: list, output_path: Path):
    """Export rules to Excel with formatting."""
    # Create DataFrame
    df = pd.DataFrame(rules, columns=["Category", "Attribute", "Rule type", "Rule"])

    # Sort by Category, Attribute, Rule type
    df = df.sort_values(["Category", "Attribute", "Rule type"]).reset_index(drop=True)

    # Remove duplicate rules
    df = df.drop_duplicates()

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Data Quality Rules"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Rule type colors
    rule_type_colors = {
        "Validation": PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid"),
        "Normalization": PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"),
        "Default": PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid"),
    }

    # Write data
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical='top')

            if r_idx == 1:
                cell.font = header_font
                cell.fill = header_fill
            else:
                rule_type = ws.cell(row=r_idx, column=3).value
                if rule_type in rule_type_colors:
                    cell.fill = rule_type_colors[rule_type]

    # Column widths
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 35
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 85

    # Freeze header
    ws.freeze_panes = 'A2'

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    # Save
    wb.save(output_path)

    return df

def main():
    """Main execution."""
    print("Loading profiling data...")
    profiling_data = load_profiling_data()
    print(f"Loaded {len(profiling_data)} attributes")

    print("Loading shape constraints...")
    config = load_shape_constraints()

    print("Generating data-driven rules...")
    rules = generate_rules(profiling_data, config)
    print(f"Generated {len(rules)} rules")

    print(f"Exporting to Excel: {OUTPUT_FILE}")
    df = export_to_excel(rules, OUTPUT_FILE)

    # Summary
    print("\n" + "="*60)
    print("DATA-DRIVEN RULES GENERATION COMPLETE")
    print("="*60)
    print(f"\nTotal Rules: {len(df)}")
    print(f"\nRules by Category:")
    print(df['Category'].value_counts().to_string())
    print(f"\nRules by Rule Type:")
    print(df['Rule type'].value_counts().to_string())
    print(f"\nTop 10 Attributes by Rule Count:")
    print(df['Attribute'].value_counts().head(10).to_string())
    print(f"\nOutput saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
