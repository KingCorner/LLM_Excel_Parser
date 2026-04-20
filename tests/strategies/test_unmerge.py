#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 16:44
#   @FileRole:


import pytest

from llm_excel_parser.strategies.unmerge import (
    FillForwardStrategy,
    TopLeftStrategy,
    TagStrategy,
    get_unmerge_strategy
)
from llm_excel_parser.core.enums import MergeAction


class TestUnmergeStrategies:
    """所有具体策略类的行为测试"""

    def test_fill_forward_strategy(self):
        """测试 FillForwardStrategy: 所有格子均继承主格值"""
        strategy = FillForwardStrategy()
        val = "MergeValue"

        # 无论是左上角主格还是其他附属格，都直接返回原值
        assert strategy.resolve(val, row=1, col=1, is_top_left=True) == "MergeValue"
        assert strategy.resolve(val, row=2, col=2, is_top_left=False) == "MergeValue"

    def test_top_left_strategy(self):
        """测试 TopLeftStrategy: 仅主格保留值，其余全置为 None"""
        strategy = TopLeftStrategy()
        val = "MergeValue"

        assert strategy.resolve(val, row=1, col=1, is_top_left=True) == "MergeValue"
        assert strategy.resolve(val, row=2, col=2, is_top_left=False) is None

    def test_tag_strategy(self):
        """测试 TagStrategy: 非主格会被注入 [xxx] 的降维占位符标记"""
        strategy = TagStrategy()
        val = "MergeValue"

        assert strategy.resolve(val, row=1, col=1, is_top_left=True) == "MergeValue"
        assert strategy.resolve(val, row=2, col=2, is_top_left=False) == "[MergeValue]"

        # 测试值为数字的情况
        assert strategy.resolve(100, row=1, col=2, is_top_left=False) == "[100]"


class TestGetUnmergeStrategyFactory:
    """测试简易工厂的路由注册"""

    def test_get_fill_forward(self):
        strategy = get_unmerge_strategy(MergeAction.FILL_FORWARD)
        assert isinstance(strategy, FillForwardStrategy)

    def test_get_top_left(self):
        strategy = get_unmerge_strategy(MergeAction.TOP_LEFT)
        assert isinstance(strategy, TopLeftStrategy)

    def test_get_tag(self):
        strategy = get_unmerge_strategy(MergeAction.TAG)
        assert isinstance(strategy, TagStrategy)

    def test_invalid_action_raises_keyerror(self):
        """当传入了未注册的枚举行为，应抛出异常"""

        # 测试健壮性，若有新的 Enum 但是工厂没加，直接抛错
        class FakeAction:
            pass

        with pytest.raises(KeyError):
            get_unmerge_strategy("UNKNOWN_ACTION")
