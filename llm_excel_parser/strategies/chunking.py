#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 17:39
#   @FileRole: 分块拆解策略

import math
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Type
from llm_excel_parser.core.datatypes import StructuredTable
from llm_excel_parser.core.enums import ChunkStrategy
from llm_excel_parser.config import default_config
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.utils.formatters import render_chunk_row

logger = get_logger("chunking_strategy")


class BaseChunker(ABC):
    @abstractmethod
    def split(self, table: StructuredTable, **kwargs) -> List[List[Dict[str, Any]]]:
        """将 StructuredTable 的 body_rows 切分为多个批次(Batches)"""
        pass


class FixedRowChunker(BaseChunker):
    """策略A: 基于固定行数的切片策略（包含尾部碎片合并）"""

    def __init__(self, chunk_size: int = default_config.DEFAULT_CHUNK_SIZE,
                 min_tail_rows: int = default_config.DEFAULT_MIN_TAIL_ROWS):
        self.chunk_size = chunk_size
        self.min_tail_rows = min_tail_rows

    def split(self, table: StructuredTable, **kwargs) -> List[List[Dict[str, Any]]]:
        batches = []
        body_rows = table.body_rows

        for i in range(0, len(body_rows), self.chunk_size):
            batches.append(body_rows[i: i + self.chunk_size])

        # 尾部碎片合并机制: 若最后一批行数 < 阈值, 则合并到上一批
        if len(batches) > 1 and len(batches[-1]) < self.min_tail_rows:
            tail_batch = batches.pop()
            batches[-1].extend(tail_batch)
            logger.debug(f"触发尾部碎片合并：最后 {len(tail_batch)} 行已并入上一 Chunk。")

        return batches


class TokenChunker(BaseChunker):
    """策略B: 基于Token长度的智能切片策略"""

    def __init__(self, max_tokens: int = default_config.DEFAULT_MAX_TOKENS):
        self.max_tokens = max_tokens

    def split(self, table: StructuredTable, base_tokens: int = 0, **kwargs) -> List[List[Dict[str, Any]]]:
        batches = []
        current_batch = []
        current_tokens = base_tokens

        for row_record in table.body_rows:
            # 依赖注入：调用 formatter 估算单行的 Token
            row_str = render_chunk_row(row_record, table.max_col)
            row_tokens = math.ceil(len(row_str) * default_config.TOKEN_CONVERSION_RATIO)

            if current_tokens + row_tokens > self.max_tokens and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = base_tokens

            current_batch.append(row_record)
            current_tokens += row_tokens

        if current_batch:
            batches.append(current_batch)

        return batches


# 策略工厂映射表，以 ChunkStrategy 枚举为 key，便于 Phase 5 动态调用
CHUNKER_REGISTRY: Dict[ChunkStrategy, Type[BaseChunker]] = {
    ChunkStrategy.FIXED_ROW: FixedRowChunker,
    ChunkStrategy.TOKEN_LIMIT: TokenChunker,
}