# 云端部署启动入口：读取部署平台注入的 PORT 环境变量
import os

# [本地调试] 清除继承的代理环境变量，避免 LLM API 请求被本地代理拦成 502
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)

import uvicorn

if __name__ == '__main__':
    from api.server import app

    uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', '8000')))
