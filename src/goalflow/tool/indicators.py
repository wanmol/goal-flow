import functools
import time
from typing import Callable

from goalflow.node import BaseNode


def execute_time_indicator():
    """
    方法执行时间
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            node_id = ""
            node_title =""
            node_type=""
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time

                if args and isinstance(args[0],BaseNode):
                    base_node = args[0]
                    node_title= base_node.title
                    node_id = base_node.id
                    node_type = base_node.type
                print(f"\n节点耗时统计，节点id：{node_id}，节点类型名：{node_type}，节点名：{node_title}，执行状态：正常，耗时{elapsed:.4f}s\n")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                print(f"\n节点耗时统计，节点id：{node_id}，节点类型名：{node_type}，节点名：{node_title}，执行状态：异常，耗时{elapsed:.4f}s\n")
        return wrapper
    return decorator