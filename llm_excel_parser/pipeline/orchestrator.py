#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:03
#   @FileRole: 流水线总调度器 (统筹 Phase 1 ~ 5)

import os
from typing import Union, BinaryIO

from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.enums import MergeAction
from llm_excel_parser.core.datatypes import ExcelChunk

from llm_excel_parser.pipeline.phase1_loader import SecureLoader
from llm_excel_parser.pipeline.phase2_detector import StructureDetector
from llm_excel_parser.pipeline.phase3_renderer import DataRenderer
from llm_excel_parser.pipeline.phase4_header import HeaderAnalyzer
from llm_excel_parser.pipeline.phase5_chunker import ChunkAssembler

logger = get_logger("orchestrator")


def process_excel(
        source: Union[str, bytes, BinaryIO],
        merge_action: MergeAction = MergeAction.FILL_FORWARD,
        chunk_size: int = 50,
        max_rows: int = 100000,
        max_cols: int = 2000,
        include_hidden_rows: bool = False
) -> list[ExcelChunk]:
    """
    暴露给用户的流水线统筹方法
    """
    source_name = source if isinstance(source, str) else f"BinaryStream({type(source).__name__})"
    logger.info(f"=== 启动Excel处理流：{source_name} ===")

    loader_config = {
        "max_rows": max_rows,
        "max_cols": max_cols,
        "include_hidden_rows": include_hidden_rows
    }

    # Phase 1: 安全预检与文件加载
    wb = SecureLoader.check_dimensions_and_route(source, loader_config)

    if isinstance(source, str):
        filename = os.path.basename(source)
    else:
        filename = "stream_input_excel"

    all_chunks = []

    try:
        for sheetname in wb.sheetnames:
            ws = wb[sheetname]

            # Phase 2: 结构探测与区块划分
            # 接收List[BoundingBox], 即使是一张Sheet也可能有多个表被切出来
            boxes = StructureDetector.detect_tables(ws)
            if not boxes:
                logger.debug(f"Sheet '{sheetname}' 内未检测到有效数据，已跳过。")
                continue

            for box_idx, box in enumerate(boxes):
                # 如果单个Sheet切出了多张表，加上 _T1, _T2 后缀区分；单表则保持原样
                table_sheet_name = f"{sheetname}" if len(boxes) == 1 else f"{sheetname}_T{box_idx + 1}"
                box_range = box.range_str
                logger.info(f"处理表区块: {table_sheet_name} (物理坐标: {box_range})")

                # Phase 3: 数据渲染与合并消解
                raw_content = DataRenderer.render_box(ws, box, action=merge_action)

                # Phase 4: 表头识别专家系统
                structured_table = HeaderAnalyzer.analyze(filename, table_sheet_name, raw_content)

                # 将物理坐标写入结构体，以便向下传导进元数据
                structured_table.box_range = box_range

                # Phase 5: 上下文切片与组装
                sheet_chunks = ChunkAssembler.execute_chunking(structured_table, chunk_row_size=chunk_size)
                all_chunks.extend(sheet_chunks)

    finally:
        wb.close()
        logger.info(f"=== Excel流水线处理完成，共产出 {len(all_chunks)} 块上下文 ===")

    return all_chunks
