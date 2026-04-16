#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 17:38
#   @FileRole: 合并格消解策略


from abc import ABC, abstractmethod
from typing import Any
from llm_excel_parser.core.enums import MergeAction


class BaseUnmergeStrategy(ABC):
    @abstractmethod
    def resolve(self, value: Any, row: int, col: int, is_top_left: bool) -> Any:
        pass


class FillForwardStrategy(BaseUnmergeStrategy):
    """自动向下/向右复制主格值"""

    def resolve(self, value: Any, row: int, col: int, is_top_left: bool) -> Any:
        return value


class TopLeftStrategy(BaseUnmergeStrategy):
    """保持原样(仅左上角有值，其余为空)"""

    def resolve(self, value: Any, row: int, col: int, is_top_left: bool) -> Any:
        return value if is_top_left else None


class TagStrategy(BaseUnmergeStrategy):
    """注入占位符标签"""

    def resolve(self, value: Any, row: int, col: int, is_top_left: bool) -> Any:
        return value if is_top_left else f"[{value}]"


def get_unmerge_strategy(action: MergeAction) -> BaseUnmergeStrategy:
    strategies = {
        MergeAction.FILL_FORWARD: FillForwardStrategy(),
        MergeAction.TOP_LEFT: TopLeftStrategy(),
        MergeAction.TAG: TagStrategy()
    }
    return strategies[action]
