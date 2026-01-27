"""Wikipedia scraper for standard definitions."""

import json
import logging
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WikipediaScraper:
    """
    Scrape and cache Wikipedia definitions for electrical terms.
    """

    WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Wikipedia scraper.

        Args:
            config: Configuration dictionary with data paths.
        """
        self.config = config or {}
        data_config = self.config.get("data", {}).get("input", {})
        self.cache_dir = Path(
            data_config.get("wikipedia", "./data/input/wikipedia")
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_file = self.cache_dir / "definitions_cache.json"
        self.cache = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        """Load cached definitions from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {}

    def _save_cache(self) -> None:
        """Save cache to file."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def get_definition(self, term: str, use_cache: bool = True) -> dict[str, Any]:
        """
        Get Wikipedia definition for a term.

        Args:
            term: Term to look up.
            use_cache: Whether to use cached results.

        Returns:
            Dictionary with term definition and metadata.
        """
        cache_key = term.lower().replace(" ", "_")

        # Check cache
        if use_cache and cache_key in self.cache:
            logger.debug(f"Cache hit for term: {term}")
            return self.cache[cache_key]

        # Fetch from Wikipedia
        try:
            result = self._fetch_from_wikipedia(term)

            if result:
                self.cache[cache_key] = result
                self._save_cache()

            return result

        except Exception as e:
            logger.warning(f"Failed to fetch Wikipedia definition for '{term}': {e}")
            return {"term": term, "error": str(e)}

    def _fetch_from_wikipedia(self, term: str) -> dict[str, Any]:
        """
        Fetch definition from Wikipedia API.

        Args:
            term: Term to look up.

        Returns:
            Dictionary with term definition.
        """
        # Format term for Wikipedia URL
        formatted_term = term.replace(" ", "_")
        url = f"{self.WIKIPEDIA_API}{formatted_term}"

        response = requests.get(url, timeout=10)

        if response.status_code == 404:
            # Try with "(electrical)" suffix for disambiguation
            url = f"{self.WIKIPEDIA_API}{formatted_term}_(electrical)"
            response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return {"term": term, "found": False}

        data = response.json()

        return {
            "term": term,
            "found": True,
            "title": data.get("title", term),
            "extract": data.get("extract", ""),
            "description": data.get("description", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }

    def get_definitions_batch(
        self, terms: list[str], use_cache: bool = True
    ) -> dict[str, dict[str, Any]]:
        """
        Get definitions for multiple terms.

        Args:
            terms: List of terms to look up.
            use_cache: Whether to use cached results.

        Returns:
            Dictionary mapping terms to their definitions.
        """
        results = {}

        for term in terms:
            results[term] = self.get_definition(term, use_cache)

        return results

    def get_electrical_terms_definitions(self) -> dict[str, dict[str, Any]]:
        """
        Get definitions for common electrical terms.

        Returns:
            Dictionary of definitions for electrical terms.
        """
        common_terms = [
            "contactor",
            "relay",
            "rated current",
            "rated voltage",
            "utilization category",
            "AC-3",
            "AC-4",
            "coil voltage",
            "auxiliary contact",
            "mechanical durability",
            "electrical durability",
            "IEC 60947",
        ]

        return self.get_definitions_batch(common_terms)

    def format_for_prompt(
        self, terms: list[str] | None = None
    ) -> str:
        """
        Format Wikipedia definitions for inclusion in LLM prompt.

        Args:
            terms: Optional list of terms. If not provided, uses common terms.

        Returns:
            Formatted string representation.
        """
        if terms is None:
            definitions = self.get_electrical_terms_definitions()
        else:
            definitions = self.get_definitions_batch(terms)

        lines = ["Wikipedia Definitions:"]
        lines.append("-" * 40)

        for term, data in definitions.items():
            if data.get("found"):
                lines.append(f"\n{term.upper()}:")
                lines.append(f"  {data.get('extract', 'No definition available.')[:500]}")
            else:
                lines.append(f"\n{term.upper()}: Definition not found")

        return "\n".join(lines)

    def clear_cache(self) -> None:
        """Clear the definition cache."""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
        logger.info("Wikipedia cache cleared")

    def scrape_for_matched_attributes(
        self, matched_attributes: list[str]
    ) -> str:
        """
        Scrape Wikipedia definitions at runtime for matched attributes only.

        This method is called AFTER attribute matching to get definitions
        only for attributes that exist in both cross-tab and RAG specs.

        Args:
            matched_attributes: List of canonical attribute names that were
                              matched between cross-tab and RAG specifications.

        Returns:
            Formatted string with Wikipedia definitions for the prompt.
        """
        logger.info(
            f"Runtime Wikipedia scraping for {len(matched_attributes)} matched attributes"
        )

        # Build search terms for each attribute
        search_terms = []
        for attr in matched_attributes:
            # Add the attribute itself
            human_readable = attr.replace("_", " ")
            search_terms.append(human_readable)

            # Add related electrical terms
            related_terms = self._get_related_terms(attr)
            search_terms.extend(related_terms)

        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in search_terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_terms.append(term)

        logger.info(f"Fetching definitions for {len(unique_terms)} unique terms")

        # Fetch definitions (will use cache for previously fetched terms)
        definitions = self.get_definitions_batch(unique_terms, use_cache=True)

        # Count new fetches vs cache hits
        new_fetches = sum(
            1 for term in unique_terms
            if term.lower().replace(" ", "_") not in self.cache
        )
        logger.info(f"Fetched {new_fetches} new definitions, {len(unique_terms) - new_fetches} from cache")

        # Format for prompt
        lines = ["Wikipedia Definitions (scraped at runtime for matched attributes):"]
        lines.append("-" * 60)

        for term, data in definitions.items():
            if data.get("found"):
                lines.append(f"\n{term.upper()}:")
                extract = data.get("extract", "No definition available.")
                lines.append(f"  {extract[:500]}")
                if data.get("url"):
                    lines.append(f"  Source: {data.get('url')}")
            else:
                lines.append(f"\n{term.upper()}: Definition not found on Wikipedia")

        return "\n".join(lines)

    def _get_related_terms(self, attribute: str) -> list[str]:
        """
        Get related Wikipedia search terms for an attribute.

        Args:
            attribute: Canonical attribute name.

        Returns:
            List of related terms to search.
        """
        # Mapping of attributes to related Wikipedia terms
        related_terms_map = {
            "rated_current": ["electric current", "IEC 60947"],
            "rated_voltage": ["voltage", "rated voltage"],
            "coil_voltage": ["electromagnet", "relay coil"],
            "utilization_category": ["contactor", "IEC 60947"],
            "mechanical_durability": ["mechanical endurance"],
            "electrical_durability": ["electrical endurance", "arc erosion"],
            "auxiliary_contact": ["auxiliary contact", "control circuit"],
            "power_rating": ["electric power", "watt"],
            "frequency": ["utility frequency", "alternating current"],
            "ip_rating": ["IP code", "ingress protection"],
        }

        return related_terms_map.get(attribute.lower(), [])

    def extract_standard_values(
        self,
        attribute: str,
        search_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Extract industry standard values from Wikipedia for an attribute.

        This method fetches Wikipedia definitions and extracts standard values,
        ranges, and units for use in VALIDITY rules.

        Args:
            attribute: Canonical attribute name.
            search_terms: Optional list of specific terms to search.

        Returns:
            Dictionary containing:
                - definition: Text definition from Wikipedia
                - standard_values: List of standard values (for enumerations)
                - standard_range: Dict with min/max (for ranges)
                - unit: Unit of measurement
                - reference_standard: IEC or other standard reference
                - source_url: Wikipedia URL
        """
        result = {
            "attribute": attribute,
            "definition": "",
            "standard_values": None,
            "standard_range": None,
            "unit": "",
            "reference_standard": "",
            "source_url": "",
        }

        # Use provided terms or get related terms
        if search_terms:
            terms = search_terms
        else:
            terms = [attribute.replace("_", " ")] + self._get_related_terms(attribute)

        # Fetch definitions from Wikipedia
        definitions = self.get_definitions_batch(terms, use_cache=True)

        # Process the definitions to extract standard values
        for term, data in definitions.items():
            if not data.get("found"):
                continue

            extract = data.get("extract", "")
            result["definition"] = extract
            result["source_url"] = data.get("url", "")

            # Extract values based on attribute type
            attr_lower = attribute.lower()

            # Voltage extraction
            if "voltage" in attr_lower:
                values = self._extract_voltage_values(extract)
                if values:
                    result["standard_values"] = values
                    result["unit"] = "V"
                    result["reference_standard"] = "IEC 60038"
                    break

            # Current extraction
            elif "current" in attr_lower:
                range_val = self._extract_current_range(extract)
                if range_val:
                    result["standard_range"] = range_val
                    result["unit"] = "A"
                    result["reference_standard"] = "IEC 60947-4-1"
                    break

            # Frequency extraction
            elif "frequency" in attr_lower:
                values = self._extract_frequency_values(extract)
                if values:
                    result["standard_values"] = values
                    result["unit"] = "Hz"
                    result["reference_standard"] = "IEC 60038"
                    break

            # IP rating extraction
            elif "ip" in attr_lower and ("rating" in attr_lower or "code" in attr_lower):
                values = self._extract_ip_ratings(extract)
                if values:
                    result["standard_values"] = values
                    result["reference_standard"] = "IEC 60529"
                    break

            # Temperature extraction
            elif "temperature" in attr_lower:
                range_val = self._extract_temperature_range(extract)
                if range_val:
                    result["standard_range"] = range_val
                    result["unit"] = "C"
                    result["reference_standard"] = "IEC 60947-1"
                    break

            # Utilization category
            elif "utilization" in attr_lower or "category" in attr_lower:
                values = self._extract_utilization_categories(extract)
                if values:
                    result["standard_values"] = values
                    result["reference_standard"] = "IEC 60947-4-1"
                    break

        return result

    def _extract_voltage_values(self, text: str) -> list[int] | None:
        """Extract standard voltage values from text."""
        import re

        # Common standard voltages (IEC 60038)
        standard_voltages = [24, 48, 110, 120, 220, 230, 240, 380, 400, 415, 440, 480, 500, 690]

        # Try to find voltage values in text
        pattern = r'\b(\d{2,4})\s*[Vv](?:olts?)?\b'
        matches = re.findall(pattern, text)

        if matches:
            found_voltages = []
            for match in matches:
                voltage = int(match)
                if voltage in standard_voltages:
                    found_voltages.append(voltage)

            if found_voltages:
                return sorted(list(set(found_voltages)))

        # Return common standard voltages if none found in text
        return standard_voltages

    def _extract_current_range(self, text: str) -> dict[str, float] | None:
        """Extract current range from text."""
        import re

        # Try to find current range patterns
        patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:to|[-–])\s*(\d+(?:\.\d+)?)\s*[Aa](?:mperes?)?',
            r'from\s+(\d+(?:\.\d+)?)\s*[Aa]?\s+to\s+(\d+(?:\.\d+)?)\s*[Aa]',
            r'range[:\s]+(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*[Aa]',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    min_val = float(match.group(1))
                    max_val = float(match.group(2))
                    return {"min": min_val, "max": max_val}
                except (ValueError, IndexError):
                    continue

        # Default range for contactors/relays
        return {"min": 0.1, "max": 5000}

    def _extract_frequency_values(self, text: str) -> list[int] | None:
        """Extract frequency values from text."""
        import re

        # Standard power frequencies
        standard_frequencies = [50, 60]

        # Try to find frequency values
        pattern = r'\b(\d{2})\s*[Hh][Zz]\b'
        matches = re.findall(pattern, text)

        if matches:
            found_freqs = []
            for match in matches:
                freq = int(match)
                if freq in standard_frequencies:
                    found_freqs.append(freq)

            if found_freqs:
                return sorted(list(set(found_freqs)))

        # Return standard frequencies
        return standard_frequencies

    def _extract_ip_ratings(self, text: str) -> list[str] | None:
        """Extract IP ratings from text."""
        import re

        # Standard IP ratings pattern
        pattern = r'\bIP\s*[0-6X][0-9X]\b'
        matches = re.findall(pattern, text, re.IGNORECASE)

        if matches:
            # Normalize and deduplicate
            ratings = sorted(list(set(m.upper().replace(" ", "") for m in matches)))
            return ratings

        # Return common IP ratings
        return ["IP00", "IP20", "IP40", "IP54", "IP55", "IP65", "IP66", "IP67"]

    def _extract_temperature_range(self, text: str) -> dict[str, float] | None:
        """Extract temperature range from text."""
        import re

        # Try to find temperature range patterns
        patterns = [
            r'(-?\d+)\s*(?:°?[Cc]|degrees?\s*[Cc]?)\s*(?:to|[-–])\s*(-?\d+)\s*(?:°?[Cc]|degrees?\s*[Cc]?)',
            r'(-?\d+)\s*to\s*(-?\d+)\s*°?[Cc]',
            r'range[:\s]+(-?\d+)\s*[-–]\s*(-?\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    min_val = float(match.group(1))
                    max_val = float(match.group(2))
                    return {"min": min_val, "max": max_val}
                except (ValueError, IndexError):
                    continue

        # Default operating temperature range
        return {"min": -25, "max": 70}

    def _extract_utilization_categories(self, text: str) -> list[str] | None:
        """Extract utilization categories from text."""
        import re

        # Standard utilization categories (IEC 60947-4-1)
        standard_categories = [
            "AC-1", "AC-2", "AC-3", "AC-4",
            "AC-5a", "AC-5b", "AC-6a", "AC-6b",
            "AC-7a", "AC-7b", "AC-8a", "AC-8b",
            "DC-1", "DC-3", "DC-5", "DC-6",
        ]

        # Try to find categories in text
        pattern = r'\b(AC|DC)-[1-8][ab]?\b'
        matches = re.findall(pattern, text, re.IGNORECASE)

        if matches:
            found_cats = []
            for base, suffix in re.findall(r'\b((?:AC|DC)-[1-8][ab]?)\b', text, re.IGNORECASE):
                cat = base.upper()
                if cat in standard_categories:
                    found_cats.append(cat)

            if found_cats:
                return sorted(list(set(found_cats)))

        # Return common AC categories
        return ["AC-1", "AC-2", "AC-3", "AC-4"]
