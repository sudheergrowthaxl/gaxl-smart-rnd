"""Configuration module."""
from .settings import Settings, get_settings
from .attribute_config import PRIORITY_ATTRIBUTES, DATATYPE_RULE_MAPPING

__all__ = ["Settings", "get_settings", "PRIORITY_ATTRIBUTES", "DATATYPE_RULE_MAPPING"]
