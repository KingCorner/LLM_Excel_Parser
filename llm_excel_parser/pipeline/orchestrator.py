#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:03
#   @FileRole: 流水线总调度器 (统筹 Phase 1 ~ 5)

import os
from typing import Union, BinaryIO, Optional, List, Any

from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.enums import MergeAction, ChunkStrategy
from llm_excel_parser.core.datatypes import ExcelChunk, CellData, BoundingBox
from llm_excel_parser.core.interfaces import BaseWorksheet

from llm_excel_parser.pipeline.phase1_loader import SecureLoader
from llm_excel_parser.pipeline.phase2_detector import StructureDetector
from llm_excel_parser.pipeline.phase3_renderer import DataRenderer
from llm_excel_parser.pipeline.phase4_header import HeaderAnalyzer
from llm_excel_parser.pipeline.phase5_chunker import ChunkAssembler

logger = get_logger("orchestrator")


def _matrix_to_cell_data(
        ws: BaseWorksheet,
        box: BoundingBox,
        rendered_matrix: List[List[Any]],
        include_hidden_rows: bool
) -> List[CellData]:
    """将 Phase 3 产出的二维值矩阵映射回含物理坐标的 CellData 列表。

    Phase 3 在构建矩阵时跳过了隐藏行/列，此处以相同规则重建行列索引映射，
    确保 row/column 字段与 Excel 物理坐标严格一致。
    样式读取依赖适配器是否实现 get_cell_style；若未实现则以空字典兜底，
    启发式表头打分的样式特征不生效但不影响整体流程。
    """
    ignore_hidden = not include_hidden_rows
    visible_rows = [r for r in range(box.min_row, box.max_row + 1)
                    if not (ignore_hidden and ws.is_row_hidden(r))]
    visible_cols = [c for c in range(box.min_col, box.max_col + 1)
                    if not (ignore_hidden and ws.is_col_hidden(c))]

    cell_data: List[CellData] = []
    for i, r in enumerate(visible_rows):
        if i >= len(rendered_matrix):
            break
        row_vals = rendered_matrix[i]
        for j, c in enumerate(visible_cols):
            if j >= len(row_vals):
                break
            style = ws.get_cell_style(r, c) if hasattr(ws, 'get_cell_style') else {}
            cell_data.append({'row': r, 'column': c, 'value': row_vals[j], 'style': style})

    return cell_data


def process_excel(
        source: Union[str, bytes, BinaryIO],
        merge_action: MergeAction = MergeAction.FILL_FORWARD,
        chunk_strategy: Union[str, ChunkStrategy] = ChunkStrategy.FIXED_ROW,
        chunk_size: int = 50,
        max_tokens: int = 2000,
        max_rows: int = 100000,
        max_cols: int = 2000,
        include_hidden_rows: bool = False,
        use_llm_layout_analyzer: bool = False,
        llm_service: Optional[Any] = None,
        custom_header_keywords: Optional[List[str]] = None
) -> List[ExcelChunk]:
    """
    暴露给用户的流水线统筹方法

    :param source:                  输入源，支持本地路径(str)、字节流(bytes)或二进制IO对象
    :param merge_action:            合并单元格处理策略，默认 FILL_FORWARD
    :param chunk_strategy:          切片策略，ChunkStrategy.FIXED_ROW(默认) 或 ChunkStrategy.TOKEN_LIMIT，也接受等价字符串
    :param chunk_size:              fixed_row 策略下每块最大行数，默认 50
    :param max_tokens:              token_limit 策略下每块最大 token 数，默认 2000
    :param max_rows:                安全限制：单 Sheet 最大行数，超限抛出 OverDimensionError
    :param max_cols:                安全限制：单 Sheet 最大列数，超限抛出 OverDimensionError
    :param include_hidden_rows:     是否纳入隐藏行，默认 False
    :param use_llm_layout_analyzer: 是否启用 LLM 兜底表头分析，需配合 llm_service 使用
    :param llm_service:             实现 LLMServiceProtocol 的服务实例
    :param custom_header_keywords:  用于表头匹配的自定义关键词列表
    :return:                        List[ExcelChunk]
    """
    source_name = source if isinstance(source, str) else f"BinaryStream({type(source).__name__})"
    logger.info(f"=== 启动Excel处理流：{source_name} ===")

    filename = os.path.basename(source) if isinstance(source, str) else "stream_input_excel"
    ignore_hidden = not include_hidden_rows

    loader_config = {
        "max_rows": max_rows,
        "max_cols": max_cols,
        "include_hidden_rows": include_hidden_rows,
    }

    # Phase 1: 安全预检与文件加载 → List[BaseWorksheet]
    worksheets = SecureLoader.check_dimensions_and_route(source, loader_config)

    all_chunks: List[ExcelChunk] = []

    for ws in worksheets:
        sheetname = ws.title

        # Phase 2: 结构探测与区块划分 → List[BoundingBox]
        boxes = StructureDetector.detect_tables(ws)
        if not boxes:
            logger.debug(f"Sheet '{sheetname}' 内未检测到有效数据，已跳过。")
            continue

        for box_idx, box in enumerate(boxes):
            table_sheet_name = sheetname if len(boxes) == 1 else f"{sheetname}_T{box_idx + 1}"
            box_range = box.range_str
            logger.info(f"处理表区块: {table_sheet_name} (物理坐标: {box_range})")

            # Phase 3: 数据渲染与合并消解 → List[List[Any]]
            rendered_matrix = DataRenderer.render_box(ws, box, action=merge_action, ignore_hidden=ignore_hidden)

            # 桥接：将二维值矩阵重建为含物理坐标与样式的 CellData 列表
            cell_data = _matrix_to_cell_data(ws, box, rendered_matrix, include_hidden_rows)

            # Phase 4: 表头识别专家系统 → StructuredTable
            structured_table = HeaderAnalyzer.analyze(
                filename=filename,
                sheetname=table_sheet_name,
                content=cell_data,
                use_llm_layout_analyzer=use_llm_layout_analyzer,
                llm_service=llm_service,
                custom_header_keywords=custom_header_keywords
            )
            structured_table.box_range = box_range

            # Phase 5: 上下文切片与组装 → List[ExcelChunk]
            sheet_chunks = ChunkAssembler.execute_chunking(
                structured_table,
                strategy=chunk_strategy,
                chunk_row_size=chunk_size,
                max_tokens=max_tokens
            )
            all_chunks.extend(sheet_chunks)

    logger.info(f"=== Excel流水线处理完成，共产出 {len(all_chunks)} 块上下文 ===")
    return all_chunks