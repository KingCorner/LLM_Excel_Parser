#    -*- coding: UTF-8 -*-
#   @Author:   KingCorner
#   @Time:     2026/4/16 19:19
#   @FileRole: 全局配置中心

class GlobalConfig:
    # --- Phase 2: 结构探测层配置 ---
    # 容忍的最大连续空行数 (超过此数值则认为是两个独立的表格)
    DETECT_MAX_EMPTY_ROWS: int = 5
    # 容忍的最大连续空列数
    DETECT_MAX_EMPTY_COLS: int = 3

    # --- 全局安全限制 (从架构图中提取) ---
    # 防止读取恶意超大文件导致 OOM
    MAX_ROW_LIMIT: int = 100000
    MAX_COL_LIMIT: int = 1000

    # --- LLM 交互配置 ---
    # 调用 LLM 的默认最大重试次数
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 60


# 实例化一个单例供全局导入使用
default_config = GlobalConfig()
