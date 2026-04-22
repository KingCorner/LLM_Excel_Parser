#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 16:44
#   @FileRole:


import pytest
from unittest.mock import Mock

from llm_excel_parser.strategies.chunking import (
    FixedRowChunker,
    TokenChunker
)


@pytest.fixture
def mock_table():
    """创建一个模拟的 StructuredTable 对象，数据结构对齐 Phase 5 要求"""
    table = Mock()
    table.headers = [{"row": 1, "data": {1: "ID", 2: "Name", 3: "Score"}}]
    # 构造了 5 行标准数据
    table.body_rows = [
        {"row": 2, "data": {1: 1, 2: "Alice", 3: 90}},
        {"row": 3, "data": {1: 2, 2: "Bob", 3: 85}},
        {"row": 4, "data": {1: 3, 2: "Charlie", 3: 92}},
        {"row": 5, "data": {1: 4, 2: "David", 3: 88}},
        {"row": 6, "data": {1: 5, 2: "Eva", 3: 95}},
    ]
    table.max_col = 3
    return table


class TestFixedRowChunker:
    """测试固定行数分块逻辑"""

    def test_split_exact_multiple(self, mock_table):
        """测试整除情况：chunk_size 恰好能将数据均分（如设为 1）"""
        chunker = FixedRowChunker(chunk_size=1, min_tail_rows=0)
        batches = chunker.split(mock_table)

        assert len(batches) == 5
        # 验证提取出的第一块内容是否为单行字典
        assert len(batches[0]) == 1
        assert batches[0][0]["data"][2] == "Alice"

    def test_split_with_tail_merge(self, mock_table):
        """测试尾部碎片合并逻辑 (min_tail_rows)"""
        # 5条数据, 按 size=2 切分, 正常是 [2, 2, 1]
        # 但是设 min_tail_rows=2, 那么最后 1 条会被吸收到上一块, 变成 [2, 3]
        chunker = FixedRowChunker(chunk_size=2, min_tail_rows=2)
        batches = chunker.split(mock_table)

        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 3  # 合并了尾部
        assert batches[1][-1]["data"][2] == "Eva"

    def test_split_empty_table(self):
        """测试空表格：没有 body_rows 时返回空列表"""
        empty_table = Mock()
        empty_table.body_rows = []

        chunker = FixedRowChunker(chunk_size=10)
        assert chunker.split(empty_table) == []

    def test_split_chunk_size_larger_than_data(self, mock_table):
        """测试 chunk_size 大于数据总量时：只有 1 个 Chunk"""
        chunker = FixedRowChunker(chunk_size=100)
        batches = chunker.split(mock_table)

        assert len(batches) == 1
        assert len(batches[0]) == 5


class TestTokenChunker:
    """测试基于 Token 的分块策略"""

    def test_token_limit_split(self, mock_table):
        """测试到达 token 阈值后正常切块"""
        # 单行渲染后大约是 "行2 | 1 | Alice | 90" (约 20 字符 = 10 Token)
        # 如果设置 max_tokens=25, 基础base=0，那么一个 chunk 最多放 2 行 (20 Token)
        chunker = TokenChunker(max_tokens=25)
        batches = chunker.split(mock_table, base_tokens=0)

        # 5 行数据，每 2 行一切，应分为 [2, 2, 1] 也就是 3 块
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    def test_token_limit_with_huge_base_tokens(self, mock_table):
        """测试 base_tokens 很大导致单行就超标的情况"""
        # 如果表头(base_tokens)极大, 每一行都会触发强制新建立 Chunk
        chunker = TokenChunker(max_tokens=10)
        batches = chunker.split(mock_table, base_tokens=100)

        # 强制单行切块
        assert len(batches) == 5
        assert len(batches[0]) == 1
