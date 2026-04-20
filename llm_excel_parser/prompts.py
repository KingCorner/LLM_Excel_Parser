#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 18:48
#   @FileRole: 提示词解耦


HEADER_ANALYZER_PROMPT_TEMPLATE = """请分析以下电子表格的头部，返回表头占据了前几行。
数字第一列是物理行号。表头可能是一行或多行合并。
===数据===
{md_table_str}
==========
请仅以JSON格式输出，不要输出任何推理过程，格式如：{{"header_row_count": 2, "boundary_row_idx": 3}}
注意：boundary_row_idx 是表头最后一行的物理行号。"""