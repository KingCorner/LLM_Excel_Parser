#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 20:40
#   @FileRole: formatters 单元测试


import datetime
import pytest
from unittest.mock import Mock
from llm_excel_parser.utils.formatters import (
    format_cell_value,
    rows_dict_to_markdown_table,
    render_chunk_header,
    render_chunk_row,
    build_chunk_context
)


class TestFormatCellValue:
    """针对 format_cell_value 的单元测试"""

    def test_none_value(self):
        """测试 None 值"""
        assert format_cell_value(None) is None

    def test_number_formatting(self):
        """测试数字格式化 (尤其是 x.0 抹平逻辑)"""
        assert format_cell_value(42) == 42
        assert format_cell_value(42.0) == 42  # 应该被抹平转化成 int
        assert type(format_cell_value(42.0)) is int
        assert format_cell_value(42.5) == 42.5  # 真实的浮点数应保持不变
        assert type(format_cell_value(42.5)) is float

    def test_string_formatting(self):
        """测试字符串清洗逻辑"""
        assert format_cell_value("  hello world  ") == "hello world"  # 去除首尾空格
        assert format_cell_value("\n\t\r") is None  # 纯空白字符应等效转化为 None
        assert format_cell_value("") is None  # 空字符串转化为 None

    def test_datetime_formatting(self):
        """测试日期时间序列化逻辑"""
        # 1. 含有时分秒的 datetime
        dt_with_time = datetime.datetime(2026, 4, 16, 20, 30, 45)
        assert format_cell_value(dt_with_time) == "2026-04-16 20:30:45"

        # 2. 只有日期的 datetime (来自 openpyxl 常见行为)
        dt_date_only = datetime.datetime(2026, 4, 16, 0, 0, 0)
        assert format_cell_value(dt_date_only) == "2026-04-16"

        # 3. 纯 date 对象
        pure_date = datetime.date(2026, 4, 16)
        assert format_cell_value(pure_date) == "2026-04-16"

        # 4. 纯 time 对象
        pure_time = datetime.time(20, 30, 45)
        assert format_cell_value(pure_time) == "20:30:45"

    def test_fallback_type(self):
        """测试其他类型兜底 (原样返回)"""
        assert format_cell_value(True) is True
        assert format_cell_value(False) is False
        assert format_cell_value(["list"]) == ["list"]


class TestRowsDictToMarkdownTable:
    """针对 rows_dict_to_markdown_table 的单元测试"""

    def test_normal_dict_conversion(self):
        """测试标准的二维字典转化为 Markdown 表格"""
        rows_dict = {
            1: {1: {"value": "ID"}, 2: {"value": "Name"}},
            2: {1: {"value": 1001}, 2: {"value": "Alice"}}
        }
        scan_indices = [1, 2]
        max_col = 2

        expected = (
            "1 | ID | Name |\n"
            "2 | 1001 | Alice |"
        )
        assert rows_dict_to_markdown_table(rows_dict, scan_indices, max_col) == expected

    def test_missing_columns_and_rows(self):
        """测试列数据缺失/空缺时的处理 (应填补为空字符串)"""
        # 第一行只有第1列和第3列有数据，第二行缺失
        rows_dict = {
            1: {1: {"value": "A"}, 3: {"value": "C"}},
            3: {1: {"value": "X"}}
        }
        # 假设我们只扫描 第1和第2行，且 max_col=3
        scan_indices = [1, 2]
        max_col = 3

        expected = (
            "1 | A |  | C |\n"  # 中间的 2 列缺失，应当为空白
            "2 |  |  |  |"  # 第2行整体在字典里不存在，应全为空
        )
        assert rows_dict_to_markdown_table(rows_dict, scan_indices, max_col) == expected

    def test_pipe_character_escape(self):
        """测试防破坏机制：替换内部的管道符 |"""
        rows_dict = {
            1: {1: {"value": "Hello | World"}}  # 单元格内容自带了 |
        }
        scan_indices = [1]
        max_col = 1

        # 半角的 | 应当被替换成了全角的 ｜
        expected = "1 | Hello ｜ World |"
        result = rows_dict_to_markdown_table(rows_dict, scan_indices, max_col)
        assert result == expected


class TestPhase5Formatters:
    """针对 Phase 5 新增渲染逻辑的单元测试"""

    def test_render_chunk_header_normal(self):
        """正常表头的渲染与估算"""
        mock_table = Mock()
        mock_table.max_col = 2
        mock_table.headers = [
            {"row": 1, "data": {1: "ID", 2: "Name"}}
        ]

        header_str, base_tokens = render_chunk_header(mock_table)
        assert header_str == "表头 | ID | Name"
        # 字符长度 14 -> 7 tokens + 50 基础预留 = 57
        assert base_tokens == 57

    def test_render_chunk_header_empty(self):
        """无表头时的降级处理"""
        mock_table = Mock()
        mock_table.headers = []

        header_str, base_tokens = render_chunk_header(mock_table)
        assert header_str == "表头 | (无表头数据)"
        assert base_tokens == 5

    def test_render_chunk_row(self):
        """单行数据渲染及破坏字符替换"""
        row_record = {
            "row": 5,
            "data": {1: "Hello\nWorld", 2: "A|B"}
        }
        res = render_chunk_row(row_record, max_col=2)
        # \n 被替换为空格，| 被替换为全角 ｜
        assert res == "行5 | Hello World | A｜B"

    def test_build_chunk_context(self):
        """整体 Markdown 上下文组装测试"""
        mock_table = Mock()
        mock_table.filename = "test.xlsx"
        mock_table.sheetname = "Sheet1"
        mock_table.max_col = 1

        batch = [
            {"row": 10, "data": {1: "Row10"}},
            {"row": 11, "data": {1: "Row11"}}
        ]

        context = build_chunk_context(
            table=mock_table,
            batch=batch,
            header_str="表头 | Data",
            current_chunk_idx=1,
            total_chunks=3
        )

        # 验证必需的上下文提示词都在
        assert "=== 电子表格数据片段 (1/3) ===" in context
        assert "文件名: test.xlsx" in context
        assert "行号范围: 10 ~ 11" in context
        assert "表头 | Data" in context
        assert "行10 | Row10" in context
        assert "行11 | Row11" in context
