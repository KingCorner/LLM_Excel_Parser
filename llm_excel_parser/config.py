#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 19:19
#   @FileRole: 全局配置

class GlobalConfig:
    # Phase 2: 结构探测层配置
    # 容忍的最大连续空行数 (超过此数值则认为是两个独立的表格)
    DETECT_MAX_EMPTY_ROWS: int = 5
    # 容忍的最大连续空列数
    DETECT_MAX_EMPTY_COLS: int = 3

    # Phase 4: 表头识别层配置 (启发式 & LLM)
    HEADER_SCAN_ROW_LIMIT: int = 5  # 启发式扫描的最大行数 (默认扫前5行)
    HEADER_LLM_SCAN_ROW_LIMIT: int = 10  # LLM布局探测扫描的最大行数 (默认给LLM看前10行)
    HEADER_MIN_SCORE_THRESHOLD: int = 25  # 判定为表头的最低分数线阈值

    # Phase 4 启发式打分权重配置
    HEADER_DENSITY_THRESHOLD: float = 0.8  # 高密度判定阈值 (非空单元格占比>80%)
    HEADER_WEIGHT_DENSITY_HIGH: int = 30  # 满足高宽度密度的得分
    HEADER_WEIGHT_KEYWORD_MATCH: int = 50  # 命中自定义关键字单次得分 (权重极高)
    HEADER_WEIGHT_TYPE_MUTATION: int = 40  # 数据类型突变得分 (如: 纯文本突变为纯数字)
    HEADER_WEIGHT_STYLE_MUTATION: int = 20  # 样式突变得分 (如: 加粗/背景色 突变为 无样式)

    # 全局安全限制
    # 防止读取恶意超大文件导致 OOM
    MAX_ROW_LIMIT: int = 100000
    MAX_COL_LIMIT: int = 1000

    # LLM 交互配置
    # 调用 LLM 的默认最大重试次数
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 60


# 实例化一个单例供全局导入使用
default_config = GlobalConfig()
