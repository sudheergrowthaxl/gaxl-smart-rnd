"""
Data-Driven Rules Generator with Source References and Pythonic Expressions
Generates data quality rules from profiling statistics enhanced with domain knowledge.
Includes: Source/Reference and Pythonic validation expression for each rule.
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
OUTPUT_FILE = BASE_DIR / "data" / "output" / "Data_Quality_Rules_with_Sources.xlsx"

# Domain knowledge with standards
DOMAIN_KNOWLEDGE = {
    "voltage": {
        "standard_values": [24, 48, 110, 120, 220, 230, 240, 380, 400, 415, 440, 480, 500, 690],
        "range": (12, 1000),
        "unit": "V",
        "standard": "IEC 60038",
        "source": "IEC 60038 Standard Voltages"
    },
    "control_voltage": {
        "standard_values": [24, 48, 110, 120, 220, 230, 240],
        "range": (12, 400),
        "unit": "V",
        "standard": "IEC 60947-4",
        "source": "IEC 60947-4 Control Circuit Voltages"
    },
    "current": {
        "standard_values": [6, 9, 12, 16, 25, 32, 40, 50, 65, 80, 95, 115, 145, 170, 205, 250, 300, 400, 500, 630, 800, 1000, 1250, 1600, 2050],
        "range": (0.1, 5000),
        "unit": "A",
        "standard": "IEC 60947-4-1",
        "source": "IEC 60947-4-1 Contactor Ratings"
    },
    "frequency": {
        "standard_values": [50, 60],
        "range": (45, 65),
        "unit": "Hz",
        "standard": "IEC 60038",
        "source": "IEC 60038 Power Frequencies"
    },
    "ip_rating": {
        "standard_values": ["IP00", "IP20", "IP40", "IP54", "IP55", "IP65", "IP66", "IP67"],
        "pattern": r"IP[0-6][0-9X]",
        "standard": "IEC 60529",
        "source": "IEC 60529 Ingress Protection"
    },
    "temperature": {
        "range": (-40, 85),
        "operating_range": (-25, 70),
        "unit": "C",
        "standard": "IEC 60947-1",
        "source": "IEC 60947-1 Operating Conditions"
    },
    "utilization_category": {
        "standard_values": ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5a", "AC-5b", "AC-6a", "AC-6b", "AC-7a", "AC-7b", "AC-8a", "AC-8b", "DC-1", "DC-3", "DC-5"],
        "standard": "IEC 60947-4-1",
        "source": "IEC 60947-4-1 Utilization Categories"
    },
    "poles": {
        "standard_values": [1, 2, 3, 4],
        "range": (1, 4),
        "source": "Industry Standard - Contactor Poles"
    },
    "horsepower": {
        "range": (0.25, 1000),
        "unit": "HP",
        "source": "NEMA MG-1 Motor Ratings"
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

def load_profiling_data():
    """Load profiling statistics from JSON file."""
    with open(PROFILING_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_shape_constraints():
    """Load shape constraints configuration."""
    with open(SHAPE_CONFIG, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_category_from_profiling(profiling_data: dict) -> str:
    """Determine category from profiling data."""
    rs_category = profiling_data.get("RS Product Category", {})
    top_values = rs_category.get("top_values", [])
    if top_values:
        category_str = top_values[0].get("value", "")
        if "Contactors" in category_str:
            return "Contactors"
    return "Contactors"

def derive_completeness_rules(attr_name: str, attr_stats: dict, config: dict, category: str) -> list:
    """Derive completeness rules with source and pythonic expression."""
    rules = []
    missing_pct = attr_stats.get("missing_percentage", 0)
    populated_pct = 100 - missing_pct
    thresholds = config.get("shape_constraints", {}).get("completeness", {})

    mandatory_threshold = thresholds.get("mandatory_threshold", 5.0)
    expected_threshold = thresholds.get("expected_threshold", 20.0)

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name", "MaterialNumber"]:
        return rules

    if missing_pct == 100.0:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": f"Dead field - 100% missing, consider removing from schema",
            "Source": f"Profiling Stats: missing_percentage=100%",
            "Pythonic Expression": f"# Field '{attr_name}' is always empty - flag for removal\ndf['{attr_name}'].isna().all()"
        })
    elif missing_pct < mandatory_threshold:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": f"Mandatory field - must not be empty ({populated_pct:.1f}% populated)",
            "Source": f"Profiling Stats: missing_percentage={missing_pct:.2f}% (< {mandatory_threshold}% threshold)",
            "Pythonic Expression": f"df['{attr_name}'].notna() & (df['{attr_name}'] != '')"
        })
    elif missing_pct < expected_threshold:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": f"Expected field - should be populated ({populated_pct:.1f}% have values)",
            "Source": f"Profiling Stats: missing_percentage={missing_pct:.2f}% ({mandatory_threshold}%-{expected_threshold}% range)",
            "Pythonic Expression": f"# Warning if empty\ndf['{attr_name}'].notna() | df['{attr_name}'].isna()  # Log warning for NaN"
        })

    return rules

def derive_validation_rules(attr_name: str, attr_stats: dict, config: dict, category: str) -> list:
    """Derive validation rules with source and pythonic expression."""
    rules = []
    datatype = attr_stats.get("datatype", "")
    range_vals = attr_stats.get("range", [None, None])
    top_values = attr_stats.get("top_values", [])
    missing_pct = attr_stats.get("missing_percentage", 0)

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name"]:
        return rules

    # Get domain knowledge if available
    domain = ATTRIBUTE_DOMAIN_MAP.get(attr_name)
    domain_info = DOMAIN_KNOWLEDGE.get(domain, {}) if domain else {}

    # Numeric range validation
    if datatype == "Numeric" and range_vals and range_vals[0] is not None:
        min_val, max_val = range_vals
        if domain_info and "range" in domain_info:
            std_min, std_max = domain_info["range"]
            unit = domain_info.get("unit", "")
            standard = domain_info.get("standard", "")
            source = domain_info.get("source", "Domain Knowledge")

            rule_text = f"Value must be between {std_min} and {std_max}"
            if unit:
                rule_text += f" {unit}"
            if standard:
                rule_text += f" per {standard}"

            rules.append({
                "Category": category,
                "Attribute": attr_name,
                "Rule type": "Validation",
                "Rule": rule_text,
                "Source": source,
                "Pythonic Expression": f"(df['{attr_name}'] >= {std_min}) & (df['{attr_name}'] <= {std_max})"
            })
        elif min_val != max_val:
            rules.append({
                "Category": category,
                "Attribute": attr_name,
                "Rule type": "Validation",
                "Rule": f"Data shows range {min_val} to {max_val}",
                "Source": f"Profiling Stats: range=[{min_val}, {max_val}]",
                "Pythonic Expression": f"(df['{attr_name}'] >= {min_val}) & (df['{attr_name}'] <= {max_val})"
            })

    # Categorical enumeration validation
    if datatype == "Categorical" and top_values:
        values = [v.get("value") for v in top_values if v.get("value")]
        if len(values) >= 2 and len(values) <= 10:
            if domain_info and "standard_values" in domain_info:
                std_vals = domain_info["standard_values"]
                source = domain_info.get("source", "Domain Knowledge")
                std_vals_str = ", ".join(str(v) for v in std_vals[:8])
                if len(std_vals) > 8:
                    std_vals_str += f" (+{len(std_vals)-8} more)"
                rules.append({
                    "Category": category,
                    "Attribute": attr_name,
                    "Rule type": "Validation",
                    "Rule": f"Must be one of standard values: {std_vals_str}",
                    "Source": source,
                    "Pythonic Expression": f"df['{attr_name}'].isin({std_vals})"
                })
            else:
                vals_str = ", ".join(f'"{v}"' for v in values[:5])
                counts_info = ", ".join(f"{v.get('value')}({v.get('count')})" for v in top_values[:3])
                rules.append({
                    "Category": category,
                    "Attribute": attr_name,
                    "Rule type": "Validation",
                    "Rule": f"Expected values: {vals_str}",
                    "Source": f"Profiling Stats: top_values=[{counts_info}]",
                    "Pythonic Expression": f"df['{attr_name}'].isin({values})"
                })

    # IP Rating pattern validation
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must match pattern IP[0-6][0-9] per IEC 60529",
            "Source": "IEC 60529 Ingress Protection Standard",
            "Pythonic Expression": f"df['{attr_name}'].str.match(r'^IP[0-6][0-9X]$', na=False)"
        })

    # UPC validation
    if "UPC" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must be valid 12-digit UPC-A or 13-digit EAN with valid check digit",
            "Source": "GS1 UPC/EAN Standard",
            "Pythonic Expression": f"df['{attr_name}'].astype(str).str.match(r'^\\d{{12,13}}$', na=False)"
        })

    # Frequency validation
    if "Frequency" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": 'Must be 50 Hz, 60 Hz, or "50/60 Hz"',
            "Source": "IEC 60038 Power Frequencies",
            "Pythonic Expression": f"df['{attr_name}'].isin([50, 60, '50/60', '50/60 Hz', '50 Hz', '60 Hz'])"
        })

    # Phase validation
    if attr_name == "zz_Phase":
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": 'Must be "1 Phase" or "3 Phase"',
            "Source": "Industry Standard - AC Power Phases",
            "Pythonic Expression": f"df['{attr_name}'].isin(['1 Phase', '3 Phase', '1', '3', 'Single', 'Three'])"
        })

    # Number of Poles validation
    if "Number of Poles" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must be integer between 1 and 4",
            "Source": "Industry Standard - Contactor Pole Configurations",
            "Pythonic Expression": f"df['{attr_name}'].isin([1, 2, 3, 4, '1', '2', '3', '4'])"
        })

    # Auxiliary Contact format validation
    if "Auxiliary Contact" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Format must match pattern: [0-9]+NO(+[0-9]+NC)?",
            "Source": "IEC 60947-5-1 Auxiliary Contact Notation",
            "Pythonic Expression": f"df['{attr_name}'].str.match(r'^\\d+NO(\\+\\d+NC)?$', na=True)"
        })

    # Contact Configuration validation
    if "Contact" in attr_name and ("Configuration" in attr_name or "Form" in attr_name):
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must specify NO (Normally Open) and/or NC (Normally Closed)",
            "Source": "IEC 60947-5-1 Contact Designation",
            "Pythonic Expression": f"df['{attr_name}'].str.contains(r'NO|NC|SPST|SPDT|DPST|DPDT', na=True, regex=True)"
        })

    # Horsepower validation
    if "Horsepower" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must be positive numeric value",
            "Source": "NEMA MG-1 Motor Ratings",
            "Pythonic Expression": f"pd.to_numeric(df['{attr_name}'], errors='coerce') > 0"
        })

    # Wire Size validation
    if "Wire Size" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "AWG values: 22-4/0 or metric mm² values",
            "Source": "NEC/IEC Wire Gauge Standards",
            "Pythonic Expression": f"df['{attr_name}'].str.match(r'^(\\d+(/\\d+)?\\s*AWG|\\d+(\\.\\d+)?\\s*mm)', na=True)"
        })

    # Temperature validation
    if "Temperature" in attr_name and ".UOM" not in attr_name and "Range" not in attr_name:
        if "Storage" in attr_name:
            rules.append({
                "Category": category,
                "Attribute": attr_name,
                "Rule type": "Validation",
                "Rule": "Must be within -40°C to +85°C",
                "Source": "IEC 60947-1 Storage Conditions",
                "Pythonic Expression": f"(df['{attr_name}'] >= -40) & (df['{attr_name}'] <= 85)"
            })
        elif "Operating" in attr_name or "Ambient" in attr_name:
            rules.append({
                "Category": category,
                "Attribute": attr_name,
                "Rule type": "Validation",
                "Rule": "Must be within -25°C to +70°C per IEC 60947-1",
                "Source": "IEC 60947-1 Operating Conditions",
                "Pythonic Expression": f"(df['{attr_name}'] >= -25) & (df['{attr_name}'] <= 70)"
            })

    # 80 Character Description length validation
    if "80 Character" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Validation",
            "Rule": "Must not exceed 80 characters",
            "Source": "Data Schema Constraint",
            "Pythonic Expression": f"df['{attr_name}'].str.len() <= 80"
        })

    return rules

def derive_normalization_rules(attr_name: str, attr_stats: dict, category: str) -> list:
    """Derive normalization rules with source and pythonic expression."""
    rules = []
    top_values = attr_stats.get("top_values", [])

    # Skip system/internal attributes
    if attr_name.startswith("_") or attr_name in ["ID", "Type", "Action", "Name", "MaterialNumber"]:
        return rules

    # Voltage normalization
    if "Voltage" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"230VAC", "230 V AC", "230V~" normalize to "230 V AC"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+)\\s*V\\s*AC', r'\\1 V AC', regex=True).str.replace(r'(\\d+)VAC', r'\\1 V AC', regex=True)"
        })

    # Current normalization
    if "Current" in attr_name and "Rating" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"6 Amps", "6A", "6 A" normalize to "6 A"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+)\\s*[Aa]mps?', r'\\1 A', regex=True).str.replace(r'(\\d+)A\\b', r'\\1 A', regex=True)"
        })

    # Frequency normalization
    if "Frequency" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"50Hz", "50 Hz", "50HZ" normalize to "50 Hz"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+)\\s*[Hh][Zz]', r'\\1 Hz', regex=True)"
        })

    # Poles normalization
    if "Number of Poles" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"3P", "3 Pole", "Three Pole" normalize to "3"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'3P': '3', '3 Pole': '3', 'Three Pole': '3', '3-Pole': '3'}})"
        })

    # Mounting type normalization
    if "Mounting" in attr_name and "Type" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"On Rail", "35mm rail", "DIN 35" normalize to "DIN Rail"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'On Rail': 'DIN Rail', '35mm rail': 'DIN Rail', 'DIN 35': 'DIN Rail', 'TS35': 'DIN Rail'}})"
        })
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"Screw mount", "Bolt mount" normalize to "Panel Mount"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'Screw mount': 'Panel Mount', 'Bolt mount': 'Panel Mount', 'Surface mount': 'Panel Mount'}})"
        })

    # Phase normalization
    if attr_name == "zz_Phase":
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"Single phase", "1P", "1-phase" normalize to "1 Phase"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'Single phase': '1 Phase', '1P': '1 Phase', '1-phase': '1 Phase', '1 Ph': '1 Phase'}})"
        })
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"Three phase", "3P", "3-phase" normalize to "3 Phase"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'Three phase': '3 Phase', '3P': '3 Phase', '3-phase': '3 Phase', '3 Ph': '3 Phase'}})"
        })

    # Auxiliary contact normalization
    if "Auxiliary Contact" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"1 NO + 1 NC", "1NO/1NC" normalize to "1NO+1NC"',
            "Source": "IEC 60947-5-1 Standard Notation",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+)\\s*NO\\s*[+/]\\s*(\\d+)\\s*NC', r'\\1NO+\\2NC', regex=True)"
        })

    # IP Rating normalization
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"IP 20", "ip20", "IP-20" normalize to "IP20"',
            "Source": "IEC 60529 Standard Format",
            "Pythonic Expression": f"df['{attr_name}'].str.upper().str.replace(r'IP\\s*-?\\s*(\\d+)', r'IP\\1', regex=True)"
        })

    # Temperature normalization
    if "Temperature" in attr_name and ".UOM" not in attr_name and "Range" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": 'Express as range: "-25°C to +55°C"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"# Format: df['{attr_name}'].apply(lambda x: f'{{x}}°C' if pd.notna(x) else x)"
        })

    # Horsepower normalization
    if "Horsepower" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": 'Express as "X HP" not "X hp" or "X horsepower"',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+\\.?\\d*)\\s*(hp|horsepower)', r'\\1 HP', regex=True, flags=re.IGNORECASE)"
        })

    # Vendor name normalization
    if "VendorName" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": '"ABB Ltd", "ABB Inc", "ABB" normalize to "ABB"',
            "Source": "Vendor Master Data Standardization",
            "Pythonic Expression": f"df['{attr_name}'].replace({{'ABB Ltd': 'ABB', 'ABB Inc': 'ABB', 'ABB Inc.': 'ABB'}})"
        })

    # Dimensions normalization
    if "Dimensions" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": 'Use format "H x W x D mm" with spaces',
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"df['{attr_name}'].str.replace(r'(\\d+)x(\\d+)x(\\d+)', r'\\1 x \\2 x \\3', regex=True)"
        })

    # Weight normalization
    if "Weight" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Normalization",
            "Rule": "Express in kg for values >= 1kg, otherwise in grams",
            "Source": "Data Standardization Pattern",
            "Pythonic Expression": f"# df['{attr_name}'].apply(lambda x: f'{{x}} kg' if x >= 1 else f'{{x*1000}} g')"
        })

    return rules

def derive_default_rules(attr_name: str, attr_stats: dict, category: str) -> list:
    """Derive default value rules with source and pythonic expression."""
    rules = []
    missing_pct = attr_stats.get("missing_percentage", 0)

    if missing_pct > 80 or attr_name.startswith("_"):
        return rules

    # Frequency default
    if "Frequency" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Default",
            "Rule": 'If AC voltage specified without frequency, default to "50/60 Hz"',
            "Source": "IEC 60038 - Dual Frequency Standard",
            "Pythonic Expression": f"df.loc[df['{attr_name}'].isna() & df['zz_Control Voltage'].notna(), '{attr_name}'] = '50/60 Hz'"
        })

    # Ambient temperature default
    if "Ambient Temperature" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Default",
            "Rule": 'If not specified, default to "40°C max"',
            "Source": "IEC 60947-1 Standard Reference Conditions",
            "Pythonic Expression": f"df['{attr_name}'].fillna('40°C max')"
        })

    # IP Rating default
    if "IP" in attr_name and "Rating" in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Default",
            "Rule": 'If terminal cover present, default to "IP20"',
            "Source": "IEC 60529 - Minimum finger protection",
            "Pythonic Expression": f"df.loc[df['{attr_name}'].isna(), '{attr_name}'] = 'IP20'"
        })

    # Control voltage frequency
    if "Control Voltage" in attr_name and ".UOM" not in attr_name:
        rules.append({
            "Category": category,
            "Attribute": attr_name,
            "Rule type": "Default",
            "Rule": 'If AC coil and frequency missing, default to "50/60 Hz"',
            "Source": "IEC 60038 - Universal Frequency Compatibility",
            "Pythonic Expression": f"# Apply 50/60 Hz default for AC control voltages"
        })

    return rules

def generate_rules(profiling_data: dict, config: dict) -> list:
    """Generate all rules from profiling data."""
    all_rules = []
    category = get_category_from_profiling(profiling_data)

    for attr_name, attr_stats in profiling_data.items():
        if not isinstance(attr_stats, dict):
            continue

        all_rules.extend(derive_completeness_rules(attr_name, attr_stats, config, category))
        all_rules.extend(derive_validation_rules(attr_name, attr_stats, config, category))
        all_rules.extend(derive_normalization_rules(attr_name, attr_stats, category))
        all_rules.extend(derive_default_rules(attr_name, attr_stats, category))

    return all_rules

def export_to_excel(rules: list, output_path: Path):
    """Export rules to Excel with formatting."""
    df = pd.DataFrame(rules)

    # Reorder columns
    column_order = ["Category", "Attribute", "Rule type", "Rule", "Source", "Pythonic Expression"]
    df = df[column_order]

    # Sort and deduplicate
    df = df.sort_values(["Category", "Attribute", "Rule type"]).drop_duplicates().reset_index(drop=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Data Quality Rules"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

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
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 32
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 55
    ws.column_dimensions['E'].width = 40
    ws.column_dimensions['F'].width = 70

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    wb.save(output_path)
    return df

def main():
    print("="*70)
    print("DATA QUALITY RULES GENERATOR WITH SOURCES & PYTHONIC EXPRESSIONS")
    print("="*70)

    print("\nLoading profiling data...")
    profiling_data = load_profiling_data()
    print(f"  Loaded {len(profiling_data)} attributes")

    print("\nLoading shape constraints...")
    config = load_shape_constraints()

    print("\nGenerating data-driven rules with sources...")
    rules = generate_rules(profiling_data, config)
    print(f"  Generated {len(rules)} rules")

    print(f"\nExporting to Excel: {OUTPUT_FILE}")
    df = export_to_excel(rules, OUTPUT_FILE)

    print("\n" + "="*70)
    print("GENERATION COMPLETE")
    print("="*70)
    print(f"\nTotal Rules: {len(df)}")
    print(f"\nRules by Rule Type:")
    print(df['Rule type'].value_counts().to_string())
    print(f"\nSource Types Referenced:")
    source_types = df['Source'].apply(lambda x: x.split(':')[0] if ':' in str(x) else x.split(' ')[0]).value_counts()
    print(source_types.head(10).to_string())
    print(f"\nOutput saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
