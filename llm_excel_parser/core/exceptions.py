#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/15 19:49
#   @FileRole: 自定义异常类

class ExcelParserBaseException(Exception):
    """项目自定义异常基类"""
    pass


# 1. 基础环境与输入检查异常
class InvalidInputTypeError(ExcelParserBaseException, TypeError):
    """不支持的输入流类型异常"""
    pass


class MissingDependencyError(ExcelParserBaseException, ImportError):
    """可选依赖项缺失异常 (例如老旧xls文件解析缺少xlrd)"""
    pass


# 2. 流水线阶段异常
class OverDimensionError(ExcelParserBaseException):
    """(Phase 1) Excel维度超限异常 (防止OOM炸弹)"""
    pass


class UnsupportedFormatError(ExcelParserBaseException):
    """(Phase 1) 不受支持的文件格式异常"""
    pass


class FileCorruptedError(ExcelParserBaseException):
    """(Phase 1) 文件损坏或无法被解析引擎加载"""
    pass


class StructureDetectionError(ExcelParserBaseException):
    """(Phase 2) 结构探测异常"""
    pass


class DataRenderError(ExcelParserBaseException):
    """(Phase 3) 数据加载与渲染异常"""
    pass


class HeaderAnalysisError(ExcelParserBaseException):
    """(Phase 4) 表头智能识别异/分析常"""
    pass
