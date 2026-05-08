"""Fixture prompts and canned responses for benchmarks.

Heavy prompt and long response are built from a single dict of fixture secrets.
At import time we run each secret through the proxy's actual `display_value()`
so the long response contains the *exact* tokens the proxy will store in its
session DB — that way the unmask path is genuinely exercised, not bypassed.
"""
from __future__ import annotations
from aivion_mask_core.masker import display_value

# --- Heavy fixture secrets ------------------------------------------------
#
# Each entry: name → (entity_type, raw_secret).
# We use only API-key-style secrets here (each produces a unique display token
# that round-trips via the session DB). URL components and AWS_SECRET_KEY are
# not stored / always-redacted, so including them in the response would not
# exercise unmask — they'd be in the request prompt only.

HEAVY_SECRETS: dict[str, tuple[str, str]] = {
    "github": ("GITHUB_TOKEN",       "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd1234"),
    "openai": ("OPENAI_API_KEY_V2",  "sk-proj-abcdefghijklmnopqrstuvwxyzABCDEF1234567890ABCDEFGHIJ"),
    "stripe": ("STRIPE_SECRET_KEY",  "sk_live_51Hxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
}

# Real display tokens that the proxy will produce and store. Computed once at
# import time so the rest of the module can reference them as constants.
HEAVY_DISPLAY: dict[str, str] = {
    name: display_value(secret, etype) for name, (etype, secret) in HEAVY_SECRETS.items()
}

# --- Prompts --------------------------------------------------------------

CLEAN_PROMPT = (
    "Write a one-paragraph summary of how a load balancer distributes traffic "
    "across backend instances, mentioning health checks and round-robin scheduling."
)

HEAVY_PROMPT = (
    "Help me audit this config for issues:\n"
    "DATABASE_URL=postgresql://app_user:7Hd2KqLmN3pX@db.prod.internal:5432/orders\n"
    f"GITHUB_TOKEN={HEAVY_SECRETS['github'][1]}\n"
    f"OPENAI_API_KEY={HEAVY_SECRETS['openai'][1]}\n"
    f"STRIPE_SECRET_KEY={HEAVY_SECRETS['stripe'][1]}\n"
    "What's wrong here, and what should I rotate first?"
)
# Note: AWS_SECRET_ACCESS_KEY intentionally omitted. AWS_SECRET_KEY is in
# _ALWAYS_REDACT, which assigns it the display token "***". That single-token
# entry collides with the "***" appearing inside other display tokens
# (e.g. "ghp_AB***1234"), corrupting unmask. The bench drops it to measure
# the unmask path cleanly. The collision is documented in CLAUDE.md.

# --- Mock responses -------------------------------------------------------

SHORT_RESPONSE_TEXT = (
    "A load balancer distributes incoming requests across multiple backend "
    "instances using strategies like round-robin, least-connections, or weighted "
    "routing. It periodically polls each backend's health-check endpoint and "
    "removes failing nodes from rotation until they recover. This keeps latency "
    "low and individual instance load bounded."
)

# Long response embeds the *actual* display tokens (computed above), so when
# the proxy receives this back from the mock, its unmask phase finds entries
# in the session DB and replaces them with the original secrets.
LONG_RESPONSE_TEXT = (
    "I'll go through these one by one.\n\n"
    f"1. The GitHub token {HEAVY_DISPLAY['github']} should be revoked at "
    "https://github.com/settings/tokens and reissued with the minimum scopes.\n"
    f"2. The OpenAI key {HEAVY_DISPLAY['openai']} — rotate via the OpenAI "
    "dashboard and audit billing for the last 30 days.\n"
    f"3. The Stripe live key {HEAVY_DISPLAY['stripe']} is the highest blast "
    "radius of the bunch — revoke immediately and rotate webhook signing "
    "secrets too.\n\n"
    "Beyond that, the database password is also exposed and should be rotated, "
    "but I have less to say about it since it's fully redacted in what I'm "
    "seeing.\n\n"
    "Order of rotation by impact: Stripe, database, OpenAI, GitHub. After "
    "rotation, move everything to a secrets manager (Doppler, 1Password, AWS "
    "Secrets Manager) and read at runtime instead of committing a .env file."
)


def make_request_body(
    prompt: str,
    model: str = "claude-haiku-4-5",
    stream: bool = False,
    max_tokens: int = 1024,
) -> dict:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "stream": stream,
        "messages": [{"role": "user", "content": prompt}],
    }
