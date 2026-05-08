from __future__ import annotations
import logging
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path

_log = logging.getLogger(__name__)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

AIVION_DIR = Path.home() / ".aivion-mask"
CONFIG_PATH = AIVION_DIR / "config.toml"

DEFAULT_UPSTREAMS: dict[str, str] = {
    "/v1/messages":         "https://api.anthropic.com",
    "/v1/chat/completions": "https://api.openai.com/v1",
}

_DEFAULT_TOML = """\
[sidecar]
port = 47474
session_ttl_hours = 8
unmask_response = true

# Custom regex patterns (optional):
# [[sidecar.custom_patterns]]
# name    = "MY_INTERNAL_TOKEN"
# pattern = 'int_[A-Za-z0-9]{32}'

# ── Claude ───────────────────────────────────────────────────────────────────
# No config needed. API key or OAuth token is forwarded directly from your
# tool's request headers (ANTHROPIC_BASE_URL + existing auth = done).

"""

@dataclass
class CustomPattern:
    name: str
    pattern: str
    abbrev: str = ""  # kept for config compat; no longer used (masked values are display_value format)

@dataclass
class SidecarSettings:
    port: int = 47474
    session_ttl_hours: int = 8
    unmask_response: bool = True
    custom_patterns: list[CustomPattern] = field(default_factory=list)

@dataclass
class OpenAISettings:
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""

@dataclass
class Config:
    sidecar: SidecarSettings = field(default_factory=SidecarSettings)
    openai: OpenAISettings = field(default_factory=OpenAISettings)

def _filter_known(data: dict, cls) -> dict:
    """Drop unknown keys so old config files don't break newer dataclasses."""
    known = {f.name for f in fields(cls)}
    extra = set(data) - known
    if extra:
        _log.info("Ignoring unknown config keys for %s: %s", cls.__name__, sorted(extra))
    return {k: v for k, v in data.items() if k in known}


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
    sidecar = SidecarSettings(**_filter_known(sidecar_data, SidecarSettings))
    sidecar.custom_patterns = [CustomPattern(**_filter_known(p, CustomPattern)) for p in raw_patterns]
    openai = OpenAISettings(**_filter_known(data.get("openai", {}), OpenAISettings))
    return Config(sidecar=sidecar, openai=openai)
