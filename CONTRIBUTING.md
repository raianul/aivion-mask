# Contributing to aivion-mask

Thanks for your interest in contributing.

---

## What lives here

This repo contains the open source components of aivion-mask:

| Path | What it is |
|---|---|
| `packages/core/` | Shared masking engine — patterns, session, tokens, streaming |
| `packages/claude/` | Anthropic Claude provider (`aivion-mask-claude`) |
| `packages/openai/` | OpenAI provider (`aivion-mask-openai`) |
| `extension/browser/` | Chrome/Firefox browser extension (scaffold) |

---

## Good first contributions

- **New credential patterns** — add regex patterns for types not yet covered in `packages/core/aivion_mask_core/masker.py`
- **Browser extension content scripts** — adapters for AI platforms not yet supported
- **False positive reports** — open an issue with the pattern triggering incorrectly

---

## How to contribute

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make your changes with tests
4. Open a pull request with a clear description of what and why

---

## Development setup

```bash
# Core
cd packages/core && pip install -e ".[dev]" && pytest

# Claude provider
cd packages/claude && pip install -e ".[dev]" && pytest

# OpenAI provider
cd packages/openai && pip install -e ".[dev]" && pytest
```

Or with uv workspace from the repo root:

```bash
uv sync && uv run pytest packages/core packages/claude packages/openai
```

---

## Adding a credential pattern

When adding a new pattern to `packages/core/aivion_mask_core/masker.py`:

- Include at least one positive and one negative test case in `packages/core/tests/test_masker.py`
- Use entropy filtering where appropriate to reduce false positives
- Document the pattern source (e.g. "GitHub token format per GitHub docs")

---

## Code style

- Python: `ruff` (config in each `pyproject.toml`)
- No external runtime dependencies in `packages/core/` — must work offline

---

## Reporting issues

Open a GitHub issue with:
- Which component (`core` / `claude` / `openai` / browser extension)
- What you expected vs what happened
- A minimal reproduction if possible

For false positives / false negatives: include the pattern (redact any real secrets) and the entity type.

---

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
