#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/25
#   @FileRole: orchestrator 单元测试

import io
import pytest
from unittest.mock import MagicMock, patch, call

from llm_excel_parser.core.datatypes import BoundingBox, StructuredTable, ExcelChunk
from llm_excel_parser.core.interfaces import BaseWorksheet
from llm_excel_parser.core.enums import MergeAction
from llm_excel_parser.pipeline.orchestrator import _matrix_to_cell_data, process_excel


# ========== 辅助工厂 ==========

def make_ws(
    title: str = "Sheet1",
    hidden_rows: set = None,
    hidden_cols: set = None,
    style_map: dict = None,
    has_get_cell_style: bool = True,
) -> MagicMock:
    """构造符合 BaseWorksheet 协议的 Mock 工作表。

    has_get_cell_style=True  → 使用 spec=BaseWorksheet（接口已声明 get_cell_style）。
    has_get_cell_style=False → 使用不含 get_cell_style 的显式 spec 列表，
                               模拟未升级接口的旧适配器（orchestrator 的 hasattr 兜底路径）。
    """
    hidden_rows = hidden_rows or set()
    hidden_cols = hidden_cols or set()
    style_map = style_map or {}

    if has_get_cell_style:
        ws = MagicMock(spec=BaseWorksheet)
        ws.get_cell_style.side_effect = lambda r, c: style_map.get((r, c), {})
    else:
        # 不含 get_cell_style，令 hasattr 返回 False
        _legacy_spec = [
            'title', 'max_dimensions', 'get_cell_value',
            'iter_rows', 'get_merged_regions', 'is_row_hidden', 'is_col_hidden',
        ]
        ws = MagicMock(spec=_legacy_spec)

    ws.title = title
    ws.is_row_hidden.side_effect = lambda r: r in hidden_rows
    ws.is_col_hidden.side_effect = lambda c: c in hidden_cols

    return ws


def make_box(min_row=1, max_row=2, min_col=1, max_col=2) -> BoundingBox:
    return BoundingBox(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col)


def make_structured_table(filename="t.xlsx", sheetname="S1") -> StructuredTable:
    return StructuredTable(
        filename=filename,
        sheetname=sheetname,
        headers=[{"row": 1, "data": {1: "A"}}],
        body_rows=[{"row": 2, "data": {1: "v"}}],
        max_col=1,
        box_range="A1:A2",
    )


def make_chunk(chunk_id="abcd1234") -> ExcelChunk:
    return ExcelChunk(
        chunk_id=chunk_id,
        metadata={"strategy": "fixed_row"},
        formatted_context="ctx",
        raw_data=[],
    )


# ========== _matrix_to_cell_data 测试 ==========

class TestMatrixToCellData:

    def test_basic_coordinate_mapping(self):
        """矩阵值正确映射到物理行列坐标"""
        ws = make_ws()
        box = make_box(min_row=2, max_row=3, min_col=3, max_col=4)
        matrix = [["A", "B"], ["C", "D"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert len(cells) == 4
        assert cells[0] == {"row": 2, "column": 3, "value": "A", "style": {}}
        assert cells[1] == {"row": 2, "column": 4, "value": "B", "style": {}}
        assert cells[2] == {"row": 3, "column": 3, "value": "C", "style": {}}
        assert cells[3] == {"row": 3, "column": 4, "value": "D", "style": {}}

    def test_hidden_rows_excluded_by_default(self):
        """include_hidden_rows=False 时应跳过隐藏行"""
        ws = make_ws(hidden_rows={2})
        box = make_box(min_row=1, max_row=3, min_col=1, max_col=1)
        # 行1、行2(隐藏)、行3  → 矩阵只有可见的 2 行
        matrix = [["visible_r1"], ["visible_r3"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=False)

        rows = [c["row"] for c in cells]
        assert 2 not in rows, "隐藏行不应出现在输出中"
        assert rows == [1, 3]

    def test_hidden_rows_included_when_flag_true(self):
        """include_hidden_rows=True 时隐藏行应被纳入"""
        ws = make_ws(hidden_rows={2})
        box = make_box(min_row=1, max_row=2, min_col=1, max_col=1)
        matrix = [["r1"], ["r2_hidden"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert [c["row"] for c in cells] == [1, 2]

    def test_hidden_cols_excluded(self):
        """隐藏列应在 ignore_hidden=True 时被跳过"""
        ws = make_ws(hidden_cols={2})
        box = make_box(min_row=1, max_row=1, min_col=1, max_col=3)
        # 可见列: 1, 3 → 矩阵有 2 列
        matrix = [["col1_val", "col3_val"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=False)

        cols = [c["column"] for c in cells]
        assert 2 not in cols
        assert cols == [1, 3]

    def test_style_injected_from_get_cell_style(self):
        """当适配器实现 get_cell_style 时，样式应注入到 CellData"""
        style = {"is_bold": True, "has_bg": False}
        ws = make_ws(style_map={(1, 1): style})
        box = make_box(min_row=1, max_row=1, min_col=1, max_col=1)
        matrix = [["val"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert cells[0]["style"] == style

    def test_no_get_cell_style_fallback_to_empty_dict(self):
        """旧适配器未实现 get_cell_style（接口升级前）时，style 应兜底为空字典"""
        ws = make_ws(has_get_cell_style=False)
        box = make_box(min_row=1, max_row=1, min_col=1, max_col=1)
        matrix = [["val"]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert cells[0]["style"] == {}

    def test_matrix_shorter_than_visible_rows(self):
        """矩阵行数少于可见行时，多余的可见行应被忽略，不抛异常"""
        ws = make_ws()
        box = make_box(min_row=1, max_row=3, min_col=1, max_col=1)
        matrix = [["only_row1"]]  # 只有 1 行，但可见行有 3 行

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert len(cells) == 1
        assert cells[0]["row"] == 1

    def test_row_shorter_than_visible_cols(self):
        """矩阵某行列数少于可见列时，多余的列应被忽略，不抛异常"""
        ws = make_ws()
        box = make_box(min_row=1, max_row=1, min_col=1, max_col=3)
        matrix = [["only_col1"]]  # 只有 1 列，但可见列有 3 列

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert len(cells) == 1
        assert cells[0]["column"] == 1

    def test_empty_matrix_returns_empty_list(self):
        """空矩阵应返回空列表"""
        ws = make_ws()
        box = make_box()
        cells = _matrix_to_cell_data(ws, box, [], include_hidden_rows=True)
        assert cells == []

    def test_none_value_preserved(self):
        """矩阵中的 None 值应原样保留在 CellData.value 中"""
        ws = make_ws()
        box = make_box(min_row=1, max_row=1, min_col=1, max_col=1)
        matrix = [[None]]

        cells = _matrix_to_cell_data(ws, box, matrix, include_hidden_rows=True)

        assert cells[0]["value"] is None


# ========== process_excel 测试 ==========

PATCH_LOADER = "llm_excel_parser.pipeline.orchestrator.SecureLoader.check_dimensions_and_route"
PATCH_DETECTOR = "llm_excel_parser.pipeline.orchestrator.StructureDetector.detect_tables"
PATCH_RENDERER = "llm_excel_parser.pipeline.orchestrator.DataRenderer.render_box"
PATCH_HEADER = "llm_excel_parser.pipeline.orchestrator.HeaderAnalyzer.analyze"
PATCH_CHUNKER = "llm_excel_parser.pipeline.orchestrator.ChunkAssembler.execute_chunking"


@pytest.fixture
def mock_pipeline(request):
    """批量 patch 整条流水线，各阶段返回可覆盖的默认值。"""
    ws = make_ws("Sheet1")
    box = make_box(min_row=1, max_row=2, min_col=1, max_col=2)
    structured = make_structured_table()
    chunk = make_chunk()

    with (
        patch(PATCH_LOADER, return_value=[ws]) as mock_loader,
        patch(PATCH_DETECTOR, return_value=[box]) as mock_detector,
        patch(PATCH_RENDERER, return_value=[["v1", "v2"], ["v3", "v4"]]) as mock_renderer,
        patch(PATCH_HEADER, return_value=structured) as mock_header,
        patch(PATCH_CHUNKER, return_value=[chunk]) as mock_chunker,
    ):
        yield {
            "ws": ws,
            "box": box,
            "structured": structured,
            "chunk": chunk,
            "loader": mock_loader,
            "detector": mock_detector,
            "renderer": mock_renderer,
            "header": mock_header,
            "chunker": mock_chunker,
        }


class TestProcessExcel:

    def test_happy_path_returns_chunks(self, mock_pipeline):
        """标准路径：单 Sheet 单 Box，应返回来自 Phase 5 的所有 Chunks"""
        result = process_excel("workbook.xlsx")

        assert len(result) == 1
        assert result[0] is mock_pipeline["chunk"]

    def test_all_phases_called_once(self, mock_pipeline):
        """每个 Phase 在单 Sheet 单 Box 的情况下应各被调用一次"""
        process_excel("workbook.xlsx")

        mock_pipeline["loader"].assert_called_once()
        mock_pipeline["detector"].assert_called_once()
        mock_pipeline["renderer"].assert_called_once()
        mock_pipeline["header"].assert_called_once()
        mock_pipeline["chunker"].assert_called_once()

    def test_filename_extracted_from_path(self, mock_pipeline):
        """当 source 为路径字符串时，Phase 4 应收到正确的文件名（不含目录）"""
        process_excel("/some/path/to/report.xlsx")

        _, kwargs = mock_pipeline["header"].call_args
        assert kwargs.get("filename") == "report.xlsx" or \
               mock_pipeline["header"].call_args[0][0] == "report.xlsx"

    def test_filename_is_stream_input_for_bytes(self, mock_pipeline):
        """当 source 为 bytes 时，filename 应为 'stream_input_excel'"""
        process_excel(b"\x50\x4B\x03\x04")

        call_args = mock_pipeline["header"].call_args
        filename_arg = call_args[1].get("filename") or call_args[0][0]
        assert filename_arg == "stream_input_excel"

    def test_filename_is_stream_input_for_binary_io(self, mock_pipeline):
        """当 source 为 BinaryIO 时，filename 应为 'stream_input_excel'"""
        process_excel(io.BytesIO(b"\x50\x4B\x03\x04"))

        call_args = mock_pipeline["header"].call_args
        filename_arg = call_args[1].get("filename") or call_args[0][0]
        assert filename_arg == "stream_input_excel"

    def test_empty_sheet_skipped(self, mock_pipeline):
        """Phase 2 未检测到任何 Box 时，该 Sheet 应被跳过，返回空列表"""
        mock_pipeline["detector"].return_value = []

        result = process_excel("workbook.xlsx")

        assert result == []
        mock_pipeline["renderer"].assert_not_called()
        mock_pipeline["header"].assert_not_called()
        mock_pipeline["chunker"].assert_not_called()

    def test_multiple_sheets_aggregated(self, mock_pipeline):
        """多 Sheet 时，所有 Sheet 的 Chunks 应被合并到同一列表返回"""
        ws1 = make_ws("Sheet1")
        ws2 = make_ws("Sheet2")
        mock_pipeline["loader"].return_value = [ws1, ws2]
        mock_pipeline["chunker"].return_value = [make_chunk("aaa"), make_chunk("bbb")]

        result = process_excel("workbook.xlsx")

        # 每个 Sheet 各产出 2 个 Chunk，共 4 个
        assert len(result) == 4

    def test_multiple_boxes_in_one_sheet(self, mock_pipeline):
        """单 Sheet 含多个 Box 时，Sheet 名应加 _T1/_T2 后缀"""
        box1 = make_box(min_row=1, max_row=2, min_col=1, max_col=2)
        box2 = make_box(min_row=5, max_row=6, min_col=1, max_col=2)
        mock_pipeline["detector"].return_value = [box1, box2]

        process_excel("workbook.xlsx")

        # Phase 4 应被调用两次，Sheet 名分别为 _T1, _T2
        assert mock_pipeline["header"].call_count == 2
        calls = mock_pipeline["header"].call_args_list
        sheetnames = [c[1].get("sheetname") or c[0][1] for c in calls]
        assert any("_T1" in s for s in sheetnames)
        assert any("_T2" in s for s in sheetnames)

    def test_single_box_sheet_name_not_suffixed(self, mock_pipeline):
        """单 Sheet 仅含一个 Box 时，Sheet 名不应追加 _T1 后缀"""
        process_excel("workbook.xlsx")

        call_args = mock_pipeline["header"].call_args
        sheetname_arg = call_args[1].get("sheetname") or call_args[0][1]
        assert "_T" not in sheetname_arg

    def test_box_range_set_on_structured_table(self, mock_pipeline):
        """process_excel 应将 BoundingBox.range_str 写入 structured_table.box_range"""
        box = mock_pipeline["box"]
        structured = mock_pipeline["structured"]

        process_excel("workbook.xlsx")

        assert structured.box_range == box.range_str

    def test_merge_action_forwarded_to_renderer(self, mock_pipeline):
        """merge_action 参数应原样传递给 DataRenderer.render_box"""
        process_excel("workbook.xlsx", merge_action=MergeAction.TOP_LEFT)

        _, kwargs = mock_pipeline["renderer"].call_args
        assert kwargs.get("action") == MergeAction.TOP_LEFT

    def test_chunk_strategy_forwarded_to_chunker(self, mock_pipeline):
        """chunk_strategy 参数应传递给 ChunkAssembler.execute_chunking"""
        process_excel("workbook.xlsx", chunk_strategy="token_limit", max_tokens=500)

        _, kwargs = mock_pipeline["chunker"].call_args
        assert kwargs.get("strategy") == "token_limit"
        assert kwargs.get("max_tokens") == 500

    def test_loader_config_includes_security_limits(self, mock_pipeline):
        """max_rows / max_cols / include_hidden_rows 应传入 Phase 1 配置"""
        process_excel("workbook.xlsx", max_rows=5000, max_cols=100, include_hidden_rows=True)

        _, kwargs = mock_pipeline["loader"].call_args
        config = kwargs.get("loader_config") or mock_pipeline["loader"].call_args[0][1]
        assert config["max_rows"] == 5000
        assert config["max_cols"] == 100
        assert config["include_hidden_rows"] is True

    def test_llm_service_forwarded_to_header_analyzer(self, mock_pipeline):
        """llm_service 和 use_llm_layout_analyzer 应透传到 Phase 4"""
        mock_llm = MagicMock()
        process_excel("workbook.xlsx", use_llm_layout_analyzer=True, llm_service=mock_llm)

        _, kwargs = mock_pipeline["header"].call_args
        assert kwargs.get("use_llm_layout_analyzer") is True
        assert kwargs.get("llm_service") is mock_llm

    def test_custom_keywords_forwarded_to_header_analyzer(self, mock_pipeline):
        """custom_header_keywords 应透传到 Phase 4"""
        kw = ["编号", "金额"]
        process_excel("workbook.xlsx", custom_header_keywords=kw)

        _, kwargs = mock_pipeline["header"].call_args
        assert kwargs.get("custom_header_keywords") == kw

    def test_returns_empty_list_for_empty_file(self, mock_pipeline):
        """Phase 1 返回空 Sheet 列表时，最终结果应为空列表"""
        mock_pipeline["loader"].return_value = []

        result = process_excel("empty.xlsx")

        assert result == []
