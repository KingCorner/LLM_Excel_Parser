#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/25
#   @FileRole: 针对 config-cleanup 重构的单元测试
#              覆盖：ChunkStrategy 枚举、config 常量引用、phase5 字符串兼容、CHUNKER_REGISTRY 新 key

import pytest
from unittest.mock import patch

from llm_excel_parser.core.enums import ChunkStrategy
from llm_excel_parser.config import default_config
from llm_excel_parser.strategies.chunking import (
    FixedRowChunker, TokenChunker, CHUNKER_REGISTRY
)
from llm_excel_parser.pipeline.phase5_chunker import ChunkAssembler
from llm_excel_parser.core.datatypes import StructuredTable
from llm_excel_parser.core.exceptions import ChunkingError
from llm_excel_parser.utils.formatters import (
    render_chunk_header, render_chunk_row, build_chunk_context, rows_dict_to_markdown_table
)


# ===== fixtures =====

@pytest.fixture
def simple_table() -> StructuredTable:
    return StructuredTable(
        filename="data.xlsx",
        sheetname="Sheet1",
        headers=[{"row": 1, "data": {1: "Name", 2: "Score"}}],
        body_rows=[
            {"row": 2, "data": {1: "Alice", 2: 90}},
            {"row": 3, "data": {1: "Bob",   2: 85}},
        ],
        max_col=2,
        box_range="A1:B3",
    )


# ===== ChunkStrategy 枚举 =====

class TestChunkStrategyEnum:

    def test_values_match_legacy_strings(self):
        """枚举值必须与旧字符串字面量完全一致，保证向后兼容"""
        assert ChunkStrategy.FIXED_ROW.value == "fixed_row"
        assert ChunkStrategy.TOKEN_LIMIT.value == "token_limit"

    def test_construct_from_string(self):
        """ChunkStrategy("fixed_row") 应能构造出对应枚举成员"""
        assert ChunkStrategy("fixed_row") is ChunkStrategy.FIXED_ROW
        assert ChunkStrategy("token_limit") is ChunkStrategy.TOKEN_LIMIT

    def test_invalid_string_raises(self):
        """非法字符串应抛出 ValueError（枚举自身行为）"""
        with pytest.raises(ValueError):
            ChunkStrategy("unknown_strategy")


# ===== CHUNKER_REGISTRY 以枚举为 key =====

class TestChunkerRegistry:

    def test_registry_keys_are_enum(self):
        """CHUNKER_REGISTRY 的 key 必须是 ChunkStrategy 枚举，不能是字符串"""
        for key in CHUNKER_REGISTRY:
            assert isinstance(key, ChunkStrategy), f"key {key!r} 不是 ChunkStrategy 枚举"

    def test_registry_contains_all_strategies(self):
        """所有 ChunkStrategy 成员都应在注册表中"""
        for member in ChunkStrategy:
            assert member in CHUNKER_REGISTRY, f"{member} 未注册到 CHUNKER_REGISTRY"

    def test_registry_maps_to_correct_classes(self):
        assert CHUNKER_REGISTRY[ChunkStrategy.FIXED_ROW] is FixedRowChunker
        assert CHUNKER_REGISTRY[ChunkStrategy.TOKEN_LIMIT] is TokenChunker


# ===== config 常量被正确引用 =====

class TestConfigConstants:

    def test_fixed_row_chunker_default_uses_config(self):
        """FixedRowChunker 默认参数应来自 config，而非硬编码"""
        chunker = FixedRowChunker()
        assert chunker.chunk_size == default_config.DEFAULT_CHUNK_SIZE
        assert chunker.min_tail_rows == default_config.DEFAULT_MIN_TAIL_ROWS

    def test_token_chunker_default_uses_config(self):
        """TokenChunker 默认参数应来自 config，而非硬编码"""
        chunker = TokenChunker()
        assert chunker.max_tokens == default_config.DEFAULT_MAX_TOKENS

    def test_token_conversion_ratio_used_in_chunker(self):
        """TokenChunker 的 token 估算系数应与 config.TOKEN_CONVERSION_RATIO 一致"""
        import math
        from unittest.mock import Mock
        table = Mock()
        row = {"row": 1, "data": {1: "hello"}}
        table.body_rows = [row]
        table.max_col = 1

        from llm_excel_parser.utils.formatters import render_chunk_row
        row_str = render_chunk_row(row, 1)
        expected_tokens = math.ceil(len(row_str) * default_config.TOKEN_CONVERSION_RATIO)

        # max_tokens 恰好等于 expected_tokens，这一行不会被切走
        chunker = TokenChunker(max_tokens=expected_tokens + 1)
        batches = chunker.split(table, base_tokens=0)
        assert len(batches) == 1

    def test_separator_width_used_in_build_chunk_context(self):
        """build_chunk_context 的分隔线宽度应来自 config.SEPARATOR_WIDTH"""
        from unittest.mock import Mock
        table = Mock()
        table.filename = "f.xlsx"
        table.sheetname = "S1"
        table.max_col = 1
        batch = [{"row": 1, "data": {1: "v"}}]

        context = build_chunk_context(table, batch, "表头 | H", 1, 1)
        expected_sep = "-" * default_config.SEPARATOR_WIDTH
        assert expected_sep in context

    def test_pipe_escape_used_in_markdown_table(self):
        """管道符转义字符应来自 config.MARKDOWN_PIPE_ESCAPE，原始半角 | 不出现在单元格内容中"""
        rows_dict = {1: {1: {"value": "A|B"}}}
        result = rows_dict_to_markdown_table(rows_dict, [1], 1)
        # 转义符（全角）应出现在输出中
        assert default_config.MARKDOWN_PIPE_ESCAPE in result
        # 单元格内容 "A|B" 的原始半角 | 应已被替换为全角；结果中应含 "A｜B"
        assert "A｜B" in result
        assert "A|B" not in result

    def test_pipe_escape_used_in_render_chunk_row(self):
        """render_chunk_row 的管道符转义应来自 config.MARKDOWN_PIPE_ESCAPE"""
        row = {"row": 1, "data": {1: "X|Y"}}
        result = render_chunk_row(row, 1)
        assert default_config.MARKDOWN_PIPE_ESCAPE in result

    def test_header_base_tokens_used_in_render_chunk_header(self):
        """render_chunk_header 的基础 token 预留应来自 config.HEADER_BASE_TOKENS"""
        import math
        from unittest.mock import Mock
        table = Mock()
        table.max_col = 1
        table.headers = [{"row": 1, "data": {1: "X"}}]

        header_str, base_tokens = render_chunk_header(table)
        expected = math.ceil(len(header_str) * default_config.TOKEN_CONVERSION_RATIO) + default_config.HEADER_BASE_TOKENS
        assert base_tokens == expected


# ===== phase5_chunker 字符串兼容性 =====

class TestPhase5ChunkerCompatibility:

    def test_accepts_string_fixed_row(self, simple_table):
        """phase5 应向后兼容，仍接受字符串 'fixed_row'"""
        chunks = ChunkAssembler.execute_chunking(simple_table, strategy="fixed_row")
        assert len(chunks) > 0
        assert chunks[0].metadata["strategy"] == "fixed_row"

    def test_accepts_string_token_limit(self, simple_table):
        """phase5 应向后兼容，仍接受字符串 'token_limit'"""
        chunks = ChunkAssembler.execute_chunking(simple_table, strategy="token_limit", max_tokens=9999)
        assert len(chunks) > 0
        assert chunks[0].metadata["strategy"] == "token_limit"

    def test_accepts_enum_fixed_row(self, simple_table):
        """phase5 应接受 ChunkStrategy 枚举入参"""
        chunks = ChunkAssembler.execute_chunking(simple_table, strategy=ChunkStrategy.FIXED_ROW)
        assert chunks[0].metadata["strategy"] == "fixed_row"

    def test_accepts_enum_token_limit(self, simple_table):
        """phase5 应接受 ChunkStrategy.TOKEN_LIMIT 枚举入参"""
        chunks = ChunkAssembler.execute_chunking(simple_table, strategy=ChunkStrategy.TOKEN_LIMIT, max_tokens=9999)
        assert chunks[0].metadata["strategy"] == "token_limit"

    def test_invalid_string_raises_chunking_error(self, simple_table):
        """非法策略字符串应抛出 ChunkingError（而非 ValueError）"""
        with pytest.raises(ChunkingError):
            ChunkAssembler.execute_chunking(simple_table, strategy="no_such_strategy")

    def test_metadata_strategy_is_string_not_enum(self, simple_table):
        """metadata['strategy'] 应存储字符串值，而非枚举对象（便于 JSON 序列化）"""
        chunks = ChunkAssembler.execute_chunking(simple_table, strategy=ChunkStrategy.FIXED_ROW)
        assert isinstance(chunks[0].metadata["strategy"], str)