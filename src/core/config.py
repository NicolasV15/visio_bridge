from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Default configuration values
DEFAULTS: dict[str, Any] = {
    "backend": "auto",
    "desktop_transport_mode": "auto",
    "vm_name": "",
    "visible": False,
    "timeout": 180,
    "stage_local": None,
}

_cached_config: dict[str, Any] | None = None

def get_config_paths() -> list[Path]:
    """Return list of candidate paths for the configuration file, in order of priority."""
    paths = []
    
    # 1. Current working directory
    cwd = Path(os.getcwd())
    paths.append(cwd / "visio_bridge.json")
    paths.append(cwd / ".visio_bridge.json")
    
    # 2. Package root directory (where pyproject.toml / parent of src/ resides)
    try:
        pkg_root = Path(__file__).resolve().parent.parent.parent
        paths.append(pkg_root / "visio_bridge.json")
        paths.append(pkg_root / ".visio_bridge.json")
    except Exception:
        pass
        
    # 3. User home directory
    try:
        home = Path.home()
        paths.append(home / ".visio_bridge.json")
    except Exception:
        pass
        
    return paths

def load_config(force_reload: bool = False) -> dict[str, Any]:
    """Load configuration from the first existing config file found, merging with defaults.
    
    Results are cached in memory. Pass force_reload=True to force re-reading from disk.
    """
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config
        
    config = DEFAULTS.copy()
    
    for path in get_config_paths():
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Merge loaded data with defaults
                        for k, v in data.items():
                            if k in DEFAULTS:
                                config[k] = v
                        # Store the source path of configuration
                        config["_config_path"] = str(path)
                        break
            except Exception:
                # Silently fall back if the JSON is malformed or unreadable
                pass
                
    _cached_config = config
    return config
