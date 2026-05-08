from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .session import get_token, save_token, get_all_mappings

_log = logging.getLogger(__name__)


def register_custom_patterns(entries: list) -> None:
    """Extend _PATTERNS with user-defined regexes from config. Call once at startup."""
    for entry in entries:
        try:
            compiled = re.compile(entry.pattern)
        except re.error as exc:
            _log.warning("Skipping invalid custom pattern %r: %s", entry.name, exc)
            continue
        _PATTERNS.append((entry.name, compiled))
        _log.info("[CUSTOM PATTERN] registered %s", entry.name)


@dataclass
class Entity:
    entity_type: str
    value: str
    start: int
    end: int


# Each entry: (entity_type, compiled_pattern)
# Mirrors the credential patterns in core/recognizers/index.ts
#
# Pattern length notes:
#   Exact counts ({n}) — used only when the length is protocol/crypto-determined and stable:
#     AWS key IDs, Twilio SIDs, Shopify/Mailgun tokens (all hex UUIDs), Azure AccountKey (86 = base64(64 bytes))
#   Minimum counts ({n,}) — used for provider-defined formats that can change between releases:
#     GitHub PATs, OpenAI keys, Google API keys, npm tokens
#   Sources to check when a provider changes formats:
#     GitHub  → docs.github.com/authentication/keeping-your-account-and-data-secure/about-authentication-to-github
#     OpenAI  → platform.openai.com/docs/api-reference/authentication
#     Google  → cloud.google.com/docs/authentication/api-keys
#     npm     → docs.npmjs.com/about-access-tokens
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS_ACCESS_KEY_ID",   re.compile(r'\bAKIA[A-Z0-9]{16}\b')),
    ("AWS_SECRET_KEY",      re.compile(r'(?:aws_secret_access_key|secret_key|secret_access_key)\s*[=:]\s*[\'"]?([A-Za-z0-9/+=]{40})', re.I)),
    # github.com token formats — {32,} instead of {36} so a length bump doesn't silently miss
    ("GITHUB_TOKEN",        re.compile(r'\b(?:ghp_[A-Za-z0-9]{32,}|ghs_[A-Za-z0-9]{32,}|gho_[A-Za-z0-9]{32,}|github_pat_[A-Za-z0-9_]{32,})\b')),
    # OpenAI classic key — {40,} catches any future length increase
    ("OPENAI_API_KEY",      re.compile(r'\bsk-[A-Za-z0-9]{40,}\b')),
    ("OPENAI_API_KEY_V2",   re.compile(r'\bsk-proj-[A-Za-z0-9_-]{48,}\b')),
    ("ANTHROPIC_API_KEY",   re.compile(r'\bsk-ant-api\d{2}-[A-Za-z0-9_-]{93,}\b')),
    # Google API key — AIza prefix is stable; payload length can vary
    ("GOOGLE_API_KEY",      re.compile(r'\bAIza[A-Za-z0-9_-]{32,}\b')),
    ("SLACK_BOT_TOKEN",     re.compile(r'\bxoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}\b')),
    ("SLACK_USER_TOKEN",    re.compile(r'\bxoxp-[0-9]{10,13}-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{32}\b')),
    ("SLACK_APP_TOKEN",     re.compile(r'\bxapp-\d-[A-Z0-9]{10,}-\d{11}-[A-Za-z0-9]{64}\b')),
    ("SLACK_WEBHOOK",       re.compile(r'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+')),
    ("STRIPE_SECRET_KEY",   re.compile(r'\bsk_live_[A-Za-z0-9]{24,}\b')),
    ("STRIPE_TEST_KEY",     re.compile(r'\bsk_test_[A-Za-z0-9]{24,}\b')),
    ("STRIPE_RESTRICTED",   re.compile(r'\brk_live_[A-Za-z0-9]{24,}\b')),
    ("SENDGRID_API_KEY",    re.compile(r'\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b')),
    ("TWILIO_ACCOUNT_SID",  re.compile(r'\bAC[a-f0-9]{32}\b')),
    # npm token — {32,} instead of {36}
    ("NPM_TOKEN",           re.compile(r'\bnpm_[A-Za-z0-9]{32,}\b')),
    ("PYPI_TOKEN",          re.compile(r'\bpypi-[A-Za-z0-9_-]{32,}\b')),
    ("SHOPIFY_TOKEN",       re.compile(r'\bshpat_[a-fA-F0-9]{32}\b')),
    ("SHOPIFY_CUSTOM_TOKEN",re.compile(r'\bshpca_[a-fA-F0-9]{32}\b')),
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


# Entity types that get structural (per-component) masking instead of whole-value replacement
_URL_TYPES = {"DATABASE_URL", "DATABASE_URL_REDIS", "URL_WITH_CREDENTIALS"}


# Entity types whose values must never be partially revealed
_ALWAYS_REDACT = {"URL_PASS", "AWS_SECRET_KEY"}


def display_value(value: str, entity_type: str) -> str:
    """Return a safe partial-reveal string for logging and user display.

    Passwords are always fully hidden. Other values expose a length-proportional
    prefix+suffix so the LLM retains context without leaking the secret.
    """
    if entity_type in _ALWAYS_REDACT:
        return "***"
    n = len(value)
    if n <= 4:
        return "***"
    if n <= 8:
        return value[0] + "***" + value[-1]
    if n <= 16:
        return value[:2] + "***" + value[-2:]
    if n <= 32:
        return value[:4] + "***" + value[-4:]
    return value[:6] + "***" + value[-4:]


async def _get_or_create_token(
    conn, session_id: str, value: str, entity_type: str, ttl_hours: int
) -> str:
    token = await get_token(conn, session_id, value)
    if token is None:
        token = display_value(value, entity_type)
        await save_token(conn, session_id, token, value, 0, ttl_hours)
        _log.info("[MASKED] %s", entity_type)
    return token


async def _mask_url_parts(url: str, conn, session_id: str, ttl_hours: int) -> str:
    """Replace username, password, hostname, and db name with display values inline.

    Preserves scheme, port, and URL structure so the LLM retains semantic meaning.
    URL components are NOT stored in the session — their values are too short/common
    for safe pre-redaction. Falls back to whole-URL masking if parsing fails.
    """
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            raise ValueError("not a full URL")
    except Exception:
        return await _get_or_create_token(conn, session_id, url, "DATABASE_URL", ttl_hours)

    port_str = f":{p.port}" if p.port else ""
    db_name = p.path.lstrip("/") if p.path else ""

    user_disp = display_value(p.username, "URL_USER") if p.username else None
    pass_disp = display_value(p.password, "URL_PASS") if p.password else None
    host_disp = display_value(p.hostname, "URL_HOST") if p.hostname else None
    db_disp   = display_value(db_name, "URL_DB") if db_name else None

    host_part = f"{host_disp or p.hostname or ''}{port_str}"
    if user_disp and pass_disp:
        netloc = f"{user_disp}:{pass_disp}@{host_part}"
    elif user_disp:
        netloc = f"{user_disp}@{host_part}"
    elif pass_disp:
        netloc = f":{pass_disp}@{host_part}"
    else:
        netloc = host_part

    path = f"/{db_disp}" if db_disp else ""
    return f"{p.scheme}://{netloc}{path}"


def detect(text: str) -> list[Entity]:
    """Find all credential entities in text. Deduplicates overlapping spans."""
    candidates: list[Entity] = []
    for entity_type, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            candidates.append(Entity(entity_type, m.group(0), m.start(), m.end()))

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


def _bounded_pattern(original: str) -> re.Pattern[str]:
    """Build a regex for `original` with word boundaries when the edges are word chars.

    For tokens like `ghp_ABC` or `AKIAxxx` (start+end are word chars) we anchor with `\b` to
    prevent substring matches inside arbitrary text. For tokens that start/end with non-word
    chars (URLs, JSON snippets), we drop the boundary on that side since `\b` requires a
    word↔non-word transition and would never match.
    """
    escaped = re.escape(original)
    left  = r"\b" if original[:1].isalnum() or original[:1] == "_" else ""
    right = r"\b" if original[-1:].isalnum() or original[-1:] == "_" else ""
    return re.compile(f"{left}{escaped}{right}")


async def mask_message(
    text: str,
    conn,
    session_id: str,
    ttl_hours: int,
) -> str:
    """Pre-redact known entities, detect new ones, assign tokens, return masked text."""
    # Step 1: replace known values with their display tokens (prevents turn-3 leak).
    mappings = await get_all_mappings(conn, session_id)  # {token: original}
    for token, original in mappings.items():
        if not original:
            continue
        text = _bounded_pattern(original).sub(token, text)

    # Step 2: detect new entities — CPU-bound regex runs in thread pool
    loop = asyncio.get_running_loop()
    entities = await loop.run_in_executor(None, detect, text)
    if not entities:
        return text

    # Step 3: replace right-to-left to preserve indices
    entities.sort(key=lambda e: e.start, reverse=True)
    for entity in entities:
        if entity.entity_type in _URL_TYPES:
            replacement = await _mask_url_parts(entity.value, conn, session_id, ttl_hours)
        else:
            replacement = await _get_or_create_token(conn, session_id, entity.value, entity.entity_type, ttl_hours)
        text = text[: entity.start] + replacement + text[entity.end :]
    return text
