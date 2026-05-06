# Contributing to aivion-mask

Thanks for your interest in contributing.

---

## What lives here

This repo contains the open source components of aivion-mask:

- `extension/vscode/` — VS Code extension
- `extension/browser/` — Chrome/Firefox browser extension
- `sdk/python/` — Python SDK
- `sdk/typescript/` — TypeScript SDK
- `core/` — Shared masking logic and recognizer patterns

The server-side infrastructure (session store, audit trail, policy management) is not in this repo.

---

## Good first contributions

- **New recognizer patterns** — add regex patterns for credential types not yet covered in `core/recognizers/`
- **Browser extension content scripts** — adapters for AI platforms not yet supported
- **SDK improvements** — error handling, type safety, docs
- **False positive reports** — open an issue with the pattern that's triggering incorrectly

---

## How to contribute

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make your changes
4. Open a pull request with a clear description of what and why

---

## Recognizer patterns

When adding a new credential recognizer to `core/recognizers/`:

- Include at least one positive test case and one negative test case
- Use entropy filtering where appropriate to reduce false positives
- Document the pattern source (e.g. "GitHub token format per GitHub docs")
- Add it to the entity list in `core/recognizers/README.md`

---

## Code style

- TypeScript: ESLint + Prettier (config in each package)
- Python: ruff (config in `pyproject.toml`)
- No external runtime dependencies in `core/` — it must work offline

---

## Reporting issues

Open a GitHub issue with:
- Which component (VS Code extension / browser extension / SDK / core)
- What you expected vs what happened
- A minimal reproduction if possible

For false positives / false negatives in detection: include the pattern (redact any real secrets) and the entity type.

---

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
