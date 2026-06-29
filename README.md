# HXQ LLM API

基于 VLLM 的心理咨询大模型 API 服务。通过 OpenAI 兼容协议调用 VLLM 推理服务，提供心理咨询对话能力。

## 技术栈

- **框架**: FastAPI + Uvicorn
- **模型推理**: VLLM（通过 OpenAI 兼容 API 调用）
- **数据库**: MySQL（对话上下文与配置存储）
- **包管理**: uv
- **部署**: Docker Compose
- **Python**: >= 3.11

## 核心功能

| 功能 | 说明 |
|------|------|
| 心理咨询对话 | 基于 VLLM 部署的 GLM-4 模型，支持流式/非流式响应 |
| 在线咨询师对话 | 通过 OpenAI 兼容协议调用第三方模型（如 Qwen），SSE 流式输出 |
| 对话记忆 | 可选的长期记忆功能，跨会话记住用户信息 |
| 安全防护 | 敏感词过滤、自杀关键词拦截与危机干预引导 |
| 推荐医生 | 基于关键词检测的咨询师/医生推荐意图识别 |
| 水印系统 | 零宽字符水印嵌入与检测 |
| 上下文管理 | MySQL 存储对话历史，支持多角色对话 |

## 项目结构

```
├── api/                  # API 层
│   ├── app.py            # FastAPI 应用主模块（路由定义）
│   ├── chat.py           # 聊天处理模块（VLLM 调用）
│   ├── online_chat.py    # 在线咨询师对话（第三方模型）
│   ├── memory.py         # 记忆功能
│   ├── protocol.py       # 请求/响应数据模型
│   ├── config.py         # 配置管理接口
│   └── common.py         # 公共常量与工具函数
├── configs/
│   ├── base.py           # 全局配置（Pydantic Settings）
│   └── sensitive_words.txt  # 敏感词库
├── db/
│   └── mysql.py          # 数据库操作封装
├── static/               # 静态文件（聊天页面等）
├── vllm_client.py        # VLLM API 客户端
├── logger.py             # 日志配置
├── main.py               # 服务启动入口
├── docker-compose.yml    # Docker 编排
├── Dockerfile            # 容器构建
└── pyproject.toml        # 项目元数据与依赖
```

## 快速开始

### 环境准备

1. **安装 uv**（推荐）：

```bash
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **配置环境变量**：

```bash
cp .env_template .env
# 编辑 .env 文件，填写数据库、VLLM 地址等配置
```

### 本地开发

```bash
# 安装依赖
uv sync

# 启动服务
uv run python main.py
```

服务启动后访问 http://127.0.0.1:32105/docs 查看 API 文档。

### Docker 部署

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f hxq-llm-api

# 停止服务
docker-compose down
```

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `32105` | 监听端口 |
| `DB_IP` | `127.0.0.1` | MySQL 地址 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_NAME` | `hxq_llm` | 数据库名 |
| `DB_USERNAME` | `root` | 数据库用户名 |
| `DB_PASSWORD` | - | 数据库密码 |
| `VLLM_API_URL` | `http://127.0.0.1:8000/v1` | VLLM 服务地址 |
| `VLLM_API_KEY` | - | VLLM API Key（可选） |
| `VLLM_MODEL_NAME` | `glm-4-9b-chat-int4` | VLLM 模型名称 |
| `IS_ENABLE_SENSITIVE_WORDS` | `True` | 是否启用敏感词过滤 |
| `IS_ENABLE_WATERMARK` | `True` | 是否启用水印 |
| `HXQ_MEM_ENABLED` | `False` | 是否启用记忆功能 |
| `HXQ_MEM_API_URL` | - | 记忆服务地址 |
| `QWEN_API_URL` | - | 在线咨询师模型地址（OpenAI 兼容） |
| `QWEN_MODEL_NAME` | `Qwen3.6-35B-A3B` | 在线咨询师模型名称 |

## API 接口

### 标准 OpenAI 兼容接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/models` | 获取可用模型列表 |
| POST | `/v1/chat/completions` | 聊天补全（支持流式） |

### 业务接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/apis/chat/sendChat` | 发送对话（含记忆、安全检查） |
| POST | `/apis/chat/getContext` | 获取对话上下文 |
| POST | `/apis/chat/onlineStream` | 在线咨询师对话（SSE 流式） |
| GET | `/apis/get_config/` | 获取系统配置 |
| POST | `/apis/update_config/` | 更新系统配置 |
| POST | `/apis/check_watermark` | 检测水印 |
| GET | `/server_check` | 健康检查 |

### 页面

| 路径 | 说明 |
|------|------|
| `/chat` | 聊天页面 |
| `/chat_online` | 在线心理咨询师对话页面 |
| `/docs` | Swagger API 文档（非 prod 环境） |
