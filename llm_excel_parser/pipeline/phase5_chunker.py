#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:02
#   @FileRole: 上下文切片与格式组装

import uuid
import math
from typing import List, Union
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.datatypes import StructuredTable, ExcelChunk
from llm_excel_parser.core.enums import ChunkStrategy
from llm_excel_parser.core.exceptions import ChunkingError
from llm_excel_parser.config import default_config
from llm_excel_parser.strategies.chunking import CHUNKER_REGISTRY
from llm_excel_parser.utils.formatters import render_chunk_header, build_chunk_context

logger = get_logger("phase5_chunker")


class ChunkAssembler:
    """
    上下文切片与格式组装器
    """

    @classmethod
    def execute_chunking(
            cls,
            table: StructuredTable,
            strategy: Union[str, ChunkStrategy] = ChunkStrategy.FIXED_ROW,
            chunk_row_size: int = 50,
            min_tail_rows: int = 10,
            max_tokens: int = 2000
    ) -> List[ExcelChunk]:
        """
        执行切片流水线主入口
        """
        if not table.body_rows:
            logger.warning(f"[{table.sheetname}] 当前表格无数据行，跳过切片。")
            return []

        # 1. 格式化提取 Header 字符串 (依赖 utils 层)
        header_str, header_token_count = render_chunk_header(table)

        # 2. 将字符串归一化为 ChunkStrategy 枚举，统一后续路由逻辑
        if isinstance(strategy, str):
            try:
                strategy = ChunkStrategy(strategy)
            except ValueError:
                raise ChunkingError(f"不受支持的切片策略: {strategy!r}")

        if strategy not in CHUNKER_REGISTRY:
            raise ChunkingError(f"不受支持的切片策略: {strategy!r}")

        # 根据选择实例化对应的 Chunker，并将对应的参数带入
        if strategy == ChunkStrategy.FIXED_ROW:
            chunker = CHUNKER_REGISTRY[strategy](chunk_size=chunk_row_size, min_tail_rows=min_tail_rows)
        else:
            chunker = CHUNKER_REGISTRY[strategy](max_tokens=max_tokens)

        # 执行切片，获得分割好的数据批次 (TokenLimit需要传入基础的header算力)
        batches = chunker.split(table, base_tokens=header_token_count)

        # 3. 将切片后的数据组装成针对模型友好的协议对象
        chunks = []
        total_chunks = len(batches)

        for idx, batch in enumerate(batches):
            # 将具体行拼接为上下文
            final_context = build_chunk_context(
                table=table,
                batch=batch,
                header_str=header_str,
                current_chunk_idx=idx + 1,
                total_chunks=total_chunks
            )

            # 封装返回给用户的标准结构
            chunk = ExcelChunk(
                chunk_id=uuid.uuid4().hex[:8],
                metadata={
                    "filename": table.filename,
                    "sheetname": table.sheetname,
                    "chunk_index": idx + 1,
                    "total_chunks": total_chunks,
                    "start_row": batch[0]["row"],
                    "end_row": batch[-1]["row"],
                    "strategy": strategy.value,
                    "approx_tokens": math.ceil(len(final_context) * default_config.TOKEN_CONVERSION_RATIO)
                },
                formatted_context=final_context,
                raw_data=batch
            )
            chunks.append(chunk)

        logger.info(f"[{table.sheetname}] 上下文组装完毕, 产出 {len(chunks)} 块 (策略: {strategy})")
        return chunks