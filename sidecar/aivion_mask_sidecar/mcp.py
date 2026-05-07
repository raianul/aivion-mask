def get_manifest(port: int) -> dict:
    return {
        "name": "aivion-mask",
        "version": "0.1.0",
        "description": "Local credential masking proxy — secrets never reach your LLM",
        "proxy": {
            "url": f"http://127.0.0.1:{port}/v1",
            "protocol": "openai",
        },
        "health": f"http://127.0.0.1:{port}/health",
    }
