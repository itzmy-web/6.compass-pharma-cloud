# [云端版] SQLite 内嵌数据库工具（原 MySQL 版保留在本地项目）
# 工具名/签名与 MySQL 版完全一致，agent 与 prompts 无需任何改动
import re
import sqlite3
from pathlib import Path

from langchain_core.tools import tool
from api.monitor import monitor
from utils.logger_utils import logger

DB_PATH = Path(__file__).parents[1] / 'pharma.sqlite'


def _conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    return conn


# ---------- SQL 只读白名单（与 MySQL 版同款） ----------
_READONLY_PREFIXES = ('select', 'show', 'desc', 'describe', 'explain')
_FORBIDDEN_KEYWORDS = (
    'drop', 'delete', 'update', 'insert', 'truncate', 'alter', 'create',
    'grant', 'revoke', 'replace', 'merge', 'call', 'rename', 'handler',
    'shutdown', 'kill', 'vacuum', 'attach', 'detach', 'pragma',
)
_MULTISTATEMENT_RE = re.compile(r';\s*\S')


def _check_readonly_sql(sql: str):
    s = re.sub(r'--[^\n]*', '', sql)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    s = s.strip().rstrip(';').strip()
    if not s:
        return '拦截：空SQL'
    low = s.lower()
    if not low.startswith(_READONLY_PREFIXES):
        return ('拦截：仅允许只读查询（SELECT/SHOW/DESC/EXPLAIN），'
                f'收到的语句以「{s[:40]}」开头')
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf'\b{kw}\b', low):
            return f'拦截：检测到禁止的关键词 {kw.upper()}，本工具只读'
    if _MULTISTATEMENT_RE.search(s + ';'):
        return '拦截：仅允许单条SQL语句'
    return None


def _translate_to_sqlite(sql: str) -> str:
    """把 MySQL 方言的只读语句翻译成 SQLite 等价形式"""
    s = sql.strip().rstrip(';').strip()
    low = s.lower()
    if low.startswith('show tables'):
        return ("SELECT name AS tables_in_pharma FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    if low.startswith('show '):  # show columns from x / show create table x
        m = re.search(r'from\s+([A-Za-z_][A-Za-z0-9_]*)', low)
        if m:
            return f"PRAGMA table_info({m.group(1)})"
    if low.startswith('desc') and re.match(r'^desc(ribe)?\s+', low):
        m = re.match(r'^desc(ribe)?\s+([A-Za-z_][A-Za-z0-9_]*)', low)
        if m:
            return f"PRAGMA table_info({m.group(2)})"
    return s


def _rows_to_table(cursor) -> str:
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    if not rows:
        return '(查询成功，无数据返回)'
    def fmt(v):
        return 'NULL' if v is None else str(v)
    head = ','.join(cols)
    body = '\n'.join(','.join(fmt(v) for v in row) for row in rows)
    return head + '\n' + body


@tool
def list_sql_tables() -> str:
    """
    查询当前库中有哪些可用表!
    :return: 可用表:1,2,3   /  没有可用
    """
    monitor.report_tool(tool_name='搜索表名工具')
    try:
        conn = _conn()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        names = [r[0] for r in cur.fetchall()]
        conn.close()
        return f'可用表:{",".join(names)}' if names else '没有可用表'
    except Exception as e:
        return '数据库连接失败: ' + str(e)


@tool
def get_table_data(table_name: str) -> str:
    """
    查询指定表名的数据,参数就是表名! 为了让助手理解表的结构!
    返回前100行，第一行为表头，逗号分隔。
    """
    monitor.report_tool(tool_name='搜索指定表名的数据工具', args={'table_name': table_name})
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table_name):
        return f'非法表名: {table_name}'
    try:
        conn = _conn()
        cur = conn.execute(f'SELECT * FROM {table_name} LIMIT 100')
        result = _rows_to_table(cur)
        conn.close()
        return result
    except Exception as e:
        return '数据库连接失败: ' + str(e)


@tool
def execute_sql_query(sql: str) -> str:
    """
    执行自定义SQL【只读】查询
    :param sql: 自定义SQL查询语句（仅允许 SELECT/SHOW/DESC/EXPLAIN 单条只读语句）
    :return: 查询数据 表格形式
    """
    monitor.report_tool(tool_name='执行自定义SQL查询工具', args={'sql': sql})
    reject = _check_readonly_sql(sql)
    if reject:
        logger.warning(f'[SQL防护] {reject} | 原SQL: {sql[:100]}')
        return f'{reject}。本工具仅支持只读查询，请改写为 SELECT 语句。'
    try:
        conn = _conn()
        cur = conn.execute(_translate_to_sqlite(sql))
        result = _rows_to_table(cur)
        conn.close()
        return result
    except Exception as e:
        return '查询执行失败: ' + str(e)

if __name__ == '__main__':
    print(list_sql_tables.invoke({}))
