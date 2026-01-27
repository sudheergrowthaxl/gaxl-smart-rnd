"""Data source loading modules."""

from src.data_sources.crosstab_loader import CrosstabLoader
from src.data_sources.profiling_loader import ProfilingLoader
from src.data_sources.wikipedia_scraper import WikipediaScraper

__all__ = [
    "CrosstabLoader",
    "ProfilingLoader",
    "WikipediaScraper",
]
