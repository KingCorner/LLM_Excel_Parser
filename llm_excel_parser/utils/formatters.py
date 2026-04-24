#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 21:58
#   @FileRole: 基础格式化

import math
import datetime
from typing import Any, Dict, List
from llm_excel_parser.core.datatypes import StructuredTable
from llm_excel_parser.config import default_config


def format_cell_value(value: Any) -> Any:
    """
    格式化单元格值，确保输出纯净的 Python 基础类型，
    以便完美接入后续的表头打分(Phase 4)及大模型序列化(Phase 5)
    """
    if value is None:
        return None

    # 1. 抹平没用的小数点 (如 1.0 -> 1)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    # 2. 字符串深度清洗
    if isinstance(value, str):
        val_stripped = value.strip()
        # 如果去掉空格是个空串，统一等效为 None，防止破坏打分密度
        if not val_stripped:
            return None
        return val_stripped

    # 3. 日期时间对象序列化规整 (openpyxl 会抛出原生的 datetime 对象)
    if isinstance(value, datetime.datetime):
        # 如果只有日期没有时分秒，则只输出年月日，节省 Token
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")

    elif isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")

    elif isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")

    # 4. 其他类型兜底 (如 bool 等)，直接放行
    return value


def rows_dict_to_markdown_table(rows_dict: Dict[int, Dict[int, Any]], scan_indices: List[int], max_col: int) -> str:
    """
    将内部二维字典行数据转换为轻量级 Markdown 表格字符串，
    专供 Phase 4 (大模型表格布局探测) 拼装 Prompt 使用。
    """
    md_lines = []

    for r_idx in scan_indices:
        row = rows_dict.get(r_idx, {})

        # 遍历列宽，缺失的列填充空字符串
        # 使用全角 "｜" 替换半角 "|"，防止单元格自带的管道符破坏 Markdown 渲染表格结构
        row_vals = [
            str(row.get(c, {}).get("value", "")).replace("|", default_config.MARKDOWN_PIPE_ESCAPE)
            for c in range(1, max_col + 1)
        ]

        # 拼装行： 行号 | 值1 | 值2 | ...
        md_lines.append(f"{r_idx} | " + " | ".join(row_vals) + " |")

    return "\n".join(md_lines)


def render_chunk_header(table: StructuredTable) -> tuple[str, int]:
    """渲染表头区并返回字符串及基础Token占用"""
    if not table.headers:
        return "表头 | (无表头数据)", 5
    header_str_lines = []
    for h in table.headers:
        h_data = h["data"]
        row_items = [str(h_data.get(c, "")) for c in range(1, table.max_col + 1)]
        header_str_lines.append("表头 | " + " | ".join(row_items))
    final_header_str = "\n".join(header_str_lines)
    base_tokens = math.ceil(len(final_header_str) * default_config.TOKEN_CONVERSION_RATIO) + default_config.HEADER_BASE_TOKENS
    return final_header_str, base_tokens


def render_chunk_row(row_record: Dict, max_col: int) -> str:
    """渲染带有逻辑行号的单行数据"""
    r_idx = row_record["row"]
    r_data = row_record["data"]
    # 替换其中的换行等可能破坏Markdown表格的字符
    row_vals = [str(r_data.get(c, "")).replace("\n", " ").replace("|", default_config.MARKDOWN_PIPE_ESCAPE) for c in range(1, max_col + 1)]
    return f"行{r_idx} | " + " | ".join(row_vals)


def build_chunk_context(
        table: StructuredTable,
        batch: List[Dict],
        header_str: str,
        current_chunk_idx: int,
        total_chunks: int
) -> str:
    """将数据拼接为 LLM 友好的 Markdown/CSV 格式"""
    start_row = batch[0]["row"]
    end_row = batch[-1]["row"]
    context_parts = [
        f"=== 电子表格数据片段 ({current_chunk_idx}/{total_chunks}) ===",
        f"📌 文件名: {table.filename} | 工作表: {table.sheetname}",
        f"📌 行号范围: {start_row} ~ {end_row}",
        "-" * default_config.SEPARATOR_WIDTH,
        header_str,  # 每一块均带上表头
        "-" * default_config.SEPARATOR_WIDTH
    ]
    for row_record in batch:
        context_parts.append(render_chunk_row(row_record, table.max_col))
    return "\n".join(context_parts)
