from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

AIVION_DIR = Path.home() / ".aivion-mask"
CONFIG_PATH = AIVION_DIR / "config.toml"

_DEFAULT_TOML = """\
[sidecar]
port = 47474
session_ttl_hours = 8
idle_shutdown_minutes = 0
unmask_response = true

# Add custom regex patterns below. Example:
# [[sidecar.custom_patterns]]
# name = "MY_INTERNAL_TOKEN"
# pattern = 'int_[A-Za-z0-9]{32}'
# abbrev = "INT"   # optional — token becomes __INT1__, __INT2__, etc.

[llm]
api_base = "https://api.openai.com/v1"
api_key = ""
"""

@dataclass
class CustomPattern:
    name: str
    pattern: str
    abbrev: str = ""  # if empty, derived from name (first 3 chars uppercase)

@dataclass
class SidecarSettings:
    port: int = 47474
    session_ttl_hours: int = 8
    idle_shutdown_minutes: int = 0
    unmask_response: bool = True
    custom_patterns: list[CustomPattern] = field(default_factory=list)

@dataclass
class LLMSettings:
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""

@dataclass
class Config:
    sidecar: SidecarSettings = field(default_factory=SidecarSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)

def load_config() -> Config:
    if not CONFIG_PATH.exists():
        AIVION_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_DEFAULT_TOML)
        CONFIG_PATH.chmod(0o600)
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    sidecar_data = dict(data.get("sidecar", {}))
    raw_patterns = sidecar_data.pop("custom_patterns", [])
    sidecar = SidecarSettings(**sidecar_data)
    sidecar.custom_patterns = [CustomPattern(**p) for p in raw_patterns]
    llm = LLMSettings(**data.get("llm", {}))
    return Config(sidecar=sidecar, llm=llm)
