"""
EMR Timestamp Archaeologist - 批处理痕迹检测器
检测同一时间段内多份病历时间戳完全相同（精确到秒）的批处理痕迹
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from models import AnomalyType, EmrTimestampRecord, TimestampAnomaly, create_timestamp_anomaly


@dataclass
class BatchGroup:
    """
    批处理群组 - 表示时间戳完全相同的一组病历章节

    Attributes:
        timestamp: 共同的时间戳
        entries: 该群组包含的条目列表 (record_id, chapter_id)
        identical_count: 相同时间戳的章节数量
        confidence: 批处理置信度 (0-1)
    """
    timestamp: datetime
    entries: list[tuple[str, str]]  # (record_id, chapter_id)
    identical_count: int
    confidence: float

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "entries": [
                {"record_id": rid, "chapter_id": cid}
                for rid, cid in self.entries
            ],
            "identical_count": self.identical_count,
            "confidence": self.confidence,
        }


class BatchDetector:
    """
    批处理痕迹检测器

    检测同一时间段内多份病历时间戳完全相同（精确到秒）的批处理痕迹。
    这种模式通常表明病历是在事后一次性补写，而非按实际时间顺序记录。

    Attributes:
        threshold_seconds: 时间相同阈值（秒），超过此阈值视为不同时间
    """

    def __init__(self, threshold_seconds: int = 60) -> None:
        """
        初始化批处理检测器

        Args:
            threshold_seconds: 时间相同阈值，默认为60秒。
                             超过此阈值的时间差视为不同时间点
        """
        self.threshold_seconds = threshold_seconds
        self._batch_groups: list[BatchGroup] = []

    def is_identical_timestamps(
        self, time1: datetime, time2: datetime
    ) -> bool:
        """
        判断两个时间戳是否视为相同（允许秒级误差）

        Args:
            time1: 第一个时间戳
            time2: 第二个时间戳

        Returns:
            bool: 如果时间差在阈值内返回 True
        """
        if time1 is None or time2 is None:
            return False
        delta = abs((time1 - time2).total_seconds())
        return delta <= self.threshold_seconds

    def calculate_batch_score(
        self, identical_count: int, total_records: int
    ) -> float:
        """
        计算批处理置信度分数 (0-1)

        置信度基于相同时间戳的章节数量占总记录的比例。
        数量越多、占比越高，置信度越高。

        Args:
            identical_count: 相同时间戳的章节数量
            total_records: 总记录数（章节总数）

        Returns:
            float: 置信度分数 (0-1)
        """
        if total_records == 0 or identical_count == 0:
            return 0.0

        # 基础分数：基于数量
        # 3个相同 -> 0.5, 5个 -> 0.7, 10个 -> 0.9
        if identical_count < 3:
            base_score = 0.3 + (identical_count * 0.1)
        elif identical_count < 5:
            base_score = 0.5 + ((identical_count - 3) * 0.15)
        elif identical_count < 10:
            base_score = 0.7 + ((identical_count - 5) * 0.04)
        else:
            base_score = min(0.95, 0.9 + ((identical_count - 10) * 0.01))

        # 调整因子：基于占比
        ratio = identical_count / total_records
        if ratio >= 0.5:
            ratio_factor = 1.0
        elif ratio >= 0.3:
            ratio_factor = 0.9
        elif ratio >= 0.1:
            ratio_factor = 0.7
        else:
            ratio_factor = 0.5

        return min(1.0, base_score * ratio_factor)

    def detect_batch_patterns(
        self, records: list[EmrTimestampRecord]
    ) -> list[BatchGroup]:
        """
        扫描所有记录，识别时间戳完全相同的病历群组

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[BatchGroup]: 批处理群组列表
        """
        self._batch_groups = []

        # 收集所有章节时间戳
        timestamp_entries: dict[str, list[tuple[str, str, datetime]]] = defaultdict(list)
        # key: "YYYY-MM-DD HH:MM:SS" 格式的时间戳字符串
        # value: (record_id, chapter_id, 原始datetime) 列表

        for record in records:
            for chapter in record.chapters:
                ts_key = chapter.created_time.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_entries[ts_key].append(
                    (record.record_id, chapter.chapter_id, chapter.created_time)
                )

        # 找出所有相同时间戳的群组
        for ts_key, entries in timestamp_entries.items():
            if len(entries) >= 2:  # 至少有2个章节时间戳相同
                # 使用第一个条目的时间戳作为群组时间戳
                group_timestamp = entries[0][2]
                identical_count = len(entries)

                # 计算置信度
                total_chapters = sum(len(r.chapters) for r in records)
                confidence = self.calculate_batch_score(identical_count, total_chapters)

                group = BatchGroup(
                    timestamp=group_timestamp,
                    entries=[(e[0], e[1]) for e in entries],
                    identical_count=identical_count,
                    confidence=confidence,
                )
                self._batch_groups.append(group)

        # 按置信度排序
        self._batch_groups.sort(key=lambda g: g.confidence, reverse=True)

        return self._batch_groups

    def get_batch_groups(self) -> list[BatchGroup]:
        """
        返回所有批处理群组

        Returns:
            list[BatchGroup]: 批处理群组列表（按置信度降序）
        """
        return self._batch_groups

    def filter_significant_batches(
        self, min_identical_count: int = 3
    ) -> list[BatchGroup]:
        """
        过滤小规模批处理，仅返回达到阈值的群组

        Args:
            min_identical_count: 最小相同数量阈值，默认为3

        Returns:
            list[BatchGroup]: 过滤后的批处理群组列表
        """
        return [
            g for g in self._batch_groups
            if g.identical_count >= min_identical_count
        ]

    def detect(
        self, records: list[EmrTimestampRecord]
    ) -> list[TimestampAnomaly]:
        """
        检测批处理痕迹，返回异常列表

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[TimestampAnomaly]: 时间戳异常列表
        """
        if not records:
            return []

        # 运行检测
        self.detect_batch_patterns(records)

        # 过滤显著批处理（至少3个相同时间戳）
        significant_batches = self.filter_significant_batches(min_identical_count=3)

        anomalies: list[TimestampAnomaly] = []

        for group in significant_batches:
            # 收集受影响的记录ID
            affected_records = list(set(entry[0] for entry in group.entries))

            # 构建证据信息
            evidence = {
                "timestamp": group.timestamp.isoformat(),
                "identical_count": group.identical_count,
                "confidence": group.confidence,
                "affected_chapters": [
                    {"record_id": rid, "chapter_id": cid}
                    for rid, cid in group.entries
                ],
            }

            # 计算严重程度（基于置信度和数量）
            # 置信度 0-1 -> 严重程度 3-10
            base_severity = int(group.confidence * 7) + 3
            # 数量加成
            if group.identical_count >= 10:
                base_severity = min(10, base_severity + 2)
            elif group.identical_count >= 7:
                base_severity = min(10, base_severity + 1)

            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.BATCH_PROCESSING,
                severity=base_severity,
                description=(
                    f"检测到批处理痕迹：{group.identical_count}份病历章节"
                    f"在 {group.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"时间戳完全相同，置信度 {group.confidence:.1%}"
                ),
                affected_records=affected_records,
                evidence=evidence,
            )
            anomalies.append(anomaly)

        # 按严重程度排序
        anomalies.sort(key=lambda a: a.severity, reverse=True)

        return anomalies


# 便捷函数
def detect_batch_patterns(
    records: list[EmrTimestampRecord],
    threshold_seconds: int = 60
) -> list[TimestampAnomaly]:
    """
    便捷函数：检测批处理痕迹

    Args:
        records: 病历时间戳记录列表
        threshold_seconds: 时间相同阈值（秒）

    Returns:
        list[TimestampAnomaly]: 时间戳异常列表
    """
    detector = BatchDetector(threshold_seconds=threshold_seconds)
    return detector.detect(records)