#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 17:37
#   @FileRole: 核心接口定义

from typing import Protocol, Any, Dict, Tuple, List, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_excel_parser.core.datatypes import CellStyle
from abc import ABC, abstractmethod


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


class BaseWorksheet(ABC):
    """
    统一的工作表适配器接口 (Engine-Agnostic)
    流水线 Phase 2-5 仅依赖此接口，剥离对任意底层库的依赖
    """

    @property
    @abstractmethod
    def title(self) -> str:
        """获取 Sheet 名称"""
        pass

    @property
    @abstractmethod
    def max_dimensions(self) -> Tuple[int, int]:
        """获取当前工作表的最大范围，返回 (max_row, max_col)"""
        pass

    @abstractmethod
    def get_cell_value(self, row: int, col: int) -> Any:
        """获取指定行、列单元格的真实值(1-based)"""
        pass

    @abstractmethod
    def iter_rows(self, min_row: int, max_row: int, min_col: int, max_col: int) -> Iterator[List[Any]]:
        """迭代指定范围内的行数据，返回只包含值的生成器"""
        pass

    @abstractmethod
    def get_merged_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取所有合并单元格的坐标信息列表: [(min_row, min_col, max_row, max_col), ...]"""
        pass

    @abstractmethod
    def is_row_hidden(self, row: int) -> bool:
        """判断某一行是否被隐藏"""
        pass

    @abstractmethod
    def is_col_hidden(self, col: int) -> bool:
        """判断某一列是否被隐藏"""
        pass

    @abstractmethod
    def get_cell_style(self, row: int, col: int) -> 'CellStyle':
        """获取指定单元格的样式特征，返回 CellStyle 字典 (1-based)"""
        pass
