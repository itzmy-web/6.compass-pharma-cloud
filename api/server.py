# [核心] FastAPI 服务端：把 Vue 前端和主智能体连起来
# 2026-10-11 补齐（zip 里缺失，协议按 ui/src/App.vue 逆向）：
#   POST /api/task        提交问题，后台跑 run_deep_agent
#   WS   /ws/{thread_id}  推送 monitor 事件（session_created/tool_start/assistant_call/task_result/error）
#   GET  /api/files       列出会话目录文件
#   GET  /api/download    下载会话文件（限定项目目录内）
#   POST /api/upload      上传文件到 upload/session_<thread_id>/（agent 开始时会自动拷贝到会话目录）
#   /outputs/<...>        会话产物的静态访问
#   /                     Vue 前端构建产物（ui_dist/）
import asyncio
import io
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent.main_agent import run_deep_agent
from api.monitor import manager

PROJECT_DIR = Path(__file__).parents[1].resolve()
OUTPUT_DIR = PROJECT_DIR / 'output'
UPLOAD_DIR = PROJECT_DIR / 'upload'
DEMO_DIR = PROJECT_DIR / 'demo' / 'reports'


def _seed_demo_reports():
    """首次启动时把 demo/reports 下的样例产物铺进 output/，让报告中心不空着。

    只在 output/ 里没有 .demo_seeded 标记时执行一次：
    - 已存在的同名文件绝不覆盖（用户自己生成的内容优先）
    - 用户删掉样例报告后重启不会「复活」（标记位已落盘）
    """
    marker = OUTPUT_DIR / '.demo_seeded'
    if marker.exists() or not DEMO_DIR.exists():
        return
    copied = 0
    for src in DEMO_DIR.rglob('*'):
        if not src.is_file():
            continue
        dst = OUTPUT_DIR / src.relative_to(DEMO_DIR)
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    marker.write_text('seeded', encoding='utf-8')
    print(f'[demo] 已铺入 {copied} 个样例产物到 output/')


@asynccontextmanager
async def lifespan(app):
    # 把事件循环绑给 WebSocket 管理器，monitor 才能定向推送
    manager.set_loop(asyncio.get_running_loop())
    OUTPUT_DIR.mkdir(exist_ok=True)
    _seed_demo_reports()
    yield

app = FastAPI(title='航策向标 - deep_agent_search', lifespan=lifespan)


@app.post('/api/task')
async def create_task(payload: dict):
    """提交问题，后台执行主智能体。前端立即拿到 thread_id 用于订阅 WS。"""
    query = (payload.get('query') or '').strip()
    if not query:
        return JSONResponse({'error': 'query 不能为空'}, status_code=400)
    thread_id = payload.get('thread_id') or f"web_{uuid.uuid4().hex[:8]}"
    asyncio.create_task(run_deep_agent(query=query, thread_id=thread_id))
    return {'thread_id': thread_id}


@app.websocket('/ws/{thread_id}')
async def ws_endpoint(websocket: WebSocket, thread_id: str):
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == 'ping':
                await websocket.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception:
        manager.disconnect(websocket, thread_id)


@app.get('/api/db/stats')
async def db_stats():
    """左侧栏「数据库速览」：内嵌 SQLite 三张表的行数统计（只读）。"""
    import sqlite3
    db_path = PROJECT_DIR / 'pharma.sqlite'
    if not db_path.exists():
        return {'drugs': 0, 'inventory': 0, 'sales_records': 0}
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        out = {}
        for table in ('drugs', 'inventory', 'sales_records'):
            try:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                out[table] = cur.fetchone()[0]
            except sqlite3.Error:
                out[table] = 0
        con.close()
        return out
    except Exception:
        return {'drugs': 0, 'inventory': 0, 'sales_records': 0}


@app.get('/api/db/tables')
async def db_tables():
    """左侧栏「数据快览」：列出内嵌 SQLite 全部业务表与行数（只读）。"""
    import sqlite3
    db_path = PROJECT_DIR / 'pharma.sqlite'
    if not db_path.exists():
        return {'tables': []}
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        names = [r[0] for r in cur.fetchall()]
        tables = []
        for n in names:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{n}"')
                tables.append({'name': n, 'rows': cur.fetchone()[0]})
            except sqlite3.Error:
                tables.append({'name': n, 'rows': 0})
        con.close()
        return {'tables': tables}
    except Exception:
        return {'tables': []}


@app.get('/api/db/table')
async def db_table(name: str, limit: int = 20):
    """预览某张表的数据（只读，表名走 sqlite_master 白名单校验，防注入）。"""
    import sqlite3
    db_path = PROJECT_DIR / 'pharma.sqlite'
    if not db_path.exists():
        return {'error': 'database not found'}
    limit = max(1, min(int(limit), 100))
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        # 白名单校验：表名必须真实存在于库中
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,))
        if cur.fetchone() is None:
            con.close()
            return JSONResponse({'error': 'table not found'}, status_code=404)
        cur.execute(f'SELECT * FROM "{name}" LIMIT {limit}')
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [[('' if v is None else str(v)) for v in r] for r in cur.fetchall()]
        con.close()
        return {'name': name, 'columns': columns, 'rows': rows, 'limit': limit}
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get('/api/reports')
async def list_reports(ext: str = '', session: str = ''):
    """报告中心：跨会话汇总 output/ 下所有产物文件（可按后缀 / 会话过滤）。"""
    if not OUTPUT_DIR.exists():
        return {'files': [], 'total': 0, 'totalSize': 0, 'sessions': []}
    files = []
    sessions = {}
    for f in OUTPUT_DIR.rglob('*'):
        if not f.is_file() or f.name.startswith('.'):
            continue
        try:
            rel = f.relative_to(OUTPUT_DIR).as_posix()
        except ValueError:
            continue
        suffix = f.suffix.lower().lstrip('.')
        # 找所属会话目录（output/session_xxx/...）
        parts = rel.split('/')
        sess = parts[0] if len(parts) > 1 else '根目录'
        st = f.stat()
        files.append({
            'name': f.name,
            'path': str(f.resolve()),
            'rel': rel,
            'url': '/outputs/' + rel,
            'session': sess,
            'ext': suffix,
            'size': st.st_size,
            'mtime': st.st_mtime,
        })
        s = sessions.setdefault(sess, {'id': sess, 'count': 0, 'size': 0})
        s['count'] += 1
        s['size'] += st.st_size
    if ext:
        wanted = {x.strip().lower() for x in ext.split(',') if x.strip()}
        files = [x for x in files if x['ext'] in wanted]
    if session:
        files = [x for x in files if x['session'] == session]
    files.sort(key=lambda x: x['mtime'], reverse=True)
    # 会话列表始终基于全量统计（便于前端做筛选项）
    sess_list = sorted(sessions.values(), key=lambda s: s['id'])
    return {
        'files': files,
        'total': len(files),
        'totalSize': sum(x['size'] for x in files),
        'sessions': sess_list,
    }


def _safe_report_paths(raw) -> list[Path]:
    """把前端传来的路径收敛到 OUTPUT_DIR 内，越界直接丢弃。

    兼容三种写法：绝对路径、相对 OUTPUT_DIR（session_x/a.md）、相对项目根（output/session_x/a.md）。
    """
    out = []
    for item in raw or []:
        if not isinstance(item, str) or not item.strip():
            continue
        raw_path = Path(item)
        candidates = [raw_path] if raw_path.is_absolute() else [
            OUTPUT_DIR / raw_path,
            PROJECT_DIR / raw_path,
            raw_path,
        ]
        for p in candidates:
            try:
                rp = p.resolve()
                rp.relative_to(OUTPUT_DIR.resolve())
            except (ValueError, OSError):
                continue
            if rp.is_file():
                out.append(rp)
                break
    return out


@app.post('/api/reports/zip')
async def reports_zip(payload: dict):
    """报告中心：多选文件打包成 zip 一次性下载。"""
    paths = _safe_report_paths(payload.get('paths'))
    if not paths:
        return JSONResponse({'error': '没有可打包的文件'}, status_code=400)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for p in paths:
            arc = p.relative_to(OUTPUT_DIR.resolve()).as_posix()
            # 防止重名覆盖：同名自动加序号
            if arc in used:
                stem, dot, tail = arc.rpartition('.')
                n = 1
                while f'{stem}({n}){dot}{tail}' in used:
                    n += 1
                arc = f'{stem}({n}){dot}{tail}'
            used.add(arc)
            zf.write(p, arcname=arc)
    buf.seek(0)
    fname = f'reports_{uuid.uuid4().hex[:8]}.zip'
    return StreamingResponse(
        buf,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@app.post('/api/reports/delete')
async def reports_delete(payload: dict):
    """报告中心：删除选中文件（限定 OUTPUT_DIR 内）。"""
    paths = _safe_report_paths(payload.get('paths'))
    removed = []
    for p in paths:
        try:
            p.unlink()
            removed.append(p.relative_to(OUTPUT_DIR.resolve()).as_posix())
        except OSError:
            continue
    return {'removed': removed, 'count': len(removed)}


@app.get('/api/files')
async def list_files(path: str):
    """列出会话目录下的文件。安全约束：只允许 output 目录内。"""
    p = Path(path)
    try:
        p.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return JSONResponse({'error': 'forbidden'}, status_code=403)
    files = []
    if p.exists() and p.is_dir():
        for f in sorted(p.iterdir()):
            if f.is_file():
                st = f.stat()
                files.append({'name': f.name, 'path': str(f),
                              'size': st.st_size, 'mtime': st.st_mtime})
    return {'files': files}


@app.get('/api/download')
async def download(path: str):
    """下载文件。安全约束：只允许项目目录内。"""
    p = Path(path)
    try:
        p.resolve().relative_to(PROJECT_DIR.resolve())
    except ValueError:
        return JSONResponse({'error': 'forbidden'}, status_code=403)
    if p.exists() and p.is_file():
        return FileResponse(p, filename=p.name)
    return JSONResponse({'error': 'not found'}, status_code=404)


@app.post('/api/upload')
async def upload(thread_id: str = Form(...), files: list[UploadFile] = File(...)):
    """上传文件到 upload/session_<thread_id>/，agent 开始执行时会自动拷入会话目录。"""
    updir = UPLOAD_DIR / f'session_{thread_id}'
    updir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        dest = updir / Path(f.filename or 'unnamed').name
        with open(dest, 'wb') as w:
            w.write(await f.read())
        saved.append(dest.name)
    return {'saved': saved}


# 会话产物静态访问（前端拼 /outputs/<session_x>/文件名 直接打开）
OUTPUT_DIR.mkdir(exist_ok=True)
app.mount('/outputs', StaticFiles(directory=str(OUTPUT_DIR)), name='outputs')

# Vue 前端构建产物
UI_DIST = PROJECT_DIR / 'ui_dist'
if UI_DIST.exists():
    app.mount('/', StaticFiles(directory=str(UI_DIST), html=True), name='ui')


if __name__ == '__main__':
    import os
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', '8000')))
