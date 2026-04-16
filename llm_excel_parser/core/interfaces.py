#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 17:37
#   @FileRole: 核心接口定义

from typing import Protocol, Any, Dict


class LLMServiceProtocol(Protocol):
    """大模型服务调用协议接口"""

    def generate(self, prompt: str, **kwargs) -> str:
        """同步调用生成文本"""
        ...

    async def async_generate(self, prompt: str, **kwargs) -> str:
        """异步调用生成文本"""
        ...

    def analyze_structure(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """针对结构化数据的特定分析调用"""
        ...