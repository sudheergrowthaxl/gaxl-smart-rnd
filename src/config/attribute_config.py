"""Configuration for priority attributes and rule type mappings."""

from typing import List, Dict

# Priority attributes for DQ rule derivation
# These are the key product attributes that will be processed
PRIORITY_ATTRIBUTES: List[str] = [
    "ID",
    "Name",
    "MaterialNumber",
    "RS Product Category",
    "zz_Type",
    "dr_Series",
    "zz_Number of Poles",
    "zz_Contact Current Rating",
    "zz_Contact Current Rating.UOM",
    "zz_Control Voltage",
    "zz_Control Voltage.UOM",
    "_VendorName",
    "_MfrPartNumber",
    "_ProductDescription",
    "_DateCreated",
]

# Mapping from detected datatype to recommended rule types
DATATYPE_RULE_MAPPING: Dict[str, List[str]] = {
    "ID": ["PRIMARY_KEY", "FORMAT_PATTERN", "NOT_NULL"],
    "Numeric": ["RANGE", "DATA_TYPE", "STATISTICAL_BOUNDS", "PRECISION"],
    "Categorical": ["VALUE_SET", "CASE_CONSISTENCY", "FORMAT_CONSISTENCY"],
    "Text": ["FORMAT_PATTERN", "LENGTH", "NOT_EMPTY"],
    "Constant": ["VALUE_SET"],
    "Empty": [],  # Skip empty columns
}

# Severity mapping based on missing percentage
MISSING_SEVERITY_THRESHOLDS: Dict[str, tuple] = {
    "Critical": (0, 5),      # 0-5% missing -> Critical if violated
    "High": (5, 20),         # 5-20% missing -> High severity
    "Medium": (20, 50),      # 20-50% missing -> Medium severity
    "Low": (50, 100),        # >50% missing -> Low severity
}

# Standard values for common contactor attributes
STANDARD_VALUES = {
    "zz_Number of Poles": ["1", "2", "3", "4", "5"],
    "zz_Contact Current Rating.UOM": ["A", "Amp", "mA"],
    "zz_Control Voltage.UOM": ["V", "VAC", "VDC"],
    "zz_Type": [
        "Contactor",
        "IEC Contactor",
        "General Purpose Contactors",
        "Lighting Contactor",
        "Definite Purpose Contactor",
        "Vacuum Contactor",
        "Reversing Contactor",
    ],
}

# Common vendor names
KNOWN_VENDORS = [
    "SIEMENS",
    "ABB",
    "EATON CUTLER HAMMER",
    "SCHNEIDER ELECTRIC",
    "SQUARE D",
    "ALLEN BRADLEY",
    "ROCKWELL AUTOMATION",
]
