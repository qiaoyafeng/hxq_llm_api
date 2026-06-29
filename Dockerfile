FROM python:3.11.9-slim

RUN sed -i 's@deb.debian.org@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc procps vim && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /opt/hxq_llm_api

# 先复制依赖文件以利用 Docker 缓存
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制项目代码
COPY . /opt/hxq_llm_api

# 默认端口
ENV HOST=0.0.0.0
ENV PORT=32105
EXPOSE 32105

CMD ["uv", "run", "python", "main.py"]
