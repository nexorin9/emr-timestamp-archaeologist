# EMR Timestamp Archaeologist - 病历时间戳考古器

用考古学「地层学」方法分析电子病历（EMR）各章节的时间戳，构建「病历考古地层图」，自动检测倒填时间、突击补写、批处理造假等异常时间模式，生成可视化的真实性审计报告。

## 项目背景

电子病历的时间戳真实性是医疗质量管理和医保合规审计的重要关注点。传统的病历审查依赖人工逐份检查，效率低下且难以发现系统性造假模式。本工具借鉴考古学的地层学方法，将病历各章节的时间戳按创建顺序排列为「地层」，通过多维度算法检测异常时间模式。

## 核心功能

### 1. EMR 元数据解析
- 支持 XML、JSON、CSV 多种格式
- 自动提取病历各章节的创建时间、修改时间
- 统一时间格式处理（支持 ISO8601、Unix timestamp、常见日期格式）

### 2. 时序地层图构建
- 将病历章节按时间顺序构建可视化「地层图」
- 标注关键业务时间锚点（手术开始、入院时间等）
- 支持导出为 JSON 格式供后续分析

### 3. 多类型时间戳异常检测
- **批处理痕迹检测**：检测同一时间段内多份病历时间戳完全相同的模式
- **夜间突击补写检测**：识别夜间（22:00-05:00）集中修改病历的行为
- **时间线矛盾检测**：检测章节时间与业务时间锚点的矛盾
- **异常序列模式检测**：检测修改时间回溯、周期性修改等异常模式

### 4. LLM 叙述性分析报告
- 调用大语言模型生成考古学风格的叙述性审计报告
- 自动生成科室风险排行和整改建议

### 5. CLI + HTML 可视化界面
- 完整的命令行工具，支持批量分析和报告生成
- 交互式 HTML 报告，支持地层图可视化和异常筛选

## 技术架构

```
emr-timestamp-archaeologist/
├── src/
│   ├── py/                    # Python 数据处理和检测引擎
│   │   ├── models.py          # 核心数据模型
│   │   ├── parser.py          # EMR 元数据解析器
│   │   ├── stratum_builder.py # 时序地层图构建器
│   │   ├── detectors/         # 各类异常检测器
│   │   ├── detection_engine.py# 综合异常检测引擎
│   │   ├── llm_reporter.py    # LLM 报告生成器
│   │   ├── report_renderer.py # HTML 报告渲染器
│   │   ├── pipeline.py        # 主分析管道
│   │   ├── config.py          # 配置管理
│   │   ├── debug_tools.py     # 调试工具
│   │   └── cli.py             # Python CLI 入口
│   └── cli/                   # TypeScript/Node.js CLI
│       ├── index.ts           # 主入口
│       └── commands/          # 命令模块
├── data/                      # 示例数据和测试数据
├── templates/                 # HTML 报告模板
└── tests/                     # 测试文件
```

## 技术栈

- **Python**：数据处理、统计、LLM 集成
- **TypeScript/Node.js**：CLI 界面
- **HTML/CSS/JavaScript**：可视化报告

## 安装

### 环境要求

- Python >= 3.10
- Node.js >= 18.0.0

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd emr-timestamp-archaeologist
   ```

2. **安装 Python 依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **安装 Node.js 依赖**
   ```bash
   npm install
   ```

4. **构建项目**
   ```bash
   npm run build
   ```

## 快速开始

### 1. 配置 API Key

```bash
# 首次使用需要配置 LLM API key
emr-archaeologist config set-api-key
```

或创建 `.env` 文件：
```env
ANTHROPIC_API_KEY=your-api-key-here
```

### 2. 准备数据

将病历元数据导出为 XML、JSON 或 CSV 格式。数据格式示例：

**XML 格式**：
```xml
<emr_record>
  <patient_id>P12345</patient_id>
  <visit_id>V20240301</visit_id>
  <chapter id="admission" name="入院记录">
    <created_time>2024-03-01 08:30:00</created_time>
    <modified_time>2024-03-01 08:30:00</modified_time>
    <author_id>DR001</author_id>
  </chapter>
  <chapter id="surgery" name="手术记录">
    <created_time>2024-03-01 10:00:00</created_time>
    <modified_time>2024-03-01 14:30:00</modified_time>
    <author_id>DR002</author_id>
  </chapter>
</emr_record>
```

**JSON 格式**：
```json
{
  "patient_id": "P12345",
  "visit_id": "V20240301",
  "record_type": "inpatient",
  "business_time": "2024-03-01T09:00:00",
  "chapters": [
    {
      "chapter_id": "admission",
      "chapter_name": "入院记录",
      "chapter_order": 1,
      "created_time": "2024-03-01T08:30:00",
      "modified_time": "2024-03-01T08:30:00",
      "author_id": "DR001"
    }
  ]
}
```

### 3. 运行分析

```bash
# 分析病历数据
emr-archaeologist analyze --input ./data/sample.xml --output ./output/

# 生成 HTML 报告
emr-archaeologist report --input ./output/analysis_result.json --output ./output/report.html

# 启动本地服务器预览报告
emr-archaeologist serve --port 8080
```

### 4. 查看报告

HTML 报告包含：
- **病历考古地层图**：可视化展示各章节时间戳关系
- **异常时间线**：高亮标注所有检测到的异常
- **批处理热力图**：展示批处理痕迹的时空分布
- **夜间活动图**：展示夜间修改活动的分布
- **综合风险仪表盘**：展示整体风险评分和各类型占比

## 命令参考

### analyze - 分析病历

```bash
emr-archaeologist analyze [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input, -i` | 输入文件路径或目录 | 必需 |
| `--output, -o` | 输出目录 | ./output/ |
| `--format, -f` | 输入格式（auto/xml/json/csv） | auto |
| `--llm` | 启用 LLM 报告生成 | true |
| `--detectors` | 指定启用的检测器 | all |
| `--verbose` | 输出详细日志 | false |
| `--debug` | 启用调试模式 | false |

### report - 生成报告

```bash
emr-archaeologist report [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input, -i` | 分析结果 JSON 文件路径 | 必需 |
| `--output, -o` | 输出 HTML 文件路径 | report.html |
| `--template` | 报告模板路径 | 内置模板 |
| `--no-browser` | 生成报告后不自动打开浏览器 | false |

### serve - 启动预览服务器

```bash
emr-archaeologist serve [options]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--port, -p` | 服务器端口 | 8080 |
| `--host` | 服务器地址 | localhost |
| `--no-browser` | 不自动打开浏览器 | false |

### config - 配置管理

```bash
emr-archaeologist config [options]
```

| 子命令 | 说明 |
|--------|------|
| `set-api-key` | 设置 API key |
| `show` | 显示当前配置 |
| `reset` | 重置配置 |

## 异常类型说明

### 1. 批处理痕迹（BATCH_PROCESSING）

**特征**：同一时间段内，多份病历的时间戳完全相同（精确到秒）。

**可能原因**：
- 批量导入历史病历
- 系统迁移导致的时间戳统一
- 故意造假的时间戳批处理

**处理建议**：
1. 核实相关病历的纸质原件
2. 检查同期是否有大量病历集中归档
3. 结合其他异常综合判断

### 2. 夜间突击补写（NIGHT_RUSH）

**特征**：在夜间时段（22:00-05:00）集中创建或修改病历。

**可能原因**：
- 值班医生补写病历
- 出院病历集中归档
- 恶意规避检查的突击补写

**处理建议**：
1. 统计各科室夜间修改比例
2. 与历史基线对比，识别异常高峰
3. 重点抽查夜间修改量大的科室

### 3. 时间线矛盾（TIME_CONTRADICTION）

**特征**：病历章节之间的时间顺序不符合医疗规范。

**示例**：
- 手术记录创建时间早于手术开始时间
- 出院小结创建时间早于出院时间
- 病程记录时间早于入院时间

**处理建议**：
1. 核实业务时间锚点的准确性
2. 检查是否有系统时间设置错误
3. 结合其他证据判断是否为时间篡改

### 4. 锚点违规（ANCHOR_VIOLATION）

**特征**：章节时间戳早于关键业务时间锚点。

**示例**：
- 手术记录在手术开始前已创建
- 死亡病例在死亡时间前已归档

**处理建议**：
1. 立即核实相关业务事实
2. 检查系统时间设置
3. 报请主管部门调查

### 5. 可疑序列（SUSPICIOUS_SEQUENCE）

**特征**：修改时间存在回溯、周期性规律或异常接近。

**示例**：
- 第二次修改时间早于第一次
- 每天固定时间修改
- 多个章节在5分钟内连续修改

**处理建议**：
1. 分析修改序列的时间间隔分布
2. 检测是否存在自动化修改模式
3. 重点关注风险评分高的病历

## 输入数据格式

### XML 格式

```xml
<?xml version="1.0" encoding="UTF-8"?>
<emr_batch>
  <record>
    <patient_id>P12345</patient_id>
    <visit_id>V20240301</visit_id>
    <record_type>inpatient</record_type>
    <business_time>2024-03-01 09:00:00</business_time>
    <chapters>
      <chapter id="admission" name="入院记录" order="1">
        <created_time>2024-03-01 08:30:00</created_time>
        <modified_time>2024-03-01 08:30:00</modified_time>
        <author_id>DR001</author_id>
      </chapter>
    </chapters>
  </record>
</emr_batch>
```

### JSON 格式

```json
{
  "records": [
    {
      "patient_id": "P12345",
      "visit_id": "V20240301",
      "record_type": "inpatient",
      "business_time": "2024-03-01T09:00:00",
      "chapters": [
        {
          "chapter_id": "admission",
          "chapter_name": "入院记录",
          "chapter_order": 1,
          "created_time": "2024-03-01T08:30:00",
          "modified_time": "2024-03-01T08:30:00",
          "author_id": "DR001"
        }
      ]
    }
  ]
}
```

### CSV 格式

```csv
patient_id,visit_id,record_type,chapter_id,chapter_name,chapter_order,created_time,modified_time,author_id
P12345,V20240301,inpatient,admission,入院记录,1,2024-03-01 08:30:00,2024-03-01 08:30:00,DR001
P12345,V20240301,inpatient,surgery,手术记录,2,2024-03-01 14:30:00,2024-03-01 14:30:00,DR002
```

## 输出报告解读

### 地层图

横向为时间轴，纵向为章节层级。每个章节显示为一条色块，颜色表示章节类型。时间轴上标注关键业务锚点（如手术开始时间）。

**阅读方法**：
- 正常情况下，章节按时间顺序从下向上排列
- 如果出现章节跨越其他章节（如手术记录在入院记录之前），需重点关注
- 异常章节用红色标记

### 风险分数

综合风险分数为 0-100 的评分，分数越高风险越大。

| 分数范围 | 风险等级 | 说明 |
|----------|----------|------|
| 0-30 | 低风险 | 基本正常 |
| 31-60 | 中风险 | 存在轻微异常，建议关注 |
| 61-80 | 高风险 | 存在明显异常，需要核查 |
| 81-100 | 极高风险 | 存在严重异常，必须处理 |

## 常见问题

**Q: 支持哪些 EMR 系统导出的数据？**
A: 目前支持标准 XML、JSON、CSV 格式的通用导出格式。如需特定 EMR 系统格式支持，请提交 Issue。

**Q: LLM 报告生成是否必须？**
A: 可以使用 `--no-llm` 选项禁用 LLM 报告生成，仅输出结构化的 JSON 结果。

**Q: 如何处理大量病历数据？**
A: 建议使用 `--input` 指定包含多个文件的目录，程序会自动批量处理。

**Q: 夜间时间段可以修改吗？**
A: 可以通过配置文件修改 `night_start` 和 `night_end` 参数。

**Q: 报告可以导出为 PDF 吗？**
A: 可以使用 `--export-pdf` 选项（需要安装 Playwright 或 WeasyPrint）。

**Q: 如何调试检测结果？**
A: 使用 `--debug` 和 `--verbose` 选项可以输出详细的检测过程和中间结果。

**Q: 误报率如何控制？**
A: 可以通过设置检测器的阈值参数来平衡灵敏度和误报率。

**Q: 是否支持网络获取 EMR 数据？**
A: 可以通过 `serve` 命令的 `--api-proxy` 选项代理 API 请求。

**Q: 数据安全如何保障？**
A: 所有数据处理在本地完成，不会上传到任何服务器。API key 采用加密存储。

**Q: 如何参与开发？**
A: 欢迎提交 Pull Request 或 Issue。

## 许可协议

Apache License 2.0 - 详见 LICENSE 文件

---

## 支持作者

如果您觉得这个项目对您有帮助，欢迎打赏支持！
Wechat:gdgdmp
![Buy Me a Coffee](buymeacoffee.png)

**Buy me a coffee (crypto)**

| 币种 | 地址 |
|------|------|
| BTC | `bc1qc0f5tv577z7yt59tw8sqaq3tey98xehy32frzd` |
| ETH / USDT | `0x3b7b6c47491e4778157f0756102f134d05070704` |
| SOL | `6Xuk373zc6x6XWcAAuqvbWW92zabJdCmN3CSwpsVM6sd` |
