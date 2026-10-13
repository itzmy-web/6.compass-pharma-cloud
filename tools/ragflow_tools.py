import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool
from api.monitor import monitor
from utils.logger_utils import logger
try:
    from ragflow_sdk import RAGFlow
    _RAGFLOW_SDK_AVAILABLE = True
except ImportError:
    RAGFlow = None
    _RAGFLOW_SDK_AVAILABLE = False

# [修复] 本模块自己加载 .env —— 原先依赖 agent.llm 先被 import 才有环境变量，
# 单独测试本模块时 RAGFLOW_API_URL 会是 None
load_dotenv(find_dotenv())

# [鲁棒性修复 2026-10-11] T4 测试发现：RAGFlow 服务不可达时，SDK 的 HTTP 请求
# 无 timeout 会无限挂起，且子智能体反复重试多达 23 次（耗时 29 分钟）。
# 修复：① SDK 调用放进线程池并强制超时 ② 连续失败 2 次熔断，直接拒绝后续调用
# ③ 熔断后成功一次（服务恢复）自动闭合。

_RAGFLOW_CALL_TIMEOUT = float(os.getenv("RAGFLOW_CALL_TIMEOUT", "20"))   # 单次SDK调用超时(秒)
_RAGFLOW_FAILURE_THRESHOLD = 2                                            # 连续失败N次后熔断

if _RAGFLOW_SDK_AVAILABLE:
    _ragflow_client = RAGFlow(
        api_key=os.getenv("RAGFLOW_API_KEY"),
        base_url=os.getenv("RAGFLOW_API_URL")
    )
else:
    _ragflow_client = None

_executor = ThreadPoolExecutor(max_workers=2)
_state_lock = threading.Lock()
_consecutive_failures = 0


def _call_ragflow(func, *args, **kwargs):
    """带超时 + 熔断的 RAGFlow SDK 调用包装。
    返回 (result, None) 或 (None, 失败原因)。"""
    global _consecutive_failures
    if not _RAGFLOW_SDK_AVAILABLE or _ragflow_client is None:
        return None, ("RAGFlow服务不可用（云端环境未安装 ragflow-sdk），请立即停止调用本工具并告知用户服务暂不可用")
    with _state_lock:
        if _consecutive_failures >= _RAGFLOW_FAILURE_THRESHOLD:
            return None, (f"RAGFlow服务不可用（已连续失败{_consecutive_failures}次，熔断生效），"
                          f"请立即停止调用本工具并告知用户服务暂不可用")
    future = _executor.submit(func, *args, **kwargs)
    try:
        result = future.result(timeout=_RAGFLOW_CALL_TIMEOUT)
    except FutureTimeout:
        with _state_lock:
            _consecutive_failures += 1
        reason = (f"RAGFlow服务响应超时（>{_RAGFLOW_CALL_TIMEOUT:.0f}s），"
                  f"已计入失败 {_consecutive_failures}/{_RAGFLOW_FAILURE_THRESHOLD}")
        logger.warning(f"[RAGFlow熔断] {reason}")
        return None, reason
    except Exception as e:
        with _state_lock:
            _consecutive_failures += 1
        reason = f"RAGFlow调用失败（{_consecutive_failures}/{_RAGFLOW_FAILURE_THRESHOLD}）：{e}"
        logger.warning(f"[RAGFlow熔断] {reason}")
        return None, reason
    with _state_lock:
        _consecutive_failures = 0   # 成功则熔断复位
    return result, None


@tool
def get_assistant_list() -> str:
    """
      获取ragflow服务中所有的聊天助手信息! 用于后续具体提问的筛选!
      返回格式: 助手名称:xxx , 描述: xx , 关联的知识库: x,x,x,x \n
              助手名称:xxx , 描述: xx , 关联的知识库: x,x,x,x \n
    """
    monitor.report_tool(tool_name="查询ragflow助手列表信息")
    # 1. 查询所有的聊天助手（带超时+熔断）
    chat_list, err = _call_ragflow(lambda: _ragflow_client.list_chats())
    if err:
        return f"查询助手列表失败：{err}"
    if not chat_list or len(chat_list) == 0:
        return "未找到可用任何助手"
    # 2. 查询每个助手的关联的知识库
    final_result = ""
    for chat in chat_list:
        name = chat.name
        description = chat.description
        datasets = chat.datasets
        dataset_name_list = [dataset['name'] for dataset in datasets]
        final_result += f"助手名称:{name} , 描述: {description} , 关联的知识库: {','.join(dataset_name_list)} \n"
    # 3. 返回拼接结果
    return final_result


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """
      向指定的助手提问,并获取返回结果!
      参数 chat_name就是助手的名称,名称需要get_assistant_list查询和确认
          question是本次提问的问题
      返回结果就是提问的回答
    """
    monitor.report_tool(tool_name="向ragflow提问工具", args={"chat_name": chat_name})

    def _ask():
        list_chats = _ragflow_client.list_chats(name=chat_name)
        if not list_chats or len(list_chats) == 0:
            return None
        chat = list_chats[0]
        session = chat.create_session(name="temp_session")
        stream = session.ask(question=question, stream=True)
        final_result = ""
        for chunk in stream:
            # 遍历的chunk本身就是累加的，取最后一个即可
            final_result = chunk.content
        chat.delete_sessions([session.id])
        return final_result or "(助手返回了空答案)"

    result, err = _call_ragflow(_ask)
    if err:
        return f"向{chat_name}提问失败：{err}（RAGFlow助手当前不可用，请不要继续重试）"
    if result is None:
        return f"未找到名称为{chat_name}的助手"
    return result


if __name__ == "__main__":
    # print(get_assistant_list.invoke({}))
    print(create_ask_delete.invoke({"chat_name": "test", "question": "空调的绝热工作怎么做？"}))
