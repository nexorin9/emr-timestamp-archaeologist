"""
EMR Timestamp Archaeologist - LLM 报告生成器
使用 LLM 将检测结果转化为可读性强的考古学风格叙述报告
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models import AnomalyType, TimestampAnomaly

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@dataclass
class DepartmentRisk:
    """科室风险数据"""
    department: str
    anomaly_count: int
    risk_score: float
    primary_anomaly_types: list[str] = field(default_factory=list)


@dataclass
class LLMReport:
    """LLM 生成的报告"""
    narrative: str = ""
    summary_table: str = ""
    department_ranking: str = ""
    recommendations: str = ""
    full_report: str = ""
    generated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.generated_at is None:
            self.generated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "narrative": self.narrative,
            "summary_table": self.summary_table,
            "department_ranking": self.department_ranking,
            "recommendations": self.recommendations,
            "full_report": self.full_report,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


class LLMReporter:
    """
    LLM 报告生成器

    将病历时间戳异常检测结果转化为考古学风格的叙述报告。
    使用「文物鉴定」「地层分析」「年代测定」等比喻。

    Attributes:
        api_key: LLM API 密钥
        model: 使用的模型名称
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    """

    # 异常类型中文名称映射
    ANOMALY_TYPE_NAMES = {
        AnomalyType.BATCH_PROCESSING: "批处理痕迹",
        AnomalyType.NIGHT_RUSH: "夜间突击补写",
        AnomalyType.TIME_CONTRADICTION: "时间线矛盾",
        AnomalyType.SUSPICIOUS_SEQUENCE: "异常修改序列",
        AnomalyType.ANCHOR_VIOLATION: "锚点违规",
    }

    # 严重程度标签
    SEVERITY_LABELS = {
        (8, 10): "严重",
        (5, 7): "中等",
        (3, 4): "轻微",
        (0, 2): "提示",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        初始化 LLM 报告生成器

        Args:
            api_key: LLM API 密钥
            model: 使用的模型名称，默认为 gpt-4o-mini
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 初始化 LLM 客户端
        self._client = None
        self._provider = self._detect_provider()

    def _detect_provider(self) -> str:
        """检测 LLM 提供商"""
        if self.model.startswith("claude"):
            if not HAS_ANTHROPIC:
                raise ImportError("anthropic package is required for Claude models")
            return "anthropic"
        elif self.model.startswith("gpt") or self.model.startswith("o1") or self.model.startswith("o3"):
            if not HAS_OPENAI:
                raise ImportError("openai package is required for OpenAI models")
            return "openai"
        else:
            # 默认使用 OpenAI
            if not HAS_OPENAI:
                raise ImportError("openai package is required")
            return "openai"

    def _get_client(self) -> object:
        """获取 LLM 客户端"""
        if self._client is None:
            if self._provider == "anthropic":
                self._client = anthropic.Anthropic(api_key=self.api_key)
            else:
                self._client = openai.OpenAI(api_key=self.api_key)
        return self._client

    def build_system_prompt(self) -> str:
        """
        构建系统提示词（考古学家角色设定）

        Returns:
            str: 系统提示词
        """
        return """你是「病历时间戳考古研究院」的资深考古学家。

你的专业是用考古学的方法论来分析电子病历的时间戳，识别倒填时间、突击补写、批处理造假等异常模式。

你的分析风格：
- 严谨、科学、客观
- 使用考古学比喻（地层学、文物鉴定、年代测定）
- 叙事流畅，可读性强
- 对异常发现保持中立，只陈述事实和证据

你即将阅读一份病历时间戳检测报告，需要以考古学家的视角撰写一份鉴定报告。

报告结构：
1. 开篇：概述本次「考古挖掘」的整体发现
2. 地层分析：详细解读各类异常的时间分布特征
3. 文物鉴定：对每个异常进行「年代测定」和真伪评估
4. 出土报告：给出总体评价和风险定级
5. 审批意见：提出整改建议

注意：
- 保持专业的考古学语气
- 异常就是「出土文物」，不是「犯罪证据」
- 避免使用「欺诈」「造假」等带有情感倾向的词汇
- 重点关注时间线地层的完整性和一致性
- 你的报告将用于医院内部质量控制，而非追责"""

    def build_user_prompt(
        self,
        report_data: dict,
        include_details: bool = True,
    ) -> str:
        """
        根据检测结果构建用户提示词

        Args:
            report_data: 检测报告数据
            include_details: 是否包含详细异常信息

        Returns:
            str: 用户提示词
        """
        # 提取关键信息
        total_records = report_data.get("total_records", 0)
        total_anomalies = report_data.get("total_anomalies", 0)
        overall_risk_score = report_data.get("overall_risk_score", 0)
        risk_level = report_data.get("risk_level", "未知")

        # 异常类型分布
        anomalies_by_type = report_data.get("anomalies_by_type", {})
        type_details = []
        for atype, count in anomalies_by_type.items():
            type_name = self.ANOMALY_TYPE_NAMES.get(AnomalyType(atype), atype)
            type_details.append(f"- {type_name}: {count}例")

        # 严重程度分布
        anomalies_by_severity = report_data.get("anomalies_by_severity", {})
        severity_details = []
        for label, count in anomalies_by_severity.items():
            severity_details.append(f"- {label}: {count}例")

        # 统计摘要
        summary_stats = report_data.get("summary_stats", {})
        records_with_anomalies = summary_stats.get("records_with_anomalies", 0)

        # 构建基础信息部分
        prompt = f"""## 病历时间戳考古报告

### 挖掘概况

本次考古挖掘共扫描病历记录 **{total_records}** 份，发现时间戳异常 **{total_anomalies}** 处，涉及 **{records_with_anomalies}** 份病历。

### 风险定级

综合风险评分：**{overall_risk_score}/100**（{risk_level}）

### 异常类型分布

{chr(10).join(type_details) if type_details else "无异常类型数据"}

### 严重程度分布

{chr(10).join(severity_details) if severity_details else "无严重程度数据"}
"""

        # 添加详细异常列表
        if include_details:
            top_anomalies = report_data.get("top_anomalies", [])
            if top_anomalies:
                anomaly_details = []
                for i, anomaly in enumerate(top_anomalies[:10], 1):
                    atype = anomaly.get("anomaly_type", "unknown")
                    type_name = self.ANOMALY_TYPE_NAMES.get(AnomalyType(atype), atype)
                    severity = anomaly.get("severity", 0)
                    severity_label = anomaly.get("severity_label", "未知")
                    description = anomaly.get("description", "")
                    affected = anomaly.get("affected_records", [])

                    anomaly_details.append(f"""
### 异常 {i}: {type_name}

- **严重程度**: {severity}/10 ({severity_label})
- **描述**: {description}
- **涉及记录**: {len(affected)}份""")

                prompt += f"""
### 重点出土文物（Top 10 异常）

{chr(10).join(anomaly_details)}
"""

        prompt += """
---

请以考古学家的视角，撰写一份完整的鉴定报告。
报告需要包含：
1. 开篇概述（整体评价）
2. 地层分析（时间分布特征）
3. 文物鉴定（重点异常解读）
4. 风险评估（综合评价）
5. 审批意见（整改建议）

报告语言：中文
语气：专业、严谨、可读性强
格式：Markdown"""

        return prompt

    async def generate_narrative_async(
        self,
        report_data: dict,
    ) -> str:
        """
        异步调用 LLM 生成考古学风格的叙述报告

        Args:
            report_data: 检测报告数据

        Returns:
            str: 叙述报告文本
        """
        client = self._get_client()
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(report_data, include_details=True)

        if self._provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        else:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content

    def generate_narrative(
        self,
        report_data: dict,
    ) -> str:
        """
        调用 LLM 生成考古学风格的叙述报告

        Args:
            report_data: 检测报告数据

        Returns:
            str: 叙述报告文本
        """
        client = self._get_client()
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(report_data, include_details=True)

        if self._provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        else:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content

    def generate_summary_table(
        self,
        report_data: dict,
    ) -> str:
        """
        生成异常汇总表格（Markdown 格式）

        Args:
            report_data: 检测报告数据

        Returns:
            str: Markdown 格式的异常汇总表格
        """
        total_records = report_data.get("total_records", 0)
        total_anomalies = report_data.get("total_anomalies", 0)
        overall_risk_score = report_data.get("overall_risk_score", 0)
        risk_level = report_data.get("risk_level", "未知")

        # 异常类型分布
        anomalies_by_type = report_data.get("anomalies_by_type", {})
        type_rows = []
        for atype, count in anomalies_by_type.items():
            type_name = self.ANOMALY_TYPE_NAMES.get(AnomalyType(atype), atype)
            percentage = (count / total_anomalies * 100) if total_anomalies > 0 else 0
            type_rows.append(f"| {type_name} | {count} | {percentage:.1f}% |")

        # 严重程度分布
        anomalies_by_severity = report_data.get("anomalies_by_severity", {})
        severity_rows = []
        for label, count in anomalies_by_severity.items():
            severity_rows.append(f"| {label} | {count} |")

        table = f"""## 异常汇总表

### 总体概况

| 指标 | 数值 |
|------|------|
| 扫描病历数 | {total_records} |
| 发现异常数 | {total_anomalies} |
| 综合风险评分 | {overall_risk_score}/100 |
| 风险等级 | {risk_level} |

### 异常类型分布

| 异常类型 | 数量 | 占比 |
|----------|------|------|
| {chr(10).join(type_rows) if type_rows else "| 无异常 | 0 | 0% |"}

### 严重程度分布

| 严重程度 | 数量 |
|----------|------|
| {chr(10).join(severity_rows) if severity_rows else "| 无数据 | 0 |"}
"""

        return table

    def generate_department_ranking(
        self,
        report_data: dict,
    ) -> str:
        """
        生成科室级风险排行（如果数据包含科室信息）

        Args:
            report_data: 检测报告数据

        Returns:
            str: Markdown 格式的科室风险排行
        """
        # 从 detector_results 中提取科室信息
        detector_results = report_data.get("detector_results", [])

        # 提取 night_detector 的结果来计算科室夜间活动
        department_night_stats: dict[str, dict] = {}

        for result in detector_results:
            detector_name = result.get("detector_name", "")
            if detector_name == "night":
                anomalies = result.get("anomalies", [])
                for anomaly in anomalies:
                    evidence = anomaly.get("evidence", {})
                    department_info = evidence.get("department", "未知科室")
                    night_count = evidence.get("night_modification_count", 0)

                    if department_info not in department_night_stats:
                        department_night_stats[department_info] = {
                            "night_count": 0,
                            "total_anomalies": 0,
                        }
                    department_night_stats[department_info]["night_count"] += night_count
                    department_night_stats[department_info]["total_anomalies"] += 1

        if not department_night_stats:
            return """## 科室风险排行

> 暂无科室级别数据。检测结果中未包含足够的科室信息。

如需分析科室风险，请在病历元数据中包含 author_id 或 department 信息。
"""

        # 构建科室排行
        department_list = []
        for dept, stats in department_night_stats.items():
            night_count = stats["night_count"]
            total = stats["total_anomalies"]
            risk_score = min(100, (night_count / max(1, total)) * 100)
            department_list.append({
                "department": dept,
                "night_count": night_count,
                "total_anomalies": total,
                "risk_score": risk_score,
            })

        # 按风险分数排序
        department_list.sort(key=lambda x: -x["risk_score"])

        rows = []
        for i, dept in enumerate(department_list, 1):
            rows.append(
                f"| {i} | {dept['department']} | "
                f"{dept['night_count']} | {dept['total_anomalies']} | "
                f"{dept['risk_score']:.1f}% |"
            )

        return f"""## 科室风险排行（按夜间异常活动排序）

| 排名 | 科室 | 夜间异常数 | 总异常数 | 风险指数 |
|------|------|-----------|----------|----------|
| {chr(10).join(rows)}

> 风险指数 = 夜间异常数 / 总异常数 × 100%
"""

    def generate_recommendations(
        self,
        report_data: dict,
    ) -> str:
        """
        生成整改建议（以「考古报告审批意见」形式）

        Args:
            report_data: 检测报告数据

        Returns:
            str: Markdown 格式的整改建议
        """
        anomalies_by_type = report_data.get("anomalies_by_type", {})
        overall_risk_score = report_data.get("overall_risk_score", 0)
        risk_level = report_data.get("risk_level", "未知")

        recommendations = []

        # 根据异常类型给出针对性建议
        if AnomalyType.BATCH_PROCESSING.value in anomalies_by_type:
            count = anomalies_by_type[AnomalyType.BATCH_PROCESSING.value]
            recommendations.append(f"""
### 关于批处理痕迹

发现 **{count}例** 疑似批处理的异常。

**建议**：
1. 核查同一时间段内大量病历的书写权限记录
2. 检查是否存在模板复用或一键生成的情况
3. 确认相关科室的病历书写时间分布是否合理
""")

        if AnomalyType.NIGHT_RUSH.value in anomalies_by_type:
            count = anomalies_by_type[AnomalyType.NIGHT_RUSH.value]
            recommendations.append(f"""
### 关于夜间突击补写

发现 **{count}例** 夜间（22:00-05:00）异常修改的病历。

**建议**：
1. 核实夜间操作的真实性（如有条件，调取操作日志）
2. 评估相关科室的排班和工作流程
3. 考虑是否为值班期间补写，核实补写内容的时效性
""")

        if AnomalyType.TIME_CONTRADICTION.value in anomalies_by_type:
            count = anomalies_by_type[AnomalyType.TIME_CONTRADICTION.value]
            recommendations.append(f"""
### 关于时间线矛盾

发现 **{count}例** 时间线矛盾的异常。

**建议**：
1. 重点核查矛盾记录的业务背景
2. 检查医院信息系统的时间同步机制
3. 评估是否需要修正业务时间记录
""")

        if AnomalyType.SUSPICIOUS_SEQUENCE.value in anomalies_by_type:
            count = anomalies_by_type[AnomalyType.SUSPICIOUS_SEQUENCE.value]
            recommendations.append(f"""
### 关于异常修改序列

发现 **{count}例** 异常修改序列的病历。

**建议**：
1. 检查是否存在循环修改的情况
2. 评估修改内容的合理性
3. 考虑是否为系统故障导致的异常
""")

        if AnomalyType.ANCHOR_VIOLATION.value in anomalies_by_type:
            count = anomalies_by_type[AnomalyType.ANCHOR_VIOLATION.value]
            recommendations.append(f"""
### 关于锚点违规

发现 **{count}例** 锚点违规的异常。

**建议**：
1. 核查业务时间（如手术时间）与病历记录时间的一致性
2. 检查入院、出院时间等关键节点的记录准确性
3. 评估是否需要追溯修正
""")

        # 总体建议
        if overall_risk_score >= 70:
            overall_suggestion = """
### 总体评估

当前风险等级为 **「很高」** 或 **「极高」**，建议：

1. **立即开展专项检查**，核实异常记录的真实性
2. **追溯异常发生的时间段**，分析是否存在系统性原因
3. **上报主管部门**，启动正式的病历质量审查程序
"""
        elif overall_risk_score >= 50:
            overall_suggestion = """
### 总体评估

当前风险等级为 **「高」**，建议：

1. **加强病历书写的时间管理**，杜绝倒填时间行为
2. **开展科室自查**，对重点科室进行约谈
3. **完善病历质控机制**，将时间戳纳入常规检查项
"""
        elif overall_risk_score >= 30:
            overall_suggestion = """
### 总体评估

当前风险等级为 **「中等」** 或 **「低」**，建议：

1. **纳入常规质控**，对异常记录进行追踪
2. **开展培训宣教**，强化病历时间规范意识
3. **定期复检**，观察异常趋势变化
"""
        else:
            overall_suggestion = """
### 总体评估

当前风险等级为 **「极低」**，病历时间管理总体良好。

建议继续保持当前质控措施，定期开展常规检查。
"""

        recommendations_text = "".join(recommendations) if recommendations else "\n> 暂无针对性建议。\n"

        return f"""## 考古报告审批意见

{recommendations_text}

{overall_suggestion}

---

*本建议仅供参考，具体整改措施请结合医院实际情况制定。*
"""

    def generate_full_report(
        self,
        report_data: dict,
    ) -> LLMReport:
        """
        生成完整考古报告（摘要 + 异常详情 + 科室排行 + 建议）

        Args:
            report_data: 检测报告数据

        Returns:
            LLMReport: 完整的 LLM 报告对象
        """
        # 生成各部分内容
        summary_table = self.generate_summary_table(report_data)
        department_ranking = self.generate_department_ranking(report_data)
        recommendations = self.generate_recommendations(report_data)

        # 生成叙述报告（同步方式）
        narrative = self.generate_narrative(report_data)

        # 组装完整报告
        full_report_text = f"""{summary_table}

---

{department_ranking}

---

{narrative}

---

{recommendations}
"""

        return LLMReport(
            narrative=narrative,
            summary_table=summary_table,
            department_ranking=department_ranking,
            recommendations=recommendations,
            full_report=full_report_text,
        )

    async def generate_full_report_async(
        self,
        report_data: dict,
    ) -> LLMReport:
        """
        异步生成完整考古报告

        Args:
            report_data: 检测报告数据

        Returns:
            LLMReport: 完整的 LLM 报告对象
        """
        # 生成各部分内容
        summary_table = self.generate_summary_table(report_data)
        department_ranking = self.generate_department_ranking(report_data)
        recommendations = self.generate_recommendations(report_data)

        # 异步生成叙述报告
        narrative = await self.generate_narrative_async(report_data)

        # 组装完整报告
        full_report_text = f"""{summary_table}

---

{department_ranking}

---

{narrative}

---

{recommendations}
"""

        return LLMReport(
            narrative=narrative,
            summary_table=summary_table,
            department_ranking=department_ranking,
            recommendations=recommendations,
            full_report=full_report_text,
        )

    def call_llm_with_retry(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> str:
        """
        带重试和错误处理的 LLM 调用封装

        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            max_tokens: 最大 token 数

        Returns:
            str: LLM 响应内容

        Raises:
            Exception: 如果所有重试都失败
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                client = self._get_client()

                if self._provider == "anthropic":
                    response = client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system_prompt or "",
                        messages=messages,
                    )
                    return response.content[0].text
                else:
                    all_messages = []
                    if system_prompt:
                        all_messages.append({"role": "system", "content": system_prompt})
                    all_messages.extend(messages)
                    response = client.chat.completions.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        messages=all_messages,
                    )
                    return response.choices[0].message.content

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                else:
                    raise

        raise last_error


def create_llm_reporter(
    api_key: str,
    model: str = "gpt-4o-mini",
) -> LLMReporter:
    """
    创建 LLM 报告生成器实例

    Args:
        api_key: API 密钥
        model: 模型名称

    Returns:
        LLMReporter: LLMReporter 实例
    """
    return LLMReporter(api_key=api_key, model=model)


def generate_mock_report_data() -> dict:
    """
    生成模拟检测报告数据（用于测试）

    Returns:
        dict: 模拟的检测报告数据
    """
    return {
        "total_records": 150,
        "total_anomalies": 23,
        "overall_risk_score": 58.5,
        "risk_level": "高",
        "anomalies_by_type": {
            "batch_processing": 8,
            "night_rush": 10,
            "time_contradiction": 3,
            "suspicious_sequence": 2,
        },
        "anomalies_by_severity": {
            "严重 (8-10)": 5,
            "中等 (5-7)": 12,
            "轻微 (3-4)": 6,
        },
        "top_anomalies": [
            {
                "anomaly_type": "night_rush",
                "severity": 9,
                "severity_label": "严重",
                "description": "发现23份病历在凌晨02:00-03:00集中修改，疑似夜间突击补写",
                "affected_records": ["R001", "R002", "R003", "R004", "R005"],
                "evidence": {"department": "内科", "night_modification_count": 23},
            },
            {
                "anomaly_type": "batch_processing",
                "severity": 8,
                "severity_label": "严重",
                "description": "15份病历的手术记录章节创建时间完全相同（精确到秒）",
                "affected_records": ["R010", "R011", "R012", "R013", "R014"],
                "evidence": {"timestamp": "2024-01-15T14:30:00", "identical_count": 15},
            },
            {
                "anomaly_type": "time_contradiction",
                "severity": 7,
                "severity_label": "中等",
                "description": "病程记录显示「手术顺利」但手术记录尚未创建",
                "affected_records": ["R020"],
                "evidence": {"contradiction_type": "causality_violation"},
            },
        ],
        "detector_results": [
            {
                "detector_name": "batch",
                "anomaly_count": 8,
                "execution_time_ms": 125.5,
                "anomalies": [],
            },
            {
                "detector_name": "night",
                "anomaly_count": 10,
                "execution_time_ms": 98.3,
                "anomalies": [
                    {
                        "anomaly_type": "night_rush",
                        "severity": 9,
                        "description": "夜间异常",
                        "affected_records": ["R001"],
                        "evidence": {"department": "内科", "night_modification_count": 23},
                    }
                ],
            },
        ],
        "summary_stats": {
            "total_records": 150,
            "total_anomalies": 23,
            "records_with_anomalies": 18,
            "detector_execution_times_ms": {
                "batch": 125.5,
                "night": 98.3,
            },
        },
    }