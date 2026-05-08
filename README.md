# llm-excel-parser

**llm-excel-parser** 是一个专为大语言模型（LLM）场景设计的 Python Excel 解析库。它能将 `.xlsx` / `.xls` 文件智能解析、切片，输出结构化、带上下文的 `ExcelChunk` 列表，可直接作为 prompt 喂给任何 LLM。

---

## 核心特性

- **双格式兼容**：同时支持 `.xlsx`（openpyxl）和 `.xls`（xlrd），通过魔数嗅探自动路由，无感知切换
- **安全防护**：加载前读取 ZIP/XML 维度标签进行预检，拦截超大文件（行列超限），防御 OOM 炸弹
- **多表格检测**：基于 8-邻域连通域算法，自动识别单张 Sheet 内的多个独立子表，精确输出包围盒坐标
- **智能表头识别**：密度法 / 类型突变法 / 样式特征法三维启发式打分，支持 LLM 兜底分析与自定义关键词
- **灵活合并策略**：`fill_forward`（填充）/ `top_left`（保留主格）/ `tag`（占位符注入）三种策略
- **两种切片方式**：固定行数（含尾块合并）或 Token 上限（字符数估算），每块均自动携带表头
- **隐藏元素过滤**：可独立控制隐藏工作表、隐藏行/列的纳入与排除
- **LLM 服务集成**：透明包装用户的 LLM 客户端，自动注入指数退避重试、超时阻断、批量并发控制

---

## 安装

```bash
pip install llm-excel-parser
```

处理 `.xls` 格式时需要安装可选依赖：

```bash
pip install "llm-excel-parser[xls]"
# 或手动安装
pip install xlrd>=2.0.2
```

> **环境要求**：Python >= 3.10

---

## 快速上手

### 基础解析

```python
from llm_excel_parser import process_excel

chunks = process_excel("data.xlsx")

for chunk in chunks:
    print(f"[{chunk.chunk_id}] {chunk.metadata['sheetname']} "
          f"第 {chunk.metadata['start_row']}~{chunk.metadata['end_row']} 行")
    print(chunk.formatted_context)   # 直接传给 LLM 的上下文字符串
    print(chunk.raw_data)            # 原始 Python 字典列表
```

支持字节流输入（适用于从网络/数据库读取文件的场景）：

```python
with open("data.xlsx", "rb") as f:
    chunks = process_excel(f)

# 也支持 bytes 类型
with open("data.xlsx", "rb") as f:
    chunks = process_excel(f.read())
```

### 合并单元格策略

```python
from llm_excel_parser import MergeAction

# 向右/向下填充主格值（默认，适合大多数表格）
chunks = process_excel("data.xlsx", merge_action=MergeAction.FILL_FORWARD)

# 仅保留左上角值，从格置为 None（适合需要精确边界的场景）
chunks = process_excel("data.xlsx", merge_action=MergeAction.TOP_LEFT)

# 在从格注入带值的占位符标签（适合保留合并拓扑信息）
chunks = process_excel("data.xlsx", merge_action=MergeAction.TAG)
```

### 切片策略

```python
from llm_excel_parser import ChunkStrategy

# 固定行数策略（默认）：每块最多 50 行数据，尾块不足 10 行则并入上一块
chunks = process_excel(
    "data.xlsx",
    chunk_strategy=ChunkStrategy.FIXED_ROW,
    chunk_size=50,
)

# Token 上限策略：按 1字符 ≈ 0.5 Token 估算，每块不超过 2000 Token
chunks = process_excel(
    "data.xlsx",
    chunk_strategy=ChunkStrategy.TOKEN_LIMIT,
    max_tokens=2000,
)
```

### 自定义表头关键词

当表格中出现特定关键词时，该行的表头打分大幅提升，适用于格式固定的业务表格：

```python
chunks = process_excel(
    "data.xlsx",
    custom_header_keywords=["商品名称", "单价", "数量", "合计"],
)
```

### 隐藏元素处理

```python
# 默认：过滤所有隐藏工作表和隐藏行/列
chunks = process_excel("data.xlsx")

# 纳入隐藏工作表（hidden + veryHidden 状态均纳入）
chunks = process_excel("data.xlsx", include_hidden_sheets=True)

# 纳入隐藏行/列
chunks = process_excel("data.xlsx", include_hidden_rows=True)
```

---

## 集成 LLM 服务

### 第一步：实现接口

实现 `LLMServiceProtocol` 协议中的 `chat()` 方法，对接任意 LLM 后端：

```python
from llm_excel_parser import LLMServiceProtocol

class MyLLMService:
    """可对接 OpenAI / 通义千问 / 文心一言 / 本地模型等任意后端"""

    def __init__(self, api_key: str):
        self.client = ...  # 你的 LLM 客户端

    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
```

### 第二步：启用 LLM 辅助表头识别

对于布局复杂、启发式规则识别不准的表格，可开启 LLM 兜底分析：

```python
llm_service = MyLLMService(api_key="sk-...")

chunks = process_excel(
    "complex_layout.xlsx",
    use_llm_layout_analyzer=True,
    llm_service=llm_service,
)
```

### 第三步：批量并发处理切片

`LLMServiceWrapper` 将你的 LLM 服务包装为支持并发、重试、超时的生产级调用器：

```python
from llm_excel_parser import LLMServiceWrapper

# 包装后自动具备：3 次指数退避重试、60s 超时阻断、4 路并发
wrapped = LLMServiceWrapper(
    MyLLMService(api_key="sk-..."),
    max_retries=3,
    timeout_seconds=60,
)

def build_prompt(chunk):
    return f"请从以下表格数据中提取关键信息：\n\n{chunk.formatted_context}"

# 返回与 chunks 等长的响应列表，失败位置为 None
results = wrapped.batch_process_chunks(chunks, prompt_builder=build_prompt, max_workers=4)

for chunk, result in zip(chunks, results):
    if result:
        print(f"[{chunk.chunk_id}] {result}")
```

> **责任划分说明**
>
> | 功能 | 库负责 | 调用方负责 |
> |---|---|---|
> | 并发控制 | ✅ | |
> | 错误重试（指数退避） | ✅ | |
> | 超时阻断 | ✅ | |
> | 负载均衡（多 Key 轮询） | | ✅ |
> | 请求大模型 | | ✅ |

---

## API 参考

### `process_excel()`

```python
def process_excel(
    source: Union[str, bytes, BinaryIO],
    merge_action: MergeAction = MergeAction.FILL_FORWARD,
    chunk_strategy: Union[str, ChunkStrategy] = ChunkStrategy.FIXED_ROW,
    chunk_size: int = 50,
    max_tokens: int = 2000,
    max_rows: int = 100000,
    max_cols: int = 1000,
    include_hidden_sheets: bool = False,
    include_hidden_rows: bool = False,
    use_llm_layout_analyzer: bool = False,
    llm_service: Optional[LLMServiceProtocol] = None,
    custom_header_keywords: Optional[List[str]] = None,
) -> List[ExcelChunk]: ...
```

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `source` | `str \| bytes \| BinaryIO` | 必填 | 本地路径、字节流或文件对象 |
| `merge_action` | `MergeAction` | `FILL_FORWARD` | 合并单元格处理策略 |
| `chunk_strategy` | `ChunkStrategy \| str` | `FIXED_ROW` | 切片策略（也接受等价字符串） |
| `chunk_size` | `int` | `50` | 固定行数策略每块行数上限 |
| `max_tokens` | `int` | `2000` | Token 限制策略每块 Token 上限 |
| `max_rows` | `int` | `100000` | 单 Sheet 最大行数（超限抛出 `OverDimensionError`） |
| `max_cols` | `int` | `1000` | 单 Sheet 最大列数（超限抛出 `OverDimensionError`） |
| `include_hidden_sheets` | `bool` | `False` | 是否纳入隐藏工作表 |
| `include_hidden_rows` | `bool` | `False` | 是否纳入隐藏行/列 |
| `use_llm_layout_analyzer` | `bool` | `False` | 启用 LLM 辅助表头识别 |
| `llm_service` | `LLMServiceProtocol` | `None` | LLM 服务实例 |
| `custom_header_keywords` | `List[str]` | `None` | 自定义表头关键词（命中大幅加分） |

### `ExcelChunk`

```python
@dataclass
class ExcelChunk:
    chunk_id: str              # 8 位十六进制唯一 ID
    metadata: Dict[str, Any]  # 上下文元信息（见下表）
    formatted_context: str    # 可直接传入 LLM 的 Markdown 格式上下文字符串
    raw_data: List[Dict]      # 原始行数据列表
```

`metadata` 字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `filename` | `str` | 文件名 |
| `sheetname` | `str` | 工作表名（单 Sheet 内多子表时附 `_T1`、`_T2` 等后缀） |
| `chunk_index` | `int` | 当前分块序号（从 1 开始） |
| `total_chunks` | `int` | 本表格总分块数 |
| `start_row` | `int` | 数据起始物理行号 |
| `end_row` | `int` | 数据结束物理行号 |
| `strategy` | `str` | 切片策略名称 |
| `approx_tokens` | `int` | 当前块预估 Token 数 |

### `formatted_context` 格式示例

```
=== 电子表格数据片段 (1/3) ===
📌 文件名: sales_report.xlsx | 工作表: Sheet1
📌 行号范围: 2 ~ 51
--------------------------------------------------
表头 | 商品名称 | 单价 | 数量 | 合计
--------------------------------------------------
行2 | 苹果 | 5.5 | 100 | 550
行3 | 香蕉 | 3.2 | 200 | 640
行4 | 橙子 | 4.8 | 150 | 720
```

---

## 异常处理

所有异常均继承自 `ExcelParserBaseException`，可按需细粒度捕获：

```python
from llm_excel_parser import (
    ExcelParserBaseException,   # 基类，捕获所有解析错误
    OverDimensionError,         # 文件行/列数超限（Phase 1）
    UnsupportedFormatError,     # 不支持的文件格式（Phase 1）
    StructureDetectionError,    # 表格结构探测失败（Phase 2）
    DataRenderError,            # 数据渲染失败（Phase 3）
    HeaderAnalysisError,        # 表头识别失败（Phase 4）
)

try:
    chunks = process_excel("data.xlsx", max_rows=50000)
except OverDimensionError as e:
    print(f"文件过大，请拆分后重试: {e}")
except UnsupportedFormatError as e:
    print(f"不支持的格式，仅支持 .xlsx 和 .xls: {e}")
except ExcelParserBaseException as e:
    print(f"解析失败: {e}")
```

---

## 处理流水线

```
输入 (str路径 / bytes / BinaryIO)
        │
        ▼  Phase 1 · 安全预检与文件加载
        ├─ 魔数嗅探，自动识别 XLSX / XLS 并路由
        ├─ XML 维度预检（不加载全文件，直接读 dimension 标签）
        └─ 隐藏工作表 / 隐藏行 / 隐藏列过滤
        │
        ▼  Phase 2 · 结构探测与区块划分
        ├─ 构建稀疏布尔矩阵（含合并单元格全区域修补）
        └─ 8-邻域连通域聚类 → List[BoundingBox]
        │
        ▼  Phase 3 · 数据渲染与合并单元格消解
        ├─ 基础类型清洗（1.0→1，datetime 标准化）
        └─ 按策略渲染合并区域 → List[List[Any]]
        │
        ▼  Phase 4 · 表头识别专家系统
        ├─ 启发式三维打分（密度 / 类型突变 / 样式突变）
        ├─ 自定义关键词加权
        ├─ [可选] LLM 布局探测兜底
        └─ 切分 header / body → StructuredTable
        │
        ▼  Phase 5 · 切片与上下文组装
        ├─ 固定行数或 Token 上限切片（每块携带完整表头）
        └─ 封装物理行号、元信息 → List[ExcelChunk]
```

---

## 依赖

| 包 | 版本要求 | 用途 |
|---|---|---|
| `openpyxl` | ≥ 3.1.5 | XLSX 文件解析（必需） |
| `xlrd` | ≥ 2.0.2 | XLS 文件解析（可选，仅处理 .xls 时需要） |

本库不依赖任何特定的 LLM SDK，由用户自行安装并实现 `LLMServiceProtocol` 接口后传入。

---

## 许可证

[MIT License](LICENSE)