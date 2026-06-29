"""在线心理咨询师对话模块。

通过 OpenAI 兼容协议调用第三方模型，向前端进行 SSE 流式输出。
"""
import json
from typing import AsyncGenerator

import httpx

from configs.base import settings
from logger import get_logger
from .protocol import OnlineChatRequest


logger = get_logger(__name__)


def _build_payload(request: OnlineChatRequest) -> dict:
    """构造发往 OpenAI 兼容服务的请求体。"""
    messages = [m.model_dump() for m in request.messages]
    # 若调用方未指定 system 提示，则注入心理咨询师默认人设
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(
            0,
            {"role": "system", "content": settings.QWEN_SYSTEM_PROMPT},
        )
    return {
        "model": request.model or settings.QWEN_MODEL_NAME,
        "messages": messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stream": True,
    }


async def stream_online_chat(request: OnlineChatRequest) -> AsyncGenerator[str, None]:
    """以 SSE 形式流式转发第三方 OpenAI 兼容服务的响应。

    每个 yield 出去的字符串会被 sse-starlette 自动包装为 `data: <value>\n\n`。
    """
    url = settings.QWEN_API_URL.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if settings.QWEN_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QWEN_API_KEY}"

    payload = _build_payload(request)
    logger.info(f"online_chat request -> {url}, model={payload['model']}")

    try:
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err_bytes = await resp.aread()
                    err_text = err_bytes.decode("utf-8", errors="ignore")
                    logger.error(
                        f"qwen API error: status={resp.status_code}, body={err_text}"
                    )
                    yield json.dumps(
                        {"error": f"上游接口错误: {resp.status_code}"},
                        ensure_ascii=False,
                    )
                    yield "[DONE]"
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    # OpenAI 兼容协议的 SSE 数据行以 "data: " 开头
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    else:
                        data_str = line.strip()

                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        yield "[DONE]"
                        return

                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        finish_reason = choices[0].get("finish_reason")
                        if content:
                            yield json.dumps(
                                {"content": content}, ensure_ascii=False
                            )
                        if finish_reason:
                            yield "[DONE]"
                            return
                    except json.JSONDecodeError as e:
                        logger.warning(f"parse SSE line failed: {e}, line={data_str}")
                        continue
    except httpx.HTTPError as e:
        logger.error(f"stream_online_chat http error: {e}")
        yield json.dumps({"error": f"网络异常: {e}"}, ensure_ascii=False)
        yield "[DONE]"
    except Exception as e:
        logger.error(f"stream_online_chat unexpected error: {e}")
        yield json.dumps({"error": f"服务异常: {e}"}, ensure_ascii=False)
        yield "[DONE]"
