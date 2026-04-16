#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/14 22:02
#   @FileRole: Phase 5 - 上下文切片与格式组装器

import uuid
import math
from typing import List, Dict, Literal
from llm_excel_parser.utils.logger_module import get_logger
from llm_excel_parser.core.datatypes import StructuredTable, ExcelChunk

logger = get_logger("phase5_chunker")


class ChunkAssembler:
    """
    Phase 5: 上下文切片与格式组装器
    负责将带有表头的结构化数据表，按策略切片，并渲染为大模型友好的 Markdown/纯文本上下文。
    """

    @classmethod
    def execute_chunking(
            cls,
            table: StructuredTable,
            strategy: Literal["fixed_row", "token_limit"] = "fixed_row",
            chunk_row_size: int = 50,
            min_tail_rows: int = 10,
            max_tokens: int = 2000
    ) -> List[ExcelChunk]:
        """
        执行切片流水线主入口

        :param table: Phase 4 产出的带表头的结构化数据表
        :param strategy: 切片策略 ('fixed_row' 或 'token_limit')
        :param chunk_row_size: 固定行切片时的每块行数 (不含表头)
        :param min_tail_rows: 尾部合并阈值。如果最后一块行数小于该值，则合并到上一块
        :param max_tokens: Token策略时的单块最大Token数阀值
        """
        if not table.body_rows:
            logger.warning(f"[{table.sheetname}] 当前表格无数据行，跳过切片。")
            return []

        # 1. 预先格式化 Header 字符串区 (每个 Chunk 必带)
        header_str, header_token_count = cls._render_header(table)

        # 2. 根据策略进行切片 (仅切分批次，不在此处做字符串拼接)
        if strategy == "fixed_row":
            batches = cls._chunk_by_fixed_rows(table.body_rows, chunk_row_size, min_tail_rows)
        elif strategy == "token_limit":
            batches = cls._chunk_by_token_limit(table, max_tokens, header_token_count)
        else:
            raise ValueError(f"不受支持的切片策略: {strategy}")

        # 3. 组装最终的大模型友好 Chunk
        chunks = []
        total_chunks = len(batches)

        for idx, batch in enumerate(batches):
            chunk = cls._build_excel_chunk(
                table=table,
                batch=batch,
                header_str=header_str,
                current_chunk_idx=idx + 1,
                total_chunks=total_chunks,
                strategy_used=strategy
            )
            chunks.append(chunk)

        logger.info(f"[{table.sheetname}] 上下文组装完毕, 产出 {len(chunks)} 块 (策略: {strategy})")
        return chunks

    # ---------------- 策略实现区 ---------------- #

    @classmethod
    def _chunk_by_fixed_rows(cls, body_rows: List[Dict], chunk_size: int, min_tail_rows: int) -> List[List[Dict]]:
        """策略A: 按固定行数切分，并包含尾部碎片合并逻辑"""
        batches = []
        total_rows = len(body_rows)

        for i in range(0, total_rows, chunk_size):
            batches.append(body_rows[i: i + chunk_size])

        # 尾部碎片合并机制 (对应设计文档：若最后一批行数 < y, 则合并到上一批)
        if len(batches) > 1 and len(batches[-1]) < min_tail_rows:
            tail_batch = batches.pop()
            batches[-1].extend(tail_batch)
            logger.debug(f"触发尾部碎片合并：最后 {len(tail_batch)} 行已并入上一 Chunk。")

        return batches

    @classmethod
    def _chunk_by_token_limit(cls, table: StructuredTable, max_tokens: int, base_tokens: int) -> List[List[Dict]]:
        """策略B: 依据最大 Token 估算机制切块 (1字符 ≈ 0.5 Token)"""
        batches = []
        current_batch = []
        current_tokens = base_tokens  # 初始Token包含固定头部信息

        for row_record in table.body_rows:
            # 渲染当前行并估算token
            row_str = cls._render_single_row(row_record, table.max_col)
            row_tokens = math.ceil(len(row_str) * 0.5)

            # 如果加上这一行超标了，且当前batch不为空，则封板出一个新的 Chunk
            if current_tokens + row_tokens > max_tokens and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = base_tokens

            current_batch.append(row_record)
            current_tokens += row_tokens

        # 处理最后一批遗漏的行
        if current_batch:
            batches.append(current_batch)

        return batches

    # ---------------- 渲染与组装区 ---------------- #

    @classmethod
    def _render_header(cls, table: StructuredTable) -> tuple[str, int]:
        """渲染表头区并返回字符串及基础Token占用"""
        if not table.headers:
            return "表头 | (无表头数据)", 5

        header_str_lines = []
        for h in table.headers:
            h_data = h["data"]
            row_items = [str(h_data.get(c, "")) for c in range(1, table.max_col + 1)]
            header_str_lines.append("表头 | " + " | ".join(row_items))

        final_header_str = "\n".join(header_str_lines)
        # 估算基础内容 + 表头的 Token 占用
        base_tokens = math.ceil(len(final_header_str) * 0.5) + 50
        return final_header_str, base_tokens

    @classmethod
    def _render_single_row(cls, row_record: Dict, max_col: int) -> str:
        """渲染带有逻辑行号的单行数据"""
        r_idx = row_record["row"]
        r_data = row_record["data"]
        # 展现带有逻辑行号的数据，保证大模型能够精准定位
        row_vals = [str(r_data.get(c, "")) for c in range(1, max_col + 1)]
        return f"行{r_idx} | " + " | ".join(row_vals)

    @classmethod
    def _build_excel_chunk(
            cls,
            table: StructuredTable,
            batch: List[Dict],
            header_str: str,
            current_chunk_idx: int,
            total_chunks: int,
            strategy_used: str
    ) -> ExcelChunk:
        """将数据拼接为 LLM 友好的 Markdown/CSV 格式，并封装为对象"""

        start_row = batch[0]["row"]
        end_row = batch[-1]["row"]

        # 拼接提供给 LLM 的上下文文本
        context_parts = [
            f"=== 电子表格数据片段 ({current_chunk_idx}/{total_chunks}) ===",
            f"📌 文件名: {table.filename} | 工作表: {table.sheetname}",
            f"📌 行号范围: {start_row} ~ {end_row}",
            "-" * 50,
            header_str,  # 每块均带上表头
            "-" * 50
        ]

        for row_record in batch:
            context_parts.append(cls._render_single_row(row_record, table.max_col))

        final_context = "\n".join(context_parts)

        # 封装为标准协议对象
        return ExcelChunk(
            chunk_id=uuid.uuid4().hex[:8],
            metadata={
                "filename": table.filename,
                "sheetname": table.sheetname,
                "chunk_index": current_chunk_idx,
                "total_chunks": total_chunks,
                "start_row": start_row,
                "end_row": end_row,
                "strategy": strategy_used,
                "approx_tokens": math.ceil(len(final_context) * 0.5)
            },
            formatted_context=final_context,
            raw_data=batch
        )
