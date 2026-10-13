from agent.load_prompts import sub_agents_config
from tools.mysql_tools import list_sql_tables, get_table_data, execute_sql_query

# 数据库查询 subagent
# 三个工具说明：
#   - list_sql_tables    列出当前库所有表
#   - get_table_data     预览指定表前 100 行
#   - execute_sql_query  执行自定义 SQL（复杂筛选/联表/聚合）
db_sub_agent = {
    "name": sub_agents_config['db']['name'],
    "description": sub_agents_config['db']['description'],
    "tools": [list_sql_tables, get_table_data, execute_sql_query],
    "system_prompt": sub_agents_config['db']['system_prompt'],
}


if __name__ == "__main__":
    print(db_sub_agent.get("name"))
