#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/20 20:40
#   @FileRole: phase4_header 单元测试


import pytest
from unittest.mock import MagicMock, patch

from llm_excel_parser.pipeline.phase4_header import HeaderAnalyzer
from llm_excel_parser.core.datatypes import StructuredTable


# ================= 辅助测试数据构造器 =================
def create_mock_cell(row, col, value, style=None):
    return {"row": row, "column": col, "value": value, "style": style or {}}


# ================= 测试类 =================
class TestHeaderAnalyzer:

    def test_build_rows_dict(self):
        """测试 1D Cell 列表转换为 2D 字典的逻辑"""
        content = [
            create_mock_cell(1, 1, "ID"),
            create_mock_cell(1, 2, "NAME"),
            create_mock_cell(2, 1, 1001),
        ]

        rows_dict, max_col = HeaderAnalyzer._build_rows_dict(content)

        assert max_col == 2
        assert len(rows_dict) == 2
        assert rows_dict[1][1]["value"] == "ID"
        assert rows_dict[2][1]["value"] == 1001
        assert 2 not in rows_dict[2]  # 第二行第二列不存在数据

    def test_heuristic_scoring_keywords(self):
        """测试启发式打分：关键字命中 (最高优先级)"""
        # 构造一个两行的表，第一行是无杂乱文字，第二行命中关键字 "姓名", "金额"
        rows_dict = {
            1: {1: {"value": "测试报表"}, 2: {"value": ""}},
            2: {1: {"value": "姓名"}, 2: {"value": "金额"}},
            3: {1: {"value": "张三"}, 2: {"value": 500}}
        }
        scan_indices = [1, 2, 3]

        # 传入自定义关键字
        keywords = ["姓名", "金额"]

        # 预期：第 2 行应该因为命中双关键字得分最高，当选为表头行
        best_row = HeaderAnalyzer._heuristic_scoring(rows_dict, scan_indices, max_col=2,
                                                     custom_header_keywords=keywords)
        assert best_row == 2

    def test_heuristic_scoring_type_mutation(self):
        """测试启发式打分：数据类型突变 (纯字符串 -> 包含数字)"""
        rows_dict = {
            1: {1: {"value": "Title A"}, 2: {"value": "Title B"}},  # 都是字符串
            2: {1: {"value": "Data 1"}, 2: {"value": 99.9}},  # 出现数字
            3: {1: {"value": "Data 2"}, 2: {"value": 88.8}}
        }
        scan_indices = [1, 2, 3]

        # 预期：第 1 行与第 2 行发生类型突变组合，第 1 行得高分
        best_row = HeaderAnalyzer._heuristic_scoring(rows_dict, scan_indices, max_col=2)
        assert best_row == 1

    def test_llm_scoring_success(self):
        """测试 LLM 命中并成功返回合规 JSON"""
        # 伪造返回一段夹带废话和有效 JSON 的字符串
        mock_response = """
        经过分析，我判断表头如下：
        {"header_row_count": 2, "boundary_row_idx": 2}
        希望对您有帮助。
        """
        mock_llm_service = MagicMock()
        mock_llm_service.chat.return_value = mock_response

        rows_dict = {1: {1: {"value": "A"}}, 2: {1: {"value": "B"}}, 3: {1: {"value": "C"}}}
        scan_indices = [1, 2, 3]

        best_row = HeaderAnalyzer._llm_scoring(rows_dict, scan_indices, max_col=1, llm_service=mock_llm_service)

        assert best_row == 2
        # 验证大模型被正确调用了一次
        mock_llm_service.chat.assert_called_once()

    def test_llm_scoring_fallback(self):
        """测试 LLM 报错或返回垃圾数据时，是否正确降级返回 0"""
        mock_llm_service = MagicMock()
        mock_llm_service.chat.side_effect = Exception("LLM Timeout/Network Error")

        rows_dict = {1: {1: {"value": "A"}}}

        # 预期：发生异常时不抛出错误，而是返回边界 0 (用于触发外部降级)
        best_row = HeaderAnalyzer._llm_scoring(rows_dict, [1], max_col=1, llm_service=mock_llm_service)
        assert best_row == 0

    @patch.object(HeaderAnalyzer, '_heuristic_scoring')
    @patch.object(HeaderAnalyzer, '_llm_scoring')
    def test_analyze_orchestration(self, mock_llm_scoring, mock_heuristic_scoring):
        """测试整体 main analyze 函数的调度路由机制"""
        content = [create_mock_cell(1, 1, "ID"), create_mock_cell(2, 1, 1)]

        # 场景 A: 开启 LLM，且 LLM 成功分析 (返回边界 1)
        mock_llm_service = MagicMock()
        mock_llm_scoring.return_value = 1

        res1 = HeaderAnalyzer.analyze("f.xlsx", "s1", content, use_llm_layout_analyzer=True,
                                      llm_service=mock_llm_service)

        mock_llm_scoring.assert_called_once()  # LLM调用了
        mock_heuristic_scoring.assert_not_called()  # 没走到启发式分析
        assert res1.headers[0]['row'] == 1
        assert res1.body_rows[0]['row'] == 2

        # -----------------------------------------------------------------
        mock_llm_scoring.reset_mock()
        mock_heuristic_scoring.reset_mock()

        # 场景 B: 开启 LLM，但 LLM 遭遇失败 (返回0)，退化到启发式
        mock_llm_scoring.return_value = 0
        mock_heuristic_scoring.return_value = 1

        res2 = HeaderAnalyzer.analyze("f.xlsx", "s1", content, use_llm_layout_analyzer=True,
                                      llm_service=mock_llm_service)

        mock_llm_scoring.assert_called_once()  # LLM 尝试了
        mock_heuristic_scoring.assert_called_once()  # 降级并调用了启发式
        assert len(res2.headers) == 1
