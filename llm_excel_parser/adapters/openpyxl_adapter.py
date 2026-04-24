#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/19 18:58
#   @FileRole: Openpyxl 原生引擎层的包装适配器


from typing import Any, Tuple, List, Iterator
from llm_excel_parser.core.interfaces import BaseWorksheet
from llm_excel_parser.core.datatypes import CellStyle
from llm_excel_parser.utils.matrix_algo import col_idx_to_letter


class OpenpyxlWorksheetAdapter(BaseWorksheet):
    def __init__(self, ws):
        """传入 openpyxl 的 worksheet 对象"""
        self._ws = ws

    @property
    def title(self) -> str:
        return self._ws.title

    @property
    def max_dimensions(self) -> Tuple[int, int]:
        return self._ws.max_row, self._ws.max_column

    def get_cell_value(self, row: int, col: int) -> Any:
        return self._ws.cell(row=row, column=col).value

    def iter_rows(self, min_row: int, max_row: int, min_col: int, max_col: int) -> Iterator[List[Any]]:
        return self._ws.iter_rows(
            min_row=min_row, max_row=max_row,
            min_col=min_col, max_col=max_col,
            values_only=True
        )

    def get_merged_regions(self) -> List[Tuple[int, int, int, int]]:
        regions = []
        if hasattr(self._ws, 'merged_cells'):
            for merged_range in self._ws.merged_cells.ranges:
                min_col, min_row, max_col, max_row = merged_range.bounds
                regions.append((min_row, min_col, max_row, max_col))
        return regions

    def is_row_hidden(self, row: int) -> bool:
        if not hasattr(self._ws, 'row_dimensions'):
            return False
        return row in self._ws.row_dimensions and self._ws.row_dimensions[row].hidden

    def is_col_hidden(self, col: int) -> bool:
        if not hasattr(self._ws, 'column_dimensions'):
            return False
        col_letter = col_idx_to_letter(col)
        return col_letter in self._ws.column_dimensions and self._ws.column_dimensions[col_letter].hidden

    def get_cell_style(self, row: int, col: int) -> CellStyle:
        cell = self._ws.cell(row=row, column=col)
        style: CellStyle = {}
        try:
            if cell.font and cell.font.bold:
                style['is_bold'] = True
        except Exception:
            pass
        try:
            fill = cell.fill
            if fill and fill.fill_type not in (None, 'none') and fill.fgColor:
                color = fill.fgColor
                # rgb 为 "00000000" 时表示无填充
                rgb = getattr(color, 'rgb', None)
                if rgb and rgb != '00000000':
                    style['has_bg'] = True
        except Exception:
            pass
        return style
