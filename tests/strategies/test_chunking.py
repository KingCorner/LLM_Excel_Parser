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
    """使用 fixture 创建一个模拟的 StructuredTable 对象"""
    table = Mock()
    table.headers = ["ID", "Name", "Score"]
    # 构造了 5 行数据作为 body_rows
    table.body_rows = [
        [1, "Alice", 90],
        [2, "Bob", 85],
        [3, "Charlie", 92],
        [4, "David", 88],
        [5, "Eva", 95],
    ]
    return table


class TestFixedRowChunker:
    """测试固定行数分块逻辑"""

    def test_split_exact_multiple(self, mock_table):
        """测试整除情况：chunk_size 恰好能将数据均分（如设为 1）"""
        chunker = FixedRowChunker(chunk_size=1)
        chunks = chunker.split(mock_table)

        assert len(chunks) == 5
        # 验证提取出的第一块内容
        assert chunks[0]["headers"] == ["ID", "Name", "Score"]
        assert chunks[0]["data"] == [[1, "Alice", 90]]

    def test_split_with_remainder(self, mock_table):
        """测试存在余数的情况：最后一块数据长度小于 chunk_size"""
        chunker = FixedRowChunker(chunk_size=2)
        chunks = chunker.split(mock_table)

        # 5条数据按 size=2 切分，应分为 3 块 (2, 2, 1)
        assert len(chunks) == 3
        assert len(chunks[0]["data"]) == 2
        assert len(chunks[2]["data"]) == 1
        assert chunks[2]["data"] == [[5, "Eva", 95]]

    def test_split_empty_table(self):
        """测试空表格：没有 body_rows 时返回空列表"""
        empty_table = Mock()
        empty_table.headers = ["ID"]
        empty_table.body_rows = []

        chunker = FixedRowChunker(chunk_size=10)
        chunks = chunker.split(empty_table)

        assert chunks == []

    def test_split_chunk_size_larger_than_data(self, mock_table):
        """测试 chunk_size 大于数据总量时：只有 1 个 Chunk"""
        chunker = FixedRowChunker(chunk_size=100)
        chunks = chunker.split(mock_table)

        assert len(chunks) == 1
        assert len(chunks[0]["data"]) == 5


class TestTokenChunker:
    """测试基于 Token 的分块策略"""

    def test_token_chunker_raises_not_implemented(self, mock_table):
        """TokenChunker 目前应抛出未实现异常"""
        chunker = TokenChunker()

        with pytest.raises(NotImplementedError) as exc_info:
            chunker.split(mock_table)

        assert "Token级别的切片将在后续版本支持" in str(exc_info.value)
