"""
HXQ LLM API 服务启动入口
"""
import uvicorn

from api.app import create_app
from configs.base import settings


app = create_app()


if __name__ == "__main__":
    host = settings.HOST
    port = settings.PORT
    print(f"Starting HXQ LLM API server...")
    print(f"Visit http://{host}:{port}/docs for API document.")
    uvicorn.run(app, host=host, port=port)
