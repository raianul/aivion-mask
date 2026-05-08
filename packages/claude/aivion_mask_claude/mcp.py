from . import __version__


def get_manifest(port: int) -> dict:
    return {
        "name": "aivion-mask",
        "version": __version__,
        "description": "Local credential masking proxy — secrets never reach your LLM",
        "proxy": {
            "url": f"http://127.0.0.1:{port}/v1",
            "protocol": "anthropic",
        },
        "health": f"http://127.0.0.1:{port}/health",
    }
