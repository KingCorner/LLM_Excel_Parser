#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/5/8
#   @FileRole: LLMServiceWrapper 单元测试

import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from llm_excel_parser.utils.concurrency import LLMServiceWrapper
from llm_excel_parser.core.datatypes import ExcelChunk


# ===== 辅助工厂 =====

def make_service(return_value="ok", side_effect=None) -> MagicMock:
    svc = MagicMock()
    if side_effect is not None:
        svc.chat.side_effect = side_effect
    else:
        svc.chat.return_value = return_value
    return svc


def make_chunk(chunk_id="abc") -> ExcelChunk:
    return ExcelChunk(
        chunk_id=chunk_id,
        metadata={},
        formatted_context=f"context_{chunk_id}",
        raw_data=[],
    )


# ===== chat() 基础行为 =====

class TestLLMServiceWrapperChat:

    def test_successful_call_returns_response(self):
        """普通成功调用应直接返回 service.chat() 的值"""
        svc = make_service(return_value="hello")
        wrapper = LLMServiceWrapper(svc)

        result = wrapper.chat("prompt")

        assert result == "hello"
        svc.chat.assert_called_once_with("prompt")

    def test_retry_on_transient_error(self):
        """首次调用失败后应自动重试并最终返回成功结果"""
        svc = make_service()
        svc.chat.side_effect = [Exception("network error"), "recovered"]

        wrapper = LLMServiceWrapper(svc, max_retries=3)

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            result = wrapper.chat("prompt")

        assert result == "recovered"
        assert svc.chat.call_count == 2

    def test_raises_after_exhausting_retries(self):
        """所有重试均失败时应抛出最后一次的异常"""
        svc = make_service(side_effect=ValueError("persistent error"))

        wrapper = LLMServiceWrapper(svc, max_retries=3)

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            with pytest.raises(ValueError, match="persistent error"):
                wrapper.chat("prompt")

        assert svc.chat.call_count == 3

    def test_retry_count_equals_max_retries(self):
        """重试次数不应超过 max_retries"""
        svc = make_service(side_effect=RuntimeError("fail"))

        wrapper = LLMServiceWrapper(svc, max_retries=2)

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            with pytest.raises(RuntimeError):
                wrapper.chat("prompt")

        assert svc.chat.call_count == 2

    def test_timeout_triggers_retry(self):
        """首次超时后应自动重试并返回第二次成功结果。

        使用 threading.Event 阻塞第一次调用，避免 time.sleep 被 patch
        全局替换导致超时无法真正触发的问题。
        """
        blocked = threading.Event()
        call_count = 0

        def slow_on_first(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                blocked.wait(timeout=30)  # 阻塞直到 event 被 set 或 30s 保底
            return "fast"

        svc = MagicMock()
        svc.chat.side_effect = slow_on_first
        wrapper = LLMServiceWrapper(svc, max_retries=2, timeout_seconds=0.05)

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            result = wrapper.chat("prompt")

        blocked.set()  # 释放第一次调用的后台线程（清理）
        assert result == "fast"
        assert call_count == 2

    def test_timeout_exhausted_raises_timeout_error(self):
        """所有重试均超时时应抛出 TimeoutError。

        使用 threading.Event 永久阻塞，确保每次调用都真正超时。
        """
        blocked = threading.Event()

        def always_slow(prompt):
            blocked.wait(timeout=30)
            return "never"

        svc = MagicMock()
        svc.chat.side_effect = always_slow
        wrapper = LLMServiceWrapper(svc, max_retries=2, timeout_seconds=0.05)

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            with pytest.raises(TimeoutError):
                wrapper.chat("prompt")

        blocked.set()  # 清理后台线程

    def test_exponential_backoff_between_retries(self):
        """重试间隔应以 2^(n-1) 指数退避"""
        svc = make_service(side_effect=Exception("err"))

        wrapper = LLMServiceWrapper(svc, max_retries=3)
        sleep_calls = []

        with patch("llm_excel_parser.utils.concurrency.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with pytest.raises(Exception):
                wrapper.chat("prompt")

        # 3 次重试，2 次退避间隔：1s, 2s
        assert sleep_calls == [1, 2]

    def test_already_wrapped_service_not_copied(self):
        """LLMServiceWrapper 仅持有引用，不复制原始 service"""
        inner = make_service()
        wrapper = LLMServiceWrapper(inner)
        assert wrapper._service is inner


# ===== batch_process_chunks() 并发行为 =====

class TestBatchProcessChunks:

    def test_all_chunks_processed(self):
        """所有 chunk 均应被处理，返回列表与输入等长"""
        svc = make_service(return_value="result")
        wrapper = LLMServiceWrapper(svc)
        chunks = [make_chunk("c1"), make_chunk("c2"), make_chunk("c3")]

        results = wrapper.batch_process_chunks(chunks, lambda c: c.formatted_context)

        assert len(results) == 3
        assert all(r == "result" for r in results)

    def test_prompt_builder_called_with_each_chunk(self):
        """prompt_builder 应对每个 chunk 被调用一次"""
        svc = make_service(return_value="ok")
        wrapper = LLMServiceWrapper(svc)
        chunks = [make_chunk("x"), make_chunk("y")]

        seen_contexts = []
        wrapper.batch_process_chunks(chunks, lambda c: seen_contexts.append(c.chunk_id) or c.chunk_id)

        assert sorted(seen_contexts) == ["x", "y"]

    def test_failed_chunk_returns_none(self):
        """单个 chunk 失败时对应位置应为 None，其余成功位置不受影响"""
        call_count = 0

        def flaky_chat(prompt):
            nonlocal call_count
            call_count += 1
            if "fail" in prompt:
                raise RuntimeError("boom")
            return "ok"

        svc = MagicMock()
        svc.chat.side_effect = flaky_chat

        wrapper = LLMServiceWrapper(svc, max_retries=1)
        chunks = [make_chunk("good"), make_chunk("fail"), make_chunk("good2")]

        with patch("llm_excel_parser.utils.concurrency.time.sleep"):
            results = wrapper.batch_process_chunks(
                chunks,
                lambda c: c.chunk_id,
                max_workers=1,
            )

        assert results[0] == "ok"
        assert results[1] is None
        assert results[2] == "ok"

    def test_empty_chunks_returns_empty_list(self):
        """空输入应返回空列表"""
        svc = make_service()
        wrapper = LLMServiceWrapper(svc)

        results = wrapper.batch_process_chunks([], lambda c: "")

        assert results == []
        svc.chat.assert_not_called()

    def test_results_order_matches_input_order(self):
        """返回结果顺序应与输入 chunks 的顺序严格一致"""
        svc = MagicMock()
        svc.chat.side_effect = lambda p: f"resp_{p}"

        wrapper = LLMServiceWrapper(svc)
        chunks = [make_chunk(str(i)) for i in range(5)]

        results = wrapper.batch_process_chunks(chunks, lambda c: c.chunk_id, max_workers=5)

        for i, chunk in enumerate(chunks):
            assert results[i] == f"resp_{chunk.chunk_id}"
