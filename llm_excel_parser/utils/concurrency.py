#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/5/8
#   @FileRole: 并发、重试、超时控制器（包装用户的 LLMService）

import time
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from llm_excel_parser.config import default_config
from llm_excel_parser.utils.logger_module import get_logger

logger = get_logger("concurrency")


class LLMServiceWrapper:
    """
    对用户 LLMService 的透明并发包装器。

    根据设计文档第二章责任表，库方负责：
      - 错误重试：指数退避，最多 max_retries 次
      - 超时阻断：每次 chat() 调用强制限时
      - 并发控制：batch_process_chunks() 通过线程池并发处理多块

    用户方负责：
      - 负载均衡（如多 API Key 轮询）
      - 请求大模型（实现 chat() 方法）
    """

    def __init__(
        self,
        service,
        max_retries: int = default_config.LLM_MAX_RETRIES,
        timeout_seconds: int = default_config.LLM_TIMEOUT_SECONDS,
    ):
        self._service = service
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    def chat(self, prompt: str) -> str:
        """带重试 + 超时阻断的同步 chat 调用。"""
        last_exc: Optional[BaseException] = None

        for attempt in range(1, self.max_retries + 1):
            # 不使用 with 语法，改为 shutdown(wait=False)：
            # with 语句退出时会调用 shutdown(wait=True)，导致即便已超时
            # 仍会阻塞等待后台线程跑完，使超时保护形同虚设。
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self._service.chat, prompt)
            try:
                return future.result(timeout=self.timeout_seconds)
            except FuturesTimeoutError:
                future.cancel()
                last_exc = TimeoutError(
                    f"LLM 调用第 {attempt}/{self.max_retries} 次超时 "
                    f"（上限 {self.timeout_seconds}s）"
                )
                logger.warning(str(last_exc))
            except Exception as e:
                last_exc = e
                logger.warning(f"LLM 调用第 {attempt}/{self.max_retries} 次失败: {e}")
            finally:
                executor.shutdown(wait=False)

            if attempt < self.max_retries:
                backoff = 2 ** (attempt - 1)
                logger.debug(f"退避 {backoff}s 后重试...")
                time.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    def batch_process_chunks(
        self,
        chunks: list,
        prompt_builder: Callable,
        max_workers: int = 4,
    ) -> List[Optional[str]]:
        """
        并发处理 ExcelChunk 列表，每块的 prompt 由 prompt_builder 回调构建。

        每个 chunk 的调用均经过 chat()，即自动享有重试和超时保护。

        :param chunks:         Phase 5 产出的 ExcelChunk 列表
        :param prompt_builder: 将单个 ExcelChunk 转换为 prompt 字符串的回调
        :param max_workers:    最大并发线程数（库负责并发控制）
        :return:               与 chunks 等长的响应列表，失败位置为 None
        """
        results: List[Optional[str]] = [None] * len(chunks)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.chat, prompt_builder(chunk)): idx
                for idx, chunk in enumerate(chunks)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Chunk [{chunks[idx].chunk_id}] LLM 处理失败: {e}")

        success_count = sum(r is not None for r in results)
        logger.info(f"批量处理完成: {success_count}/{len(chunks)} 块成功")
        return results
