from __future__ import annotations
import re

_ABBREV: dict[str, str] = {
    "AWS_ACCESS_KEY_ID":      "AWS",
    "AWS_SECRET_KEY":         "AWS",
    "GITHUB_TOKEN":           "GH",
    "OPENAI_API_KEY":         "OAI",
    "OPENAI_API_KEY_V2":      "OAI",
    "ANTHROPIC_API_KEY":      "ANT",
    "GOOGLE_API_KEY":         "GOOG",
    "SLACK_BOT_TOKEN":        "SLK",
    "SLACK_USER_TOKEN":       "SLK",
    "SLACK_APP_TOKEN":        "SLK",
    "SLACK_WEBHOOK":          "SLK",
    "STRIPE_SECRET_KEY":      "STR",
    "STRIPE_TEST_KEY":        "STR",
    "STRIPE_RESTRICTED":      "STR",
    "SENDGRID_API_KEY":       "SG",
    "TWILIO_ACCOUNT_SID":     "TWL",
    "NPM_TOKEN":              "NPM",
    "PYPI_TOKEN":             "PYPI",
    "SHOPIFY_TOKEN":          "SHPFY",
    "SHOPIFY_CUSTOM_TOKEN":   "SHPFY",
    "MAILCHIMP_API_KEY":      "MC",
    "MAILGUN_API_KEY":        "MG",
    "DATABASE_URL":           "DB",
    "DATABASE_URL_REDIS":     "DB",
    "URL_USER":               "USER",
    "URL_PASS":               "PASS",
    "URL_HOST":               "HOST",
    "URL_DB":                 "DB",
    "PRIVATE_KEY":            "KEY",
    "JWT_TOKEN":              "JWT",
    "URL_WITH_CREDENTIALS":   "URL",
    "PRIVATE_IP":             "IP",
    "FIREBASE_URL":           "FB",
    "AZURE_STORAGE":          "AZ",
    "TERRAFORM_TOKEN":        "TF",
    "DOCKER_HUB_PAT":         "DOCK",
}

# Matches complete type-specific tokens, e.g. __DB1__, __AWS12__, __SHPFY3__
_TOKEN_RE = re.compile(r'__[A-Z]{2,6}\d+__')


def entity_abbrev(entity_type: str) -> str:
    return _ABBREV.get(entity_type, entity_type[:3].upper())


def register_abbrev(entity_type: str, abbrev: str) -> None:
    """Register a custom abbreviation for an entity type."""
    _ABBREV[entity_type] = abbrev.upper()


def make_token(entity_type: str, index: int) -> str:
    return f"__{entity_abbrev(entity_type)}{index}__"


def replace_tokens(text: str, mappings: dict[str, str]) -> str:
    # __ABBREV{n}__ style (URL components) — regex replace
    text = _TOKEN_RE.sub(lambda m: mappings.get(m.group(0), m.group(0)), text)
    # display_value style (all other types) — string replace
    for token, original in mappings.items():
        if not _TOKEN_RE.fullmatch(token):
            text = text.replace(token, original)
    return text
