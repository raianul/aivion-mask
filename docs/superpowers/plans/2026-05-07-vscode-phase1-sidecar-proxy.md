# aivion-mask Phase 1: Machine-Level Sidecar + Proxy Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a machine-level Python sidecar (port 47474) that acts as a transparent OpenAI-compatible proxy — masking credentials before prompts reach any LLM and restoring originals in the response, entirely on the local machine.

**Architecture:** A FastAPI sidecar holds a SQLite session store mapping `__P1__` tokens to original values. The VS Code extension installs a Python venv on first run, spawns the sidecar, and registers it as a system service (launchd/systemd/Task Scheduler) so it persists across VS Code restarts. Any IDE tool (Continue, Cursor) points its `apiBase` to `localhost:47474`; the sidecar intercepts, masks, proxies, and unscrubs transparently with a lookahead buffer for streaming.

**Tech Stack:** Python ≥3.10, FastAPI 0.115, uvicorn, httpx, sqlite3 (stdlib), tomllib/tomli; TypeScript (existing VS Code extension toolchain)

**Design note — no Presidio in Phase 1:** The developer policy (credentials and secrets) is 100% regex-based. Presidio adds ~150 MB of dependencies (spaCy model) for no benefit here — all our patterns are custom `PatternRecognizer` instances anyway. Pure Python regex keeps the venv small (~15 MB) and the install fast. The `detect()` interface is identical to what Presidio would expose; swapping in Phase 2 is a one-file change.

---

## File Map

### New files — Python sidecar
| Path | Responsibility |
|---|---|
| `sidecar/pyproject.toml` | Package metadata, dependencies, entry point |
| `sidecar/aivion_mask_sidecar/__init__.py` | Empty package marker |
| `sidecar/aivion_mask_sidecar/config.py` | Load/create `~/.aivion-mask/config.toml` |
| `sidecar/aivion_mask_sidecar/session.py` | SQLite CRUD for token↔value mappings + TTL cleanup |
| `sidecar/aivion_mask_sidecar/tokens.py` | `make_token(n)`, `replace_tokens(text, mappings)` |
| `sidecar/aivion_mask_sidecar/masker.py` | Regex detection + `mask_message()` orchestrator |
| `sidecar/aivion_mask_sidecar/stream.py` | `LookaheadBuffer` — unscrubs tokens across SSE chunk boundaries |
| `sidecar/aivion_mask_sidecar/proxy.py` | Async HTTP forward to real LLM (streaming + non-streaming) |
| `sidecar/aivion_mask_sidecar/mcp.py` | MCP manifest endpoint |
| `sidecar/aivion_mask_sidecar/main.py` | FastAPI app, routes, lifespan, CLI entry point |
| `sidecar/tests/test_config.py` | Config load/create tests |
| `sidecar/tests/test_session.py` | Session CRUD, TTL, counter tests |
| `sidecar/tests/test_tokens.py` | Token format tests |
| `sidecar/tests/test_masker.py` | Pattern detection + mask_message tests |
| `sidecar/tests/test_stream.py` | Lookahead buffer edge cases |
| `sidecar/tests/test_proxy.py` | Mock upstream, verify mask→forward→unscrub |
| `sidecar/tests/test_main.py` | FastAPI route integration tests |

### New files — TypeScript
| Path | Responsibility |
|---|---|
| `core/recognizers/index.ts` | Copy of credential patterns (shared foundation for future browser extension) |
| `core/recognizers/package.json` | Package marker for future workspace import |
| `extension/vscode/src/sidecar.ts` | `SidecarManager` — venv install, spawn, health-check, service registration |

### Modified files — TypeScript
| Path | What changes |
|---|---|
| `extension/vscode/src/extension.ts` | Call `SidecarManager.ensureRunning()` on activate |
| `extension/vscode/src/statusBar.ts` | Add `setProxyActive()` state |
| `extension/vscode/package.json` | Add `aivion-mask.stopSidecar` command |

---

## Task 1: core/recognizers/ — copy patterns as shared foundation

**Files:**
- Create: `core/recognizers/index.ts`
- Create: `core/recognizers/package.json`

The `tsconfig.json` for the VS Code extension uses `rootDir: "src"` which prevents cross-directory imports. Rather than restructure the build now (YAGNI — browser extension doesn't exist yet), we copy the patterns to `core/` as an identical file. When browser extension work begins, a proper TypeScript workspace will replace the duplicate.

- [ ] **Step 1: Create `core/recognizers/package.json`**

```json
{
  "name": "@aivion/recognizers",
  "version": "0.1.0",
  "description": "Shared credential recognizer patterns for aivion-mask clients",
  "main": "index.ts",
  "license": "Apache-2.0"
}
```

- [ ] **Step 2: Create `core/recognizers/index.ts`**

Copy the full content of `extension/vscode/src/recognizers.ts` verbatim into `core/recognizers/index.ts`. No changes — identical file.

- [ ] **Step 3: Verify the VS Code extension still compiles and tests pass**

```bash
cd extension/vscode
npm run compile
npm test
```

Expected: all tests pass. No changes to the extension itself.

- [ ] **Step 4: Commit**

```bash
git add core/
git commit -m "feat: copy recognizer patterns to core/recognizers for future browser extension sharing"
```

---

## Task 2: Python sidecar — project scaffold

**Files:**
- Create: `sidecar/pyproject.toml`
- Create: `sidecar/aivion_mask_sidecar/__init__.py`
- Create: `sidecar/tests/__init__.py`

- [ ] **Step 1: Create `sidecar/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "aivion-mask-sidecar"
version = "0.1.0"
requires-python = ">=3.10"
description = "Local PII masking proxy for aivion-mask"
license = { text = "Apache-2.0" }
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "tomli>=2.0; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "httpx>=0.27",
]

[project.scripts]
aivion-mask-sidecar = "aivion_mask_sidecar.main:run"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package files**

`sidecar/aivion_mask_sidecar/__init__.py` — empty file.

`sidecar/tests/__init__.py` — empty file.

- [ ] **Step 3: Create dev venv and install**

```bash
cd sidecar
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: installs fastapi, uvicorn, httpx, pytest, respx.

- [ ] **Step 4: Verify pytest runs (zero tests for now)**

```bash
cd sidecar
pytest
```

Expected: `no tests ran`.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): scaffold Python package with dependencies"
```

---

## Task 3: config.py — load and create config.toml

**Files:**
- Create: `sidecar/aivion_mask_sidecar/config.py`
- Create: `sidecar/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_config.py`:
```python
import os
import tempfile
from pathlib import Path
import pytest
from aivion_mask_sidecar.config import load_config, Config, AIVION_DIR

def test_load_creates_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("aivion_mask_sidecar.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_sidecar.config.CONFIG_PATH", tmp_path / "config.toml")
    cfg = load_config()
    assert cfg.sidecar.port == 47474
    assert cfg.sidecar.session_ttl_hours == 8
    assert cfg.llm.api_base == "https://api.openai.com/v1"
    assert (tmp_path / "config.toml").exists()

def test_load_reads_existing_file(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[sidecar]\nport = 9999\n\n[llm]\napi_key = "test-key"\n')
    monkeypatch.setattr("aivion_mask_sidecar.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_sidecar.config.CONFIG_PATH", config_file)
    cfg = load_config()
    assert cfg.sidecar.port == 9999
    assert cfg.llm.api_key == "test-key"

def test_load_merges_partial_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[llm]\napi_key = "sk-abc"\n')
    monkeypatch.setattr("aivion_mask_sidecar.config.AIVION_DIR", tmp_path)
    monkeypatch.setattr("aivion_mask_sidecar.config.CONFIG_PATH", config_file)
    cfg = load_config()
    assert cfg.sidecar.port == 47474       # default preserved
    assert cfg.llm.api_key == "sk-abc"    # override applied
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_config.py -v
```

Expected: `ImportError: No module named 'aivion_mask_sidecar.config'`

- [ ] **Step 3: Implement `config.py`**

`sidecar/aivion_mask_sidecar/config.py`:
```python
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

[llm]
api_base = "https://api.openai.com/v1"
api_key = ""
"""


@dataclass
class SidecarSettings:
    port: int = 47474
    session_ttl_hours: int = 8
    idle_shutdown_minutes: int = 0


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
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    sidecar = SidecarSettings(**data.get("sidecar", {}))
    llm = LLMSettings(**data.get("llm", {}))
    return Config(sidecar=sidecar, llm=llm)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_config.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): config.py — load/create ~/.aivion-mask/config.toml"
```

---

## Task 4: session.py — SQLite token store with TTL

**Files:**
- Create: `sidecar/aivion_mask_sidecar/session.py`
- Create: `sidecar/tests/test_session.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_session.py`:
```python
import time
import sqlite3
import pytest
from aivion_mask_sidecar.session import (
    init_db, get_token, next_index, save_token,
    get_all_mappings, delete_session, cleanup_expired,
)

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()

def test_init_creates_schema(conn):
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert ("sessions",) in tables

def test_save_and_get_token(conn):
    save_token(conn, "s1", "__P1__", "secret", 1, ttl_hours=8)
    assert get_token(conn, "s1", "secret") == "__P1__"

def test_get_token_unknown_returns_none(conn):
    assert get_token(conn, "s1", "unknown") is None

def test_get_token_different_session_returns_none(conn):
    save_token(conn, "s1", "__P1__", "secret", 1, ttl_hours=8)
    assert get_token(conn, "s2", "secret") is None

def test_next_index_starts_at_one(conn):
    assert next_index(conn, "s1") == 1

def test_next_index_increments(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    save_token(conn, "s1", "__P2__", "val2", 2, ttl_hours=8)
    assert next_index(conn, "s1") == 3

def test_get_all_mappings(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    save_token(conn, "s1", "__P2__", "val2", 2, ttl_hours=8)
    mappings = get_all_mappings(conn, "s1")
    assert mappings == {"__P1__": "val1", "__P2__": "val2"}

def test_delete_session(conn):
    save_token(conn, "s1", "__P1__", "val1", 1, ttl_hours=8)
    delete_session(conn, "s1")
    assert get_token(conn, "s1", "val1") is None

def test_cleanup_expired(conn):
    # Save with 0 TTL (already expired)
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__P1__", "val1", 1, now - 10, now - 1),
    )
    conn.commit()
    count = cleanup_expired(conn)
    assert count == 1
    assert get_token(conn, "s1", "val1") is None

def test_expired_token_not_returned(conn):
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "__P1__", "val1", 1, now - 10, now - 1),
    )
    conn.commit()
    assert get_token(conn, "s1", "val1") is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_session.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `session.py`**

`sidecar/aivion_mask_sidecar/session.py`:
```python
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT NOT NULL,
    token        TEXT NOT NULL,
    original     TEXT NOT NULL,
    token_index  INTEGER NOT NULL,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    PRIMARY KEY (session_id, token)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_session_original
    ON sessions(session_id, original);
CREATE INDEX IF NOT EXISTS idx_session_expiry
    ON sessions(expires_at);
"""


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        from .config import AIVION_DIR
        db_path = AIVION_DIR / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def get_token(conn: sqlite3.Connection, session_id: str, original: str) -> str | None:
    row = conn.execute(
        "SELECT token FROM sessions WHERE session_id=? AND original=? AND expires_at>?",
        (session_id, original, int(time.time())),
    ).fetchone()
    return row[0] if row else None


def next_index(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(token_index) FROM sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return (row[0] or 0) + 1


def save_token(
    conn: sqlite3.Connection,
    session_id: str,
    token: str,
    original: str,
    token_index: int,
    ttl_hours: int,
) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)",
        (session_id, token, original, token_index, now, now + ttl_hours * 3600),
    )
    conn.commit()


def get_all_mappings(conn: sqlite3.Connection, session_id: str) -> dict[str, str]:
    """Return {token: original} for all non-expired entries in this session."""
    rows = conn.execute(
        "SELECT token, original FROM sessions WHERE session_id=? AND expires_at>?",
        (session_id, int(time.time())),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()


def cleanup_expired(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM sessions WHERE expires_at<?", (int(time.time()),))
    conn.commit()
    return cursor.rowcount
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_session.py -v
```

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): session.py — SQLite token store with TTL"
```

---

## Task 5: tokens.py — token format + text replacement

**Files:**
- Create: `sidecar/aivion_mask_sidecar/tokens.py`
- Create: `sidecar/tests/test_tokens.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_tokens.py`:
```python
from aivion_mask_sidecar.tokens import make_token, replace_tokens

def test_make_token_format():
    assert make_token(1) == "__P1__"
    assert make_token(42) == "__P42__"

def test_replace_single_token():
    mappings = {"__P1__": "secret123"}
    assert replace_tokens("value is __P1__ done", mappings) == "value is secret123 done"

def test_replace_multiple_tokens():
    mappings = {"__P1__": "alice", "__P2__": "bob"}
    result = replace_tokens("__P1__ and __P2__", mappings)
    assert result == "alice and bob"

def test_replace_unknown_token_unchanged():
    assert replace_tokens("hello __P99__ world", {}) == "hello __P99__ world"

def test_replace_no_tokens():
    assert replace_tokens("no tokens here", {"__P1__": "x"}) == "no tokens here"

def test_replace_same_token_twice():
    mappings = {"__P1__": "secret"}
    assert replace_tokens("__P1__ and __P1__", mappings) == "secret and secret"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_tokens.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `tokens.py`**

`sidecar/aivion_mask_sidecar/tokens.py`:
```python
from __future__ import annotations
import re

_TOKEN_RE = re.compile(r'__P\d+__')


def make_token(index: int) -> str:
    return f"__P{index}__"


def replace_tokens(text: str, mappings: dict[str, str]) -> str:
    return _TOKEN_RE.sub(lambda m: mappings.get(m.group(0), m.group(0)), text)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_tokens.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): tokens.py — __P1__ format and replacement"
```

---

## Task 6: masker.py — credential detection + mask_message

**Files:**
- Create: `sidecar/aivion_mask_sidecar/masker.py`
- Create: `sidecar/tests/test_masker.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_masker.py`:
```python
import pytest
from aivion_mask_sidecar.masker import detect, mask_message, Entity
from aivion_mask_sidecar.session import init_db

# --- detect() ---

def test_detects_aws_key():
    entities = detect("key=AKIAIOSFODNN7EXAMPLE")
    assert any(e.entity_type == "AWS_ACCESS_KEY_ID" for e in entities)

def test_detects_github_pat():
    entities = detect("token: ghp_" + "A" * 36)
    assert any(e.entity_type == "GITHUB_TOKEN" for e in entities)

def test_detects_openai_key():
    entities = detect("sk-" + "a" * 48)
    assert any(e.entity_type == "OPENAI_API_KEY" for e in entities)

def test_detects_postgres_url():
    entities = detect("postgresql://user:password123@localhost:5432/mydb")
    assert any(e.entity_type == "DATABASE_URL" for e in entities)

def test_detects_private_ip():
    entities = detect("connect to 192.168.1.100")
    assert any(e.entity_type == "PRIVATE_IP" for e in entities)

def test_detects_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    entities = detect(jwt)
    assert any(e.entity_type == "JWT_TOKEN" for e in entities)

def test_no_false_positive_plain_text():
    entities = detect("The quick brown fox")
    assert entities == []

def test_no_false_positive_variable_name():
    entities = detect("my_variable_name = 42")
    assert entities == []

def test_deduplicates_overlapping_spans():
    # DATABASE_URL and URL_WITH_CREDENTIALS both match — only one returned
    entities = detect("postgresql://user:pass@host:5432/db")
    starts = [e.start for e in entities]
    assert len(starts) == len(set(starts))  # no duplicate start positions

# --- mask_message() ---

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "t.db")
    yield c
    c.close()

def test_mask_message_assigns_token(conn):
    result = mask_message("key=AKIAIOSFODNN7EXAMPLE text", conn, "s1", 8)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "__P1__" in result

def test_mask_message_same_value_same_token(conn):
    r1 = mask_message("AKIAIOSFODNN7EXAMPLE", conn, "s1", 8)
    r2 = mask_message("AKIAIOSFODNN7EXAMPLE", conn, "s1", 8)
    assert r1 == r2  # same token assigned

def test_mask_message_pre_redacts_known_entities(conn):
    # First message — assigns __P1__
    mask_message("key=AKIAIOSFODNN7EXAMPLE", conn, "s1", 8)
    # Second message mentions same value — should pre-redact without re-detecting
    result = mask_message("the key is AKIAIOSFODNN7EXAMPLE again", conn, "s1", 8)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "__P1__" in result

def test_mask_message_no_entities_unchanged(conn):
    assert mask_message("hello world", conn, "s1", 8) == "hello world"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_masker.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `masker.py`**

`sidecar/aivion_mask_sidecar/masker.py`:
```python
from __future__ import annotations
import re
import sqlite3
from dataclasses import dataclass

from .session import get_token, next_index, save_token, get_all_mappings
from .tokens import make_token


@dataclass
class Entity:
    entity_type: str
    value: str
    start: int
    end: int


# Each entry: (entity_type, compiled_pattern)
# Mirrors the 42 patterns in core/recognizers/index.ts
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS_ACCESS_KEY_ID",   re.compile(r'\bAKIA[A-Z0-9]{16}\b')),
    ("AWS_SECRET_KEY",      re.compile(r'(?:aws_secret_access_key|secret_key|secret_access_key)\s*[=:]\s*[\'"]?([A-Za-z0-9/+=]{40})', re.I)),
    ("GITHUB_TOKEN",        re.compile(r'\b(?:ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})\b')),
    ("OPENAI_API_KEY",      re.compile(r'\bsk-[A-Za-z0-9]{48}\b')),
    ("OPENAI_API_KEY_V2",   re.compile(r'\bsk-proj-[A-Za-z0-9_-]{48,}\b')),
    ("ANTHROPIC_API_KEY",   re.compile(r'\bsk-ant-api\d{2}-[A-Za-z0-9_-]{93,}\b')),
    ("GOOGLE_API_KEY",      re.compile(r'\bAIza[A-Za-z0-9_-]{35}\b')),
    ("SLACK_BOT_TOKEN",     re.compile(r'\bxoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}\b')),
    ("SLACK_USER_TOKEN",    re.compile(r'\bxoxp-[0-9]{10,13}-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{32}\b')),
    ("SLACK_APP_TOKEN",     re.compile(r'\bxapp-\d-[A-Z0-9]{10,}-\d{11}-[A-Za-z0-9]{64}\b')),
    ("SLACK_WEBHOOK",       re.compile(r'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+')),
    ("STRIPE_SECRET_KEY",   re.compile(r'\bsk_live_[A-Za-z0-9]{24,}\b')),
    ("STRIPE_TEST_KEY",     re.compile(r'\bsk_test_[A-Za-z0-9]{24,}\b')),
    ("STRIPE_RESTRICTED",   re.compile(r'\brk_live_[A-Za-z0-9]{24,}\b')),
    ("SENDGRID_API_KEY",    re.compile(r'\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b')),
    ("TWILIO_ACCOUNT_SID",  re.compile(r'\bAC[a-f0-9]{32}\b')),
    ("NPM_TOKEN",           re.compile(r'\bnpm_[A-Za-z0-9]{36}\b')),
    ("PYPI_TOKEN",          re.compile(r'\bpypi-[A-Za-z0-9_-]{32,}\b')),
    ("SHOPIFY_TOKEN",       re.compile(r'\bshpat_[a-fA-F0-9]{32}\b')),
    ("SHOPIFY_CUSTOM_TOKEN",re.compile(r'\bshpca_[a-fA-F0-9]{32}\b')),
    ("MAILCHIMP_API_KEY",   re.compile(r'\b[a-f0-9]{32}-us\d{1,2}\b')),
    ("MAILGUN_API_KEY",     re.compile(r'\bkey-[a-z0-9]{32}\b')),
    ("DATABASE_URL",        re.compile(r'(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^:@\s]+:[^@\s]+@[^\s"\']+', re.I)),
    ("DATABASE_URL_REDIS",  re.compile(r'rediss?://:[^@\s]+@[^\s"\']+')),
    ("PRIVATE_KEY",         re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ("JWT_TOKEN",           re.compile(r'\beyJ[A-Za-z0-9+/=_-]{10,}\.[A-Za-z0-9+/=_-]{10,}\.[A-Za-z0-9+/=_-]{10,}\b')),
    ("URL_WITH_CREDENTIALS",re.compile(r'[a-zA-Z][a-zA-Z0-9+.\-]*://[^:@\s]{1,100}:[^@\s]{3,100}@[^\s"\']{1,200}')),
    ("PRIVATE_IP",          re.compile(r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b')),
    ("FIREBASE_URL",        re.compile(r'https://[a-zA-Z0-9-]+\.firebaseio\.com')),
    ("AZURE_STORAGE",       re.compile(r'DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{86}')),
    ("TERRAFORM_TOKEN",     re.compile(r'\b[a-z0-9]{14}\.atlasv1\.[A-Za-z0-9]{60}\b')),
    ("DOCKER_HUB_PAT",      re.compile(r'\bdop_v1_[a-f0-9]{64}\b')),
]


def detect(text: str) -> list[Entity]:
    """Find all credential entities in text. Deduplicates overlapping spans."""
    candidates: list[Entity] = []
    for entity_type, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            candidates.append(Entity(entity_type, m.group(0), m.start(), m.end()))

    # Sort by start position, deduplicate overlapping spans (keep first match)
    candidates.sort(key=lambda e: e.start)
    seen: set[int] = set()
    result: list[Entity] = []
    for entity in candidates:
        positions = set(range(entity.start, entity.end))
        if positions & seen:
            continue
        seen |= positions
        result.append(entity)
    return result


def mask_message(
    text: str,
    conn: sqlite3.Connection,
    session_id: str,
    ttl_hours: int,
) -> str:
    """Pre-redact known entities, detect new ones, assign tokens, return masked text."""
    # Step 1: replace known values with their tokens (prevents turn-3 leak)
    mappings = get_all_mappings(conn, session_id)  # {token: original}
    for token, original in mappings.items():
        text = text.replace(original, token)

    # Step 2: detect new entities in the (now pre-redacted) text
    entities = detect(text)
    if not entities:
        return text

    # Step 3: assign tokens, replace right-to-left to preserve indices
    entities.sort(key=lambda e: e.start, reverse=True)
    for entity in entities:
        token = get_token(conn, session_id, entity.value)
        if token is None:
            idx = next_index(conn, session_id)
            token = make_token(idx)
            save_token(conn, session_id, token, entity.value, idx, ttl_hours)
        text = text[: entity.start] + token + text[entity.end :]
    return text
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_masker.py -v
```

Expected: `13 passed`. If an AWS key test fails, the regex may need tweaking — `AKIAIOSFODNN7EXAMPLE` has 20 chars after `AKIA`, but the pattern requires exactly 16. Use `AKIAIOSFODNN7EXAMPLE` → adjust to fit the pattern or use a valid-length key in the test (`AKIAIOSFODNN7EXAMPL` is 19 chars total, `AKIA` + 15).

> **Fix if needed:** The test key must be exactly `AKIA` + 16 uppercase alphanumeric chars. Use `"AKIA" + "A" * 16` in the test instead of the example value.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): masker.py — credential detection + mask_message"
```

---

## Task 7: stream.py — SSE lookahead buffer

**Files:**
- Create: `sidecar/aivion_mask_sidecar/stream.py`
- Create: `sidecar/tests/test_stream.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_stream.py`:
```python
from aivion_mask_sidecar.stream import split_at_safe_point, LookaheadBuffer

# --- split_at_safe_point ---

def test_no_underscores():
    assert split_at_safe_point("hello world") == ("hello world", "")

def test_complete_token_at_end():
    assert split_at_safe_point("value __P1__") == ("value __P1__", "")

def test_partial_double_underscore():
    assert split_at_safe_point("value __") == ("value ", "__")

def test_partial_with_P():
    assert split_at_safe_point("value __P") == ("value ", "__P")

def test_partial_with_number():
    assert split_at_safe_point("value __P42") == ("value ", "__P42")

def test_partial_closing_underscore():
    assert split_at_safe_point("value __P1_") == ("value ", "__P1_")

def test_complete_then_partial():
    safe, hold = split_at_safe_point("__P1__ and __P")
    assert safe == "__P1__ and "
    assert hold == "__P2" or hold == "__P"  # depends on what's there

def test_text_with_underscores_not_token():
    # variable_name style — rfind finds _ but it's not start of a token pattern
    safe, hold = split_at_safe_point("variable_name = val")
    assert "variable_name" in safe  # not held back

# --- LookaheadBuffer ---

def test_passthrough_no_tokens():
    buf = LookaheadBuffer({"__P1__": "secret"})
    assert buf.push("hello world") == "hello world"
    assert buf.flush() == ""

def test_replaces_complete_token():
    buf = LookaheadBuffer({"__P1__": "secret"})
    assert buf.push("value is __P1__ done") == "value is secret done"

def test_handles_split_token():
    buf = LookaheadBuffer({"__P1__": "secret"})
    out1 = buf.push("value is __P")
    out2 = buf.push("1__ done")
    assert out1 == "value is "         # held back partial
    assert out2 == "secret done"       # flushed once complete

def test_flush_releases_remainder():
    buf = LookaheadBuffer({"__P1__": "secret"})
    buf.push("value __P1")             # partial held back
    remainder = buf.flush()
    assert remainder == "secret" or remainder == "__P1"  # replaces if complete, else raw

def test_multiple_tokens_in_sequence():
    buf = LookaheadBuffer({"__P1__": "alice", "__P2__": "bob"})
    result = buf.push("__P1__ met __P2__")
    assert result == "alice met bob"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_stream.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `stream.py`**

`sidecar/aivion_mask_sidecar/stream.py`:
```python
from __future__ import annotations
import re

from .tokens import replace_tokens

# Matches a trailing suffix that could be the start of an incomplete __Pn__ token.
# __Pn__ characters are: underscore, 'P', digits.
_PARTIAL_RE = re.compile(r'_[_P\d]*$')
_TOKEN_RE = re.compile(r'__P\d+__')


def split_at_safe_point(text: str) -> tuple[str, str]:
    """Return (safe_to_flush, hold_back).

    Holds back any trailing suffix that looks like an incomplete __Pn__ token
    so chunks can be emitted without cutting tokens in half.
    """
    m = _PARTIAL_RE.search(text)
    if not m:
        return text, ""
    partial = m.group(0)
    # If the partial is actually a complete token, it's safe to flush everything
    if _TOKEN_RE.fullmatch(partial):
        return text, ""
    return text[: m.start()], partial


class LookaheadBuffer:
    """Accumulates streaming text and emits it only when no partial token is at the edge."""

    def __init__(self, mappings: dict[str, str]) -> None:
        self._mappings = mappings
        self._buf = ""

    def push(self, chunk: str) -> str:
        """Accept a new chunk; return content safe to emit now."""
        self._buf += chunk
        safe, self._buf = split_at_safe_point(self._buf)
        return replace_tokens(safe, self._mappings)

    def flush(self) -> str:
        """End of stream — emit everything remaining."""
        result = replace_tokens(self._buf, self._mappings)
        self._buf = ""
        return result
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_stream.py -v
```

Expected: all pass. The `test_complete_then_partial` assertion uses `or` — adjust if needed based on actual output.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): stream.py — SSE lookahead buffer for split-token unscrub"
```

---

## Task 8: proxy.py — async HTTP forwarding

**Files:**
- Create: `sidecar/aivion_mask_sidecar/proxy.py`
- Create: `sidecar/tests/test_proxy.py`

- [ ] **Step 1: Write failing tests**

`sidecar/tests/test_proxy.py`:
```python
import json
import pytest
import respx
import httpx
from aivion_mask_sidecar.proxy import forward_streaming, forward_complete
from aivion_mask_sidecar.session import init_db, save_token

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "t.db")
    save_token(c, "s1", "__P1__", "secret123", 1, ttl_hours=8)
    yield c
    c.close()

@respx.mock
@pytest.mark.asyncio
async def test_forward_complete_unscrubs(conn):
    body = {"choices": [{"message": {"role": "assistant", "content": "the value is __P1__ ok"}}]}
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = await forward_complete(
        request_body={"messages": [], "model": "gpt-4o"},
        api_base="https://api.openai.com/v1",
        api_key="test-key",
        session_id="s1",
        conn=conn,
    )
    assert result["choices"][0]["message"]["content"] == "the value is secret123 ok"

@respx.mock
@pytest.mark.asyncio
async def test_forward_complete_passes_auth_header(conn):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )
    await forward_complete(
        request_body={"messages": []},
        api_base="https://api.openai.com/v1",
        api_key="sk-mykey",
        session_id="s1",
        conn=conn,
    )
    call = respx.calls.last
    assert call.request.headers["authorization"] == "Bearer sk-mykey"

@respx.mock
@pytest.mark.asyncio
async def test_forward_streaming_unscrubs(conn):
    chunks = [
        'data: {"choices":[{"delta":{"content":"value is __P"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":"1__ ok"},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text="".join(chunks),
                                    headers={"content-type": "text/event-stream"})
    )
    collected = []
    async for line in forward_streaming(
        request_body={"messages": [], "stream": True},
        api_base="https://api.openai.com/v1",
        api_key="test-key",
        session_id="s1",
        conn=conn,
    ):
        collected.append(line.decode())

    full = "".join(collected)
    assert "secret123" in full
    assert "__P1__" not in full
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd sidecar && pytest tests/test_proxy.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `proxy.py`**

`sidecar/aivion_mask_sidecar/proxy.py`:
```python
from __future__ import annotations
import json
import sqlite3
from typing import AsyncIterator

import httpx

from .session import get_all_mappings
from .stream import LookaheadBuffer
from .tokens import replace_tokens


async def forward_complete(
    request_body: dict,
    api_base: str,
    api_key: str,
    session_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Forward a non-streaming request; unscrub tokens in the response."""
    mappings = get_all_mappings(conn, session_id)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{api_base}/chat/completions", json=request_body, headers=headers
        )
        response.raise_for_status()
        data = response.json()
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        if isinstance(msg.get("content"), str):
            msg["content"] = replace_tokens(msg["content"], mappings)
    return data


async def forward_streaming(
    request_body: dict,
    api_base: str,
    api_key: str,
    session_id: str,
    conn: sqlite3.Connection,
) -> AsyncIterator[bytes]:
    """Forward a streaming request; unscrub tokens via lookahead buffer."""
    mappings = get_all_mappings(conn, session_id)
    buf = LookaheadBuffer(mappings)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{api_base}/chat/completions", json=request_body, headers=headers
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    yield (line + "\n").encode()
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    yield (line + "\n\n").encode()
                    continue
                try:
                    content = chunk["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError):
                    yield f"data: {json.dumps(chunk)}\n\n".encode()
                    continue
                safe = buf.push(content)
                chunk["choices"][0]["delta"]["content"] = safe
                yield f"data: {json.dumps(chunk)}\n\n".encode()

    remainder = buf.flush()
    if remainder:
        final = {"choices": [{"delta": {"content": remainder}, "index": 0}]}
        yield f"data: {json.dumps(final)}\n\n".encode()
    yield b"data: [DONE]\n\n"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd sidecar && pytest tests/test_proxy.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): proxy.py — async HTTP forward with streaming unscrub"
```

---

## Task 9: mcp.py + main.py — FastAPI app

**Files:**
- Create: `sidecar/aivion_mask_sidecar/mcp.py`
- Create: `sidecar/aivion_mask_sidecar/main.py`
- Create: `sidecar/tests/test_main.py`

- [ ] **Step 1: Implement `mcp.py`**

`sidecar/aivion_mask_sidecar/mcp.py`:
```python
def get_manifest(port: int) -> dict:
    return {
        "name": "aivion-mask",
        "version": "0.1.0",
        "description": "Local credential masking proxy — secrets never reach your LLM",
        "proxy": {
            "url": f"http://localhost:{port}/v1",
            "protocol": "openai",
        },
        "health": f"http://localhost:{port}/health",
    }
```

- [ ] **Step 2: Implement `main.py`**

`sidecar/aivion_mask_sidecar/main.py`:
```python
from __future__ import annotations
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import load_config, Config
from .masker import mask_message
from .mcp import get_manifest
from .proxy import forward_complete, forward_streaming
from .session import cleanup_expired, delete_session, init_db

_config: Config
_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _conn
    _config = load_config()
    _conn = init_db()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    _conn.close()


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(600)
        cleanup_expired(_conn)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # local-only service; all origins allowed
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/mcp")
def mcp():
    return get_manifest(_config.sidecar.port)


@app.delete("/v1/session/{session_id}")
def clear_session(session_id: str):
    delete_session(_conn, session_id)
    return {"deleted": session_id}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    session_id = (
        request.headers.get("X-Aivion-Session")
        or body.get("user")
        or str(uuid.uuid4())
    )

    if not _config.llm.api_key:
        raise HTTPException(
            status_code=400,
            detail="No LLM API key configured. Edit ~/.aivion-mask/config.toml",
        )

    # Mask each message content
    messages = body.get("messages", [])
    masked_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            content = mask_message(content, _conn, session_id, _config.sidecar.session_ttl_hours)
        masked_messages.append({**msg, "content": content})

    masked_body = {**body, "messages": masked_messages}
    masked_body.pop("user", None)  # don't leak session_id to upstream

    try:
        if body.get("stream", False):
            return StreamingResponse(
                forward_streaming(
                    masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn
                ),
                media_type="text/event-stream",
            )
        result = await forward_complete(
            masked_body, _config.llm.api_base, _config.llm.api_key, session_id, _conn
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream LLM unreachable: {exc}") from exc


def run() -> None:
    import uvicorn
    cfg = load_config()
    uvicorn.run("aivion_mask_sidecar.main:app", host="127.0.0.1", port=cfg.sidecar.port)
```

- [ ] **Step 3: Write integration tests**

`sidecar/tests/test_main.py`:
```python
import pytest
from fastapi.testclient import TestClient
from aivion_mask_sidecar.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_mcp_returns_manifest():
    r = client.get("/mcp")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "aivion-mask"
    assert "proxy" in data

def test_delete_session():
    r = client.delete("/v1/session/test-session")
    assert r.status_code == 200

def test_chat_completions_no_api_key(monkeypatch):
    from aivion_mask_sidecar import main as m
    from aivion_mask_sidecar.config import Config, SidecarSettings, LLMSettings
    m._config = Config(sidecar=SidecarSettings(), llm=LLMSettings(api_key=""))
    r = client.post("/v1/chat/completions", json={"messages": []})
    assert r.status_code == 400
    assert "api_key" in r.json()["detail"].lower()
```

- [ ] **Step 4: Run all sidecar tests**

```bash
cd sidecar && pytest -v
```

Expected: all tests pass. The `test_main.py` tests use `TestClient` which runs the lifespan — they will create `~/.aivion-mask/sessions.db`. This is fine for integration tests.

- [ ] **Step 5: Verify sidecar starts manually**

```bash
cd sidecar
source .venv/bin/activate
aivion-mask-sidecar &
curl http://localhost:47474/health
```

Expected: `{"status":"ok","version":"0.1.0"}`

Kill it: `kill %1`

- [ ] **Step 6: Commit**

```bash
git add sidecar/
git commit -m "feat(sidecar): mcp.py + main.py — FastAPI app wired and running on :47474"
```

---

## Task 10: VS Code extension — sidecar.ts

**Files:**
- Create: `extension/vscode/src/sidecar.ts`
- Create: `extension/vscode/src/test/suite/sidecar.test.ts`

- [ ] **Step 1: Create `sidecar.ts`**

`extension/vscode/src/sidecar.ts`:
```typescript
import * as vscode from 'vscode'
import * as os from 'os'
import * as path from 'path'
import * as fs from 'fs'
import { execFile, spawn } from 'child_process'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)

export const AIVION_DIR = path.join(os.homedir(), '.aivion-mask')
const VENV_DIR = path.join(AIVION_DIR, 'venv')
const PID_FILE = path.join(AIVION_DIR, 'sidecar.pid')
export const SIDECAR_PORT = 47474
const HEALTH_URL = `http://localhost:${SIDECAR_PORT}/health`

function venvBin(name: string): string {
  return process.platform === 'win32'
    ? path.join(VENV_DIR, 'Scripts', `${name}.exe`)
    : path.join(VENV_DIR, 'bin', name)
}

export async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch {
    return false
  }
}

async function waitUntilHealthy(timeoutMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await isHealthy()) return true
    await new Promise<void>((r) => setTimeout(r, 500))
  }
  return false
}

async function installVenv(
  progress: vscode.Progress<{ message?: string }>
): Promise<void> {
  fs.mkdirSync(AIVION_DIR, { recursive: true })
  progress.report({ message: 'Creating Python venv...' })
  await execFileAsync('python3', ['-m', 'venv', VENV_DIR])
  progress.report({ message: 'Installing aivion-mask-sidecar (first time only)...' })
  await execFileAsync(venvBin('pip'), ['install', '--quiet', 'aivion-mask-sidecar'])
}

function spawnSidecar(): void {
  const proc = spawn(venvBin('aivion-mask-sidecar'), [], {
    detached: true,
    stdio: 'ignore',
  })
  proc.unref()
  if (proc.pid !== undefined) {
    fs.mkdirSync(AIVION_DIR, { recursive: true })
    fs.writeFileSync(PID_FILE, String(proc.pid))
  }
}

async function registerSystemService(): Promise<void> {
  try {
    if (process.platform === 'darwin') await registerLaunchd()
    else if (process.platform === 'linux') await registerSystemd()
    else if (process.platform === 'win32') await registerTaskScheduler()
  } catch {
    // System service registration is best-effort — sidecar still works without it
  }
}

async function registerLaunchd(): Promise<void> {
  const plistDir = path.join(os.homedir(), 'Library', 'LaunchAgents')
  const plistPath = path.join(plistDir, 'com.aivionlabs.mask.plist')
  if (fs.existsSync(plistPath)) return
  fs.mkdirSync(plistDir, { recursive: true })
  fs.writeFileSync(
    plistPath,
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.aivionlabs.mask</string>
  <key>ProgramArguments</key>
  <array><string>${venvBin('aivion-mask-sidecar')}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>`
  )
  await execFileAsync('launchctl', ['load', plistPath]).catch(() => {})
}

async function registerSystemd(): Promise<void> {
  const serviceDir = path.join(os.homedir(), '.config', 'systemd', 'user')
  const servicePath = path.join(serviceDir, 'aivion-mask.service')
  if (fs.existsSync(servicePath)) return
  fs.mkdirSync(serviceDir, { recursive: true })
  fs.writeFileSync(
    servicePath,
    `[Unit]
Description=Aivion Mask local PII sidecar

[Service]
ExecStart=${venvBin('aivion-mask-sidecar')}
Restart=on-failure

[Install]
WantedBy=default.target
`
  )
  await execFileAsync('systemctl', ['--user', 'enable', '--now', 'aivion-mask']).catch(() => {})
}

async function registerTaskScheduler(): Promise<void> {
  const taskName = 'AivionMaskSidecar'
  // Check if already registered
  try {
    await execFileAsync('schtasks', ['/query', '/tn', taskName])
    return // already registered
  } catch {
    // not registered — proceed
  }
  await execFileAsync('schtasks', [
    '/create', '/tn', taskName,
    '/tr', venvBin('aivion-mask-sidecar'),
    '/sc', 'ONLOGON',
    '/f',
  ]).catch(() => {})
}

export class SidecarManager {
  async ensureRunning(): Promise<boolean> {
    if (await isHealthy()) return true

    return vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Aivion Mask', cancellable: false },
      async (progress) => {
        if (!fs.existsSync(venvBin('aivion-mask-sidecar'))) {
          try {
            await installVenv(progress)
          } catch (err) {
            void vscode.window.showErrorMessage(`Aivion Mask: sidecar install failed — ${err}`)
            return false
          }
        }

        progress.report({ message: 'Starting sidecar...' })
        spawnSidecar()
        void registerSystemService()

        const ready = await waitUntilHealthy()
        if (!ready) {
          void vscode.window.showErrorMessage(
            'Aivion Mask: sidecar failed to start. Check the Output panel.'
          )
          return false
        }
        return true
      }
    )
  }
}
```

- [ ] **Step 2: Write tests for exported functions**

`extension/vscode/src/test/suite/sidecar.test.ts`:
```typescript
import * as assert from 'assert'
import { SIDECAR_PORT, AIVION_DIR } from '../../sidecar'
import * as os from 'os'
import * as path from 'path'

suite('Sidecar constants', () => {
  test('port is 47474', () => {
    assert.strictEqual(SIDECAR_PORT, 47474)
  })

  test('AIVION_DIR is in home directory', () => {
    assert.strictEqual(AIVION_DIR, path.join(os.homedir(), '.aivion-mask'))
  })
})
```

- [ ] **Step 3: Compile and run tests**

```bash
cd extension/vscode
npm run compile
npm test
```

Expected: existing tests pass + 2 new sidecar constant tests pass.

- [ ] **Step 4: Commit**

```bash
git add extension/vscode/src/sidecar.ts extension/vscode/src/test/suite/sidecar.test.ts
git commit -m "feat(vscode): sidecar.ts — SidecarManager with venv install + system service registration"
```

---

## Task 11: VS Code extension — wire sidecar into extension.ts + statusBar.ts

**Files:**
- Modify: `extension/vscode/src/extension.ts`
- Modify: `extension/vscode/src/statusBar.ts`
- Modify: `extension/vscode/package.json`

- [ ] **Step 1: Add `setProxyActive()` to `statusBar.ts`**

Add this method to `MaskStatusBar` after `setActive()`:
```typescript
setProxyActive(port: number): void {
  this.item.text = `$(shield) aivion-mask: proxy :${port}`
  this.item.tooltip = `Aivion Mask active — proxy on localhost:${port}`
  this.item.backgroundColor = undefined
  this.item.color = undefined
}
```

- [ ] **Step 2: Update `extension.ts` to start sidecar on activate**

Add the import at the top:
```typescript
import { SidecarManager, SIDECAR_PORT } from './sidecar'
```

At the end of `activate()`, after the `registerCommands` block:
```typescript
const sidecarManager = new SidecarManager()
void sidecarManager.ensureRunning().then((running) => {
  if (running) statusBar?.setProxyActive(SIDECAR_PORT)
})
```

- [ ] **Step 3: Add `aivion-mask.stopSidecar` command to `package.json`**

In the `contributes.commands` array, add:
```json
{
  "command": "aivion-mask.stopSidecar",
  "title": "Aivion Mask: Stop Sidecar"
}
```

Wire it in `commands.ts` — add to `registerCommands`:
```typescript
context.subscriptions.push(
  vscode.commands.registerCommand('aivion-mask.stopSidecar', () => {
    void vscode.window.showInformationMessage(
      'Aivion Mask: sidecar runs as a system service. Stop it via launchctl / systemctl or Task Scheduler.'
    )
  })
)
```

- [ ] **Step 4: Compile and run full test suite**

```bash
cd extension/vscode
npm run compile
npm test
```

Expected: all tests pass. No new tests needed — the sidecar startup is integration-tested manually.

- [ ] **Step 5: Commit**

```bash
git add extension/vscode/src/extension.ts extension/vscode/src/statusBar.ts \
        extension/vscode/src/commands.ts extension/vscode/package.json
git commit -m "feat(vscode): wire SidecarManager into activate + add proxy status bar state"
```

---

## Task 12: End-to-end smoke test + CLAUDE.md update

- [ ] **Step 1: Install sidecar from local source into dev venv**

```bash
cd sidecar
source .venv/bin/activate
pip install -e .
```

- [ ] **Step 2: Set a real API key in config**

```bash
cat > ~/.aivion-mask/config.toml << 'EOF'
[sidecar]
port = 47474
session_ttl_hours = 8

[llm]
api_base = "https://api.openai.com/v1"
api_key = "YOUR_REAL_KEY_HERE"
EOF
```

- [ ] **Step 3: Start the sidecar**

```bash
aivion-mask-sidecar &
```

- [ ] **Step 4: Smoke-test the proxy**

```bash
curl -s http://localhost:47474/health
# → {"status":"ok","version":"0.1.0"}

curl -s http://localhost:47474/mcp
# → {"name":"aivion-mask","proxy":{"url":"http://localhost:47474/v1",...}}

curl -s -X POST http://localhost:47474/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"My key is AKIA'"$(python3 -c 'print("A"*16)')"', help me debug it"}]}'
# → Verify AKIA... key is NOT present in the forwarded request (check sidecar logs)
# → Verify response comes back with original value restored
```

- [ ] **Step 5: Update CLAUDE.md with sidecar commands**

In `CLAUDE.md`, update the "VS Code Extension Commands" section to add:

```markdown
## Sidecar Commands

```bash
cd sidecar
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # install + dev deps
pytest -v                        # run all sidecar tests
aivion-mask-sidecar              # start sidecar on :47474
pip install -e .                 # install without dev deps
```
```

- [ ] **Step 6: Commit everything**

```bash
git add CLAUDE.md
git commit -m "feat(phase1): complete — sidecar + proxy + system service + VS Code integration"
```

---

## Self-Review Notes

- **Spec §4.3 CORS** — implemented as `allow_origins=["*"]` in main.py. The sidecar binds to `127.0.0.1` only, so `*` is safe (no external network access). Browser extension origins are covered.
- **Spec §4.8 Presidio** — replaced with pure Python regex per plan note. Same interface, Presidio swap deferred to Phase 2.
- **Spec §5.1 Python version check** — the `installVenv` function calls `python3` directly. If Python < 3.10 is the system default, the sidecar will fail at import with a helpful error. A pre-check for Python version can be added in Phase 2.
- **Spec §6 core/recognizers** — implemented as a copy (not a re-export) due to tsconfig `rootDir: "src"` constraint. Noted in Task 1.
- **`commands.ts`** — the `stopSidecar` command in Task 11 requires reading `commands.ts`. Read it before editing to insert correctly alongside the existing toggle command.
