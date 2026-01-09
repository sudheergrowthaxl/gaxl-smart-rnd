"""Application settings and configuration."""

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    temperature: float = float(os.getenv("TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "8000"))

    # Base paths
    base_dir: Path = Path(__file__).parent.parent.parent

    # Data paths
    raw_data_path: Path = Path(os.getenv(
        "RAW_DATA_PATH",
        "data/a7e6e2fc-6699-495a-9669-ec91804103f4_out 1 (1).xlsx"
    ))
    profiling_path: Path = Path(os.getenv(
        "PROFILING_PATH",
        "data/python_profiling 3.json"
    ))
    schema_path: Path = Path(os.getenv(
        "SCHEMA_PATH",
        "data/schema"  # Folder containing Taxonomy Model Excel file
    ))
    xml_template_path: Path = Path(os.getenv(
        "XML_TEMPLATE_PATH",
        "Customer_Ontology_Prompt.xml"
    ))

    # Output paths
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    output_json_filename: Path = Path(os.getenv("DQ_RULES_JSON", "dq_rules.json"))
    output_excel_filename: Path = Path(os.getenv("DQ_RULES_EXCEL", "dq_rules.xlsx"))

    # Processing settings
    sample_size: int = 1000
    max_iterations: int = 20

    def get_absolute_path(self, relative_path: Path) -> Path:
        """Convert relative path to absolute path from base directory."""
        if relative_path.is_absolute():
            return relative_path
        return self.base_dir / relative_path

    @property
    def raw_data_abs_path(self) -> Path:
        return self.get_absolute_path(self.raw_data_path)

    @property
    def profiling_abs_path(self) -> Path:
        return self.get_absolute_path(self.profiling_path)

    @property
    def output_abs_dir(self) -> Path:
        path = self.get_absolute_path(self.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
