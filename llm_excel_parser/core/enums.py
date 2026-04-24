#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 21:51
#   @FileRole:

from enum import Enum

class MergeAction(Enum):
    FILL_FORWARD = "fill_forward"  # 自动向下/向右复制主格值
    TOP_LEFT = "top_left"          # 保持原样(仅左上角有值)
    TAG = "tag"                    # 注入占位符标签

class ExcelFormat(Enum):
    XLS = "xls"
    XLSX = "xlsx"
    UNKNOWN = "unknown"

class ChunkStrategy(Enum):
    FIXED_ROW = "fixed_row"      # 按固定行数切片
    TOKEN_LIMIT = "token_limit"  # 按 Token 上限切片