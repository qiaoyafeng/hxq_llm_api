from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置"""

    ENV: str = "dev"
    ROOT_PATH: str = ""
    BASE_DOMAIN: str = "http://127.0.0.1:32105"
    HOST: str = "0.0.0.0"
    PORT: int = 32105
    API_KEY: str = ""

    # 数据库配置
    DB_IP: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "hxq_llm"
    DB_USERNAME: str = "root"
    DB_PASSWORD: str = "123456"

    # Table 名
    TABLE_CHAT_LOG: str = "chat_log"
    TABLE_SYS_CONFIG: str = "sys_config"

    # VLLM 模型配置
    VLLM_API_URL: str = "http://127.0.0.1:8000/v1"
    VLLM_API_KEY: str = ""
    VLLM_MODEL_NAME: str = "glm-4-9b-chat-int4"

    # 安全检查配置
    IS_ENABLE_SENSITIVE_WORDS: bool = True
    IS_ENABLE_WATERMARK: bool = True

    # hxq 记忆功能配置
    HXQ_MEM_ENABLED: bool = False
    HXQ_MEM_API_URL: str = ""
    HXQ_MEM_API_KEY: str = ""
    HXQ_MEM_USER_ID_PREFIX: str = "hxq_llm_"

    # 在线心理咨询师对话（OpenAI 兼容协议）
    QWEN_API_URL: str = "http://127.0.0.1:11434/v1"
    QWEN_API_KEY: str = ""
    QWEN_MODEL_NAME: str = "qwen3.6:35b"
    QWEN_SYSTEM_PROMPT: str = (
        "你是一名专业、富有同理心的心理咨询师。"
        "请使用温和、尊重、共情的语气与来访者交流，认真倾听其情绪与困扰，"
        "在合适时给予专业、可操作的建议；当涉及自伤、自杀或严重心理危机时，"
        "务必引导其寻求线下专业帮助或拨打心理援助热线。"
    )

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
