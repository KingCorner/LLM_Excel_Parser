# -*- coding: UTF-8 -*-
# @Author: KingCorner
# @Time:   2026/4/14 21:37
# @FileRole: 暴露给用户的顶级API

# 1. 暴露核心数据结构
from .core.datatypes import BoundingBox, ExcelChunk, StructuredTable

# 2. 暴露核心枚举类
from .core.enums import MergeAction

# 3. 暴露 LLM 接口协议（方便用户实现并传入自己的 LLM 客户端）
from .core.interfaces import LLMServiceProtocol

# 4. 暴露流水线总控制器的顶级执行函数
from .pipeline.orchestrator import process_excel

# 5. 暴露自定义异常基类及常用异常，方便用户在外层捕获处理
from .core.exceptions import (
    ExcelParserBaseException,
    OverDimensionError,
    UnsupportedFormatError,
    StructureDetectionError,
    DataRenderError,
    HeaderAnalysisError
)

__version__ = "0.1.0"

# 控制 from llm_excel_parser import * 时暴露的内容
__all__ = [
    # 核心方法
    "process_excel",

    # 数据协议与枚举
    "MergeAction",
    "BoundingBox",
    "ExcelChunk",
    "StructuredTable",
    "LLMServiceProtocol",

    # 错误异常类
    "ExcelParserBaseException",
    "OverDimensionError",
    "UnsupportedFormatError",
    "StructureDetectionError",
    "DataRenderError",
    "HeaderAnalysisError",
]