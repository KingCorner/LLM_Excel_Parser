# -*- coding: UTF-8 -*-
# @Author: KingCorner
# @Time:   2026/4/14 21:37
# @FileRole: 暴露给用户的顶级API

# 1. 暴露核心数据结构
from .core.datatypes import BoundingBox

# from .core.datatypes import ExcelChunk (如果 datatypes 中已有，解除注释)

# 2. 暴露 LLM 接口协议（方便用户实现并传入自己的 LLM 客户端）
# from .core.interfaces import LLMServiceProtocol

# 3. 暴露未来总控制器的顶级执行函数 (占位，等 orchestrator 写好后启用)
# from .pipeline.orchestrator import process_excel

__version__ = "0.1.0"

# 控制 from llm_excel_parser import * 时暴露的内容
__all__ = [
    "BoundingBox",
    # "ExcelChunk",
    # "LLMServiceProtocol",
    # "process_excel",
]
