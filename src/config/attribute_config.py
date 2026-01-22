"""Configuration for dynamic attribute selection and rule type mappings."""

from typing import List, Dict, Any, Optional
import re


# Default number of attributes to select if no taxonomy filter matches
# This is a fallback - primary filtering uses taxonomy schema
DEFAULT_ATTRIBUTE_COUNT: int = 16

# Default schema folder path for taxonomy model
DEFAULT_SCHEMA_PATH: str = "data/schema"

# Maximum missing percentage threshold - attributes with missing > this are skipped
MAX_MISSING_THRESHOLD: float = 70.0

# Minimum cardinality thresholds by datatype - attributes below these are ignored
# Only derive rules if cardinality exceeds these thresholds
# Note: Lower thresholds allow more attributes to be processed
CARDINALITY_THRESHOLDS: Dict[str, float] = {
    "Numeric": 0.1,       # >0.1% cardinality required for numeric fields (was 2%)
    "Categorical": 0.1,   # >0.1% cardinality required for categorical fields (was 10%)
    "Text": 0.1,          # >0.1% cardinality required for text/string fields (was 20%)
    "ID": 0.0,            # ID fields always processed (high cardinality expected)
    "Constant": 0.0,      # Constant fields always processed
    "Empty": 100.0,       # Empty fields never processed
}

# Possible attribute names that might contain Parent Class/Category information
# These are checked in order of priority
PARENT_CLASS_INDICATOR_ATTRIBUTES: List[str] = [
    "RS Product Category",
    "Product Category",
    "Category",
    "ProductCategory",
    "product_category",
    "category",
    "Class",
    "ProductClass",
    "product_class",
    "class",
    "Type",
    "ProductType",
    "product_type",
]


def extract_parent_class(category_value: str) -> str:
    """
    Extract the parent class/category from a hierarchical category value.

    Handles formats like:
    - "RS Web Taxonomy>>Industrial Controls>>Contactors & Accessories>>Contactors"
    - "Category > SubCategory > SubSubCategory"
    - "Category/SubCategory/SubSubCategory"
    - "Category|SubCategory"

    Args:
        category_value: The full category path string

    Returns:
        The extracted parent class (leaf node of the hierarchy)
    """
    if not category_value or not isinstance(category_value, str):
        return "Unknown"

    # Try different delimiters in order of likelihood
    delimiters = [">>", " > ", ">", "/", "|", "\\", " - "]

    for delimiter in delimiters:
        if delimiter in category_value:
            parts = [p.strip() for p in category_value.split(delimiter) if p.strip()]
            if parts:
                # Return the last (most specific) part as the parent class
                return parts[-1]

    # If no delimiter found, return the value itself (cleaned)
    return category_value.strip()


def derive_dataset_name_from_path(file_path: str) -> str:
    """
    Derive a dataset name from the file path.

    Args:
        file_path: Path to the data file

    Returns:
        Derived dataset name
    """
    if not file_path:
        return "Dataset"

    from pathlib import Path
    path = Path(file_path)

    # Get filename without extension
    name = path.stem

    # Clean up common patterns
    # Remove UUIDs
    name = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '', name, flags=re.IGNORECASE)
    # Remove _out, _data, _export suffixes
    name = re.sub(r'_(out|data|export|raw|clean)\s*\d*', '', name, flags=re.IGNORECASE)
    # Remove extra underscores and spaces
    name = re.sub(r'[_\s]+', '_', name).strip('_')

    if not name:
        return "Product_Data"

    return name


def find_parent_class_attribute(profiling_stats: Dict[str, Any]) -> Optional[str]:
    """
    Find the attribute that contains parent class/category information.

    Args:
        profiling_stats: Dictionary of attribute name -> profiling statistics

    Returns:
        Name of the attribute containing parent class, or None if not found
    """
    # Check known indicator attributes first
    for indicator in PARENT_CLASS_INDICATOR_ATTRIBUTES:
        if indicator in profiling_stats:
            stats = profiling_stats[indicator]
            # Check if it's not empty and has values
            if isinstance(stats, dict):
                if stats.get('datatype') != 'Empty' and stats.get('missing_percentage', 100) < 100:
                    return indicator
            else:
                # ProfilingResult object
                if hasattr(stats, 'datatype') and stats.datatype != 'Empty':
                    if hasattr(stats, 'missing_percentage') and stats.missing_percentage < 100:
                        return indicator

    # Fallback: look for any attribute with "category" or "class" in the name
    for attr_name in profiling_stats.keys():
        lower_name = attr_name.lower()
        if 'category' in lower_name or 'class' in lower_name or 'type' in lower_name:
            stats = profiling_stats[attr_name]
            if isinstance(stats, dict):
                if stats.get('datatype') != 'Empty' and stats.get('missing_percentage', 100) < 100:
                    return attr_name
            else:
                if hasattr(stats, 'datatype') and stats.datatype != 'Empty':
                    return attr_name

    return None


def get_parent_class_from_profiling(profiling_stats: Dict[str, Any]) -> str:
    """
    Get the parent class/category from profiling statistics.

    Args:
        profiling_stats: Dictionary of attribute name -> profiling statistics

    Returns:
        Parent class string
    """
    parent_attr = find_parent_class_attribute(profiling_stats)

    if not parent_attr:
        return "Unknown"

    stats = profiling_stats[parent_attr]

    # Get top value from the statistics
    top_values = None
    if isinstance(stats, dict):
        top_values = stats.get('top_values', [])
    elif hasattr(stats, 'top_values'):
        top_values = stats.top_values

    if top_values and len(top_values) > 0:
        # Get the most frequent value
        top_value = top_values[0]
        if isinstance(top_value, dict):
            category_value = str(top_value.get('value', ''))
        else:
            category_value = str(top_value)

        return extract_parent_class(category_value)

    return "Unknown"


# Mapping from detected datatype to recommended rule types
# Note: Completeness rules (NOT_NULL) are now handled dynamically in DataProfilerAgent
# based on actual missing percentage - see recommend_rule_types() method
DATATYPE_RULE_MAPPING: Dict[str, List[str]] = {
    "ID": ["PRIMARY_KEY", "FORMAT_PATTERN"],  # NOT_NULL added dynamically based on missing %
    "Numeric": ["RANGE", "DATA_TYPE", "STATISTICAL_BOUNDS", "PRECISION"],
    "Categorical": ["VALUE_SET", "CASE_CONSISTENCY", "FORMAT_CONSISTENCY"],
    "Text": ["FORMAT_PATTERN", "LENGTH"],  # NOT_EMPTY added dynamically based on missing %
    "Constant": ["VALUE_SET"],
    "Empty": [],  # Skip empty columns
}

# DATA-DRIVEN SEVERITY MAPPING
# Severity is now determined by actual missing percentage in the data
# This mapping is used for reference and documentation
MISSING_SEVERITY_THRESHOLDS: Dict[str, tuple] = {
    "Critical": (0, 5),      # 0-5% missing -> Required field, Critical if violated
    "High": (5, 20),         # 5-20% missing -> Well-populated field
    "Medium": (20, 50),      # 20-50% missing -> Moderately populated field
    "Low": (50, 95),         # 50-95% missing -> Partially populated field
    "Sparse": (95, 100),     # 95-100% missing -> Sparse/Optional field, NO completeness rules
}


def get_data_driven_severity(missing_percentage: float) -> str:
    """
    Get severity level based on actual missing percentage.

    DATA-DRIVEN APPROACH:
    - Sparse fields (>95% missing) should have "Low" severity or no completeness rules
    - The severity reflects the actual data state, not ideal expectations

    Args:
        missing_percentage: The percentage of missing values

    Returns:
        Appropriate severity level string
    """
    if missing_percentage >= 95:
        return "Low"  # Sparse field - no completeness rule should be generated
    elif missing_percentage >= 50:
        return "Low"  # Partially populated - optional field
    elif missing_percentage >= 20:
        return "Medium"  # Moderately populated
    elif missing_percentage >= 5:
        return "High"  # Well populated
    else:
        return "Critical"  # Required field (<5% missing)


def get_data_driven_threshold(missing_percentage: float) -> float:
    """
    Calculate the threshold percentage based on actual missing percentage.

    The threshold represents the acceptable failure rate. For data-driven rules,
    this should be slightly above the current missing rate to allow for minor variance.

    Args:
        missing_percentage: The percentage of missing values

    Returns:
        Appropriate threshold percentage
    """
    if missing_percentage >= 95:
        # Sparse field - threshold equals missing percentage
        return missing_percentage
    elif missing_percentage >= 50:
        # Partially populated - add small buffer
        return min(missing_percentage + 2, 100)
    elif missing_percentage >= 20:
        # Moderately populated - add buffer
        return min(missing_percentage + 5, 100)
    elif missing_percentage >= 5:
        # Well populated - add small buffer
        return min(missing_percentage + 2, 20)
    else:
        # Required field - low threshold
        return max(missing_percentage + 1, 2)


def is_sparse_field(missing_percentage: float) -> bool:
    """
    Check if a field is considered sparse (mostly empty).

    Sparse fields should NOT have completeness rules generated.

    Args:
        missing_percentage: The percentage of missing values

    Returns:
        True if the field is sparse (>95% missing)
    """
    return missing_percentage >= 95


def should_skip_for_missing(missing_percentage: float) -> bool:
    """
    Check if an attribute should be skipped due to high missing percentage.

    Args:
        missing_percentage: The percentage of missing values

    Returns:
        True if missing > MAX_MISSING_THRESHOLD (70%)
    """
    return missing_percentage > MAX_MISSING_THRESHOLD


def meets_cardinality_threshold(datatype: str, cardinality_pct: float) -> bool:
    """
    Check if an attribute meets the cardinality threshold for rule derivation.

    Different datatypes have different cardinality requirements:
    - Numeric: >0.1% cardinality
    - Categorical: >0.1% cardinality
    - Text: >0.1% cardinality

    Args:
        datatype: The detected datatype of the attribute
        cardinality_pct: The cardinality percentage (0-100)

    Returns:
        True if cardinality meets or exceeds the threshold for this datatype
    """
    threshold = CARDINALITY_THRESHOLDS.get(datatype, 0.0)
    return cardinality_pct >= threshold