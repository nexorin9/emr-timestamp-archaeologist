"""
EMR Timestamp Archaeologist - 时间线矛盾检测器
检测病历章节时间线与业务时间的矛盾（如手术记录创建时间早于手术开始时间）
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
    create_timestamp_anomaly,
)


class AnchorType(Enum):
    """业务时间锚点类型"""
    ADMISSION = "admission"           # 入院时间
    DISCHARGE = "discharge"          # 出院时间
    SURGERY_START = "surgery_start"  # 手术开始时间
    SURGERY_END = "surgery_end"      # 手术结束时间
    TRANSFER = "transfer"            # 转科时间
    EXAM = "exam"                    # 检查时间
    CONSULTATION = "consultation"    # 会诊时间
    ROUND = "round"                  # 查房时间
    CUSTOM = "custom"                # 自定义锚点


@dataclass
class BusinessAnchor:
    """
    业务时间锚点 - 表示病历中的关键业务时间点

    Attributes:
        anchor_type: 锚点类型
        anchor_time: 锚点时间
        record_id: 关联的病历记录ID
        label: 锚点标签（如"左膝关节置换手术开始"）
    """
    anchor_type: AnchorType
    anchor_time: datetime
    record_id: str
    label: str

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "anchor_type": self.anchor_type.value,
            "anchor_time": self.anchor_time.isoformat(),
            "record_id": self.record_id,
            "label": self.label,
        }


@dataclass
class TemporalContradiction:
    """
    时间矛盾 - 表示检测到的时间线矛盾

    Attributes:
        contradiction_type: 矛盾类型
        record_id: 涉及的病历记录ID
        chapter_ids: 涉及的章节ID列表
        description: 矛盾描述
        severity: 严重程度 (0-10)
        evidence: 证据信息
    """
    contradiction_type: str
    record_id: str
    chapter_ids: list[str]
    description: str
    severity: int
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "contradiction_type": self.contradiction_type,
            "record_id": self.record_id,
            "chapter_ids": self.chapter_ids,
            "description": self.description,
            "severity": self.severity,
            "evidence": self.evidence,
        }


@dataclass
class CausalityViolation:
    """
    因果矛盾 - 表示检测到的因果关系矛盾

    Attributes:
        cause_chapter: 原因章节（记载事件结果的章节）
        effect_chapter: 结果章节（应先发生的章节尚未创建）
        description: 矛盾描述
        severity: 严重程度 (0-10)
    """
    cause_chapter: EmrChapter
    effect_chapter: EmrChapter
    description: str
    severity: int
    record_id: str

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "cause_chapter": {
                "chapter_id": self.cause_chapter.chapter_id,
                "chapter_name": self.cause_chapter.chapter_name,
                "created_time": self.cause_chapter.created_time.isoformat(),
            },
            "effect_chapter": {
                "chapter_id": self.effect_chapter.chapter_id,
                "chapter_name": self.effect_chapter.chapter_name,
                "created_time": self.effect_chapter.created_time.isoformat(),
            },
            "description": self.description,
            "severity": self.severity,
            "record_id": self.record_id,
        }


class TimeContradictionDetector:
    """
    时间线矛盾检测器

    检测病历章节时间线与业务时间的矛盾，包括：
    - 锚点违规：章节时间戳早于锚定业务时间
    - 时序矛盾：章节创建时间不符合正常时序
    - 因果矛盾：结果在原因之前

    Attributes:
        max_time_gap_minutes: 章节间正常时间间隔上限（分钟）
    """

    # 常见章节名称关键词映射到锚点类型
    CHAPTER_KEYWORDS = {
        "手术记录": AnchorType.SURGERY_START,
        "术前": AnchorType.SURGERY_START,
        "术后": AnchorType.SURGERY_END,
        "入院记录": AnchorType.ADMISSION,
        "出院记录": AnchorType.DISCHARGE,
        "转科记录": AnchorType.TRANSFER,
        "查房": AnchorType.ROUND,
        "会诊": AnchorType.CONSULTATION,
        "检查": AnchorType.EXAM,
    }

    # 因果矛盾关键词：当某章节提到这些词时，相关业务锚点章节应该已经存在
    CAUSALITY_KEYWORDS = {
        "手术顺利": [AnchorType.SURGERY_START, AnchorType.SURGERY_END],
        "手术结束": [AnchorType.SURGERY_START],
        "手术中": [AnchorType.SURGERY_START],
        "麻醉": [AnchorType.SURGERY_START],
        "转入": [AnchorType.TRANSFER],
        "出院": [AnchorType.DISCHARGE],
    }

    def __init__(self, max_time_gap_minutes: int = 120) -> None:
        """
        初始化时间矛盾检测器

        Args:
            max_time_gap_minutes: 章节间正常时间间隔上限，默认为120分钟
        """
        self.max_time_gap_minutes = max_time_gap_minutes
        self._anchors: dict[str, list[BusinessAnchor]] = defaultdict(list)
        self._contradictions: list[TemporalContradiction] = []
        self._causality_violations: list[CausalityViolation] = []

    def add_business_anchor(self, anchor: BusinessAnchor) -> None:
        """
        注册业务时间锚点

        Args:
            anchor: 业务时间锚点
        """
        self._anchors[anchor.record_id].append(anchor)

    def add_business_anchor_by_type(
        self,
        anchor_type: AnchorType,
        anchor_time: datetime,
        record_id: str,
        label: str,
    ) -> None:
        """
        通过类型添加业务锚点

        Args:
            anchor_type: 锚点类型
            anchor_time: 锚点时间
            record_id: 关联的病历记录ID
            label: 锚点标签
        """
        anchor = BusinessAnchor(
            anchor_type=anchor_type,
            anchor_time=anchor_time,
            record_id=record_id,
            label=label,
        )
        self.add_business_anchor(anchor)

    def _get_anchor_for_record(self, record_id: str) -> list[BusinessAnchor]:
        """获取记录的所有锚点"""
        return self._anchors.get(record_id, [])

    def _infer_anchor_from_chapter(self, chapter: EmrChapter) -> Optional[AnchorType]:
        """
        根据章节名称推断锚点类型

        Args:
            chapter: 病历章节

        Returns:
            AnchorType 或 None
        """
        for keyword, anchor_type in self.CHAPTER_KEYWORDS.items():
            if keyword in chapter.chapter_name:
                return anchor_type
        return None

    def check_anchor_violation(
        self, record: EmrTimestampRecord
    ) -> list[TemporalContradiction]:
        """
        检测锚点违规：章节时间戳早于锚定业务时间

        例如：手术记录在手术开始时间之前就已创建

        Args:
            record: 病历时间戳记录

        Returns:
            list[TemporalContradiction]: 锚点违规列表
        """
        violations = []
        anchors = self._get_anchor_for_record(record.record_id)

        if not anchors:
            # 尝试从章节名称推断锚点
            for chapter in record.chapters:
                inferred_type = self._infer_anchor_from_chapter(chapter)
                if inferred_type:
                    # 创建一个推断的锚点用于检查
                    # 但不添加到实际锚点列表
                    pass

        for anchor in anchors:
            for chapter in record.chapters:
                # 检查章节创建时间是否早于锚点时间
                if chapter.created_time < anchor.anchor_time:
                    # 计算时间差
                    gap = (anchor.anchor_time - chapter.created_time).total_seconds()
                    gap_minutes = gap / 60

                    # 严重程度：时间差越大越严重
                    if gap_minutes >= 60:
                        severity = min(10, 7 + int(gap_minutes / 60))
                    elif gap_minutes > 10:
                        severity = min(10, 5 + int(gap_minutes / 10))
                    else:
                        severity = 3

                    violation = TemporalContradiction(
                        contradiction_type="anchor_violation",
                        record_id=record.record_id,
                        chapter_ids=[chapter.chapter_id],
                        description=(
                            f"章节「{chapter.chapter_name}」创建时间"
                            f"({chapter.created_time.strftime('%Y-%m-%d %H:%M:%S')}) "
                            f"早于业务锚点「{anchor.label}」"
                            f"({anchor.anchor_time.strftime('%Y-%m-%d %H:%M:%S')})，"
                            f"时间差 {gap_minutes:.0f} 分钟"
                        ),
                        severity=severity,
                        evidence={
                            "chapter_id": chapter.chapter_id,
                            "chapter_name": chapter.chapter_name,
                            "chapter_created_time": chapter.created_time.isoformat(),
                            "anchor_type": anchor.anchor_type.value,
                            "anchor_time": anchor.anchor_time.isoformat(),
                            "anchor_label": anchor.label,
                            "time_gap_minutes": gap_minutes,
                        },
                    )
                    violations.append(violation)

        return violations

    def check_temporal_sequence(
        self, record: EmrTimestampRecord
    ) -> list[TemporalContradiction]:
        """
        检测时序矛盾：章节创建时间是否符合正常时序

        检查前序章节的创建时间不能在后续章节之后，
        以及章节创建时间是否出现回溯

        Args:
            record: 病历时间戳记录

        Returns:
            list[TemporalContradiction]: 时序矛盾列表
        """
        contradictions = []

        if not record.chapters or len(record.chapters) < 2:
            return contradictions

        # 按创建时间排序
        sorted_chapters = sorted(record.chapters, key=lambda c: c.created_time)

        for i in range(len(sorted_chapters) - 1):
            current = sorted_chapters[i]
            next_chapter = sorted_chapters[i + 1]

            # 检查是否时间回溯（后创建的章节反而有更早的时间戳）
            if current.created_time > next_chapter.created_time:
                gap_seconds = (current.created_time - next_chapter.created_time).total_seconds()
                gap_minutes = gap_seconds / 60

                # 严重程度基于时间回溯量
                if gap_minutes >= 60:
                    severity = min(10, 8 + int(gap_minutes / 60))
                elif gap_minutes > 10:
                    severity = min(10, 5 + int(gap_minutes / 10))
                else:
                    severity = 3

                contradiction = TemporalContradiction(
                    contradiction_type="temporal_sequence",
                    record_id=record.record_id,
                    chapter_ids=[current.chapter_id, next_chapter.chapter_id],
                    description=(
                        f"时序矛盾：章节「{next_chapter.chapter_name}」创建时间"
                        f"({next_chapter.created_time.strftime('%Y-%m-%d %H:%M:%S')}) "
                        f"早于前序章节「{current.chapter_name}」"
                        f"({current.created_time.strftime('%Y-%m-%d %H:%M:%S')})，"
                        f"时间回溯 {gap_minutes:.0f} 分钟"
                    ),
                    severity=severity,
                    evidence={
                        "earlier_chapter": {
                            "chapter_id": next_chapter.chapter_id,
                            "chapter_name": next_chapter.chapter_name,
                            "created_time": next_chapter.created_time.isoformat(),
                        },
                        "later_chapter": {
                            "chapter_id": current.chapter_id,
                            "chapter_name": current.chapter_name,
                            "created_time": current.created_time.isoformat(),
                        },
                        "time_gap_minutes": gap_minutes,
                    },
                )
                contradictions.append(contradiction)

        # 检查章节顺序与时间顺序的一致性
        chapters_by_order = sorted(record.chapters, key=lambda c: c.chapter_order)
        for i in range(len(chapters_by_order) - 1):
            current = chapters_by_order[i]
            next_chapter = chapters_by_order[i + 1]

            # 如果章节顺序靠后的反而创建时间更早
            if current.chapter_order < next_chapter.chapter_order:
                if current.created_time > next_chapter.created_time:
                    gap_seconds = (current.created_time - next_chapter.created_time).total_seconds()
                    gap_minutes = gap_seconds / 60

                    # 检查时间差是否异常（正常修改可能稍早）
                    if gap_minutes >= self.max_time_gap_minutes:
                        severity = min(10, 4 + int(gap_minutes / 30))
                    else:
                        continue  # 正常范围内的时间差异不视为矛盾

                    contradiction = TemporalContradiction(
                        contradiction_type="order_time_mismatch",
                        record_id=record.record_id,
                        chapter_ids=[current.chapter_id, next_chapter.chapter_id],
                        description=(
                            f"章节顺序与时间矛盾：顺序靠后的「{next_chapter.chapter_name}」"
                            f"({next_chapter.created_time.strftime('%H:%M:%S')}) "
                            f"创建时间早于顺序靠前的「{current.chapter_name}」"
                            f"({current.created_time.strftime('%H:%M:%S')})，"
                            f"间隔 {gap_minutes:.0f} 分钟"
                        ),
                        severity=severity,
                        evidence={
                            "chapter_order": current.chapter_order,
                            "next_chapter_order": next_chapter.chapter_order,
                            "chapter_created_times": [
                                c.created_time.isoformat()
                                for c in [current, next_chapter]
                            ],
                            "time_gap_minutes": gap_minutes,
                        },
                    )
                    contradictions.append(contradiction)

        return contradictions

    def check_causality(
        self, record: EmrTimestampRecord
    ) -> list[CausalityViolation]:
        """
        检测因果矛盾：结果在原因之前

        例如：病程记录写了「手术顺利」但手术记录尚未创建

        Args:
            record: 病历时间戳记录

        Returns:
            list[CausalityViolation]: 因果矛盾列表
        """
        violations = []
        anchors = self._get_anchor_for_record(record.record_id)

        for chapter in record.chapters:
            # 检查章节内容是否包含因果关键词
            for keyword, required_anchors in self.CAUSALITY_KEYWORDS.items():
                if keyword in chapter.chapter_name or keyword in chapter.chapter_name:
                    # 需要检查相关锚点章节是否存在且时间合理
                    for required_type in required_anchors:
                        # 查找匹配的锚点
                        matching_anchors = [
                            a for a in anchors
                            if a.anchor_type == required_type
                        ]

                        for anchor in matching_anchors:
                            # 如果锚点时间在章节创建时间之后，说明因果矛盾
                            if anchor.anchor_time > chapter.created_time:
                                gap_seconds = (anchor.anchor_time - chapter.created_time).total_seconds()
                                gap_minutes = gap_seconds / 60

                                severity = min(10, 5 + int(gap_minutes / 30))

                                violation = CausalityViolation(
                                    cause_chapter=chapter,
                                    effect_chapter=EmrChapter(
                                        chapter_id="inferred",
                                        chapter_name=f"推断的{required_type.value}锚点章节",
                                        chapter_order=-1,
                                        created_time=anchor.anchor_time,
                                        modified_time=anchor.anchor_time,
                                        author_id="system",
                                    ),
                                    description=(
                                        f"因果矛盾：章节「{chapter.chapter_name}」"
                                        f"({chapter.created_time.strftime('%Y-%m-%d %H:%M:%S')}) "
                                        f"提及「{keyword}」，但关联的{required_type.value}事件"
                                        f"({anchor.anchor_time.strftime('%Y-%m-%d %H:%M:%S')}) "
                                        f"发生在章节创建之后 {gap_minutes:.0f} 分钟"
                                    ),
                                    severity=severity,
                                    record_id=record.record_id,
                                )
                                violations.append(violation)

        return violations

    def get_contradiction_chain(
        self, record_id: str
    ) -> list[TemporalContradiction]:
        """
        获取矛盾的传播链

        Args:
            record_id: 病历记录ID

        Returns:
            list[TemporalContradiction]: 矛盾传播链
        """
        # 筛选特定记录的矛盾
        record_contradictions = [
            c for c in self._contradictions
            if c.record_id == record_id
        ]

        # 构建矛盾链（按时间顺序）
        return sorted(record_contradictions, key=lambda c: c.severity, reverse=True)

    def detect(
        self, records: list[EmrTimestampRecord]
    ) -> list[TimestampAnomaly]:
        """
        检测所有时间线矛盾，返回异常列表

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[TimestampAnomaly]: 时间戳异常列表
        """
        if not records:
            return []

        self._contradictions = []
        self._causality_violations = []

        anomalies: list[TimestampAnomaly] = []

        for record in records:
            # 锚点违规检测
            anchor_violations = self.check_anchor_violation(record)
            for violation in anchor_violations:
                self._contradictions.append(violation)

            # 时序矛盾检测
            sequence_contradictions = self.check_temporal_sequence(record)
            for contradiction in sequence_contradictions:
                self._contradictions.append(contradiction)

            # 因果矛盾检测
            causality_violations = self.check_causality(record)
            for violation in causality_violations:
                self._causality_violations.append(violation)

        # 将 TemporalContradiction 转换为 TimestampAnomaly
        for contradiction in self._contradictions:
            if contradiction.contradiction_type == "anchor_violation":
                anomaly_type = AnomalyType.ANCHOR_VIOLATION
            else:
                anomaly_type = AnomalyType.TIME_CONTRADICTION

            anomaly = create_timestamp_anomaly(
                anomaly_type=anomaly_type,
                severity=contradiction.severity,
                description=contradiction.description,
                affected_records=[contradiction.record_id],
                evidence=contradiction.evidence,
            )
            anomalies.append(anomaly)

        # 将 CausalityViolation 转换为 TimestampAnomaly
        for violation in self._causality_violations:
            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.TIME_CONTRADICTION,
                severity=violation.severity,
                description=violation.description,
                affected_records=[violation.record_id],
                evidence=violation.to_dict(),
            )
            anomalies.append(anomaly)

        # 按严重程度排序
        anomalies.sort(key=lambda a: a.severity, reverse=True)

        return anomalies

    def get_summary_stats(self) -> dict:
        """
        获取检测统计摘要

        Returns:
            dict: 统计摘要
        """
        return {
            "total_contradictions": len(self._contradictions),
            "total_causality_violations": len(self._causality_violations),
            "anchor_violations": sum(
                1 for c in self._contradictions
                if c.contradiction_type == "anchor_violation"
            ),
            "temporal_sequence_violations": sum(
                1 for c in self._contradictions
                if c.contradiction_type == "temporal_sequence"
            ),
            "order_time_mismatch_violations": sum(
                1 for c in self._contradictions
                if c.contradiction_type == "order_time_mismatch"
            ),
            "anchors_registered": sum(len(v) for v in self._anchors.values()),
        }


# 便捷函数
def detect_time_contradictions(
    records: list[EmrTimestampRecord],
    max_time_gap_minutes: int = 120
) -> list[TimestampAnomaly]:
    """
    便捷函数：检测时间线矛盾

    Args:
        records: 病历时间戳记录列表
        max_time_gap_minutes: 章节间正常时间间隔上限

    Returns:
        list[TimestampAnomaly]: 时间戳异常列表
    """
    detector = TimeContradictionDetector(max_time_gap_minutes=max_time_gap_minutes)
    return detector.detect(records)