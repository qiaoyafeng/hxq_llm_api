"""
FastAPI 应用主模块
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
import time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from typing_extensions import Annotated
from sse_starlette import EventSourceResponse

from api import config
from api.common import (
    build_resp,
    SUCCESS_CODE,
    SUICIDE_KEYWORDS,
    SUICIDE_MESSAGE,
    SENSITIVE_MESSAGE,
    remove_notes,
    AI_RECOMMEND_DOCTOR_KEYWORDS,
    AI_RECOMMEND_DOCTOR_MESSAGE,
    AI_RECOMMEND_DOCTOR_TAGS,
    AI_RECOMMEND_DOCTOR_ACTIVE,
    HXQ_SEAN_ROLE_ID,
    AI_RECOMMEND_DOCTOR_TAG_1,
    AI_RECOMMEND_DOCTOR_TAGS_MESSAGES,
    AI_RECOMMEND_DOCTOR_TAG_2,
    AI_RECOMMEND_DOCTOR_TAG_3,
    AI_RECOMMEND_DOCTOR_INACTIVE,
    safe_int,
    HXQ_SEAN_ROLE_TYPE,
    DEFAULT_MESSAGE,
    encode_zero_width,
    get_watermark,
    decode_zero_width,
    ENTERPRISE_CODE,
)
from api.memory import add_memory, search_memory
from configs.base import settings
from logger import get_logger
from api.chat import (
    create_chat_completion_response,
    create_stream_chat_completion_response,
    get_contexts,
    add_context,
    create_stream_chat_completion_response_for_archive,
    is_contains_sensitive_words,
    enhanced_recommend_doctor_intent_detection,
)
from api.protocol import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelCard,
    ModelList,
    SendChatRequest,
    GetContextRequest,
    ChatMessage,
    UpdateConfigRequest,
    GetConfigRequest,
    ChatForArchiveRequest,
    CheckWatermarkRequest,
    OnlineChatRequest,
)
from api.online_chat import stream_online_chat


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: "FastAPI"):
    yield


def create_app() -> "FastAPI":
    docs_enabled = settings.ENV != "prod"
    app = FastAPI(
        lifespan=lifespan,
        title="HXQ LLM API",
        summary="HXQ LLM API",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 静态文件（如果存在）
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    if os.path.isdir(static_dir):
        from starlette.staticfiles import StaticFiles
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    api_key = settings.API_KEY
    security = HTTPBearer(auto_error=False)

    async def verify_api_key(
        auth: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
    ):
        if api_key and (auth is None or auth.credentials != api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key."
            )

    if docs_enabled:
        @app.get("/docs", include_in_schema=False)
        async def custom_swagger_ui_html():
            from fastapi.openapi.docs import get_swagger_ui_html
            return get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=app.title + " - Swagger UI",
            )

    @app.get("/chat")
    async def chat_page():
        """聊天页面"""
        from fastapi.responses import FileResponse
        chat_html = os.path.join(static_dir, "chat.html")
        if os.path.isfile(chat_html):
            return FileResponse(chat_html)
        return {"message": "chat page not available"}

    @app.get("/chat_online")
    async def chat_online_page():
        """在线心理咨询师对话页面"""
        from fastapi.responses import FileResponse
        chat_online_html = os.path.join(static_dir, "chat_online.html")
        if os.path.isfile(chat_online_html):
            return FileResponse(chat_online_html)
        return {"message": "chat_online page not available"}

    @app.post(
        "/apis/chat/onlineStream",
        dependencies=[Depends(verify_api_key)],
    )
    async def online_stream_chat(request: OnlineChatRequest):
        """心理咨询师对话 - 通过 OpenAI 兼容协议调用第三方模型并以 SSE 流式返回"""
        generator = stream_online_chat(request)
        return EventSourceResponse(generator, media_type="text/event-stream")

    @app.get("/server_check")
    async def server_check():
        """server check."""
        return build_resp(SUCCESS_CODE, {})

    @app.get(
        "/v1/models",
        response_model=ModelList,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def list_models():
        model_card = ModelCard(id=settings.VLLM_MODEL_NAME)
        return ModelList(data=[model_card])

    @app.post(
        "/v1/chat/completions",
        response_model=ChatCompletionResponse,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def create_chat_completion(request: ChatCompletionRequest):
        if request.stream:
            generate = create_stream_chat_completion_response(request)
            return EventSourceResponse(generate, media_type="text/event-stream")
        else:
            return await create_chat_completion_response(request)

    @app.post(
        "/apis/chat/getContext",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def get_context(request: GetContextRequest):
        contexts = await get_contexts(request)
        return build_resp(SUCCESS_CODE, contexts)

    @app.post(
        "/apis/chat/sendChat",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def send_chat(request: SendChatRequest):
        start_time = time.time()

        if request.extend:
            try:
                req_extend = json.loads(request.extend)
            except Exception as e:
                logger.error(f"send_chat : request.extend: {request.extend},  error: {e} ")
                req_extend = {}
        else:
            req_extend = {}

        if req_extend and req_extend.get("roleType", None) == 1:
            request.roleId = str(HXQ_SEAN_ROLE_ID)

        # === 记忆功能：获取历史记忆 ===
        memory_content = None
        if settings.HXQ_MEM_ENABLED:
            memory_content = await search_memory(request.appUserId, request.roleId, request.content)
        else:
            logger.info(f"记忆功能已禁用，用户ID: {request.appUserId}, 角色ID: {request.roleId}")

        contexts = await get_contexts(
            GetContextRequest(id=request.roleId, appUserId=request.appUserId)
        )
        res_extend = {}
        messages = []

        # 如果有记忆内容，将其添加到对话开头
        if memory_content:
            memory_message = ChatMessage(
                role="system",
                content=f"\n\n以下是用户的历史记忆信息，作为参考：\n{memory_content}"
            )
            messages.append(memory_message)

        for context in contexts:
            if not context["del_status"]:
                role = context["role"]
                content = context["content"] if context["content"] else ""
                chat_message = ChatMessage(role=role, content=content)
                messages.append(chat_message)

        messages.append(ChatMessage(role="user", content=request.content))

        is_recommend_doctor = await enhanced_recommend_doctor_intent_detection(request.content)
        logger.info(f"is_recommend_doctor: {is_recommend_doctor}")

        if any(keyword in request.content for keyword in SUICIDE_KEYWORDS):
            assistant_content = SUICIDE_MESSAGE
            response_created_ts = int(datetime.now().timestamp())
            response_id = response_created_ts
        elif req_extend and not safe_int(req_extend.get("btnType", None)) and is_recommend_doctor:
            assistant_content = AI_RECOMMEND_DOCTOR_MESSAGE
            response_created_ts = int(datetime.now().timestamp())
            response_id = response_created_ts
            res_extend["ai_recommend_doctor_info"] = {
                "activated_state": AI_RECOMMEND_DOCTOR_ACTIVE,
                "ai_recommend_doctor_tags": AI_RECOMMEND_DOCTOR_TAGS,
            }
        elif req_extend and safe_int(req_extend.get("btnType", None)) == AI_RECOMMEND_DOCTOR_TAG_1:
            selected_tag = safe_int(req_extend.get("btnType", None))
            assistant_content = AI_RECOMMEND_DOCTOR_TAGS_MESSAGES[AI_RECOMMEND_DOCTOR_TAG_1]
            response_created_ts = int(datetime.now().timestamp())
            response_id = response_created_ts
            res_extend["ai_recommend_doctor_info"] = {
                "activated_state": AI_RECOMMEND_DOCTOR_INACTIVE,
                "ai_recommend_doctor_tags": AI_RECOMMEND_DOCTOR_TAGS,
                "selected_tag": selected_tag,
            }
        else:
            chat_completion_request = ChatCompletionRequest(
                model=settings.VLLM_MODEL_NAME, messages=messages
            )
            logger.info(f"chat_completion_request: {chat_completion_request}")
            try:
                chat_start_time = time.time()
                chat_completion_response = await create_chat_completion_response(
                    chat_completion_request, request.roleId
                )
                chat_end_time = time.time()
                logger.info(f"chat_completion_response cost time: {chat_end_time - chat_start_time}")
                logger.info(f"chat_completion_response: {chat_completion_response}")
                assistant_content = remove_notes(
                    chat_completion_response.choices[0].message.content
                )
                response_id = chat_completion_response.id
                response_created_ts = chat_completion_response.created
            except Exception as e:
                logger.info(f"chat_completion_request Exception: {e}")
                assistant_content = SENSITIVE_MESSAGE
                response_created_ts = int(datetime.now().timestamp())
                response_id = response_created_ts

        # 保存上下文
        add_context_start_time = time.time()
        user_message_info = {
            "user_id": request.appUserId,
            "role_id": request.roleId,
            "role": "user",
            "content": request.content,
        }
        await add_context(user_message_info)
        assistant_message_info = {
            "user_id": request.appUserId,
            "role_id": request.roleId,
            "role": "assistant",
            "content": assistant_content if assistant_content else DEFAULT_MESSAGE,
        }
        await add_context(assistant_message_info)
        add_context_end_time = time.time()
        logger.info(f"add_context cost time: {add_context_end_time - add_context_start_time}")

        # 记忆功能：更新记忆
        if settings.HXQ_MEM_ENABLED:
            mem_message = {"user": request.content}
            try:
                asyncio.create_task(
                    add_memory(request.appUserId, request.roleId, mem_message)
                )
                logger.info(f"已启动后台任务更新记忆，appUserId: {request.appUserId}, roleId: {request.roleId}")
            except Exception as e:
                logger.warning(f"启动记忆更新任务失败，但不影响主流程: {e}")

        content = assistant_content if assistant_content else DEFAULT_MESSAGE
        if settings.IS_ENABLE_WATERMARK:
            content = encode_zero_width(content, get_watermark())

        res_data = {
            "id": response_id,
            "roleId": request.roleId,
            "userId": request.appUserId,
            "content": content,
            "extend": res_extend,
            "tsGen": response_created_ts,
            "createTime": datetime.fromtimestamp(response_created_ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "appUserId": request.appUserId,
        }
        end_time = time.time()
        logger.info(f"send_chat cost time: {end_time - start_time}")
        return build_resp(SUCCESS_CODE, res_data)

    # 用于H5备案使用接口，有拦截词
    @app.post(
        "/apis/chat/sendChatForArchive",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def send_chat_for_archive(request: SendChatRequest):
        contexts = await get_contexts(
            GetContextRequest(id=request.roleId, appUserId=request.appUserId)
        )
        messages = []
        for context in contexts:
            role = context["role"]
            content = context["content"]
            chat_message = ChatMessage(role=role, content=content)
            messages.append(chat_message)
        messages.append(ChatMessage(role="user", content=request.content))

        if any(keyword in request.content for keyword in SUICIDE_KEYWORDS):
            assistant_content = SUICIDE_MESSAGE
            response_created_ts = int(datetime.now().timestamp())
            response_id = response_created_ts
        elif settings.IS_ENABLE_SENSITIVE_WORDS and is_contains_sensitive_words(
            request.content
        ):
            assistant_content = SENSITIVE_MESSAGE
            response_created_ts = int(datetime.now().timestamp())
            response_id = response_created_ts
        else:
            chat_completion_request = ChatCompletionRequest(
                model=settings.VLLM_MODEL_NAME, messages=messages
            )
            logger.info(f"chat_completion_request: {chat_completion_request}")
            try:
                chat_completion_response = await create_chat_completion_response(
                    chat_completion_request, request.roleId
                )
                logger.info(f"chat_completion_response: {chat_completion_response}")
                assistant_content = chat_completion_response.choices[0].message.content
                response_id = chat_completion_response.id
                response_created_ts = chat_completion_response.created
            except Exception as e:
                logger.info(f"chat_completion_request Exception: {e}")
                assistant_content = SENSITIVE_MESSAGE
                response_created_ts = int(datetime.now().timestamp())
                response_id = response_created_ts

        user_message_info = {
            "user_id": request.appUserId,
            "role_id": request.roleId,
            "role": "user",
            "content": request.content,
        }
        await add_context(user_message_info)
        assistant_message_info = {
            "user_id": request.appUserId,
            "role_id": request.roleId,
            "role": "assistant",
            "content": assistant_content,
        }
        await add_context(assistant_message_info)

        if settings.IS_ENABLE_WATERMARK:
            assistant_content = encode_zero_width(assistant_content, get_watermark())

        res_data = {
            "id": response_id,
            "roleId": request.roleId,
            "userId": request.appUserId,
            "content": assistant_content,
            "tsGen": response_created_ts,
            "createTime": datetime.fromtimestamp(response_created_ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "appUserId": request.appUserId,
        }
        return build_resp(SUCCESS_CODE, res_data)

    @app.get(
        "/apis/get_config/",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def get_config_api(variable: str):
        variable_config = ""
        request: GetConfigRequest = GetConfigRequest(variable=variable)
        variable_configs = await config.get_config(request)
        if variable_configs:
            variable_config = variable_configs[0]["value"]
        return build_resp(SUCCESS_CODE, {request.variable: variable_config})

    @app.post(
        "/apis/update_config/",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_api_key)],
    )
    async def update_config(request: UpdateConfigRequest):
        await config.update_config(request)
        return build_resp(SUCCESS_CODE, {request.variable: request.value})

    async def verify_api_key_archive(
        auth: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
    ):
        api_key_archive = "10069a3f0bd7505341d762be5099f9f3"
        logger.info(f"verify_api_key_archive auth received: {auth}")
        if api_key_archive and (auth is None or auth.credentials != api_key_archive):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key."
            )

    # 用于备案使用接口
    @app.post(
        "/api/chat",
        status_code=status.HTTP_200_OK,
    )
    async def chat_for_archive(request: ChatForArchiveRequest, http_request: Request):
        logger.info(f"/api/chat headers: {dict(http_request.headers)}")
        logger.info(f"/api/chat Authorization: {http_request.headers.get('authorization')}")
        authorization = http_request.headers.get("authorization", "")
        api_key_archive = "10069a3f0bd7505341d762be5099f9f3"
        # 支持 Bearer <token> 和直接传 <token> 两种方式
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        if token != api_key_archive:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key."
            )

        request.appUserId = "archive_0001"
        request.roleId = "630020"

        contexts = request.dialogue
        user_content = ""
        messages = []
        choices = []
        for context in contexts:
            role = context.role
            if role == "model":
                role = "assistant"
            else:
                role = "user"
                user_content = context.content
            content = context.content
            chat_message = ChatMessage(role=role, content=content)
            messages.append(chat_message)

        chat_completion_request = ChatCompletionRequest(
            model=settings.VLLM_MODEL_NAME, messages=messages, stream=request.stream
        )
        logger.info(f"chat_completion_request: {chat_completion_request}")

        user_message_info = {
            "user_id": request.appUserId,
            "role_id": request.roleId,
            "role": "user",
            "content": user_content,
        }
        await add_context(user_message_info)

        if settings.IS_ENABLE_SENSITIVE_WORDS and is_contains_sensitive_words(
            user_content
        ):
            assistant_content = SENSITIVE_MESSAGE
            assistant_message_info = {
                "user_id": request.appUserId,
                "role_id": request.roleId,
                "role": "assistant",
                "content": assistant_content,
            }
            await add_context(assistant_message_info)
            resp = {
                "code": 200,
                "message": "success",
                "content": assistant_content,
                "choices": choices,
                "status": "success",
                "reason": "",
            }
            return resp

        if request.stream:
            generate = create_stream_chat_completion_response_for_archive(
                chat_completion_request
            )
            return EventSourceResponse(generate, media_type="text/event-stream")
        else:
            chat_completion_response = await create_chat_completion_response(
                chat_completion_request, request.roleId
            )
            logger.info(f"chat_completion_response: {chat_completion_response}")
            assistant_content = (
                chat_completion_response.choices[0]
                .message.content.replace("\n", "")
                .replace("\r", "")
            )
            if not assistant_content:
                assistant_content = SENSITIVE_MESSAGE
            assistant_message_info = {
                "user_id": request.appUserId,
                "role_id": request.roleId,
                "role": "assistant",
                "content": assistant_content,
            }
            await add_context(assistant_message_info)
            if settings.IS_ENABLE_WATERMARK:
                assistant_content = encode_zero_width(assistant_content, get_watermark())
            resp = {
                "code": 200,
                "message": "success",
                "content": assistant_content,
                "choices": choices,
                "status": "success",
                "reason": "",
            }
            return resp

    @app.post(
        "/apis/check_watermark",
        status_code=status.HTTP_200_OK,
    )
    async def check_watermark(request: CheckWatermarkRequest):
        watermark = decode_zero_width(request.content)
        has_watermark = False
        if ENTERPRISE_CODE in watermark:
            has_watermark = True
        return build_resp(SUCCESS_CODE, {"has_watermark": has_watermark, "watermark": watermark})

    return app
