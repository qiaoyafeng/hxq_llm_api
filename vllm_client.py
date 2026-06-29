"""
VLLM API 客户端模块
通过 OpenAI 兼容协议调用 VLLM 部署的模型
"""
import json
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Sequence

import httpx

from configs.base import settings
from logger import get_logger


logger = get_logger(__name__)


@dataclass
class Response:
    """模型响应数据类，与原项目保持兼容"""
    response_text: str
    response_length: int
    prompt_length: int
    finish_reason: str  # "stop" or "length"


class VLLMClient:
    """VLLM OpenAI 兼容 API 客户端"""

    def __init__(self):
        self.api_url = settings.VLLM_API_URL.rstrip("/")
        self.api_key = settings.VLLM_API_KEY
        self.model_name = settings.VLLM_MODEL_NAME
        self.timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_messages(
        self,
        messages: Sequence[Dict[str, str]],
        system: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """构建消息列表，将 system prompt 插入首位"""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            result.append({"role": msg["role"], "content": msg.get("content", "")})
        return result

    async def chat(
        self,
        messages: Sequence[Dict[str, str]],
        system: Optional[str] = None,
        **input_kwargs,
    ) -> List[Response]:
        """
        非流式聊天接口

        Args:
            messages: 消息列表
            system: 系统提示词
            **input_kwargs: 额外参数 (temperature, top_p, max_new_tokens, repetition_penalty 等)

        Returns:
            Response 列表
        """
        url = f"{self.api_url}/chat/completions"
        built_messages = self._build_messages(messages, system)

        payload = {
            "model": self.model_name,
            "messages": built_messages,
            "stream": False,
        }

        # 透传生成参数
        temperature = input_kwargs.get("temperature")
        top_p = input_kwargs.get("top_p")
        max_new_tokens = input_kwargs.get("max_new_tokens")
        repetition_penalty = input_kwargs.get("repetition_penalty")
        n = input_kwargs.get("num_return_sequences", 1)
        stop = input_kwargs.get("stop")

        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_new_tokens is not None:
            payload["max_tokens"] = max_new_tokens
        if repetition_penalty is not None:
            payload["repetition_penalty"] = repetition_penalty
        if n and n > 1:
            payload["n"] = n
        if stop is not None:
            payload["stop"] = stop

        logger.info(f"VLLM chat request -> {url}, model={self.model_name}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)

                if resp.status_code != 200:
                    err_text = resp.text
                    logger.error(f"VLLM API error: status={resp.status_code}, body={err_text}")
                    raise Exception(f"VLLM API 调用失败: {resp.status_code} - {err_text}")

                data = resp.json()
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)

                results = []
                for choice in data.get("choices", []):
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    finish_reason = choice.get("finish_reason", "stop")
                    completion_tokens = usage.get("completion_tokens", len(content))

                    results.append(Response(
                        response_text=content,
                        response_length=completion_tokens,
                        prompt_length=prompt_tokens,
                        finish_reason=finish_reason,
                    ))

                return results

        except httpx.HTTPError as e:
            logger.error(f"VLLM chat http error: {e}")
            raise Exception(f"VLLM API 网络异常: {e}")

    async def stream_chat(
        self,
        messages: Sequence[Dict[str, str]],
        system: Optional[str] = None,
        **input_kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天接口

        Args:
            messages: 消息列表
            system: 系统提示词
            **input_kwargs: 额外参数

        Yields:
            逐个 token 的文本内容
        """
        url = f"{self.api_url}/chat/completions"
        built_messages = self._build_messages(messages, system)

        payload = {
            "model": self.model_name,
            "messages": built_messages,
            "stream": True,
        }

        # 透传生成参数
        temperature = input_kwargs.get("temperature")
        top_p = input_kwargs.get("top_p")
        max_new_tokens = input_kwargs.get("max_new_tokens")
        repetition_penalty = input_kwargs.get("repetition_penalty")
        stop = input_kwargs.get("stop")

        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_new_tokens is not None:
            payload["max_tokens"] = max_new_tokens
        if repetition_penalty is not None:
            payload["repetition_penalty"] = repetition_penalty
        if stop is not None:
            payload["stop"] = stop

        logger.info(f"VLLM stream_chat request -> {url}, model={self.model_name}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=self._get_headers(), json=payload) as resp:
                    if resp.status_code != 200:
                        err_bytes = await resp.aread()
                        err_text = err_bytes.decode("utf-8", errors="ignore")
                        logger.error(f"VLLM stream API error: status={resp.status_code}, body={err_text}")
                        raise Exception(f"VLLM API 流式调用失败: {resp.status_code}")

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                        else:
                            data_str = line.strip()

                        if not data_str:
                            continue
                        if data_str == "[DONE]":
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
                                yield content
                            if finish_reason:
                                return
                        except json.JSONDecodeError as e:
                            logger.warning(f"parse SSE line failed: {e}, line={data_str}")
                            continue

        except httpx.HTTPError as e:
            logger.error(f"VLLM stream_chat http error: {e}")
            raise Exception(f"VLLM API 流式网络异常: {e}")


# 全局客户端实例
vllm_client = VLLMClient()
