#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/15 17:01
#   @FileRole: 表头识别专家系统

import json
import re
from typing import List, Dict, Any, Optional
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.datatypes import StructuredTable, CellData

# getattr/Any 这里是为了解耦，假设你在 core.interfaces 里定义了 LLMServiceProtocol
# from llm_excel_parser.core.interfaces import LLMServiceProtocol

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
        """
        执行启发式扫描（或LLM分析），分离表头和数据体
        """
        if not content:
            return StructuredTable(filename, sheetname, [], [], 0)

        # 1. 还原为基于行的二维字典，便于按行进行特征提取
        rows_dict = {}
        max_col = 0
        for cell in content:
            r, c, v = cell['row'], cell['column'], cell['value']
            style = cell.get('style', {})  # 尝试获取 Phase3 传递的样式

            if r not in rows_dict:
                rows_dict[r] = {}
            rows_dict[r][c] = {"value": v, "style": style}
            max_col = max(max_col, c)

        sorted_row_indices = sorted(rows_dict.keys())

        # 2. 决定表头边界
        header_boundary_idx = 0

        # 优先使用 LLM 兜底分析机制 (如果开启且传入了模型)
        if use_llm_layout_analyzer and llm_service:
            header_boundary_idx = cls._llm_scoring(rows_dict, sorted_row_indices[:10], max_col, llm_service)

        # LLM 失败或未开启，则使用本地快速启发式打分 (扫前5行)
        if header_boundary_idx == 0:
            header_boundary_idx = cls._heuristic_scoring(
                rows_dict,
                sorted_row_indices[:5],
                max_col,
                custom_header_keywords
            )

        # 3. 数据分离：[最小行, boundary] 为表头，其余为 Body
        headers = []
        body_rows = []

        for r_idx in sorted_row_indices:
            # 还原为原样的 dict 传递给下游
            row_data = {
                "row": r_idx,
                "data": {c: cell_info["value"] for c, cell_info in rows_dict[r_idx].items()}
            }
            if r_idx <= header_boundary_idx:
                headers.append(row_data)
            else:
                body_rows.append(row_data)

        logger.info(f"[{sheetname}] 表头识别完成，拆刀落在第 {header_boundary_idx} 行 (包含此时上方所有行)")

        return StructuredTable(
            filename=filename,
            sheetname=sheetname,
            headers=headers,
            body_rows=body_rows,
            max_col=max_col
        )

    @staticmethod
    def _heuristic_scoring(
            rows_dict: Dict[int, Dict[int, Any]],
            scan_indices: List[int],
            max_col: int,
            custom_header_keywords: Optional[List[str]] = None
    ) -> int:
        """
        启发式打分机制
        """
        if not scan_indices:
            return 0

        scores = {}
        THRESHOLD = 25  # 判定为表头的最低分数线阈值

        for i, r_idx in enumerate(scan_indices):
            score = 0
            current_row = rows_dict[r_idx]

            # === 特征1 (密度法): 非空单元格占比。满格行得分高 ===
            non_empty_count = sum(1 for c in range(1, max_col + 1)
                                  if current_row.get(c) is not None and str(
                current_row.get(c).get("value", "")).strip() != "")
            density = non_empty_count / max_col if max_col > 0 else 0
            if density > 0.8:
                score += 30

            # === 用户自定义关键字打分 (如果有预期的列名) ===
            if custom_header_keywords:
                row_str_values = [str(current_row.get(c, {}).get("value", "")).lower() for c in range(1, max_col + 1)]
                match_count = sum(1 for kw in custom_header_keywords if any(kw.lower() in v for v in row_str_values))
                if match_count > 0:
                    score += 50 * match_count  # 命中关键字，权重极高

            # 提取当前行与下一行的对比特征
            if i + 1 < len(scan_indices):
                next_row_idx = scan_indices[i + 1]
                next_row = rows_dict[next_row_idx]

                # === 特征2 (类型突变法): 与下一行进行类型对比 ===
                curr_is_all_str = all(
                    isinstance(current_row.get(c, {}).get("value", ""), str)
                    for c in range(1, max_col + 1) if current_row.get(c)
                )
                next_has_number = any(
                    isinstance(next_row.get(c, {}).get("value", ""), (int, float))
                    for c in range(1, max_col + 1) if next_row.get(c)
                )

                if curr_is_all_str and next_has_number:
                    score += 40

                # === 特征3 (Style样式法): 样式显著且下一行没有 ===
                curr_is_bold = any(
                    current_row.get(c, {}).get("style", {}).get("is_bold") for c in range(1, max_col + 1))
                next_is_bold = any(next_row.get(c, {}).get("style", {}).get("is_bold") for c in range(1, max_col + 1))

                curr_has_bg = any(current_row.get(c, {}).get("style", {}).get("has_bg") for c in range(1, max_col + 1))
                next_has_bg = any(next_row.get(c, {}).get("style", {}).get("has_bg") for c in range(1, max_col + 1))

                if (curr_is_bold and not next_is_bold) or (curr_has_bg and not next_has_bg):
                    score += 20

            scores[r_idx] = score
            logger.debug(f"行 {r_idx} 启发式打分: {score} (密度: {density:.2f})")

        # 综合判定: 得分最高且【超过阈值】的行
        if scores:
            best_row, highest_score = max(scores.items(), key=lambda x: x[1])
            if highest_score >= THRESHOLD:
                return best_row

        return scan_indices[0]  # 兜底策略：均不达标时，只拿当前第一行当表头

    @staticmethod
    def _llm_scoring(
            rows_dict: Dict[int, Dict[int, Any]],
            scan_indices: List[int],
            max_col: int,
            llm_service: Any
    ) -> int:
        """调用大模型做表格布局探测分析 (仅前 10 行)"""
        try:
            # 1. 构建轻量级 Markdown 表格
            md_lines = []
            for r_idx in scan_indices:
                row = rows_dict[r_idx]
                row_vals = [str(row.get(c, {}).get("value", "")).replace("|", "") for c in range(1, max_col + 1)]
                md_lines.append(f"{r_idx} | " + " | ".join(row_vals) + " |")

            md_table_str = "\n".join(md_lines)

            # 2. 组装 Prompt
            prompt = (
                "请分析以下电子表格的头部，返回表头占据了前几行。\n"
                "数字第一列是物理行号。表头可能是一行或多行合并。\n"
                "===数据===\n"
                f"{md_table_str}\n"
                "==========\n"
                "请仅以JSON格式输出，不要输出任何推理过程，格式如：{\"header_row_count\": 2, \"boundary_row_idx\": 3}\n"
                "注意：boundary_row_idx 是表头最后一行的物理行号。"
            )

            # 3. 调用LLM（假设返回的是文本）
            response_text = llm_service.chat(prompt)

            # 4. 解析 JSON
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                res_json = json.loads(match.group(0))
                boundary_idx = res_json.get("boundary_row_idx", 0)
                if boundary_idx in scan_indices:
                    logger.info(f"LLM 成功分析表头，切分行号为: {boundary_idx}")
                    return boundary_idx

        except Exception as e:
            logger.warning(f"LLM 布局探测失败，退化为启发式打分。原因: {str(e)}")

        return 0  # 失败返回0，触发 fallback
