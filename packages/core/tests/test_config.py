import sys
from pathlib import Path
import pytest
from aivion_mask_core.config import load_config

def test_load_creates_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("aivion_mask_core.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_core.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = load_config()
    assert cfg.sidecar.port == 47474
    assert cfg.sidecar.session_ttl_hours == 8
    assert cfg.llm.api_base == "https://api.openai.com/v1"
    assert (tmp_path / "config.toml").exists()

def test_load_reads_existing_file(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[sidecar]\nport = 9999\n\n[llm]\napi_key = "test-key"\n')
    monkeypatch.setattr("aivion_mask_core.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_core.config.CONFIG_PATH", config_file)
    cfg = load_config()
    assert cfg.sidecar.port == 9999
    assert cfg.llm.api_key == "test-key"

def test_load_merges_partial_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[llm]\napi_key = "sk-abc"\n')
    monkeypatch.setattr("aivion_mask_core.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_core.config.CONFIG_PATH", config_file)
    cfg = load_config()
    assert cfg.sidecar.port == 47474
    assert cfg.llm.api_key == "sk-abc"
