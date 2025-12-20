"""Model list fetching utilities."""

import logging
import asyncio

import aiohttp

logger = logging.getLogger(__name__)

# Timeout settings
FETCH_TIMEOUT = 15  # seconds


async def fetch_openai_models(base_url: str, api_key: str, timeout: int = FETCH_TIMEOUT) -> list[str]:
    """Fetch model list from OpenAI-compatible API.

    Args:
        base_url: API base URL (e.g., https://api.openai.com/v1)
        api_key: API key for authentication
        timeout: Request timeout in seconds

    Returns:
        List of model IDs, sorted alphabetically
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    logger.info(f"[FetchModels] Fetching models from: {url}")
    logger.debug(f"[FetchModels] API Key: {api_key[:8]}..." if api_key else "[FetchModels] No API Key")

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            logger.debug(f"[FetchModels] Sending GET request with timeout={timeout}s...")
            async with session.get(url, headers=headers) as resp:
                logger.info(f"[FetchModels] Response status: {resp.status}")

                if resp.status == 200:
                    data = await resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    logger.info(f"[FetchModels] Found {len(models)} total models")

                    # Filter to likely chat models
                    chat_keywords = ["gpt", "chat", "claude", "llama", "qwen", "deepseek", "glm"]
                    chat_models = [
                        m for m in models
                        if any(kw in m.lower() for kw in chat_keywords)
                    ]

                    result = sorted(chat_models) if chat_models else sorted(models)
                    logger.info(f"[FetchModels] Returning {len(result)} models (filtered: {len(chat_models)})")
                    return result
                elif resp.status == 401:
                    logger.error(f"[FetchModels] Authentication failed (401): Invalid API key")
                    return []
                elif resp.status == 404:
                    logger.error(f"[FetchModels] Endpoint not found (404): {url}")
                    return []
                else:
                    body = await resp.text()
                    logger.error(f"[FetchModels] Failed with status {resp.status}: {body[:200]}")
                    return []

    except asyncio.TimeoutError:
        logger.error(f"[FetchModels] Request timed out after {timeout}s")
        return []
    except aiohttp.ClientConnectorError as e:
        logger.error(f"[FetchModels] Connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"[FetchModels] Unexpected error: {type(e).__name__}: {e}")
        return []
