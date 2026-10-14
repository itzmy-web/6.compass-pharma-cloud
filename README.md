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
  components/        DataView / ReportCenter / GuideView / LoginGate
ui_dist/    前端构建产物（服务端挂载到 /）
demo/       演示产物模板（首次启动铺入 output/）
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

左侧导航的**四个入口各自是一个独立页面**（不再是弹层），深浅两套主题都可切换。

**对话工作台** —— 欢迎页 + 消息流 + 右侧「本次会话产物」面板：

- 欢迎页：金线罗盘 Hero、4 个指标卡、3 个装饰图表卡、4 条快捷提问胶囊
- 右侧产物面板：会话号 + 3 张统计卡（文件数 / 合计体积 / 历史累计）
  + 6 组格式筛选 chips + 文件行（类型标签 / 大小 / 时间 / 预览 / 下载）
  + 空态引导（3 条可点即问）
- 执行过程：断线重连提示、任务时间线、工具调用日志、打字机结果

**数据快览** —— 内嵌 `pharma.sqlite` 的只读浏览：

- 4 张统计卡 + 表切换标签（带行数）+ 表说明
- 关键词过滤、行数选择（10/20/50/100）、粘性表头数据网格
- **字段说明数据字典**（`drugs` 10 / `inventory` 8 / `sales_records` 9 个字段）
- 「这张表可以这样问」按表给示例问法，点一下直接发起提问
- 导出当前筛选结果为 CSV（带 BOM，Excel 直接打开不乱码）

**报告中心** —— 跨会话汇总所有产物：

- 4 张统计卡：产物数 / 合计体积 / 覆盖会话数 / 近 7 天新增
- 三层筛选：格式分组 chips + 会话下拉 + 文件名搜索
- 批量：全选当前 / 清空选择 / **打包下载 zip**（选中或全部，重名自动加序号）
- 单条：在线预览 / 下载 / 删除；彩色后缀标签（MD / DOCX / PDF / CSV / JSON / 图片分色）
- 右栏：产出类型分布条形图 + 「怎么让罗盘写报告」引导 + 文件落盘说明

**使用指南** —— 把「怎么用」讲清楚：

- 三步快速上手卡片（每张带跳转按钮）
- 能力矩阵：数据库查询 / 网络搜索 / 知识库检索 / 报告生成，每条带可点示例
- 场景问题库：库存管理 / 销售分析 / 药品档案 / 综合分析，4 组共 16 条
- 内嵌数据表速查、常见问题折叠面板、安全与边界、版本信息

---

## 演示数据

`demo/reports/` 预置 8 份样例产物，内容取自 `pharma.sqlite` 的**真实聚合结果**
（2025 年度销售分析、库存预警与补货建议、区域/销售单元汇总、药品主数据速查等），
服务首次启动时自动铺入 `output/`，让报告中心一打开就有内容。

- 同名文件不覆盖，你自己生成的内容优先
- 删除样例报告后重启不会「复活」（`output/.demo_seeded` 标记位已落盘）
- 想恢复出厂演示数据：删掉 `output/.demo_seeded` 再重启

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
- `demo/reports/` 的样例产物也是基于这份样例数据算出来的，数字自洽可核对
- 换行统一为 LF（见 `.gitattributes`）
