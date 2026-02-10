import json
import logging
import os
import re
from datetime import date, datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------- CONSTANTS (fix magic number warnings) ---------------- #
MISSING_HIGH_THRESHOLD = 90
MISSING_LOW_THRESHOLD = 30
UNIQUE_RATIO_THRESHOLD = 0.1
CARDINALITY_THRESHOLD = 0.8


# -----------------------------------------------------------
# Convert non-serializable numpy/pandas objects into JSON-friendly types
# -----------------------------------------------------------
def convert_to_serializable(obj):
    if isinstance(obj, np.integer | np.int64):  # UP038
        return int(obj)
    elif isinstance(obj, np.floating | np.float64):  # UP038
        return float(obj)
    elif isinstance(obj, np.ndarray):  # safe
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp | datetime | date):  # UP038
        return obj.isoformat()
    elif pd.isna(obj):
        return None
    return str(obj)


def extract_lit_val(value):
    """
    Extract lit_val from ontology-style string.
    Example:
    lit_val: '3 poles'  →  3 poles
    """
    if not isinstance(value, str):
        return value

    match = re.search(r"lit_val:\s*'([^']*)'", value)
    if match:
        return match.group(1)

    return value  # fallback


def parse_vals_column(vals_str):
    """
    Parse vals column string to extract structured fields.

    Example input:
    '{seq=1, ref_code=null, label=industry.industrialequipment.attr_contactors_zzcontactcurrentrating,
      dtype=string, lit_val=9A, num_val=null, str_val=9A, ...}'

    Returns:
    {
        'dtype': 'string',
        'lit_val': '9A',
        'num_val': None,
        'str_val': '9A',
        'bool_val': None,
        'date_val': None,
        'unit': None,
        ...
    }
    """
    if not isinstance(vals_str, str):
        return {}

    try:
        # Remove outer quotes and braces: '{'{...}'}' or '[(...)]]'
        vals_str = vals_str.strip().strip("'\"")
        vals_str = vals_str.strip('[]{}')
        vals_str = vals_str.strip("'\"")
        vals_str = vals_str.strip('{}')

        parsed = {}

        # Try parsing as dict-like format: key=value or key: value
        # Pattern to match both formats: key=value and key: value
        patterns = [
            r'(\w+):\s*([^,\]]+?)(?=,\s*\w+:|$|\])',  # key: value format (Python repr)
            r'(\w+)=([^,}]+?)(?=,\s*\w+=|$|})',         # key=value format
        ]

        for pattern in patterns:
            matches = re.findall(pattern, vals_str)
            if matches:
                for key, value in matches:
                    value = value.strip().strip("'\"")
                    # Convert 'null' or 'None' to None
                    if value.lower() in ('null', 'none'):
                        parsed[key] = None
                    else:
                        parsed[key] = value
                break  # Use first pattern that matches

        if not parsed:
            # Log the actual string for debugging
            logger.info(f"Could not parse vals column. Sample: {vals_str[:200]}...")

        return parsed
    except Exception as e:
        logger.info(f"info parsing vals column: {e}. Sample: {str(vals_str)[:200]}")
        return {}


def get_dtype_distribution(vals_series):
    """
    Extract and count dtypes from vals column.

    Returns list of dicts: [{'dtype': 'string', 'count': 80}, ...]
    """
    dtype_counts = {}

    for vals_str in vals_series.dropna():
        parsed = parse_vals_column(vals_str)
        dtype = parsed.get('dtype')

        if dtype:
            dtype_counts[dtype] = dtype_counts.get(dtype, 0) + 1

    # Convert to list format similar to top_values
    return [
        {'dtype': dtype, 'count': count}
        for dtype, count in sorted(dtype_counts.items(), key=lambda x: x[1], reverse=True)
    ]


def validate_value_against_dtype(value, declared_dtype):
    """
    Check if a value matches its declared dtype.

    Returns: (is_valid, actual_type)
    """
    if value is None or value == '' or str(value).lower() == 'null':
        return True, 'null'

    value_str = str(value)
    declared_dtype_lower = str(declared_dtype).lower() if declared_dtype else ''

    # Check integer
    if declared_dtype_lower in ('integer', 'int', 'long'):
        try:
            # Must be valid integer (no decimals)
            if '.' in value_str:
                return False, 'float'
            int(value_str)
            return True, 'integer'
        except ValueError:
            # Determine what it actually is
            if re.match(r'^-?\d+\.\d+$', value_str):
                return False, 'float'
            elif re.match(r'^(true|false)$', value_str.lower()):
                return False, 'boolean'
            else:
                return False, 'string'

    # Check float
    elif declared_dtype_lower in ('float', 'double', 'decimal', 'numeric'):
        try:
            float(value_str)
            return True, 'float'
        except ValueError:
            if re.match(r'^(true|false)$', value_str.lower()):
                return False, 'boolean'
            else:
                return False, 'string'

    # Check boolean
    elif declared_dtype_lower in ('boolean', 'bool'):
        if value_str.lower() in ('true', 'false', '1', '0', 't', 'f', 'yes', 'no'):
            return True, 'boolean'
        else:
            return False, 'string'

    # Check date
    elif declared_dtype_lower in ('date', 'datetime', 'timestamp'):
        # Simple date format check
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
        ]
        if any(re.match(pattern, value_str) for pattern in date_patterns):
            return True, 'date'
        else:
            return False, 'string'

    # String - accepts anything
    elif declared_dtype_lower in ('string', 'str', 'text', 'varchar'):
        return True, 'string'

    # Unknown dtype - consider valid
    return True, 'unknown'


def detect_dtype_mismatches(vals_series, k=5):
    """
    Detect values that don't match their declared dtype.

    Returns mismatch info or None if no mismatches found.
    """
    mismatches = []

    for vals_str in vals_series.dropna():
        parsed = parse_vals_column(vals_str)
        declared_dtype = parsed.get('dtype')
        value = extract_value_from_vals(vals_str)

        if declared_dtype and value is not None:
            is_valid, actual_type = validate_value_against_dtype(value, declared_dtype)

            if not is_valid:
                mismatches.append({
                    'value': value,
                    'declared_dtype': declared_dtype,
                    'actual_dtype': actual_type
                })

    if not mismatches:
        return None

    # Count mismatch occurrences
    mismatch_counts = {}
    for mismatch in mismatches:
        key = (mismatch['value'], mismatch['declared_dtype'], mismatch['actual_dtype'])
        mismatch_counts[key] = mismatch_counts.get(key, 0) + 1

    # Sort by count and take top k
    top_mismatches = sorted(mismatch_counts.items(), key=lambda x: x[1], reverse=True)[:k]

    return {
        "method": "dtype_mismatch",
        "mismatch_count": len(mismatches),
        "mismatch_percentage": round(len(mismatches) / len(vals_series) * 100, 2),
        "top_mismatches": [
            {
                "value": key[0],
                "declared_dtype": key[1],
                "actual_dtype": key[2],
                "count": count,
                "issue": f"Expected {key[1]} but found {key[2]}"
            }
            for key, count in top_mismatches
        ]
    }


def extract_value_from_vals(vals_str):
    """
    Extract the appropriate value based on dtype from vals column.

    Priority: lit_val > num_val/str_val/bool_val/date_val based on dtype
    """
    parsed = parse_vals_column(vals_str)

    # Always prefer lit_val if available
    if parsed.get('lit_val'):
        return parsed['lit_val']

    # Otherwise use dtype-specific field
    dtype = parsed.get('dtype', '').lower()

    if dtype == 'integer' or dtype == 'float' or dtype == 'numeric':
        return parsed.get('num_val')
    elif dtype == 'string':
        return parsed.get('str_val')
    elif dtype == 'boolean':
        return parsed.get('bool_val')
    elif dtype == 'date':
        return parsed.get('date_val')

    # Fallback to any non-null value field
    for field in ['str_val', 'num_val', 'bool_val', 'date_val']:
        if parsed.get(field):
            return parsed[field]

    return None


def detect_semantic_type(series, name, unique_ratio):  # noqa
    # Empty
    if series.isnull().all():
        return "Empty/NA"

    # Constant
    if series.dropna().nunique() == 1:
        return "Constant"

    # Identifier
    if "id" in name.lower() or name.lower().endswith("id"):
        return "ID"

    # Numeric measure
    if pd.api.types.is_numeric_dtype(series):
        return "Numeric"

    # String-based logic
    if pd.api.types.is_object_dtype(series):
        if unique_ratio < UNIQUE_RATIO_THRESHOLD:
            return "List of Values"
        else:
            return "Text"

    return "Unknown"


def detect_data_type(series):
    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    if pd.api.types.is_integer_dtype(series):
        return "integer"

    if pd.api.types.is_float_dtype(series):
        return "float"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    return "string"


def extract_attr_key(full_key: str) -> str:
    """
    Extracts the attribute name from a dotted ontology key.
    Example:
    industry.industrialequipment.attr_contactors_zzmountingtype
    -> contactors_zzmountingtype
    """
    if ".attr_" in full_key:
        return full_key.split(".attr_", 1)[1]
    return full_key.split(".")[-1]  # safe fallback


def normalize_profiling_keys(profiling_output: dict) -> dict:
    normalized = {}

    for full_key, stats in profiling_output.items():
        short_key = extract_attr_key(full_key)

        # Store with short key (existing usage for backward compatibility)
        normalized[short_key] = stats

        # ALSO store with full attr_ukey to preserve namespace for store_iceberg
        normalized[full_key] = stats

    return normalized

def get_top_k_values(series, k=5):
    """
    Observe all unique values internally,
    but expose only top-k values with counts.
    """
    try:
        vc = series.dropna().value_counts()
        top_k = vc.head(k)

        return [
            {
                "value": extract_lit_val(val),
                "count": int(cnt)
            }
            for val, cnt in top_k.items()
        ]
    except Exception:
        return []


def get_all_distinct_values_with_counts(series):
    """
    Get ALL distinct values with their counts.

    Example:
    Input: [10a, 20, 30, 20, 30, 40]
    Output: [
        {"value": "20", "count": 2},
        {"value": "30", "count": 2},
        {"value": "10a", "count": 1},
        {"value": "40", "count": 1}
    ]
    """
    try:
        vc = series.dropna().value_counts()

        return [
            {
                "value": extract_lit_val(val),
                "count": int(cnt)
            }
            for val, cnt in vc.items()
        ]
    except Exception:
        return []

def get_numeric_range(series):
    """
    Capture min/max range for numeric columns.
    Also attempts to parse string values that look like numbers.
    Returns integers if all values are whole numbers, floats if any decimals exist.

    Examples:
    - ['1', '2', '3', '4'] → [1, 4] (integers)
    - ['1.5', '2.3', '3.7'] → [1.5, 3.7] (floats)
    - ['1', '2', '3.5'] → [1.0, 3.5] (floats, mixed)
    - ['abc', 'def'] → None (not numeric)
    """
    try:
        numeric_series = None

        # If already numeric dtype, use directly
        if pd.api.types.is_numeric_dtype(series):
            numeric_series = series
        #  NEW: If string dtype, try parsing as numeric
        elif pd.api.types.is_object_dtype(series):
            # Try to convert to numeric, coercing errors to NaN
            numeric_series = pd.to_numeric(series, errors='coerce')

            # Check if we successfully converted at least some values
            valid_count = numeric_series.notna().sum()
            total_count = series.notna().sum()

            # If less than 70% of values are numeric-like, skip
            if valid_count == 0 or (valid_count / total_count) < 0.7:
                logger.info(f"  Only {valid_count}/{total_count} values are numeric-like. Skipping range calculation.")
                return None

        if numeric_series is not None:
            min_val = numeric_series.min()
            max_val = numeric_series.max()

            if pd.isna(min_val) or pd.isna(max_val):
                return None

            #  NEW: Check if all values are integers (no decimals)
            # Remove NaN values first
            clean_series = numeric_series.dropna()

            # Check if all values are whole numbers (even if stored as float)
            all_integers = all(val == int(val) for val in clean_series)

            if all_integers:
                # Return as integers
                logger.info(f"  Range (integer): [{int(min_val)}, {int(max_val)}]")
                return [int(min_val), int(max_val)]
            else:
                # Return as floats
                logger.info(f"  Range (float): [{float(min_val)}, {float(max_val)}]")
                return [float(min_val), float(max_val)]

    except Exception as e:
        logger.info(f"   Could not calculate range: {e}")
        return None

    return None

# -----------------------------------------------------------
# Missing values → Recommendation logic
# -----------------------------------------------------------
def generate_missing_recommendations(missing_percentages):
    recommendations = {}
    for col, percent in missing_percentages.items():
        if percent >= MISSING_HIGH_THRESHOLD:
            recommendations[col] = "Drop (too much missing)"
        elif percent < MISSING_LOW_THRESHOLD:
            recommendations[col] = "Keep"
        else:
            recommendations[col] = "Consider imputation / review"
    return recommendations


def detect_numeric_outliers(series, k=5):
    clean = series.dropna()
    if clean.empty:
        return None

    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return None

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = clean[(clean < lower) | (clean > upper)]
    if outliers.empty:
        return None

    vc = outliers.value_counts().head(k)

    return {
        "datatype": "numeric",
        "method": "iqr",
        "bounds": {"lower": float(lower), "upper": float(upper)},
        "outlier_count": int(len(outliers)),
        "outlier_percentage": round(len(outliers) / len(series) * 100, 2),
        "top_outlier_values": [
            {"value": float(v), "count": int(c)}
            for v, c in vc.items()
        ]
    }

def detect_date_outliers(series, k=5):
    clean = series.dropna()
    if clean.empty:
        return None

    ordinal = clean.map(pd.Timestamp.toordinal)

    q1 = ordinal.quantile(0.25)
    q3 = ordinal.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return None

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    mask = (ordinal < lower) | (ordinal > upper)
    outliers = clean[mask]

    if outliers.empty:
        return None

    vc = outliers.value_counts().head(k)

    return {
        "datatype": "date",
        "method": "iqr",
        "outlier_count": int(len(outliers)),
        "outlier_percentage": round(len(outliers) / len(series) * 100, 2),
        "top_outlier_values": [
            {"value": v.isoformat(), "count": int(c)}
            for v, c in vc.items()
        ]
    }


def detect_string_outliers(series, k=5, rare_threshold=0.01):
    """
    Detect string outliers using multiple methods:
    1. Rare frequency (appearing <= 1% of the time)
    2. Length anomalies (significantly longer/shorter than median)
    3. Pattern anomalies (different format like '3 poles' vs '3')
    """
    clean_series = series.dropna()
    if clean_series.empty:
        return None

    outlier_values = set()
    outlier_methods = []

    # Method 1: Rare frequency
    vc = clean_series.value_counts(normalize=True)
    rare = vc[vc <= rare_threshold]
    if not rare.empty:
        outlier_values.update(rare.index)
        outlier_methods.append("rare_frequency")

    # Method 2: Length anomalies
    lengths = clean_series.astype(str).str.len()
    median_length = lengths.median()
    std_length = lengths.std()

    if std_length > 0:
        # Values with length > median + 2*std or < median - 2*std
        length_threshold = 2 * std_length
        for idx, val in clean_series.items():
            val_length = len(str(val))
            if abs(val_length - median_length) > length_threshold:
                outlier_values.add(val)

        if any(abs(len(str(v)) - median_length) > length_threshold for v in clean_series):
            outlier_methods.append("length_anomaly")

    # Method 3: Pattern anomalies (numeric vs alphanumeric)
    # Detect if majority are numeric-only but some have letters
    numeric_pattern = clean_series.astype(str).str.match(r'^\d+$')
    alphanumeric_pattern = clean_series.astype(str).str.contains(r'[a-zA-Z]')

    numeric_count = numeric_pattern.sum()
    alphanumeric_count = alphanumeric_pattern.sum()

    # If majority (>70%) are numeric but some have letters, flag those with letters
    if numeric_count > 0.7 * len(clean_series) and alphanumeric_count > 0:
        for idx, val in clean_series.items():
            if alphanumeric_pattern[idx]:
                outlier_values.add(val)
        outlier_methods.append("pattern_anomaly")

    # If no outliers found, return None
    if not outlier_values:
        return None

    # Get counts for outlier values
    counts = clean_series.value_counts().loc[list(outlier_values)].head(k)

    return {
        "datatype": "string",
        "method": ", ".join(outlier_methods),
        "outlier_count": int(len(clean_series[clean_series.isin(outlier_values)])),
        "outlier_percentage": round(len(clean_series[clean_series.isin(outlier_values)]) / len(series) * 100, 2),
        "top_outlier_values": [
            {"value": extract_lit_val(v), "count": int(c), "reason": get_outlier_reason(v, clean_series, median_length)}
            for v, c in counts.items()
        ]
    }


def get_outlier_reason(value, series, median_length):
    """
    Determine why a value is considered an outlier.
    """
    reasons = []

    # Check frequency
    freq = (series == value).sum() / len(series)
    if freq <= 0.01:
        reasons.append(f"rare ({freq*100:.2f}%)")

    # Check length
    val_length = len(str(value))
    if abs(val_length - median_length) > 2:
        reasons.append(f"unusual_length ({val_length} vs median {median_length:.0f})")

    # Check pattern
    if re.search(r'[a-zA-Z]', str(value)):
        numeric_ratio = (series.astype(str).str.match(r'^\d+$')).sum() / len(series)
        if numeric_ratio > 0.7:
            reasons.append("alphanumeric_in_numeric_context")

    return ", ".join(reasons) if reasons else "outlier"

def detect_boolean_outliers(series):
    vc = series.value_counts(dropna=True)
    if len(vc) != 2:
        return None

    minority_value = vc.idxmin()
    minority_count = vc.min()

    return {
        "datatype": "boolean",
        "method": "minority_value",
        "outlier_count": int(minority_count),
        "outlier_percentage": round(minority_count / len(series) * 100, 2),
        "top_outlier_values": [
            {"value": bool(minority_value), "count": int(minority_count)}
        ]
    }

def detect_outliers_by_datatype(series, datatype, k=5):
    if datatype in ("integer", "float"):
        return detect_numeric_outliers(series, k)

    if datatype == "date":
        return detect_date_outliers(series, k)

    if datatype == "string":
        return detect_string_outliers(series, k)

    if datatype == "boolean":
        return detect_boolean_outliers(series)

    return None

def compute_imbalance(series):
    """
    Compute imbalance on non-null values only.
    """
    non_null = series.dropna()

    if non_null.empty:
        return None

    try:
        vc_norm = non_null.value_counts(normalize=True)
        top_freq = vc_norm.iloc[0]
        top_val = vc_norm.index[0]

        return {
            "metric": "top_value",
            "percentage": f"{top_freq * 100:.2f}%",
            "top_value": extract_lit_val(top_val),
        }
    except Exception:
        return None


# Detect data type of column
# def detect_data_type(series, name):
#     result = None  # store final return value

#     if series.isnull().all():
#         result = "Empty"

#     elif series.dropna().nunique() == 1:
#         result = "Constant"

#     elif pd.api.types.is_bool_dtype(series):
#         result = "Boolean"

#     elif pd.api.types.is_numeric_dtype(series):
#         if "id" in name.lower() or name.lower().endswith("id"):
#             result = "ID (Numeric)"
#         else:
#             result = "Numeric"

#     elif pd.api.types.is_datetime64_any_dtype(series):
#         result = "Date"

#     elif pd.api.types.is_object_dtype(series):
#         nunique = series.nunique(dropna=True)
#         unique_ratio = nunique / len(series)

#         if "id" in name.lower() or name.lower().endswith("id"):
#             result = "ID"
#         else:
#             result = "Categorical" if unique_ratio < UNIQUE_RATIO_THRESHOLD else "Text"

#     else:
#         result = "Unknown"

#     return result


# -----------------------------------------------------------
# Unique values + counts (below cardinality threshold)
# -----------------------------------------------------------
def get_unique_values_with_counts(df, threshold=CARDINALITY_THRESHOLD):
    unique_values_counts = {}
    total_rows = len(df)

    for col in df.columns:
        try:
            value_counts = df[col].dropna().value_counts()
            nunique = len(value_counts)

            if nunique > 0:
                cardinality_ratio = nunique / total_rows
                if cardinality_ratio < threshold:
                    unique_values_counts[col] = [
                        {"value": val, "count": int(cnt)} for val, cnt in value_counts.items()
                    ]

        except Exception as e:
            logger.info(f"info processing unique values for '{col}': {e}")

    return unique_values_counts


# -----------------------------------------------------------
# Main profiling pipeline
# -----------------------------------------------------------
def run_python_profiling_pipeline(df: pd.DataFrame, table_name: str) -> dict:
    """
    Run profiling on DataFrame.

    Supports two formats:
    1. Wide format: Multiple columns, profile each column
    2. Long format: attribute_name, value_label, vals columns - profile per attribute
    """
    final_output = {}

    #  NEW: Detect if this is long format (attribute_name, value_label, vals)
    is_long_format = (
        'attribute_name' in df.columns and
        'value_label' in df.columns and
        'vals' in df.columns
    )

    if is_long_format:
        logger.info("Detected long format data. Profiling per attribute...")
        logger.info(" Detected long format data. Profiling per attribute...")

        # Group by attribute_name and profile each attribute's values
        for attribute_name, group_df in df.groupby('attribute_name'):
            logger.info(f"Profiling attribute: {attribute_name} ({len(group_df)} records)")
            logger.info(f"   Profiling: {attribute_name} ({len(group_df)} records)")

            #  NEW: Extract dtype distribution from vals column
            vals_series = group_df['vals']

            # info: Log first vals entry to see actual format
            first_vals = vals_series.iloc[0] if len(vals_series) > 0 else None
            logger.info(f"   Sample vals format: {str(first_vals)[:300]}...")
            logger.info(f"   Sample vals format: {str(first_vals)[:300]}...")

            dtype_distribution = get_dtype_distribution(vals_series)
            logger.info(f"   Dtype distribution: {dtype_distribution}")
            logger.info(f"   Dtype distribution: {dtype_distribution}")

            #  NEW: Detect dtype mismatches
            dtype_mismatches = detect_dtype_mismatches(vals_series)
            if dtype_mismatches:
                logger.info(f"  Dtype mismatches found: {dtype_mismatches['mismatch_count']} ({dtype_mismatches['mismatch_percentage']}%)")
                logger.info(f"  Dtype mismatches: {dtype_mismatches['mismatch_count']} values don't match their declared type")

            # Use the most common dtype as primary datatype
            primary_dtype = dtype_distribution[0]['dtype'] if dtype_distribution else None

            #  NEW: Extract actual values from vals column based on dtype
            extracted_values = []
            for vals_str in vals_series:
                value = extract_value_from_vals(vals_str)
                extracted_values.append(value)

            # TEST: Replace first '3' with '3 poles' to test outlier detection
            # if 'zznumberofpoles' in attribute_name.lower():
            #     try:
            #         first_three_idx = extracted_values.index('1')
            #         extracted_values[first_three_idx] = '3 poles'
            #         logger.info(f"  TEST: Replaced first '1' with '3 poles' at index {first_three_idx}")
            #         logger.info(f"  TEST: Replaced first '1' with '3 poles' to test outlier detection")
            #     except ValueError:
            #         pass

            #  info: logger.info all extracted values as a list
            # logger.info(f"   All extracted values for {attribute_name}: {extracted_values}")

            # Create series from extracted values for profiling
            series = pd.Series(extracted_values)
            total_rows = len(series)

            # Use primary_dtype if available, otherwise detect
            if primary_dtype:
                data_type = primary_dtype
            else:
                data_type = detect_data_type(series)

            missing_percentage = float(series.isnull().mean() * 100)

            unique_ratio = series.nunique(dropna=True) / total_rows if total_rows else 0
            cardinality_pct = round(unique_ratio * 100, 2)

            semantic_type = detect_semantic_type(series, attribute_name, unique_ratio)

            #  range (numeric only)
            col_range = get_numeric_range(series)

            #  top-5 values only
            top_values = get_top_k_values(series, k=5)

            # All distinct values with counts (only for zz_ attributes)
            if attribute_name.startswith("zz_") or ".attr_" in attribute_name:
                distinct_values = get_all_distinct_values_with_counts(series)
            else:
                distinct_values = None

            # imbalance signal
            try:
                non_null = series.dropna()
                imbalance = compute_imbalance(non_null)

                #  FIX: Use actual series dtype for outlier detection, not declared dtype
                # Detect actual data type from the series for outlier detection
                actual_series_dtype = detect_data_type(series)
                logger.info(f"   Declared dtype: {data_type}, Actual series dtype: {actual_series_dtype}")

                # Use actual dtype for outlier detection
                outliers = detect_outliers_by_datatype(series, actual_series_dtype)

                if outliers:
                    logger.info(f"  Outliers detected: {outliers['outlier_count']} ({outliers['outlier_percentage']}%)")
                    logger.info(f"  Outliers detected: {outliers['outlier_count']} values flagged as outliers")
            except Exception as e:
                logger.info(f"   info detecting outliers: {e}")
                imbalance = {
                    "metric": "top_value",
                    "percentage": "0.00%",
                    "top_value": None,
                }
                outliers = None

            sparsity = f"{missing_percentage:.2f}%"

            final_output[attribute_name] = {
                "datatype": data_type,
                "dtype_distribution": dtype_distribution,  #  NEW: Add dtype distribution
                "dtype_mismatches": dtype_mismatches,  #  NEW: Add dtype mismatch detection
                "semantic_type": semantic_type,
                "missing_percentage": round(missing_percentage, 2),
                "range": col_range,
                "top_values": top_values,
                "distinct_values": distinct_values,  # All distinct values with counts
                "cardinality": f"{cardinality_pct}%",
                "imbalance": imbalance,
                "sparsity": sparsity,
                "outliers": outliers,
                "record_count": total_rows,  # Add record count for this attribute
            }

        logger.info(f"Completed profiling for {len(final_output)} attributes.")
        logger.info(f" Completed profiling for {len(final_output)} attributes.")

        #  For long format, don't normalize keys - use full attribute names as-is
        profile_result = final_output

    else:
        # Original wide format logic
        logger.info("Processing wide format data. Profiling each column...")
        total_rows = len(df)

        for col in df.columns:
            series = df[col]

            data_type = detect_data_type(series)
            missing_percentage = float(series.isnull().mean() * 100)

            unique_ratio = series.nunique(dropna=True) / total_rows if total_rows else 0
            cardinality_pct = round(unique_ratio * 100, 2)

            semantic_type = detect_semantic_type(series, col, unique_ratio)

            #  range (numeric only)
            col_range = get_numeric_range(series)

            #  top-5 values only
            top_values = get_top_k_values(series, k=5)

            # All distinct values with counts (only for zz_ attributes)
            if col.startswith("zz_"):
                distinct_values = get_all_distinct_values_with_counts(series)
            else:
                distinct_values = None

            # imbalance signal
            try:
                non_null = series.dropna()
                imbalance = compute_imbalance(non_null)
                outliers = detect_outliers_by_datatype(series, data_type)
            except Exception:
                imbalance = {
                    "metric": "top_value",
                    "percentage": "0.00%",
                    "top_value": None,
                }
                outliers = None

            sparsity = f"{missing_percentage:.2f}%"

            final_output[col] = {
                "datatype": data_type,
                "semantic_type": semantic_type,
                "missing_percentage": round(missing_percentage, 2),
                "range": col_range,
                "top_values": top_values,
                "distinct_values": distinct_values,  # All distinct values with counts
                "cardinality": f"{cardinality_pct}%",
                "imbalance": imbalance,
                "sparsity": sparsity,
                "outliers": outliers,
            }

        logger.info("Completed profiling for all columns.")

        # 🔹 Normalize keys only for wide format
        profile_result = normalize_profiling_keys(final_output)
        logger.info("Normalized profiling output keys.")

    os.makedirs("json_files", exist_ok=True)
    json_path = os.path.join("json_files", "python_profiling.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            profile_result,
            f,
            indent=2,
            ensure_ascii=False,
            default=convert_to_serializable,
        )

    logger.info(f"python profiling output saved to: {json_path}")
    # return f"python profiling output saved to: {json_path}"



def query_all_records(table_name, lakehouse_service=None):
    """
    Query all records from Iceberg table and store in DataFrame.

    Connects to the GAXL Lakehouse and retrieves all records from the
     table in the lake_working zone.

    Args:
        table_name: Name of the table to query
        lakehouse_service: Optional LakehouseService instance. Creates new one if not provided.

    Returns:
        pandas.DataFrame: All records from the Iceberg table
    """
    try:
        from src.infrastructure.adapters.data.lakehouse_service import LakehouseService  # type: ignore[reportMissingImports]

        service = lakehouse_service or LakehouseService()
        logger.info(f"Querying all records from Iceberg table (lake_working.edb_eng.{table_name})...")

        query = f"SELECT * FROM lake_working.edb_eng.{table_name}"  # nosec: B608
        df_records = service.query_data(query)

        logger.info(
            f"Successfully retrieved {len(df_records)} records from Iceberg table : {table_name}."
        )
        logger.info(f"Columns: {list(df_records.columns)}")

        return df_records

    except Exception as e:
        error_msg = f"info querying Iceberg table: {e}"
        logger.info(error_msg)
        raise


def python_profiling(
    df: pd.DataFrame | None = None,
    registry_id: str | None = None,
    table_name: str | None = None,
):
    """
    Run Python rule-based profiling on a DataFrame.

    Args:
        df: Optional DataFrame to profile. If not provided, loads from default table.
        registry_id: Optional registry ID to retrieve DataFrame from. If provided, takes precedence over df.
        table_name: Optional table name for output file naming (defaults to 'example_table').

    Returns:
        str: Success message with path to saved profiling output
    """
    from src.infrastructure.adapters.agents.profiling_tools import get_from_registry  # type: ignore[reportMissingImports]

    if table_name is None:
        table_name = "example_table"

    # 1. Get DataFrame from registry if registry_id provided
    if registry_id:
        logger.info(f"Loading DataFrame from registry with ID: {registry_id}")
        df = get_from_registry(registry_id)
        if df is None:
            raise ValueError(f"No DataFrame found in registry with ID: {registry_id}")
        logger.info(f"Successfully loaded DataFrame from registry: {df.shape}")

        

    # 2. Fall back to provided DataFrame
    if df is None:
        # 3. Fall back to loading from default table
        logger.info("No DataFrame provided, loading from default table")
        table_name_to_query = "rs_america_limit_switches"
        df = query_all_records(table_name_to_query)

    # 4. Run profiling
    logger.info(f"Running Python profiling on DataFrame with shape: {df.shape}")
    # logger.info(f"sample data {df.head(5)}")
    profile_result = run_python_profiling_pipeline(df, table_name)
    logger.info("Python profiling completed")
    # logger.info(json.dumps(profile_result, indent=2, ensure_ascii=False, default=convert_to_serializable))

    return profile_result


import pandas as pd

def run_profiling_from_csv(csv_path: str, table_name: str = "csv_table"):
    """
    Read CSV → convert to DataFrame → run python profiling pipeline
    """
    try:
        #  Read CSV
        logger.info(f"Reading CSV file from: {csv_path}")
        df = pd.read_csv(csv_path)

        logger.info(f"CSV loaded successfully")
        logger.info(f"Shape: {df.shape}")
        logger.info(f"Columns: {list(df.columns)}")

        #  Run profiling
        logger.info("Running python profiling pipeline...")
        result = run_python_profiling_pipeline(df, table_name)

        logger.info("Profiling completed successfully")
        return result

    except Exception as e:
        logger.info(f" info during CSV profiling: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    csv_file_path = r"C:\Users\Saranya\Downloads\CONTACTORS_RAW_DATA..........csv"
    run_profiling_from_csv(csv_file_path, table_name="contactors")