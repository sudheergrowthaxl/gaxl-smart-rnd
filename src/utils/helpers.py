"""Helper utilities for the Data Quality Rules pipeline."""

import logging
import logging.config
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.utils.exceptions import ConfigurationError


def load_env(env_path: str | Path | None = None) -> None:
    """
    Load environment variables from .env file.

    Args:
        env_path: Optional path to .env file. If not provided,
                 searches in current directory and parent directories.
    """
    if env_path:
        load_dotenv(env_path)
    else:
        # Try to find .env in current or parent directories
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels
            env_file = current / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                return
            current = current.parent

        # Fallback: let dotenv search automatically
        load_dotenv()


def load_config(config_path: str | Path = "config/config.yaml") -> dict[str, Any]:
    """
    Load configuration from YAML file.

    Automatically loads .env file before processing config.

    Args:
        config_path: Path to the configuration YAML file.

    Returns:
        Dictionary containing configuration values.

    Raises:
        ConfigurationError: If configuration file cannot be loaded.
    """
    # Load .env file first
    load_env()

    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_path}",
            details={"path": str(config_path)},
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Expand environment variables
        config = _expand_env_vars(config)

        return config
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Failed to parse configuration file: {e}",
            details={"path": str(config_path), "error": str(e)},
        )


def _expand_env_vars(config: Any) -> Any:
    """Recursively expand environment variables in configuration."""
    if isinstance(config, dict):
        return {key: _expand_env_vars(value) for key, value in config.items()}
    elif isinstance(config, list):
        return [_expand_env_vars(item) for item in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        env_var = config[2:-1]
        return os.environ.get(env_var, config)
    return config


def setup_logging(
    config_path: str | Path = "config/logging_config.yaml",
    default_level: int = logging.INFO,
) -> None:
    """
    Set up logging configuration.

    Args:
        config_path: Path to the logging configuration YAML file.
        default_level: Default logging level if config file not found.
    """
    config_path = Path(config_path)

    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                log_config = yaml.safe_load(f)

            # Ensure log directory exists for file handler
            if "handlers" in log_config:
                for handler in log_config["handlers"].values():
                    if "filename" in handler:
                        log_file = Path(handler["filename"])
                        log_file.parent.mkdir(parents=True, exist_ok=True)

            logging.config.dictConfig(log_config)
        except Exception as e:
            logging.basicConfig(level=default_level)
            logging.warning(f"Failed to load logging config: {e}. Using default.")
    else:
        logging.basicConfig(
            level=default_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    Args:
        name: Name for the logger.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
