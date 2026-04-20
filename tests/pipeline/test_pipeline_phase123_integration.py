#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 17:38
#   @FileRole: 对phase1~3的单元测试


import os
import tempfile
import pytest
import openpyxl

from llm_excel_parser.pipeline.phase1_loader import SecureLoader
from llm_excel_parser.pipeline.phase2_detector import StructureDetector
from llm_excel_parser.pipeline.phase3_renderer import DataRenderer
from llm_excel_parser.core.enums import MergeAction

from llm_excel_parser.adapters.openpyxl_adapter import OpenpyxlWorksheetAdapter
from llm_excel_parser.core.interfaces import BaseWorksheet


@pytest.fixture
def complex_excel_file(tmp_path):
    """
    动态生成一个真实的 Excel 物理文件，用于集成测试。
    该表格包含两个独立的数据块（被空行隔开），并含有合并单元格。
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IntegrationSheet"

    # 表格块 1: 位于左上角 (A1:C3)
    # 包含一个合并单元格 A1:B1 (跨两列)
    ws['A1'] = "合并标头"
    ws.merge_cells('A1:B1')
    ws['C1'] = "独立标头"

    ws['A2'] = "数据A2"
    ws['B2'] = "数据B2"
    ws['C2'] = "数据C2"

    ws['A3'] = "数据A3"
    ws['B3'] = "数据B3"
    ws['C3'] = "数据C3"

    # 空出第4、第5行，形成物理断层，用于触发 Phase 2 的切表逻辑

    # 表格块 2: 位于偏右下方 (B6:C7)

    ws['B6'] = "表2标题1"
    ws['C6'] = "表2标题2"
    ws['B7'] = "内容1"
    ws['C7'] = "内容2"

    # 利用 pytest 的 tmp_path 构建路径
    filepath = tmp_path / "integration_test.xlsx"
    wb.save(filepath)
    return str(filepath)


def test_main_pipeline_happy_path(complex_excel_file):
    """
    主干链路集成测试：
    验证从加载文件 -> 识别多表格边界 -> 渲染二维数据的完整链路
    """

    # Phase 1: 安全预检与文件加载
    # 送入真实的 xlsx 物理路径
    worksheets = SecureLoader.check_dimensions_and_route(complex_excel_file)

    assert len(worksheets) == 1, "应该成功解析出一个 Worksheet 对象"
    ws = worksheets[0]
    assert ws.title == "IntegrationSheet", "Phase 1: 工作表读取或适配失败"

    assert isinstance(ws, OpenpyxlWorksheetAdapter)

    # Phase 2: 结构探测层 (切表)
    boxes = StructureDetector.detect_tables(ws, max_empty_rows=1)

    # 验证是否成功跨越空行，识别出两个独立的表格包围盒
    assert len(boxes) == 2, "Phase 2: 未能正确识别出 2 个独立的表格块"

    # 按行号排序以便后续断言 (由于底层探测算法可能不保证先后顺序)
    boxes = sorted(boxes, key=lambda b: b.min_row)
    box1 = boxes[0]  # 预期是 A1:C3
    box2 = boxes[1]  # 预期是 B6:C7

    assert box1.min_row == 1 and box1.max_row == 3 and box1.min_col == 1 and box1.max_col == 3, "表 1 坐标推断错误"
    assert box2.min_row == 6 and box2.max_row == 7 and box2.min_col == 2 and box2.max_col == 3, "表 2 坐标推断错误"

    # Phase 3: 数据渲染层 (二维数组提取 & 合并单元格消解)

    # 场景 1：使用 FILL_FORWARD 策略渲染表 1 (验证 A1:B1 的合并单元格是否被平铺补齐)
    rendered_table_1_fill = DataRenderer.render_box(ws, box1, action=MergeAction.FILL_FORWARD)

    expected_table_1_fill = [
        # 注意："合并标头" 应该在第 1 行 第 2 列 (B1) 被自动复制填充了
        ["合并标头", "合并标头", "独立标头"],
        ["数据A2", "数据B2", "数据C2"],
        ["数据A3", "数据B3", "数据C3"]
    ]

    assert rendered_table_1_fill == expected_table_1_fill, "Phase 3: 向下向右填充合并单元格策略失效"

    # 场景 2：使用 TOP_LEFT 策略渲染表 1 (验证非左上角是否留空，这里假设你的策略返回 None 或 "")
    rendered_table_1_topleft = DataRenderer.render_box(ws, box1, action=MergeAction.TOP_LEFT)

    # 取第一行，验证第二个元素 (B1) 不是"合并标头"
    top_left_header_row = rendered_table_1_topleft[0]
    assert top_left_header_row[0] == "合并标头"
    assert top_left_header_row[1] is None or top_left_header_row[1] == "", "Phase 3: TOP_LEFT 时非主格未妥善置空"
    assert top_left_header_row[2] == "独立标头"

    # 场景 3：渲染表 2，确保坐标偏移情况下数据截取完全正确 (只取 B6:C7 的内容)
    rendered_table_2 = DataRenderer.render_box(ws, box2, action=MergeAction.FILL_FORWARD)

    expected_table_2 = [
        ["表2标题1", "表2标题2"],
        ["内容1", "内容2"]
    ]
    assert rendered_table_2 == expected_table_2, "Phase 3: 偏移表格内容提取错误"

    print("\n[✔] 流水线 Phase 1 -> Phase 2 -> Phase 3 贯通集成测试全部通过！")
