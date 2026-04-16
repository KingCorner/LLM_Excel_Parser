#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 17:39
#   @FileRole: 分块拆解策略


from abc import ABC, abstractmethod
from typing import List, Dict, Any
from llm_excel_parser.core.datatypes import StructuredTable


class BaseChunker(ABC):
    @abstractmethod
    def split(self, table: StructuredTable) -> List[Dict[str, Any]]:
        pass


class FixedRowChunker(BaseChunker):
    """基于固定行数的切片策略"""

    def __init__(self, chunk_size: int = 50):
        self.chunk_size = chunk_size

    def split(self, table: StructuredTable) -> List[Dict[str, Any]]:
        chunks = []
        body = table.body_rows
        for i in range(0, len(body), self.chunk_size):
            chunks.append({
                "headers": table.headers,
                "data": body[i:i + self.chunk_size]
            })
        return chunks


class TokenChunker(BaseChunker):
    """基于Token长度的智能切片策略 (预留口)"""

    def split(self, table: StructuredTable) -> List[Dict[str, Any]]:
        raise NotImplementedError("Token级别的切片将在后续版本支持")
