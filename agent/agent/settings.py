import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

HOME_DIR = os.path.expanduser("~")

DEFAULT_SETTINGS = {
    "code_index": {
        "search": {"min_score": 0.4, "max_results": 50},
        "embedder": {
            "provider": "ollama",
            "model": "all-minilm",
			"query_prefix": "Represent this query for searching relevant code: ",
        },
        "vector_store": {
            "provider": "qdrant",
            "host": "https://localhost",
            "port": 6333,
        },
        "cache": {
            "path": os.path.join(HOME_DIR, ".index_cache.json"),
        },
    },
    "persistence": {
        "driver": "sqlite",
        "url": "./agent.db"
    },
    "api": {
        "provider": "ollama",
        #"model_id": "qwen2.5-coder:7b",
        #"model_id": "gpt-oss:latest",
        "model_id": "qwen3:8b",
    },
    "workspace": {
        "path": os.getcwd(),
    },
}


class SettingsManager:
    """
    Hierarchical configuration manager supporting nested dot-notation access.

    Supports initialization from defaults, files (JSON/YAML), and programmatic input.
    Configuration values can be accessed via dot notation (e.g., 'section.subsection.key').
    """

    _instance: "SettingsManager" = None

    @classmethod
    def get_instance(cls) -> "SettingsManager":
        if cls._instance is None:
            cls._instance = SettingsManager(DEFAULT_SETTINGS)
        return cls._instance

    def __init__(self, defaults: Optional[Dict[str, Any]] = None):
        """
        Initialize the configuration manager.

        Args:
            defaults: Default configuration dictionary
        """
        self._config: Dict[str, Any] = {}
        if defaults:
            self._config = self._deep_copy(defaults)

    def load_file(self, filepath: Union[str, Path]) -> None:
        """
        Load configuration from a JSON or YAML file.

        Args:
            filepath: Path to configuration file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is not supported
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")

        suffix = filepath.suffix.lower()

        if suffix == ".json":
            with open(filepath, "r") as f:
                file_config = json.load(f)
        elif suffix in [".yaml", ".yml"]:
            try:
                import yaml

                with open(filepath, "r") as f:
                    file_config = yaml.safe_load(f) or {}
            except ImportError:
                raise ValueError("PyYAML not installed. Install it to load YAML files.")
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

        self._merge_config(file_config)

    def load_env(self, prefix: str = "", separator: str = "__") -> None:
        """
        Load configuration from environment variables.

        Environment variables are expected to use the format: PREFIX__SECTION__KEY
        For example: APP__CODE_INDEX__EMBEDDER__MODEL=ollama

        Args:
            prefix: Optional prefix to filter environment variables
            separator: Separator used in environment variable names (default: __)
        """
        env_config: Dict[str, Any] = {}

        for key, value in os.environ.items():
            if prefix and not key.startswith(prefix):
                continue

            # Remove prefix if specified
            config_key = key[len(prefix) + len(separator) :] if prefix else key

            # Split by separator and convert to lowercase
            parts = config_key.lower().split(separator)

            # Build nested dictionary
            current = env_config
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            current[parts[-1]] = value

        self._merge_config(env_config)

    def update(self, config_dict: Dict[str, Any], overwrite: bool = False) -> None:
        """
        Update configuration with programmatic input.

        Args:
            config_dict: Configuration dictionary to merge
            overwrite: If True, overwrite existing values. If False, only add new keys.
        """
        self._merge_config(config_dict, overwrite=overwrite)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'code_index.embedder.model')
            default: Default value if key doesn't exist

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        current = self._config

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        return current

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section.

        Args:
            section: Section name (e.g., 'code_index' or 'code_index.embedder')

        Returns:
            Configuration dictionary for the section
        """
        result = self.get(section, {})
        return self._deep_copy(result) if isinstance(result, dict) else {}

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'code_index.embedder.model')
            value: Value to set
        """
        keys = key.split(".")
        current = self._config

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        """
        Get the entire configuration as a dictionary.

        Returns:
            Deep copy of the configuration dictionary
        """
        return self._deep_copy(self._config)

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-style access."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Support dictionary-style assignment."""
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        """Check if key exists in configuration."""
        return self.get(key, None) is not None

    @staticmethod
    def _deep_copy(obj: Any) -> Any:
        """Create a deep copy of an object."""
        if isinstance(obj, dict):
            return {k: SettingsManager._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [SettingsManager._deep_copy(item) for item in obj]
        else:
            return obj

    def _merge_config(self, new_config: Dict[str, Any], overwrite: bool = True) -> None:
        """
        Merge new configuration into existing configuration.

        Args:
            new_config: Configuration to merge
            overwrite: If True, overwrite existing values
        """

        def merge_recursive(base: Dict, update: Dict) -> None:
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge_recursive(base[key], value)
                elif overwrite or key not in base:
                    base[key] = self._deep_copy(value)

        merge_recursive(self._config, new_config)


# Example usage
if __name__ == "__main__":
    # Define defaults

    # Create config manager with defaults
    config = SettingsManager.get_instance()

    # Update with programmatic input
    config.update({"code_index": {"embedder": {"model": "ollama"}, "vector_store": "qdrant"}})

    # Access values using dot notation
    print(f"Embedder model: {config.get('code_index.embedder.model')}")
    print(f"Vector store: {config.get('code_index.vector_store')}")
    print(f"Persistence driver: {config.get('persistence.driver')}")
    print(f"Persistence path: {config.get('persistence.path')}")

    # Get entire section for passing to classes
    embedder_config = config.get_section("code_index.embedder")
    print(f"\nEmbedder config: {embedder_config}")

    persistence_config = config.get_section("persistence")
    print(f"Persistence config: {persistence_config}")

    # Set individual values
    config.set("logging.level", "DEBUG")
    print(f"\nLogging level: {config.get('logging.level')}")

    # Use dictionary-style access
    print(f"Using []: {config['code_index.vector_store']}")

    # Check if key exists
    if "code_index.embedder.model" in config:
        print("Embedder model exists in config")
