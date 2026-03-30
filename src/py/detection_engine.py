"""
EMR Timestamp Archaeologist - 综合异常检测引擎
整合所有检测器，构建综合异常评分和报告
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from models import (
    AnomalyType,
    EmrTimestampRecord,
    TimestampAnomaly,
)


@dataclass
class DetectorResult:
    """
    检测器执行结果

    Attributes:
        detector_name: 检测器名称
        anomalies: 检测到的异常列表
        execution_time_ms: 执行时间（毫秒）
        error: 错误信息（如果有）
    """
    detector_name: str
    anomalies: list[TimestampAnomaly]
    execution_time_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "detector_name": self.detector_name,
            "anomaly_count": len(self.anomalies),
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


@dataclass
class DetectionReport:
    """
    综合检测报告

    Attributes:
        total_records: 分析的记录总数
        total_anomalies: 异常总数
        overall_risk_score: 综合风险分数 (0-100)
        risk_level: 风险等级
        anomalies_by_type: 按类型分类的异常
        anomalies_by_severity: 按严重程度分类的异常
        top_anomalies: 最高风险异常列表
        detector_results: 各检测器执行结果
        summary_stats: 统计摘要
        generated_at: 报告生成时间
    """
    total_records: int
    total_anomalies: int
    overall_risk_score: float
    risk_level: str
    anomalies_by_type: dict[str, int] = field(default_factory=dict)
    anomalies_by_severity: dict[str, int] = field(default_factory=dict)
    top_anomalies: list[dict] = field(default_factory=list)
    detector_results: list[DetectorResult] = field(default_factory=list)
    summary_stats: dict = field(default_factory=dict)
    generated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """设置默认值"""
        if self.generated_at is None:
            self.generated_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "total_records": self.total_records,
            "total_anomalies": self.total_anomalies,
            "overall_risk_score": self.overall_risk_score,
            "risk_level": self.risk_level,
            "anomalies_by_type": self.anomalies_by_type,
            "anomalies_by_severity": self.anomalies_by_severity,
            "top_anomalies": self.top_anomalies,
            "detector_results": [r.to_dict() for r in self.detector_results],
            "summary_stats": self.summary_stats,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


class DetectionEngine:
    """
    综合异常检测引擎

    整合所有检测器，提供统一的异常检测接口：
    - 插件化检测器注册
    - 并行/串行检测执行
    - 异常去重和排序
    - 综合风险评分
    - 报告生成

    Attributes:
        llm_enabled: 是否启用 LLM 分析
    """

    # 风险等级阈值
    RISK_LEVELS = [
        (10, "极低"),
        (30, "低"),
        (50, "中等"),
        (70, "高"),
        (85, "很高"),
        (100, "极高"),
    ]

    def __init__(self, llm_enabled: bool = True) -> None:
        """
        初始化检测引擎

        Args:
            llm_enabled: 是否启用 LLM 分析，默认为 True
        """
        self.llm_enabled = llm_enabled
        self._detectors: dict[str, Callable[[list[EmrTimestampRecord]], list[TimestampAnomaly]]] = {}
        self._detector_results: list[DetectorResult] = []
        self._all_anomalies: list[TimestampAnomaly] = []
        self._records: list[EmrTimestampRecord] = []

    def register_detector(
        self,
        name: str,
        detector_func: Callable[[list[EmrTimestampRecord]], list[TimestampAnomaly]],
    ) -> None:
        """
        注册检测器（支持插件化扩展）

        Args:
            name: 检测器名称
            detector_func: 检测函数，接受病历记录列表，返回异常列表
        """
        self._detectors[name] = detector_func

    def register_detector_instance(
        self,
        name: str,
        detector_instance: object,
    ) -> None:
        """
        注册检测器实例（基于对象的 detect 方法）

        Args:
            name: 检测器名称
            detector_instance: 检测器实例，需具有 detect 方法
        """
        def wrapper(records: list[EmrTimestampRecord]) -> list[TimestampAnomaly]:
            return detector_instance.detect(records)
        self._detectors[name] = wrapper

    def run_all_detectors(
        self,
        records: list[EmrTimestampRecord],
    ) -> list[TimestampAnomaly]:
        """
        对输入数据运行所有检测器，汇总异常列表

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[TimestampAnomaly]: 汇总后的异常列表
        """
        self._records = records
        self._detector_results = []
        self._all_anomalies = []

        if not records:
            return []

        for name, detector_func in self._detectors.items():
            start_time = datetime.now()
            try:
                anomalies = detector_func(records)
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

                result = DetectorResult(
                    detector_name=name,
                    anomalies=anomalies,
                    execution_time_ms=elapsed_ms,
                )
            except Exception as e:
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                result = DetectorResult(
                    detector_name=name,
                    anomalies=[],
                    execution_time_ms=elapsed_ms,
                    error=str(e),
                )

            self._detector_results.append(result)
            self._all_anomalies.extend(result.anomalies)

        # 去重
        self._all_anomalies = self.deduplicate_anomalies(self._all_anomalies)

        # 按严重程度排序
        self._all_anomalies = self.rank_anomalies(self._all_anomalies)

        return self._all_anomalies

    def calculate_overall_risk_score(
        self,
        anomalies: Optional[list[TimestampAnomaly]] = None,
    ) -> float:
        """
        综合所有异常计算总体风险分数 (0-100)

        评分策略：
        - 基于异常数量（最多贡献30分）
        - 基于异常严重程度（最多贡献50分）
        - 基于异常类型多样性（最多贡献20分）

        Args:
            anomalies: 异常列表（如果为 None，使用上次运行的结果）

        Returns:
            float: 风险分数 (0-100)
        """
        if anomalies is None:
            anomalies = self._all_anomalies

        if not anomalies:
            return 0.0

        # 1. 异常数量得分（最多30分）
        # 10个异常以下线性增长，10个以上增速放缓
        anomaly_count = len(anomalies)
        if anomaly_count <= 10:
            count_score = anomaly_count * 2.5
        else:
            count_score = min(30.0, 25 + (anomaly_count - 10) * 0.5)

        # 2. 严重程度得分（最多50分）
        # 计算加权严重程度和
        max_possible_severity = 10 * anomaly_count
        actual_severity_sum = sum(a.severity for a in anomalies)
        severity_ratio = actual_severity_sum / max_possible_severity if max_possible_severity > 0 else 0
        severity_score = severity_ratio * 50

        # 3. 异常类型多样性得分（最多20分）
        unique_types = len(set(a.anomaly_type for a in anomalies))
        diversity_score = min(20.0, unique_types * 5)

        # 4. 高严重程度异常加成
        high_severity_count = sum(1 for a in anomalies if a.severity >= 8)
        if high_severity_count >= 3:
            severity_score = min(50.0, severity_score + 5)

        total_score = count_score + severity_score + diversity_score
        return min(100.0, max(0.0, total_score))

    def get_risk_level(self, score: float) -> str:
        """
        根据风险分数获取风险等级

        Args:
            score: 风险分数 (0-100)

        Returns:
            str: 风险等级
        """
        for threshold, level in self.RISK_LEVELS:
            if score < threshold:
                return level
        return "极高"

    def rank_anomalies(
        self,
        anomalies: list[TimestampAnomaly],
    ) -> list[TimestampAnomaly]:
        """
        按 severity 和 confidence 排序异常

        排序规则：
        1. 首先按严重程度降序
        2. 相同严重程度时，按受影响的记录数降序
        3. 相同情况下，按异常类型字母序

        Args:
            anomalies: 异常列表

        Returns:
            list[TimestampAnomaly]: 排序后的异常列表
        """
        def sort_key(a: TimestampAnomaly) -> tuple:
            affected_count = len(a.affected_records)
            return (-a.severity, -affected_count, a.anomaly_type.value)

        return sorted(anomalies, key=sort_key)

    def deduplicate_anomalies(
        self,
        anomalies: list[TimestampAnomaly],
    ) -> list[TimestampAnomaly]:
        """
        合并重复或包含关系的异常

        合并规则：
        1. 同一类型的异常，如果受影响的记录完全相同，保留最严重的
        2. 如果一个异常的受影响记录包含另一个异常，且类型相同，合并

        Args:
            anomalies: 异常列表

        Returns:
            list[TimestampAnomaly]: 去重后的异常列表
        """
        if not anomalies:
            return []

        # 按类型和严重程度分组
        grouped: dict[AnomalyType, list[TimestampAnomaly]] = {}
        for anomaly in anomalies:
            if anomaly.anomaly_type not in grouped:
                grouped[anomaly.anomaly_type] = []
            grouped[anomaly.anomaly_type].append(anomaly)

        deduped: list[TimestampAnomaly] = []

        for anom_type, type_anomalies in grouped.items():
            # 在每个类型内按严重程度降序排序
            type_anomalies = sorted(type_anomalies, key=lambda a: -a.severity)

            while type_anomalies:
                # 取出最严重的异常
                current = type_anomalies.pop(0)
                current_affected = set(current.affected_records)

                # 查找可以合并的异常
                to_merge: list[TimestampAnomaly] = []
                remaining: list[TimestampAnomaly] = []

                for other in type_anomalies:
                    other_affected = set(other.affected_records)

                    # 如果受影响记录完全相同或包含关系
                    if current_affected == other_affected:
                        to_merge.append(other)
                    elif current_affected.issubset(other_affected):
                        # current 是 other 的子集（current 更窄/更严重），保留 current，跳过 other
                        pass  # 不把 other 加入 remaining，skip it
                    elif other_affected.issubset(current_affected):
                        # other 是 current 的子集（other 更窄/更严重），更新 current 为 other
                        remaining.append(current)  # 丢弃旧的 current
                        current = other  # 更新为更严重的 other
                        current_affected = other_affected
                    else:
                        remaining.append(other)

                # 记录合并后的异常（仅保留最严重的）
                deduped.append(current)
                type_anomalies = remaining

        return deduped

    def get_summary_stats(self) -> dict:
        """
        返回统计摘要

        Returns:
            dict: 统计摘要，包含：
                - total_records: 记录总数
                - total_anomalies: 异常总数
                - anomalies_by_type: 各类型异常数量
                - anomalies_by_severity: 各严重程度异常数量
                - detector_execution_times: 各检测器执行时间
                - overall_risk_score: 综合风险分数
                - risk_level: 风险等级
        """
        # 统计各类型异常
        type_counter = Counter(a.anomaly_type for a in self._all_anomalies)
        anomalies_by_type = {
            atype.value: count for atype, count in type_counter.items()
        }

        # 统计各严重程度异常
        severity_counter = Counter(a.severity for a in self._all_anomalies)
        anomalies_by_severity = {
            f"severity_{sev}": count
            for sev, count in sorted(severity_counter.items())
        }

        # 统计各检测器执行时间
        detector_times = {
            r.detector_name: round(r.execution_time_ms, 2)
            for r in self._detector_results
        }

        # 计算风险分数
        risk_score = self.calculate_overall_risk_score()
        risk_level = self.get_risk_level(risk_score)

        return {
            "total_records": len(self._records),
            "total_anomalies": len(self._all_anomalies),
            "anomalies_by_type": anomalies_by_type,
            "anomalies_by_severity": anomalies_by_severity,
            "anomalies_by_type_detailed": {
                atype.value: {
                    "count": count,
                    "avg_severity": round(
                        sum(a.severity for a in self._all_anomalies if a.anomaly_type == atype) / count
                        if count > 0 else 0,
                        2,
                    ),
                }
                for atype, count in type_counter.items()
            },
            "detector_execution_times_ms": detector_times,
            "overall_risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "records_with_anomalies": len(set(
                rid for a in self._all_anomalies for rid in a.affected_records
            )),
        }

    def generate_report_data(self) -> DetectionReport:
        """
        生成报告数据结构（供 LLM 和 HTML 使用）

        Returns:
            DetectionReport: 综合检测报告
        """
        # 获取统计摘要
        stats = self.get_summary_stats()

        # 构建按类型分类的异常计数
        anomalies_by_type = stats.get("anomalies_by_type", {})

        # 构建按严重程度分类的异常计数
        anomalies_by_severity = {
            "严重 (8-10)": sum(1 for a in self._all_anomalies if a.severity >= 8),
            "中等 (5-7)": sum(1 for a in self._all_anomalies if 5 <= a.severity < 8),
            "轻微 (3-4)": sum(1 for a in self._all_anomalies if 3 <= a.severity < 5),
            "提示 (0-2)": sum(1 for a in self._all_anomalies if a.severity < 3),
        }

        # 获取最高风险异常（取前10个）
        top_anomalies = [
            a.to_dict() for a in self._all_anomalies[:10]
        ]

        # 计算综合风险分数
        overall_risk_score = self.calculate_overall_risk_score()
        risk_level = self.get_risk_level(overall_risk_score)

        report = DetectionReport(
            total_records=stats["total_records"],
            total_anomalies=stats["total_anomalies"],
            overall_risk_score=overall_risk_score,
            risk_level=risk_level,
            anomalies_by_type=anomalies_by_type,
            anomalies_by_severity=anomalies_by_severity,
            top_anomalies=top_anomalies,
            detector_results=self._detector_results,
            summary_stats=stats,
        )

        return report

    def get_anomalies_by_type(
        self,
        anomaly_type: AnomalyType,
        anomalies: Optional[list[TimestampAnomaly]] = None,
    ) -> list[TimestampAnomaly]:
        """
        获取指定类型的异常

        Args:
            anomaly_type: 异常类型
            anomalies: 要过滤的异常列表（可选，默认为 self._all_anomalies）

        Returns:
            list[TimestampAnomaly]: 该类型的所有异常
        """
        source = anomalies if anomalies is not None else self._all_anomalies
        return [a for a in source if a.anomaly_type == anomaly_type]

    def get_anomalies_by_severity_range(
        self,
        min_severity: int,
        max_severity: int = 10,
        anomalies: Optional[list[TimestampAnomaly]] = None,
    ) -> list[TimestampAnomaly]:
        """
        获取指定严重程度范围内的异常

        Args:
            min_severity: 最小严重程度
            max_severity: 最大严重程度
            anomalies: 要过滤的异常列表（可选，默认为 self._all_anomalies）

        Returns:
            list[TimestampAnomaly]: 该范围内的异常
        """
        source = anomalies if anomalies is not None else self._all_anomalies
        return [
            a for a in source
            if min_severity <= a.severity <= max_severity
        ]

    def get_all_detector_results(self) -> list[DetectorResult]:
        """
        获取所有检测器的执行结果

        Returns:
            list[DetectorResult]: 检测器结果列表
        """
        return self._detector_results

    def get_detector_result(self, detector_name: str) -> Optional[DetectorResult]:
        """
        获取指定检测器的执行结果

        Args:
            detector_name: 检测器名称

        Returns:
            DetectorResult 或 None
        """
        for result in self._detector_results:
            if result.detector_name == detector_name:
                return result
        return None


# 便捷函数
def create_detection_engine(llm_enabled: bool = True) -> DetectionEngine:
    """
    创建配置好的检测引擎，自动注册所有内置检测器

    Args:
        llm_enabled: 是否启用 LLM

    Returns:
        DetectionEngine: 配置好的检测引擎
    """
    from detectors import (
        BatchDetector,
        NightActivityDetector,
        SequenceDetector,
        TimeContradictionDetector,
    )

    engine = DetectionEngine(llm_enabled=llm_enabled)

    # 注册内置检测器
    engine.register_detector_instance("batch", BatchDetector())
    engine.register_detector_instance("night", NightActivityDetector())
    engine.register_detector_instance("contradiction", TimeContradictionDetector())
    engine.register_detector_instance("sequence", SequenceDetector())

    return engine


def run_detection(
    records: list[EmrTimestampRecord],
    llm_enabled: bool = True,
) -> DetectionReport:
    """
    便捷函数：运行完整检测流程

    Args:
        records: 病历时间戳记录列表
        llm_enabled: 是否启用 LLM

    Returns:
        DetectionReport: 综合检测报告
    """
    engine = create_detection_engine(llm_enabled=llm_enabled)
    engine.run_all_detectors(records)
    return engine.generate_report_data()
