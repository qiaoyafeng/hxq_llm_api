"""
记忆管理模块
负责对话记忆的获取保存功能
"""

import time
import traceback
from typing import Optional, Dict
import urllib.parse

import aiohttp
from configs.base import settings
from logger import get_logger


logger = get_logger(__name__)


def get_mem_user_id(app_user_id: str, role_id: str) -> str:
    """
    生成mem0ai的用户ID，使用appUserId和roleId的组合

    Args:
        app_user_id: 应用用户ID
        role_id: 角色ID

    Returns:
        mem0ai用户ID
    """
    return f"{settings.HXQ_MEM_USER_ID_PREFIX}{app_user_id}_{role_id}"


async def add_memory(app_user_id: str, role_id: str, message: Dict[str, str]) -> bool:
    """
    保存记忆内容

    Args:
        app_user_id: 应用用户ID
        role_id: 角色ID
        messages: 对话消息列表，每条消息包含user或assistant的content字段，用于保存到好心情记忆功能
    Returns:
        是否保存成功
    """
    if not settings.HXQ_MEM_ENABLED:
        logger.debug("好心情记忆功能未启用")
        return False

    try:
        mem_user_id = get_mem_user_id(app_user_id, role_id)

        start_time = time.time()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.HXQ_MEM_API_KEY}",
        }
        payload = {
            "user_input": message.get("user", ""),
            "user_id": mem_user_id,
        }
        
        # 只有当 message 中包含 assistant 时，才添加 assistant_response 字段
        if "assistant" in message:
            payload["assistant_response"] = message.get("assistant", "")
        # 确保URL正确编码
        url = f"{settings.HXQ_MEM_API_URL}/api/memories/add"

        # 使用aiohttp进行异步请求
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                end_time = time.time()
                logger.info(f"好心情记忆功能保存记忆耗时: {end_time - start_time} 秒")

                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        logger.info(
                            f"成功保存记忆到好心情记忆功能，用户ID: {mem_user_id}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"保存记忆到好心情记忆功能失败，用户ID: {mem_user_id}, 错误信息: {result.get('msg')}"
                        )
                        return False
                else:
                    logger.warning(
                        f"保存记忆到好心情记忆功能失败，用户ID: {mem_user_id}, 状态码: {response.status}"
                    )
                    return False

    except Exception as e:
        logger.error(f"保存好心情记忆功能记忆失败: {e}")
        traceback.print_exc()
        return False


async def search_memory(
    app_user_id: str, role_id: str, query: Optional[str] = None, limit: int = 5
) -> Optional[str]:
    """
    从好心情记忆功能获取记忆内容

    Args:
        app_user_id: 应用用户ID
        role_id: 角色ID
        query: 查询内容，用于搜索相关记忆
        limit: 返回结果数量，默认5，最大20

    Returns:
        记忆内容字符串，如果失败或未启用则返回None
    """
    if not settings.HXQ_MEM_ENABLED:
        logger.debug("好心情记忆功能未启用")
        return None

    if not settings.HXQ_MEM_API_URL:
        logger.warning("好心情记忆功能配置不完整，请检查HXQ_MEM_API_URL")
        return None

    if not query:
        logger.debug("搜索记忆功能query为空")
        return None

    try:
        mem_user_id = get_mem_user_id(app_user_id, role_id)

        start_time = time.time()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.HXQ_MEM_API_KEY}",
        }

        params = {
            "query": query,
            "user_id": mem_user_id,
            "limit": min(limit, 20),
        }

        # 确保URL正确编码
        url = f"{settings.HXQ_MEM_API_URL}/api/memories/search"
        query_string = urllib.parse.urlencode(params, encoding="utf-8")
        full_url = f"{url}?{query_string}"

        # 使用aiohttp进行异步请求
        async with aiohttp.ClientSession() as session:
            async with session.get(
                full_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                end_time = time.time()
                logger.info(f"好心情记忆功能搜索记忆耗时: {end_time - start_time} 秒")

                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        memories = result.get("data", {}).get("memories", [])
                        if memories:
                            memory_texts = [
                                m.get("memory", "") for m in memories if m.get("memory")
                            ]
                            logger.info(
                                f"成功从好心情记忆功能获取到 {len(memory_texts)} 条记忆"
                            )
                            return "\n".join(memory_texts)
                        else:
                            logger.debug(
                                f"好心情记忆功能未找到相关记忆，query: {query}"
                            )
                            return None
                    else:
                        logger.warning(
                            f"搜索好心情记忆功能失败，错误信息: {result.get('msg')}"
                        )
                        return None
                else:
                    logger.warning(f"搜索好心情记忆功能失败，状态码: {response.status}")
                    return None

    except Exception as e:
        logger.error(f"搜索好心情记忆功能失败: {e}")
        traceback.print_exc()
        return None
