"""
EMR Timestamp Archaeologist - 核心数据模型
定义病历时间戳考古所需的核心数据结构
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AnomalyType(Enum):
    """时间戳异常类型枚举"""
    BATCH_PROCESSING = "batch_processing"       # 批处理痕迹：多份病历同一时间戳
    NIGHT_RUSH = "night_rush"                   # 夜间突击补写
    TIME_CONTRADICTION = "time_contradiction"   # 时间线矛盾
    SUSPICIOUS_SEQUENCE = "suspicious_sequence" # 异常修改序列
    ANCHOR_VIOLATION = "anchor_violation"       # 锚点违规


@dataclass
class EmrChapter:
    """
    病历章节元数据

    Attributes:
        chapter_id: 章节唯一标识
        chapter_name: 章节名称（如"病程记录"、"手术记录"）
        chapter_order: 章节顺序号
        created_time: 章节创建时间
        modified_time: 章节最后修改时间
        author_id: 作者ID
    """
    chapter_id: str
    chapter_name: str
    chapter_order: int
    created_time: datetime
    modified_time: datetime
    author_id: str

    def __post_init__(self) -> None:
        """验证数据有效性"""
        if not self.chapter_id:
            raise ValueError("chapter_id 不能为空")
        if not self.chapter_name:
            raise ValueError("chapter_name 不能为空")
        if self.chapter_order < 0:
            raise ValueError("chapter_order 必须为非负整数")

    def time_gap_to(self, other: EmrChapter) -> float:
        """计算与另一个章节的时间差（秒）"""
        delta = self.created_time - other.created_time
        return abs(delta.total_seconds())


@dataclass
class EmrTimestampRecord:
    """
    病历时间戳记录

    Attributes:
        patient_id: 患者ID
        visit_id: 就诊ID
        record_id: 病历记录ID
        record_type: 病历类型（如"入院记录"、"出院记录"）
        chapters: 章节列表
        business_time: 业务时间（如手术开始时间、入院时间）
    """
    patient_id: str
    visit_id: str
    record_id: str
    record_type: str
    chapters: list[EmrChapter] = field(default_factory=list)
    business_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        """验证数据有效性"""
        if not self.patient_id:
            raise ValueError("patient_id 不能为空")
        if not self.visit_id:
            raise ValueError("visit_id 不能为空")
        if not self.record_id:
            raise ValueError("record_id 不能为空")
        if not self.record_type:
            raise ValueError("record_type 不能为空")

        # 验证 chapters 的顺序连续性
        orders = [c.chapter_order for c in self.chapters]
        if orders:
            expected = list(range(min(orders), max(orders) + 1))
            if sorted(orders) != expected:
                raise ValueError(
                    f"章节顺序不连续: {orders}，期望 {expected}"
                )

    def add_chapter(self, chapter: EmrChapter) -> None:
        """添加章节并自动验证"""
        self.chapters.append(chapter)
        # 重新验证顺序连续性
        orders = [c.chapter_order for c in self.chapters]
        expected = list(range(min(orders), max(orders) + 1))
        if sorted(orders) != expected:
            raise ValueError(
                f"添加章节后章节顺序不连续: {sorted(orders)}"
            )

    def get_chapter_by_id(self, chapter_id: str) -> Optional[EmrChapter]:
        """根据章节ID获取章节"""
        for chapter in self.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        return None

    def get_earliest_chapter(self) -> Optional[EmrChapter]:
        """获取最早创建的章节"""
        if not self.chapters:
            return None
        return min(self.chapters, key=lambda c: c.created_time)

    def get_latest_chapter(self) -> Optional[EmrChapter]:
        """获取最晚修改的章节"""
        if not self.chapters:
            return None
        return max(self.chapters, key=lambda c: c.modified_time)


@dataclass
class StratumEntry:
    """
    地层条目 - 表示病历时间轴上的一个时间戳层

    Attributes:
        record_id: 病历记录ID
        chapter_id: 章节ID
        timestamp: 时间戳
        stratum_layer: 地层序号（数字越小越早，越底层）
        anomaly_flags: 异常标记列表
    """
    record_id: str
    chapter_id: str
    timestamp: datetime
    stratum_layer: int
    anomaly_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """验证数据有效性"""
        if not self.record_id:
            raise ValueError("record_id 不能为空")
        if not self.chapter_id:
            raise ValueError("chapter_id 不能为空")
        if self.stratum_layer < 0:
            raise ValueError("stratum_layer 必须为非负整数")

    def add_anomaly_flag(self, flag: str) -> None:
        """添加异常标记"""
        if flag not in self.anomaly_flags:
            self.anomaly_flags.append(flag)

    def has_anomaly_flag(self, flag: str) -> bool:
        """检查是否存在指定异常标记"""
        return flag in self.anomaly_flags


@dataclass
class TimestampAnomaly:
    """
    时间戳异常记录

    Attributes:
        anomaly_type: 异常类型
        severity: 严重程度 (0-10)
        description: 异常描述
        affected_records: 受影响的记录ID列表
        evidence: 证据信息（用于调试和报告）
    """
    anomaly_type: AnomalyType
    severity: int  # 0-10
    description: str
    affected_records: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """验证数据有效性"""
        if not isinstance(self.anomaly_type, AnomalyType):
            raise ValueError(
                f"anomaly_type 必须是 AnomalyType 枚举类型，"
                f"得到: {type(self.anomaly_type)}"
            )
        if not 0 <= self.severity <= 10:
            raise ValueError(
                f"severity 必须在 0-10 范围内，得到: {self.severity}"
            )
        if not self.description:
            raise ValueError("description 不能为空")

    @property
    def severity_label(self) -> str:
        """获取严重程度标签"""
        if self.severity >= 8:
            return "严重"
        elif self.severity >= 5:
            return "中等"
        elif self.severity >= 3:
            return "轻微"
        else:
            return "提示"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity,
            "severity_label": self.severity_label,
            "description": self.description,
            "affected_records": self.affected_records,
            "evidence": self.evidence,
        }


# 便捷构造函数
def create_emr_chapter(
    chapter_name: str,
    created_time: datetime,
    author_id: str,
    modified_time: Optional[datetime] = None,
    chapter_id: Optional[str] = None,
    chapter_order: Optional[int] = None,
) -> EmrChapter:
    """便捷创建 EmrChapter 实例"""
    cid = chapter_id or str(uuid.uuid4())
    order = chapter_order if chapter_order is not None else 0
    mtime = modified_time or created_time

    return EmrChapter(
        chapter_id=cid,
        chapter_name=chapter_name,
        chapter_order=order,
        created_time=created_time,
        modified_time=mtime,
        author_id=author_id,
    )


def create_timestamp_anomaly(
    anomaly_type: AnomalyType,
    severity: int,
    description: str,
    affected_records: Optional[list[str]] = None,
    evidence: Optional[dict] = None,
) -> TimestampAnomaly:
    """便捷创建 TimestampAnomaly 实例"""
    return TimestampAnomaly(
        anomaly_type=anomaly_type,
        severity=severity,
        description=description,
        affected_records=affected_records or [],
        evidence=evidence or {},
    )
