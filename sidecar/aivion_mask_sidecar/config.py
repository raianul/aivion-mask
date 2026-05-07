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

[llm]
api_base = "https://api.openai.com/v1"
api_key = ""
"""

@dataclass
class SidecarSettings:
    port: int = 47474
    session_ttl_hours: int = 8
    idle_shutdown_minutes: int = 0
    unmask_response: bool = True

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
    sidecar = SidecarSettings(**data.get("sidecar", {}))
    llm = LLMSettings(**data.get("llm", {}))
    return Config(sidecar=sidecar, llm=llm)
