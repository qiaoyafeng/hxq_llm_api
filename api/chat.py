"""
聊天处理模块
核心变更：将本地模型调用替换为 VLLM API 调用
"""
import json
import uuid
from typing import AsyncGenerator, Dict, List, Optional

from configs.base import settings
from db.mysql import query_sql, build_create, update_sql
from logger import get_logger
from vllm_client import vllm_client
from .common import (
    dictify,
    jsonify,
    default_sys_message,
    HXQ_DEFAULT_ROLE_ID,
    HXQ_ROLES,
    safe_int,
    AI_RECOMMEND_DOCTOR_KEYWORDS,
)
from .protocol import (
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionResponseUsage,
    ChatCompletionStreamResponse,
    ChatCompletionStreamResponseChoice,
    Finish,
    Role,
    GetContextRequest,
    ChatMessage,
    ChatCompletionRequest,
)


logger = get_logger(__name__)

ROLE_MAPPING = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "system",
    Role.FUNCTION: "function",
    Role.TOOL: "tool",
}


def _process_request(
    request: "ChatCompletionRequest",
) -> tuple:
    """处理请求，提取消息列表和系统提示"""
    logger.info(
        "==== request ====\n{}".format(
            json.dumps(dictify(request), indent=2, ensure_ascii=False)
        )
    )

    if len(request.messages) == 0:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid length"
        )

    if request.messages[0].role == Role.SYSTEM:
        system = request.messages.pop(0).content
    else:
        system = None

    input_messages = []
    for i, message in enumerate(request.messages):
        if isinstance(message.content, list):
            # 处理多模态输入，提取文本部分
            for input_item in message.content:
                if input_item.type == "text":
                    input_messages.append(
                        {"role": ROLE_MAPPING[message.role], "content": input_item.text}
                    )
        else:
            input_messages.append(
                {"role": ROLE_MAPPING[message.role], "content": message.content or ""}
            )

    return input_messages, system


def _create_stream_chat_completion_chunk(
    completion_id: str,
    model: str,
    delta: "ChatCompletionMessage",
    index: Optional[int] = 0,
    finish_reason: Optional["Finish"] = None,
) -> str:
    choice_data = ChatCompletionStreamResponseChoice(
        index=index, delta=delta, finish_reason=finish_reason
    )
    chunk = ChatCompletionStreamResponse(
        id=completion_id, model=model, choices=[choice_data]
    )
    return jsonify(chunk)


async def create_chat_completion_response(
    request: "ChatCompletionRequest",
    chat_role_id=HXQ_DEFAULT_ROLE_ID,
) -> "ChatCompletionResponse":
    """非流式聊天完成"""
    completion_id = "chatcmpl-{}".format(uuid.uuid4().hex)
    input_messages, system = _process_request(request)

    # 构建系统提示词
    role_name = HXQ_ROLES.get(safe_int(chat_role_id), HXQ_ROLES[HXQ_DEFAULT_ROLE_ID])
    default_hxq_sys_message = f"{default_sys_message.format(role_name=role_name)}"
    if system:
        system = default_hxq_sys_message + system
    else:
        system = default_hxq_sys_message

    logger.info(f"create_chat_completion_response system: {system[:100]}...")

    # 调用 VLLM API
    responses = await vllm_client.chat(
        input_messages,
        system,
        temperature=request.temperature,
        top_p=request.top_p,
        repetition_penalty=request.repetition_penalty,
        max_new_tokens=request.max_tokens,
        num_return_sequences=request.n,
        stop=request.stop,
    )

    prompt_length, response_length = 0, 0
    choices = []
    for i, response in enumerate(responses):
        response_message = ChatCompletionMessage(
            role=Role.ASSISTANT, content=response.response_text
        )
        finish_reason = (
            Finish.STOP if response.finish_reason == "stop" else Finish.LENGTH
        )

        choices.append(
            ChatCompletionResponseChoice(
                index=i, message=response_message, finish_reason=finish_reason
            )
        )
        prompt_length = response.prompt_length
        response_length += response.response_length

    usage = ChatCompletionResponseUsage(
        prompt_tokens=prompt_length,
        completion_tokens=response_length,
        total_tokens=prompt_length + response_length,
    )

    return ChatCompletionResponse(
        id=completion_id, model=request.model, choices=choices, usage=usage
    )


async def create_stream_chat_completion_response(
    request: "ChatCompletionRequest",
) -> AsyncGenerator[str, None]:
    """流式聊天完成（OpenAI 兼容格式）"""
    completion_id = "chatcmpl-{}".format(uuid.uuid4().hex)
    input_messages, system = _process_request(request)

    from fastapi import HTTPException, status
    if request.n > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot stream multiple responses.",
        )

    yield _create_stream_chat_completion_chunk(
        completion_id=completion_id,
        model=request.model,
        delta=ChatCompletionMessage(role=Role.ASSISTANT, content=""),
    )

    async for new_token in vllm_client.stream_chat(
        input_messages,
        system,
        temperature=request.temperature,
        top_p=request.top_p,
        max_new_tokens=request.max_tokens,
        stop=request.stop,
    ):
        if len(new_token) != 0:
            yield _create_stream_chat_completion_chunk(
                completion_id=completion_id,
                model=request.model,
                delta=ChatCompletionMessage(content=new_token),
            )

    yield _create_stream_chat_completion_chunk(
        completion_id=completion_id,
        model=request.model,
        delta=ChatCompletionMessage(),
        finish_reason=Finish.STOP,
    )
    yield "[DONE]"


async def create_stream_chat_completion_response_for_archive(
    request: "ChatCompletionRequest",
) -> AsyncGenerator[str, None]:
    """流式聊天完成（备案格式）"""
    completion_id = "chatcmpl-{}".format(uuid.uuid4().hex)
    input_messages, system = _process_request(request)

    from fastapi import HTTPException, status
    if request.n > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot stream multiple responses.",
        )

    choices = []
    async for new_token in vllm_client.stream_chat(
        input_messages,
        system,
        temperature=request.temperature,
        top_p=request.top_p,
        max_new_tokens=request.max_tokens,
        stop=request.stop,
    ):
        if len(new_token) != 0:
            stream_choice = {
                "delta": f"{new_token}",
                "finish_reason": "",
            }
            choices.append(new_token)
            yield json.dumps(
                {
                    "code": 200,
                    "message": "success",
                    "content": "",
                    "choices": [stream_choice],
                    "status": "success",
                    "reason": "",
                },
                ensure_ascii=False,
            )

    stream_stop_choice = {
        "delta": "",
        "finish_reason": "stop",
    }
    yield json.dumps(
        {
            "code": 200,
            "message": "success",
            "content": "",
            "choices": [stream_stop_choice],
            "status": "success",
            "reason": "",
        },
        ensure_ascii=False,
    )

    # 保存助手回复到上下文
    assistant_content = "".join(choices)
    assistant_message_info = {
        "user_id": "archive_0001",
        "role_id": "630020",
        "role": "assistant",
        "content": assistant_content,
    }
    await add_context(assistant_message_info)


async def get_contexts(request: GetContextRequest) -> List:
    """获取对话上下文"""
    sql = f"SELECT * FROM (SELECT id, user_id , role_id , role, content, del_status , create_time  FROM {settings.TABLE_CHAT_LOG} WHERE user_id = '{request.appUserId}' and role_id = '{request.id}' ORDER BY id DESC  LIMIT {request.pageNum}, {request.pageSize}) as temp order by temp.id;"
    logger.info(f"get_contexts SQL: {sql}")
    contexts = query_sql(sql)
    return contexts


async def add_context(info, table=settings.TABLE_CHAT_LOG):
    """保存对话上下文"""
    sql = build_create(info, table)
    logger.info(f"add_context SQL : {sql} ")
    update_sql(sql)


# 从文本文件中读取敏感词
def load_sensitive_words():
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = os.path.join(base_dir, "configs", "sensitive_words.txt")
    print(f"load_sensitive_words......")
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            sensitive_words = [line.strip().lower() for line in file if line.strip()]
    except FileNotFoundError:
        print(f"Warning: {filename} not found, using empty sensitive words list")
        sensitive_words = []
    return sensitive_words


keywords = load_sensitive_words()


def is_contains_sensitive_words(text: str):
    """检测文本是否包含敏感词"""
    return any(keyword in text.lower() for keyword in keywords)


def is_contains_recommend_doctor_words(text: str):
    """检测文本是否包含推荐医生关键词"""
    return any(keyword in text.lower() for keyword in AI_RECOMMEND_DOCTOR_KEYWORDS)


async def enhanced_recommend_doctor_intent_detection(text: str):
    """推荐咨询师或医生意图识别（仅关键词检测）"""
    return is_contains_recommend_doctor_words(text)
