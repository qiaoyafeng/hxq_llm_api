import time
from enum import Enum, unique
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal


@unique
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"
    TOOL = "tool"

@unique
class RoleForArchive(str, Enum):
    USER = "user"
    ASSISTANT = "model"


@unique
class Finish(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL = "tool_calls"


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: Literal["owner"] = "owner"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelCard] = []


class Function(BaseModel):
    name: str
    arguments: str


class FunctionDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]


class FunctionAvailable(BaseModel):
    type: Literal["function", "code_interpreter"] = "function"
    function: Optional[FunctionDefinition] = None


class FunctionCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: Function


class ImageURL(BaseModel):
    url: str


class MultimodalInputItem(BaseModel):
    type: Literal["text", "image_url"]
    text: Optional[str] = None
    image_url: Optional[ImageURL] = None


class ChatMessage(BaseModel):
    role: Role
    content: Optional[Union[str, List[MultimodalInputItem]]] = None
    tool_calls: Optional[List[FunctionCall]] = None


class ChatCompletionMessage(BaseModel):
    role: Optional[Role] = None
    content: Optional[str] = None
    tool_calls: Optional[List[FunctionCall]] = None


class ChatCompletionRequest(BaseModel):
    model: str = "hxq_glm-4-9b-chat"
    messages: List[ChatMessage]
    tools: Optional[List[FunctionAvailable]] = None
    do_sample: Optional[bool] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = 1.2
    n: int = 1
    max_tokens: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    purpose: str = None


class GetContextRequest(BaseModel):
    id: str
    appUserId: str
    sessionId: str = None
    pageNum: int = 0
    pageSize: int = 10


class SendChatRequest(BaseModel):
    appUserId: str
    roleId: str
    content: str
    extend: Optional[str] = None


class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatCompletionMessage
    finish_reason: Finish


class ChatCompletionStreamResponseChoice(BaseModel):
    index: int
    delta: ChatCompletionMessage
    finish_reason: Optional[Finish] = None


class ChatCompletionResponseUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: ChatCompletionResponseUsage


class ChatCompletionStreamResponse(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionStreamResponseChoice]


class GetConfigRequest(BaseModel):
    variable: str


class UpdateConfigRequest(GetConfigRequest):
    value: str = None
    set_by: str = None


class ChatForArchiveMessage(BaseModel):
    role: RoleForArchive
    content: str


class ChatForArchiveRequest(BaseModel):
    model: str = "hxq_glm-4-9b-chat"
    stream: bool = False
    max_tokens: Optional[int] = 1024
    dialogue: List[ChatForArchiveMessage]
    appUserId: str = None
    roleId: str = None


class CheckWatermarkRequest(BaseModel):
    content: str


class OnlineChatMessage(BaseModel):
    role: str
    content: str


class OnlineChatRequest(BaseModel):
    """在线心理咨询师对话请求（OpenAI 兼容协议）。"""
    messages: List[OnlineChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 2048
    stream: bool = True
