#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 21:58
#   @FileRole: 核心数据类定义

from dataclasses import dataclass, field
from typing import List, Dict, Any, TypedDict


@dataclass
class BoundingBox:
    """表格数据包围盒 (Phase 2 -> Phase 3)"""
    min_row: int
    max_row: int
    min_col: int
    max_col: int

    def expand(self, row_margin: int, col_margin: int) -> 'BoundingBox':
        return BoundingBox(
            min_row=max(1, self.min_row - row_margin),
            max_row=self.max_row + row_margin,
            min_col=max(1, self.min_col - col_margin),
            max_col=self.max_col + col_margin
        )

    def intersects(self, other: 'BoundingBox') -> bool:
        return not (self.max_col < other.min_col or
                    self.min_col > other.max_col or
                    self.max_row < other.min_row or
                    self.min_row > other.max_row)

    def merge(self, other: 'BoundingBox') -> 'BoundingBox':
        return BoundingBox(
            min_row=min(self.min_row, other.min_row),
            max_row=max(self.max_row, other.max_row),
            min_col=min(self.min_col, other.min_col),
            max_col=max(self.max_col, other.max_col)
        )

    @property
    def range_str(self) -> str:
        """输出符合人类习惯与LLM认知的坐标范围 (如: B2:D10)"""

        def col_to_letter(col: int) -> str:
            letter = ''
            while col > 0:
                col, remainder = divmod(col - 1, 26)
                letter = chr(65 + remainder) + letter
            return letter

        start = f"{col_to_letter(self.min_col)}{self.min_row}"
        end = f"{col_to_letter(self.max_col)}{self.max_row}"
        return f"{start}:{end}" if start != end else start


class CellStyle(TypedDict, total=False):
    """单元格样式特征 (total=False表示这些字段是可选的)"""
    is_bold: bool
    has_bg: bool


class CellData(TypedDict):
    """Phase 3 输出到 Phase 4 的单个单元格数据结构"""
    row: int
    column: int
    value: Any
    style: CellStyle


@dataclass
class StructuredTable:
    """已明确物理结构的表格 (Phase 4 -> Phase 5)"""
    filename: str
    sheetname: str
    headers: List[Dict[str, Any]]
    body_rows: List[Dict[str, Any]]
    max_col: int
    box_range: str = ""


@dataclass
class ExcelChunk:
    """标准输出数据模型 - 输入给大模型或下游的最终分块 (Phase 5 输出)"""
    chunk_id: str
    metadata: Dict[str, Any]  # 建议包含 sheet_name, box_range 等
    formatted_context: str
    raw_data: List[Dict[str, Any]]
