# 罗盘医药智能体 · 经营罗盘（云端发布版）

> 市场、竞争与经营态势分析平台 —— 一句话问遍「药品 · 库存 · 销售」

基于 **DeepAgents / LangGraph** 的多智能体问数助手：主智能体调三个子代理协作，
FastAPI + WebSocket 推流执行过程，Vue3 前端，内嵌 SQLite 样例库，
**单端口即可完整跑起来**，无需 MySQL / Redis 等外部服务。

**线上演示：** https://compass-pharma-cloud.app.workbuddy.host/

---

## 它做什么

用户用自然语言提问，罗盘自动拆解任务、调用合适的子代理、把过程和结果流式推回前端：

| 子代理 | 职责 | 依赖 |
|---|---|---|
| 数据库查询助手 | 把中文问题翻成只读 SQL，查药品 / 库存 / 销售 | 内嵌 `pharma.sqlite` |
| 网络搜索助手 | 查行业资讯、竞品动态、政策变化 | Tavily API |
| RAGFlow 助手 | 检索企业内部知识库 | RAGFlow SDK（云端已熔断降级） |

还能直接产出报告：说一句「生成补货建议报告」，罗盘会写出 Markdown / Word / PDF 落到
`output/<session>/`，前端「报告中心」可在线预览、打包下载、按格式筛选。

---

## 技术栈

- **智能体**：DeepAgents / LangGraph，主智能体 + 3 子代理
- **后端**：FastAPI + WebSocket（`/ws/{thread_id}` 推流）+ StaticFiles 挂载前端
- **前端**：Vue 3 + TypeScript + Vite，单文件组件 + scoped 样式
- **数据**：SQLite（`pharma.sqlite`，只读 URI 打开 + 表名白名单）
- **模型**：SiliconFlow `Qwen/Qwen3.6-35B-A3B`（OpenAI 兼容网关），可切阿里云百炼
- **依赖管理**：uv（`pyproject.toml` + `uv.lock`）

---

## 快速开始

```bash
# 1. 装依赖
uv sync                       # 或 pip install -r requirements.txt

# 2. 配密钥（.env 已被 gitignore，复制模板填真实值）
cp .env.example .env

# 3. 起服务（默认 8000，读 PORT 环境变量）
python start.py

# 也可以：
uvicorn api.server:app --host 0.0.0.0 --port 8020
```

打开 `http://127.0.0.1:8000` 即可。登录页是**演示实现**：
短信验证码不真发短信，点「获取验证码」后验证码会直接显示在页面上；
微信 / 支付宝扫码也是模拟的授权动效。

### 前端改动后要重新构建

```bash
cd ui
npm install
npm run build
# 构建产物在 ui/dist，覆盖到项目根级的 ui_dist/
cp -r dist/* ../ui_dist/
```

`api/server.py` 把根级 `ui_dist/` 挂载到 `/`，所以必须是**根级** `ui_dist`，不是 `ui/dist`。

---

## 目录结构

```
agent/      主智能体 + 三个子智能体（DeepAgents / LangGraph）
  main_agent.py      主智能体编排
  llm.py             模型客户端
  load_prompts.py    读 prompt/prompts.yml
  sub_agents/        db_agent / search_agent / ragflow_agent
api/        FastAPI 服务
  server.py          REST + WebSocket + 静态前端挂载
  monitor.py         WebSocket 连接管理器（事件定向推送）
  context.py         运行上下文
tools/      工具集（SQLite 查询 / 网络搜索 / RAGFlow / PDF / Markdown 生成）
prompt/     prompts.yml 提示词（含失败处理纪律）
ui/         Vue3 前端源码
ui_dist/    前端构建产物（服务端挂载到 /）
utils/      日志 / 路径 / 文档转换工具
output/     运行产物目录（每次会话一个 session_<uuid> 子目录）
start.py    云端启动入口（读 PORT、清代理变量）
```

---

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/task` | 提交问题，后台跑主智能体，立即返回 `thread_id` |
| WS | `/ws/{thread_id}` | 订阅执行事件（`session_created` / `tool_start` / `assistant_call` / `task_result` / `error`） |
| GET | `/api/files?path=` | 列出会话目录文件 |
| GET | `/api/download?path=` | 下载文件（限定项目目录内） |
| POST | `/api/upload` | 上传附件到 `upload/session_<thread_id>/` |
| GET | `/api/db/stats` | 三张表行数统计 |
| GET | `/api/db/tables` | 全部业务表 + 行数 |
| GET | `/api/db/table?name=&limit=` | 预览某张表（表名走 `sqlite_master` 白名单） |
| GET | `/api/reports` | 跨会话汇总 `output/` 全部产物 |
| POST | `/api/reports/zip` | 多选打包 zip 下载 |
| POST | `/api/reports/delete` | 删除选中文件 |
| GET | `/outputs/<...>` | 会话产物静态访问 |
| GET | `/` | Vue 前端（`ui_dist/`） |

---

## 界面

**登录页** —— 左侧金线罗盘 + 「经营罗盘」标题，右侧保留项目原有的
手机验证码 / 微信扫码 / 支付宝扫码三通道，配色统一为深绿 + 金。

**工作台** —— 左侧导航栏：

- 导航：对话工作台 / 数据快览 / 报告中心 / 使用指南
- 快捷操作：新对话、导出对话
- 最近报告：最新 3 个产物一键在线预览
- 数据库速览：实时行数 + 「查看数据明细 →」弹层（表切换 + 真实数据表格）
- 快捷提问：3 条常用问题一键发送
- 历史会话：内嵌列表，可恢复 / 单删 / 清空
- 连接状态 + 账号区（主题切换 / 退出登录）

**报告中心** —— 跨会话汇总所有产物：

- 概览统计：文件总数 / 会话数 / 当前筛选体积 / 已选中
- 三层筛选：文件名搜索 + 会话下拉 + 7 组格式 chips
  （全部 / Markdown / Word / PDF / 表格 / 图片 / 文本）
- 批量操作：全选当前、**打包下载 zip**（包内保留 `session_x/` 结构，重名自动加序号）
- 单条操作：在线预览 / 下载 / 删除
- 彩色后缀标签：MD / DOCX / PDF / CSV / JSON / XLSX / 图片 分色

---

## 安全机制

- **只读 SQL 白名单**：仅放行 SELECT / SHOW / DESC / EXPLAIN，拦截 18 个危险词，检测多语句
- **表名白名单**：`/api/db/table` 先查 `sqlite_master` 校验表名存在，非法表名返回 404
- **报告路径收敛**：`/api/reports/zip`、`/api/reports/delete` 的路径统一收敛到 `output/` 内，
  越界路径（如 `../../.env`、`C:/Windows/win.ini`）直接丢弃
- **RAGFlow 熔断器**：20s 超时 + 连续 2 次失败自动熔断降级
- **agent 超时保护**：默认 600s，`AGENT_TIMEOUT_SECONDS` 可调

---

## 说明

- `.env` 含 API 密钥，已被 `.gitignore` 忽略，**从不出现在仓库里**；
  首次运行请复制 `.env.example` 并填入自己的密钥
- 登录、短信、扫码均为演示实现，不接入真实网关
- 内嵌数据库是 10 条药品 / 30 条库存 / 20 条销售的样例数据，用于演示完整链路
- 换行统一为 LF（见 `.gitattributes`）
