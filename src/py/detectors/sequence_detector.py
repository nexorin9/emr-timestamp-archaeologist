"""
EMR Timestamp Archaeologist - 异常序列模式检测器
检测时间戳修改序列中的异常模式（如同一病历频繁回溯修改、修改时间呈周期性规律等）
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
    create_timestamp_anomaly,
)


@dataclass
class RevisionLoop:
    """
    修改回溯 - 表示检测到的修改时间回溯

    Attributes:
        record_id: 病历记录ID
        chapter_id: 章节ID
        earlier_chapter: 时间上更早的章节
        later_chapter: 时间上更晚的章节
        time_gap_minutes: 时间回溯量（分钟）
        severity: 严重程度
    """
    record_id: str
    chapter_id: str
    earlier_chapter: EmrChapter
    later_chapter: EmrChapter
    time_gap_minutes: float
    severity: int

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "record_id": self.record_id,
            "chapter_id": self.chapter_id,
            "earlier_chapter": {
                "chapter_id": self.earlier_chapter.chapter_id,
                "chapter_name": self.earlier_chapter.chapter_name,
                "created_time": self.earlier_chapter.created_time.isoformat(),
            },
            "later_chapter": {
                "chapter_id": self.later_chapter.chapter_id,
                "chapter_name": self.later_chapter.chapter_name,
                "created_time": self.later_chapter.created_time.isoformat(),
            },
            "time_gap_minutes": self.time_gap_minutes,
            "severity": self.severity,
        }


@dataclass
class PeriodicRevision:
    """
    周期性修改 - 表示检测到的周期性修改模式

    Attributes:
        record_id: 病历记录ID
        chapter_id: 章节ID
        period_minutes: 检测到的周期（分钟）
        confidence: 置信度 (0-1)
        instances: 实例列表
        severity: 严重程度
    """
    record_id: str
    chapter_id: str
    period_minutes: float
    confidence: float
    instances: list[datetime]
    severity: int

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "record_id": self.record_id,
            "chapter_id": self.chapter_id,
            "period_minutes": self.period_minutes,
            "confidence": self.confidence,
            "instances": [t.isoformat() for t in self.instances],
            "severity": self.severity,
        }


@dataclass
class RushedSequence:
    """
    仓促序列 - 表示检测到的仓促补写模式

    Attributes:
        record_id: 病历记录ID
        chapter_ids: 章节ID列表
        time_gap_seconds: 时间间隔（秒）
        chapter_count: 章节数量
        severity: 严重程度
    """
    record_id: str
    chapter_ids: list[str]
    time_gap_seconds: float
    chapter_count: int
    severity: int

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "record_id": self.record_id,
            "chapter_ids": self.chapter_ids,
            "time_gap_seconds": self.time_gap_seconds,
            "chapter_count": self.chapter_count,
            "severity": self.severity,
        }


@dataclass
class SequenceRiskSegment:
    """
    风险段落 - 表示序列中具有高风险的段落

    Attributes:
        record_id: 病历记录ID
        start_time: 起始时间
        end_time: 结束时间
        risk_score: 风险分数
        risk_type: 风险类型
    """
    record_id: str
    start_time: datetime
    end_time: datetime
    risk_score: float
    risk_type: str

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "record_id": self.record_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "risk_score": self.risk_score,
            "risk_type": self.risk_type,
        }


class SequenceDetector:
    """
    异常序列模式检测器

    检测病历时间戳修改序列中的异常模式：
    - 修改时间回溯：后一次修改时间早于前一次
    - 周期性修改：修改时间呈规律性间隔（如每晚23:00定时修改）
    - 仓促补写：章节修改时间异常接近

    Attributes:
        rushed_threshold_minutes: 仓促补写的时间阈值（分钟）
        periodic_confidence_threshold: 周期性检测的置信度阈值
    """

    # 常见的周期性修改时间间隔（分钟）
    COMMON_PERIODIC_INTERVALS = [
        30, 60, 120, 180, 240, 360, 480, 720, 1440  # 30分钟到24小时
    ]

    def __init__(
        self,
        rushed_threshold_minutes: float = 5,
        periodic_confidence_threshold: float = 0.7,
    ) -> None:
        """
        初始化序列检测器

        Args:
            rushed_threshold_minutes: 仓促补写的时间阈值（分钟），默认5分钟
            periodic_confidence_threshold: 周期性检测的置信度阈值，默认0.7
        """
        self.rushed_threshold_minutes = rushed_threshold_minutes
        self.periodic_confidence_threshold = periodic_confidence_threshold
        self._revision_loops: list[RevisionLoop] = []
        self._periodic_revisions: list[PeriodicRevision] = []
        self._rushed_sequences: list[RushedSequence] = []
        self._risk_segments: list[SequenceRiskSegment] = []

    def detect_revision_loops(
        self, records: list[EmrTimestampRecord]
    ) -> list[RevisionLoop]:
        """
        检测修改时间回溯：后一次修改时间早于前一次

        通过比较章节顺序与时间顺序的不一致来检测回溯。
        如果 chapter_order 靠后的章节的 created_time 早于靠前的章节，
        说明存在时间回溯（倒填时间）。

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[RevisionLoop]: 修改回溯列表
        """
        loops: list[RevisionLoop] = []

        for record in records:
            if len(record.chapters) < 2:
                continue

            # 按章节顺序排序
            sorted_chapters = sorted(record.chapters, key=lambda c: c.chapter_order)

            for i in range(len(sorted_chapters) - 1):
                current = sorted_chapters[i]  # 顺序靠前
                next_chapter = sorted_chapters[i + 1]  # 顺序靠后

                # 检查是否时间回溯：顺序靠后的章节时间反而更早
                if next_chapter.created_time < current.created_time:
                    gap_seconds = (current.created_time - next_chapter.created_time).total_seconds()
                    gap_minutes = gap_seconds / 60

                    # 严重程度基于时间回溯量
                    if gap_minutes >= 60:
                        severity = min(10, 8 + int(gap_minutes / 60))
                    elif gap_minutes > 10:
                        severity = min(10, 5 + int(gap_minutes / 10))
                    else:
                        severity = 3

                    loop = RevisionLoop(
                        record_id=record.record_id,
                        chapter_id=next_chapter.chapter_id,
                        earlier_chapter=next_chapter,  # 实际时间更早
                        later_chapter=current,  # 实际时间更晚
                        time_gap_minutes=gap_minutes,
                        severity=severity,
                    )
                    loops.append(loop)

        self._revision_loops = loops
        return loops

    def detect_periodic_revisions(
        self, records: list[EmrTimestampRecord]
    ) -> list[PeriodicRevision]:
        """
        检测周期性修改：使用自相关分析检测规律性修改模式

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[PeriodicRevision]: 周期性修改列表
        """
        periodic: list[PeriodicRevision] = []

        for record in records:
            if len(record.chapters) < 3:
                continue

            # 收集同一作者的所有修改时间
            author_times: dict[str, list[datetime]] = defaultdict(list)
            for chapter in record.chapters:
                author_times[chapter.author_id].append(chapter.created_time)

            for author_id, times in author_times.items():
                if len(times) < 3:
                    continue

                # 按时间排序
                sorted_times = sorted(times)
                time_diffs = [
                    (sorted_times[i + 1] - sorted_times[i]).total_seconds() / 60
                    for i in range(len(sorted_times) - 1)
                ]

                # 检测最常见的周期
                best_period = 0.0
                best_confidence = 0.0

                for period in self.COMMON_PERIODIC_INTERVALS:
                    # 计算与标准周期的偏差
                    deviations = [
                        min(abs(diff - period), abs(diff % period), abs(period % diff))
                        if diff > 0 else float('inf')
                        for diff in time_diffs
                    ]
                    avg_deviation = sum(deviations) / len(deviations) if deviations else float('inf')

                    # 转换为置信度（偏差越小置信度越高）
                    if avg_deviation < 1:
                        confidence = 1.0 - (avg_deviation / 60)  # 最大60分钟偏差
                    elif avg_deviation < 30:
                        confidence = 0.7 - (avg_deviation - 1) / 100
                    else:
                        confidence = 0.0

                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_period = period

                # 如果置信度超过阈值，记录周期性修改
                if best_confidence >= self.periodic_confidence_threshold:
                    severity = min(10, int(best_confidence * 10) + 2)

                    # 收集符合周期的实例
                    instances = [
                        t for t in sorted_times
                        if any(
                            abs((t - sorted_times[i]).total_seconds() / 60 - best_period) < 10
                            for i in range(len(sorted_times))
                            if sorted_times[i] != t
                        )
                    ]

                    periodic.append(PeriodicRevision(
                        record_id=record.record_id,
                        chapter_id=",".join([c.chapter_id for c in record.chapters]),
                        period_minutes=best_period,
                        confidence=best_confidence,
                        instances=instances,
                        severity=severity,
                    ))

        self._periodic_revisions = periodic
        return periodic

    def detect_rushed_sequence(
        self, records: list[EmrTimestampRecord]
    ) -> list[RushedSequence]:
        """
        检测章节修改时间异常接近（<5分钟），疑似仓促补写

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[RushedSequence]: 仓促序列列表
        """
        rushed: list[RushedSequence] = []

        for record in records:
            if len(record.chapters) < 2:
                continue

            # 按创建时间排序
            sorted_chapters = sorted(record.chapters, key=lambda c: c.created_time)
            threshold_seconds = self.rushed_threshold_minutes * 60

            i = 0
            while i < len(sorted_chapters) - 1:
                current = sorted_chapters[i]
                next_chapter = sorted_chapters[i + 1]

                gap_seconds = (next_chapter.created_time - current.created_time).total_seconds()

                if 0 < gap_seconds < threshold_seconds:
                    # 发现仓促补写
                    # 向前向后扩展，收集所有连续的短间隔章节
                    chapter_ids = [current.chapter_id, next_chapter.chapter_id]
                    start_idx = i
                    end_idx = i + 1

                    # 向前扩展
                    while start_idx > 0:
                        prev = sorted_chapters[start_idx - 1]
                        prev_gap = (current.created_time - prev.created_time).total_seconds()
                        if 0 < prev_gap < threshold_seconds:
                            chapter_ids.insert(0, prev.chapter_id)
                            start_idx -= 1
                            current = prev
                        else:
                            break

                    # 向后扩展
                    while end_idx < len(sorted_chapters) - 1:
                        next_ch = sorted_chapters[end_idx + 1]
                        next_gap = (next_ch.created_time - sorted_chapters[end_idx].created_time).total_seconds()
                        if 0 < next_gap < threshold_seconds:
                            chapter_ids.append(next_ch.chapter_id)
                            end_idx += 1
                        else:
                            break

                    # 计算实际的时间跨度
                    total_gap = (
                        sorted_chapters[end_idx].created_time -
                        sorted_chapters[start_idx].created_time
                    ).total_seconds()

                    # 严重程度：间隔越短、章节越多越严重
                    avg_gap = total_gap / len(chapter_ids) if len(chapter_ids) > 1 else total_gap
                    if avg_gap < 60:  # 小于1分钟
                        severity = min(10, 7 + len(chapter_ids))
                    elif avg_gap < 180:  # 小于3分钟
                        severity = min(10, 5 + len(chapter_ids) // 2)
                    else:
                        severity = min(10, 3 + len(chapter_ids) // 3)

                    rushed.append(RushedSequence(
                        record_id=record.record_id,
                        chapter_ids=chapter_ids,
                        time_gap_seconds=total_gap,
                        chapter_count=len(chapter_ids),
                        severity=severity,
                    ))

                    # 跳过已处理的章节
                    i = end_idx + 1
                else:
                    i += 1

        self._rushed_sequences = rushed
        return rushed

    def calculate_sequence_risk_score(
        self, records: list[EmrTimestampRecord]
    ) -> float:
        """
        综合计算序列风险分数（0-100）

        基于修改回溯、周期性修改、仓促序列计算综合风险分数

        Args:
            records: 病历时间戳记录列表

        Returns:
            float: 综合风险分数 (0-100)
        """
        if not records:
            return 0.0

        # 检测各种异常
        loops = self.detect_revision_loops(records)
        periodic = self.detect_periodic_revisions(records)
        rushed = self.detect_rushed_sequence(records)

        # 计算各维度得分
        # 1. 修改回溯得分（最高40分）
        loop_score = min(40.0, len(loops) * 5 + sum(
            min(10, loop.severity) for loop in loops
        ))

        # 2. 周期性修改得分（最高30分）
        periodic_score = min(30.0, len(periodic) * 8 + sum(
            min(10, p.confidence * 10) for p in periodic
        ))

        # 3. 仓促序列得分（最高30分）
        rushed_score = min(30.0, len(rushed) * 5 + sum(
            min(10, r.severity) for r in rushed
        ))

        total_score = loop_score + periodic_score + rushed_score

        return min(100.0, total_score)

    def get_sequence_summary(
        self, records: list[EmrTimestampRecord]
    ) -> dict:
        """
        获取序列分析摘要

        Args:
            records: 病历时间戳记录列表

        Returns:
            dict: 序列分析摘要
        """
        # 确保已运行检测
        if not self._revision_loops:
            self.detect_revision_loops(records)
        if not self._periodic_revisions:
            self.detect_periodic_revisions(records)
        if not self._rushed_sequences:
            self.detect_rushed_sequence(records)

        # 计算总修改次数
        total_modifications = sum(len(r.chapters) for r in records)

        # 计算平均修改间隔
        all_time_gaps = []
        for record in records:
            if len(record.chapters) >= 2:
                sorted_chapters = sorted(record.chapters, key=lambda c: c.created_time)
                for i in range(len(sorted_chapters) - 1):
                    gap = (sorted_chapters[i + 1].created_time -
                           sorted_chapters[i].created_time).total_seconds() / 60
                    all_time_gaps.append(gap)

        avg_interval = sum(all_time_gaps) / len(all_time_gaps) if all_time_gaps else 0

        # 收集风险段落
        risk_segments = []
        for loop in self._revision_loops:
            risk_segments.append(SequenceRiskSegment(
                record_id=loop.record_id,
                start_time=loop.earlier_chapter.created_time,
                end_time=loop.later_chapter.created_time,
                risk_score=loop.severity * 10,
                risk_type="revision_loop",
            ))

        for r in self._rushed_sequences:
            risk_segments.append(SequenceRiskSegment(
                record_id=r.record_id,
                start_time=records[0].chapters[0].created_time,  # 简化
                end_time=records[0].chapters[-1].created_time,
                risk_score=r.severity * 10,
                risk_type="rushed_sequence",
            ))

        return {
            "total_records": len(records),
            "total_modifications": total_modifications,
            "avg_modification_interval_minutes": round(avg_interval, 2),
            "revision_loops_count": len(self._revision_loops),
            "periodic_revisions_count": len(self._periodic_revisions),
            "rushed_sequences_count": len(self._rushed_sequences),
            "risk_segments": [seg.to_dict() for seg in risk_segments],
            "overall_risk_score": self.calculate_sequence_risk_score(records),
        }

    def detect(
        self, records: list[EmrTimestampRecord]
    ) -> list[TimestampAnomaly]:
        """
        检测所有异常序列模式，返回异常列表

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[TimestampAnomaly]: 时间戳异常列表
        """
        if not records:
            return []

        anomalies: list[TimestampAnomaly] = []

        # 检测修改回溯
        loops = self.detect_revision_loops(records)
        for loop in loops:
            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.SUSPICIOUS_SEQUENCE,
                severity=loop.severity,
                description=(
                    f"检测到修改时间回溯：章节「{loop.later_chapter.chapter_name}」创建时间"
                    f"({loop.later_chapter.created_time.strftime('%Y-%m-%d %H:%M:%S')}) "
                    f"晚于后续章节「{loop.earlier_chapter.chapter_name}」"
                    f"({loop.earlier_chapter.created_time.strftime('%Y-%m-%d %H:%M:%S')})，"
                    f"时间回溯 {loop.time_gap_minutes:.0f} 分钟"
                ),
                affected_records=[loop.record_id],
                evidence=loop.to_dict(),
            )
            anomalies.append(anomaly)

        # 检测周期性修改
        periodic = self.detect_periodic_revisions(records)
        for p in periodic:
            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.SUSPICIOUS_SEQUENCE,
                severity=p.severity,
                description=(
                    f"检测到疑似周期性修改：记录 {p.record_id} 的修改呈现 "
                    f"{p.period_minutes:.0f} 分钟周期的规律性，置信度 {p.confidence:.2f}，"
                    f"发现 {len(p.instances)} 个实例"
                ),
                affected_records=[p.record_id],
                evidence=p.to_dict(),
            )
            anomalies.append(anomaly)

        # 检测仓促序列
        rushed = self.detect_rushed_sequence(records)
        for r in rushed:
            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.SUSPICIOUS_SEQUENCE,
                severity=r.severity,
                description=(
                    f"检测到仓促补写：记录 {r.record_id} 中 {r.chapter_count} 个章节"
                    f"在 {r.time_gap_seconds:.0f} 秒内连续创建，疑似仓促补写"
                ),
                affected_records=[r.record_id],
                evidence=r.to_dict(),
            )
            anomalies.append(anomaly)

        # 按严重程度排序
        anomalies.sort(key=lambda a: a.severity, reverse=True)

        return anomalies


# 便捷函数
def detect_suspicious_sequences(
    records: list[EmrTimestampRecord],
    rushed_threshold_minutes: float = 5,
    periodic_confidence_threshold: float = 0.7,
) -> list[TimestampAnomaly]:
    """
    便捷函数：检测异常序列模式

    Args:
        records: 病历时间戳记录列表
        rushed_threshold_minutes: 仓促补写的时间阈值（分钟）
        periodic_confidence_threshold: 周期性检测的置信度阈值

    Returns:
        list[TimestampAnomaly]: 时间戳异常列表
    """
    detector = SequenceDetector(
        rushed_threshold_minutes=rushed_threshold_minutes,
        periodic_confidence_threshold=periodic_confidence_threshold,
    )
    return detector.detect(records)