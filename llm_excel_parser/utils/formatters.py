#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 21:58
#   @FileRole: 基础格式化

import datetime
from typing import Any, Dict, List


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
            str(row.get(c, {}).get("value", "")).replace("|", "｜")
            for c in range(1, max_col + 1)
        ]

        # 拼装行： 行号 | 值1 | 值2 | ...
        md_lines.append(f"{r_idx} | " + " | ".join(row_vals) + " |")

    return "\n".join(md_lines)
