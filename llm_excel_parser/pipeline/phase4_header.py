#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/15 17:01
#   @FileRole: 表头识别

import json
import re
from typing import List, Dict, Any, Optional

from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.datatypes import StructuredTable, CellData
from llm_excel_parser.config import default_config
from llm_excel_parser.prompts import HEADER_ANALYZER_PROMPT_TEMPLATE
from llm_excel_parser.utils.formatters import rows_dict_to_markdown_table

logger = get_logger("phase4_header")


class HeaderAnalyzer:
    """表头识别专家系统"""

    @classmethod
    def analyze(
            cls,
            filename: str,
            sheetname: str,
            content: List[CellData],
            use_llm_layout_analyzer: bool = False,
            llm_service: Optional[Any] = None,
            custom_header_keywords: Optional[List[str]] = None
    ) -> StructuredTable:

        if not content:
            return StructuredTable(filename, sheetname, [], [], 0)

        # 1. 数据准备
        rows_dict, max_col = cls._build_rows_dict(content)
        sorted_row_indices = sorted(rows_dict.keys())

        # 2. 决定表头边界
        header_boundary_idx = 0

        # LLM 兜底分析
        if use_llm_layout_analyzer and llm_service:
            scan_indices = sorted_row_indices[:default_config.HEADER_LLM_SCAN_ROW_LIMIT]
            header_boundary_idx = cls._llm_scoring(rows_dict, scan_indices, max_col, llm_service)

        # 启发式分析 (LLM未开启或失败时)
        if header_boundary_idx == 0:
            scan_indices = sorted_row_indices[:default_config.HEADER_SCAN_ROW_LIMIT]
            header_boundary_idx = cls._heuristic_scoring(rows_dict, scan_indices, max_col, custom_header_keywords)

        # 3. 数据组装并返回
        logger.info(f"[{sheetname}] 表头识别完成，拆刀落在第 {header_boundary_idx} 行")
        return cls._split_data_to_structured_table(
            filename, sheetname, rows_dict, sorted_row_indices, header_boundary_idx, max_col
        )

    @staticmethod
    def _heuristic_scoring(
            rows_dict: Dict[int, Dict[int, Any]],
            scan_indices: List[int],
            max_col: int,
            custom_header_keywords: Optional[List[str]] = None
    ) -> int:
        """启发式特征打分算法"""
        if not scan_indices:
            return 0

        scores = {}
        for i, r_idx in enumerate(scan_indices):
            score = 0
            current_row = rows_dict[r_idx]

            # 1. 密度特征
            non_empty_count = sum(
                1 for c in range(1, max_col + 1) if str(current_row.get(c, {}).get("value", "")).strip())
            density = non_empty_count / max_col if max_col > 0 else 0
            if density > default_config.HEADER_DENSITY_THRESHOLD:
                score += default_config.HEADER_WEIGHT_DENSITY_HIGH

            # 2. 关键字特征
            if custom_header_keywords:
                row_strs = [str(current_row.get(c, {}).get("value", "")).lower() for c in range(1, max_col + 1)]
                match_count = sum(1 for kw in custom_header_keywords if any(kw.lower() in v for v in row_strs))
                score += default_config.HEADER_WEIGHT_KEYWORD_MATCH * match_count

            # 3. 与下一行的突变特征对比
            if i + 1 < len(scan_indices):
                next_row = rows_dict[scan_indices[i + 1]]

                # 类型突变
                curr_is_str = all(
                    isinstance(current_row.get(c, {}).get("value", ""), str) for c in range(1, max_col + 1) if
                    current_row.get(c))
                next_has_num = any(
                    isinstance(next_row.get(c, {}).get("value", ""), (int, float)) for c in range(1, max_col + 1) if
                    next_row.get(c))
                if curr_is_str and next_has_num:
                    score += default_config.HEADER_WEIGHT_TYPE_MUTATION

                # 样式突变
                curr_spec = any(
                    current_row.get(c, {}).get("style", {}).get("is_bold") or current_row.get(c, {}).get("style",
                                                                                                         {}).get(
                        "has_bg") for c in range(1, max_col + 1))
                next_spec = any(
                    next_row.get(c, {}).get("style", {}).get("is_bold") or next_row.get(c, {}).get("style", {}).get(
                        "has_bg") for c in range(1, max_col + 1))
                if curr_spec and not next_spec:
                    score += default_config.HEADER_WEIGHT_STYLE_MUTATION

            scores[r_idx] = score

        if scores:
            best_row, highest_score = max(scores.items(), key=lambda x: x[1])
            if highest_score >= default_config.HEADER_MIN_SCORE_THRESHOLD:
                return best_row

        return scan_indices[0]  # 兜底返回第一行

    @staticmethod
    def _llm_scoring(rows_dict, scan_indices, max_col, llm_service) -> int:
        """调用大模型做表格布局探测分析"""
        try:
            # 使用解耦出去的 formatter
            md_table_str = rows_dict_to_markdown_table(rows_dict, scan_indices, max_col)
            # 使用解耦出去的 prompt template
            prompt = HEADER_ANALYZER_PROMPT_TEMPLATE.format(md_table_str=md_table_str)

            response_text = llm_service.chat(prompt)

            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                res_json = json.loads(match.group(0))
                boundary_idx = res_json.get("boundary_row_idx", 0)
                if boundary_idx in scan_indices:
                    return boundary_idx
        except Exception as e:
            logger.warning(f"LLM 布局探测失败，退化为启发式打分。原因: {str(e)}")
        return 0

    # 以下为辅助私有方法 (保持主逻辑整洁)

    @staticmethod
    def _build_rows_dict(content: List[CellData]):
        rows_dict, max_col = {}, 0
        for cell in content:
            r, c, v = cell['row'], cell['column'], cell['value']
            rows_dict.setdefault(r, {})[c] = {"value": v, "style": cell.get('style', {})}
            max_col = max(max_col, c)
        return rows_dict, max_col

    @staticmethod
    def _split_data_to_structured_table(filename, sheetname, rows_dict, indices, boundary_idx, max_col):
        headers, body_rows = [], []
        for r_idx in indices:
            row_data = {
                "row": r_idx,
                "data": {c: cell_info["value"] for c, cell_info in rows_dict[r_idx].items()}
            }
            if r_idx <= boundary_idx:
                headers.append(row_data)
            else:
                body_rows.append(row_data)
        return StructuredTable(filename, sheetname, headers, body_rows, max_col)
