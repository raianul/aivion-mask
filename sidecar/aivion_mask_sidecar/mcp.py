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
