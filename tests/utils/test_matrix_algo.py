#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 16:21
#   @FileRole: matrix_algo单元测试


import pytest
from llm_excel_parser.utils.matrix_algo import (
    find_8_connected_components,
    merge_proximate_boxes,
    col_idx_to_letter
)
from llm_excel_parser.core.datatypes import BoundingBox


# 对find_8_connected_components测试

def test_find_8_connected_components_empty():
    """测试空集合输入是否返回空列表"""
    assert find_8_connected_components(set()) == []


def test_find_8_connected_components_single_cell():
    """测试单个单元格的连通域"""
    solid_cells = {(2, 3)}
    boxes = find_8_connected_components(solid_cells)

    assert len(boxes) == 1
    assert boxes[0].min_row == 2
    assert boxes[0].max_row == 2
    assert boxes[0].min_col == 3
    assert boxes[0].max_col == 3


def test_find_8_connected_components_adjacent():
    """测试8向相邻（上下左右及对角线）是否能被正确合并为一个包围盒"""
    solid_cells = {
        (1, 1), (1, 2),  # 水平相邻
        (2, 2),  # 对角相邻 + 垂直相邻
        (3, 3)  # 对角相邻
    }
    boxes = find_8_connected_components(solid_cells)

    assert len(boxes) == 1
    assert boxes[0].min_row == 1
    assert boxes[0].max_row == 3
    assert boxes[0].min_col == 1
    assert boxes[0].max_col == 3


def test_find_8_connected_components_disconnected():
    """测试相互断开的区域是否能输出多个包围盒"""
    solid_cells = {
        (1, 1), (1, 2),  # 区域 1
        (5, 5), (6, 5)  # 区域 2 (与区域1不应连通)
    }
    boxes = find_8_connected_components(solid_cells)

    assert len(boxes) == 2
    # 因 set 是无序的，需按坐标排序后再断言以保证测试稳定性
    boxes.sort(key=lambda b: (b.min_row, b.min_col))

    # Assert 区域 1
    assert (boxes[0].min_row, boxes[0].max_row, boxes[0].min_col, boxes[0].max_col) == (1, 1, 1, 2)
    # Assert 区域 2
    assert (boxes[1].min_row, boxes[1].max_row, boxes[1].min_col, boxes[1].max_col) == (5, 6, 5, 5)


# 对merge_proximate_boxes测试

def test_merge_proximate_boxes_empty_and_single():
    """测试空列表和单元素列表的合并"""
    assert merge_proximate_boxes([], 2, 2) == []

    b1 = BoundingBox(1, 2, 1, 2)
    assert merge_proximate_boxes([b1], 2, 2) == [b1]


def test_merge_proximate_boxes_no_merge_needed():
    """测试距离超出容忍度限制的包围盒，不应被合并"""
    b1 = BoundingBox(1, 2, 1, 2)
    b2 = BoundingBox(10, 12, 10, 12)

    # 容忍度远小于两者间距
    merged = merge_proximate_boxes([b1, b2], max_empty_rows=2, max_empty_cols=2)
    assert len(merged) == 2


def test_merge_proximate_boxes_successful_merge():
    """测试在容忍范围内的两个包围盒是否能成功合并"""
    # 假定 BoundingBox 拥有正确的 intersects, expand, merge 实现
    b1 = BoundingBox(1, 2, 1, 2)
    b2 = BoundingBox(4, 5, 1, 2)

    # 它们行之间差 1 行空白 (row 3)。如果 max_empty_rows=1，它们应该能合并
    merged = merge_proximate_boxes([b1, b2], max_empty_rows=1, max_empty_cols=0)

    assert len(merged) == 1
    assert (merged[0].min_row, merged[0].max_row, merged[0].min_col, merged[0].max_col) == (1, 5, 1, 2)


def test_merge_proximate_boxes_chain_reaction():
    """测试链式合并（A并B生成的大盒能进一步并C）"""
    b1 = BoundingBox(1, 1, 1, 1)
    b2 = BoundingBox(3, 3, 1, 1)
    b3 = BoundingBox(5, 5, 1, 1)

    # 容忍度为 1 (允许1行空隙)
    # b1 和 b2 合并后变成 (1, 3, 1, 1)，它与 b3 距离为 1 (空行4)，能接着与 b3 合并
    merged = merge_proximate_boxes([b1, b2, b3], max_empty_rows=1, max_empty_cols=0)

    assert len(merged) == 1
    assert (merged[0].min_row, merged[0].max_row, merged[0].min_col, merged[0].max_col) == (1, 5, 1, 1)


def test_merge_proximate_boxes_sorting():
    """测试合并后的盒子是否严格按照 从上到下，从左到右 排列"""
    b_bottom = BoundingBox(10, 10, 10, 10)
    b_top_right = BoundingBox(1, 1, 20, 20)
    b_top_left = BoundingBox(1, 1, 1, 1)

    # 距离极远，互不合并，仅测试最终排序返回
    merged = merge_proximate_boxes([b_bottom, b_top_right, b_top_left], 0, 0)

    assert len(merged) == 3
    assert merged[0] == b_top_left
    assert merged[1] == b_top_right
    assert merged[2] == b_bottom


# 对col_idx_to_letter 测试

@pytest.mark.parametrize("col_idx, expected", [
    (1, "A"),  # 边界起点
    (2, "B"),  # 正常个位数
    (26, "Z"),  # 字母表末尾边界
    (27, "AA"),  # 进位边界起点
    (52, "AZ"),  # 测试进位末端
    (53, "BA"),  # 再次进位
    (702, "ZZ"),  # 二位数极大边界
    (703, "AAA"),  # 三位数进位
    (16384, "XFD")  # Excel列数理论最大限制
])
def test_col_idx_to_letter_normal_cases(col_idx, expected):
    """测试合法的整数列转字母"""
    assert col_idx_to_letter(col_idx) == expected


def test_col_idx_to_letter_zero_or_negative():
    """测试0及负数越界输入 (基于源码逻辑，应该返回空字符串)"""
    assert col_idx_to_letter(0) == ""
    assert col_idx_to_letter(-5) == ""
