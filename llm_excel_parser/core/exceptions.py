#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/15 19:49
#   @FileRole: 自定义异常类

class ExcelParserBaseException(Exception):
    """项目自定义异常基类"""
    pass


class OverDimensionError(ExcelParserBaseException):
    """(Phase 1) Excel维度超限异常 (防止OOM炸弹)"""
    pass


class UnsupportedFormatError(ExcelParserBaseException):
    """(Phase 1) 不受支持的文件格式异常"""
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
