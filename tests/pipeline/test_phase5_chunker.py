#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/22 19:36
#   @FileRole:


import pytest
from llm_excel_parser.core.datatypes import StructuredTable, ExcelChunk
from llm_excel_parser.pipeline.phase5_chunker import ChunkAssembler


@pytest.fixture
def sample_structured_table() -> StructuredTable:
    """提供一个真实的 StructuredTable 数据类实例"""
    return StructuredTable(
        filename="financial.xlsx",
        sheetname="Q1_Report",
        headers=[{"row": 1, "data": {1: "Date", 2: "Revenue"}}],
        body_rows=[
            {"row": 2, "data": {1: "Jan", 2: 1000}},
            {"row": 3, "data": {1: "Feb", 2: 2000}},
            {"row": 4, "data": {1: "Mar", 2: 3000}},
        ],
        max_col=2,
        box_range="A1:B4"
    )


class TestChunkAssembler:
    """Phase 5 流水线协调器测试"""

    def test_empty_table(self):
        """无数据行时应直接返回空列表"""
        empty_table = StructuredTable("test.xlsx", "s1", [], [], 0)
        chunks = ChunkAssembler.execute_chunking(empty_table)
        assert chunks == []

    def test_invalid_strategy(self, sample_structured_table):
        """传入不支持的策略应抛出 ValueError"""
        with pytest.raises(ValueError) as exc:
            ChunkAssembler.execute_chunking(
                sample_structured_table,
                strategy="magic_split"  # type: ignore
            )
        assert "不受支持的切片策略" in str(exc.value)

    def test_fixed_row_pipeline(self, sample_structured_table):
        """端到端测试：按固定行切片流水线"""
        # 3行数据，每块1行，应生成 3 个 Chunk (min_tail_rows=0防止合并)
        chunks = ChunkAssembler.execute_chunking(
            sample_structured_table,
            strategy="fixed_row",
            chunk_row_size=1,
            min_tail_rows=0
        )

        assert len(chunks) == 3

        # 抽查第一个 Chunk 的封装协议是否标准
        chunk0 = chunks[0]
        assert isinstance(chunk0, ExcelChunk)
        assert len(chunk0.chunk_id) == 8  # uuid hex

        # 检查 Metadata
        assert chunk0.metadata["filename"] == "financial.xlsx"
        assert chunk0.metadata["strategy"] == "fixed_row"
        assert chunk0.metadata["chunk_index"] == 1
        assert chunk0.metadata["total_chunks"] == 3
        assert chunk0.metadata["start_row"] == 2
        assert chunk0.metadata["end_row"] == 2
        assert "approx_tokens" in chunk0.metadata

        # 检查上下文和纯数据
        assert "行2 | Jan | 1000" in chunk0.formatted_context
        assert len(chunk0.raw_data) == 1
        assert chunk0.raw_data[0]["row"] == 2

    def test_token_limit_pipeline(self, sample_structured_table):
        """端到端测试：按 Token 切片流水线"""
        # 设置一个极端的 max_tokens 迫使它单行切分
        chunks = ChunkAssembler.execute_chunking(
            sample_structured_table,
            strategy="token_limit",
            max_tokens=5
        )

        # 3行数据，应当被切得非常细
        assert len(chunks) > 1
        assert chunks[0].metadata["strategy"] == "token_limit"
        assert "=== 电子表格数据片段" in chunks[0].formatted_context
