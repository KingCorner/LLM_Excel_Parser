#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 18:14
#   @FileRole: 二维矩阵与几何算法工具 (BFS连通域，包围盒合并等纯算法)


from typing import List, Set, Tuple
from collections import deque
from llm_excel_parser.core.datatypes import BoundingBox


def find_8_connected_components(solid_cells: Set[Tuple[int, int]]) -> List[BoundingBox]:
    """使用 BFS 计算 8向连通域，输出最初始的微型区块"""
    visited = set()
    micro_boxes = []
    # 8 通道方向
    directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    for cell in solid_cells:
        if cell in visited:
            continue

        queue = deque([cell])
        visited.add(cell)

        min_r, max_r = cell[0], cell[0]
        min_c, max_c = cell[1], cell[1]

        while queue:
            r, c = queue.popleft()
            min_r, max_r = min(min_r, r), max(max_r, r)
            min_c, max_c = min(min_c, c), max(max_c, c)

            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                if (nr, nc) in solid_cells and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc))

        micro_boxes.append(BoundingBox(min_r, max_r, min_c, max_c))

    return micro_boxes


def merge_proximate_boxes(boxes: List[BoundingBox], max_empty_rows: int, max_empty_cols: int) -> List[BoundingBox]:
    """基于容忍距离，合并距离相近的包围盒 (宏观合并)"""
    merged = True
    while merged:
        merged = False
        new_boxes = []

        while boxes:
            current_box = boxes.pop(0)
            expanded_current = current_box.expand(max_empty_rows, max_empty_cols)

            boxes_to_keep = []
            for other_box in boxes:
                if expanded_current.intersects(other_box):
                    current_box = current_box.merge(other_box)
                    expanded_current = current_box.expand(max_empty_rows, max_empty_cols)
                    merged = True
                else:
                    boxes_to_keep.append(other_box)

            boxes = boxes_to_keep
            new_boxes.append(current_box)

        boxes = new_boxes

    # 按从上到下，从左到右排序返回
    boxes.sort(key=lambda b: (b.min_row, b.min_col))
    return boxes
