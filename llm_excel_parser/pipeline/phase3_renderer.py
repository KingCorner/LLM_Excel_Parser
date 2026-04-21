#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:01
#   @FileRole: 数据渲染层 - 将 Excel 数据块转换为脱离引擎的二维字典 / 数组

from typing import List, Dict, Any, Tuple
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.enums import MergeAction
from llm_excel_parser.core.datatypes import BoundingBox
from llm_excel_parser.core.exceptions import DataRenderError

from llm_excel_parser.utils.formatters import format_cell_value
from llm_excel_parser.strategies.unmerge import get_unmerge_strategy
from llm_excel_parser.utils.matrix_algo import col_idx_to_letter


logger = get_logger("phase3_renderer")


class DataRenderer:
    @staticmethod
    def render_box(ws, box: BoundingBox, action: MergeAction, ignore_hidden: bool = True) -> List[List[Any]]:
        """
        阶段 3: 提取 Box 区域的真实数据并处理合并单元格

        :param ws: worksheet 对象 (当前鸭子类型，未来可切其它引擎)
        :param box: Phase 2 产出的表格包围盒
        :param action: 处理合并单元格的策略枚举
        :return: 二维 List，代表该Box内所有可见单元格经过策略渲染后的最终值
        """
        if box.max_row == 0 or box.max_col == 0:
            return []

        try:
            # 1. 预计算可见行/列
            visible_rows = []
            for r in range(box.min_row, box.max_row + 1):
                if ignore_hidden and ws.is_row_hidden(r):
                    continue
                visible_rows.append(r)
            visible_cols = []
            for c in range(box.min_col, box.max_col + 1):
                if ignore_hidden and ws.is_col_hidden(c):
                    continue
                visible_cols.append(c)
            if not visible_rows or not visible_cols:
                return []

            # 2. 从全局合并单元格中，过滤出仅在这个 Box 内产生交集的拓扑关系
            merged_dict: Dict[Tuple[int, int], Dict[str, Any]] = {}
            for min_row, min_col, max_row, max_col in ws.get_merged_regions():
                # 矩阵碰撞检测
                if max_col < box.min_col or min_col > box.max_col or \
                        max_row < box.min_row or min_row > box.max_row:
                    continue

                # 提取主格原值
                master_val = format_cell_value(ws.get_cell_value(min_row, min_col))

                for r in range(max(min_row, box.min_row), min(max_row, box.max_row) + 1):
                    for c in range(max(min_col, box.min_col), min(max_col, box.max_col) + 1):
                        merged_dict[(r, c)] = {
                            "master_val": master_val,
                            "is_top_left": (r == min_row and c == min_col)
                        }

            # 3. 动态获取解码策略工厂方法，移除 if-else
            strategy = get_unmerge_strategy(action)

            # 4. 严格构建最终二维数据组 List[List[Any]]
            rendered_matrix: List[List[Any]] = []

            for r in visible_rows:
                row_data = []
                for c in visible_cols:
                    raw_val = ws.get_cell_value(r, c)
                    formatted_val = format_cell_value(raw_val)
                    final_val = formatted_val

                    # 应用策略进行消解
                    if (r, c) in merged_dict:
                        merge_info = merged_dict[(r, c)]
                        final_val = strategy.resolve(
                            value=merge_info["master_val"],
                            row=r,
                            col=c,
                            is_top_left=merge_info["is_top_left"]
                        )

                    row_data.append(final_val)
                rendered_matrix.append(row_data)

            logger.debug(f"Box({box.range_str}) 数据渲染完成，矩阵维度: "
                         f"{len(rendered_matrix)} x {len(rendered_matrix[0]) if rendered_matrix else 0}")
            return rendered_matrix

        except Exception as e:
            logger.error(f"渲染 Box({box.range_str}) 失败! Error: {str(e)}")
            raise DataRenderError(f"Phase 3 数据提取异常: 提取 box {box.range_str} 失败. 具体原因: {str(e)}") from e
