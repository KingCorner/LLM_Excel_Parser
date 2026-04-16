#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:01
#   @FileRole: 寻找并切割表格边界 (Phase 2: 结构探测层)


from typing import List, Set, Tuple
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.datatypes import BoundingBox
from llm_excel_parser.config import default_config
# 引入解耦出的底层算法
from llm_excel_parser.utils.matrix_algo import find_8_connected_components, merge_proximate_boxes

logger = get_logger("phase2_detector")


class StructureDetector:

    @classmethod
    def detect_tables(cls, ws, max_empty_rows: int = default_config.DETECT_MAX_EMPTY_ROWS,
                      max_empty_cols: int = default_config.DETECT_MAX_EMPTY_COLS) -> List[BoundingBox]:
        """
        核心切表编排逻辑：映射布尔矩阵 -> 连通域探测(调用算法层) -> 膨胀合并(调用算法层)
        返回单张Sheet中的多个独立表格区域 (BoundingBox)
        """
        max_row = ws.max_row
        max_col = ws.max_column

        if max_row == 0 or max_col == 0 or (max_row == 1 and max_col == 1 and ws.cell(1, 1).value is None):
            logger.debug(f"Sheet '{ws.title}' 为空，跳过切分。")
            return []

        # 步骤 1 & 2: 构建稀疏布尔矩阵并进行合并格修补 (强依赖 ws 业务逻辑，保留在此处)
        solid_cells = cls._build_boolean_matrix(ws, max_row, max_col)
        if not solid_cells:
            return []

        # 步骤 3: 微观连通域聚类 (调用底层算法解耦)
        micro_boxes = find_8_connected_components(solid_cells)

        # 步骤 4: 宏观合并 (消除连续空行/空列带来的断层，调用底层算法)
        final_boxes = merge_proximate_boxes(micro_boxes, max_empty_rows, max_empty_cols)

        logger.info(f"Sheet '{ws.title}' 结构探测完成, 发现 {len(final_boxes)} 个独立表格块。")
        for i, box in enumerate(final_boxes):
            logger.debug(f"  Box {i + 1}: R{box.min_row}:R{box.max_row}, C{box.min_col}:C{box.max_col}")

        return final_boxes

    @staticmethod
    def _build_boolean_matrix(ws, max_row: int, max_col: int) -> Set[Tuple[int, int]]:
        """获取具有实际展示意义的单元格坐标集合 (强依赖 Excel 解析逻辑)"""
        solid_cells = set()

        # 1. 扫描值
        for row_idx, row in enumerate(
                ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col, values_only=True), 1):
            for col_idx, val in enumerate(row, 1):
                if val is not None and str(val).strip() != "":
                    solid_cells.add((row_idx, col_idx))

        # 2. 合并单元格修补
        for merged_range in ws.merged_cells.ranges:
            for r in range(merged_range.min_row, merged_range.max_row + 1):
                for c in range(merged_range.min_col, merged_range.max_col + 1):
                    solid_cells.add((r, c))

        return solid_cells
