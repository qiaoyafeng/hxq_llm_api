FROM python:3.13-slim

# apt 使用阿里云镜像源
RUN sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc procps vim curl && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# uv 使用阿里云 PyPI 镜像源
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /opt/hxq_llm_api

# 先复制依赖文件以利用 Docker 缓存
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制项目代码
COPY . /opt/hxq_llm_api


CMD ["uv", "run", "python", "main.py"]
