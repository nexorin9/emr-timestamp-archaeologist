"""
EMR Timestamp Archaeologist - 夜间突击补写检测器
检测夜间（22:00-05:00）集中修改病历的突击补写行为
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from models import AnomalyType, EmrChapter, EmrTimestampRecord, TimestampAnomaly, create_timestamp_anomaly


@dataclass
class NightActivity:
    """
    夜间活动记录

    Attributes:
        timestamp: 活动发生时间
        record_id: 病历记录ID
        chapter_id: 章节ID
        activity_type: 活动类型 ("create" 或 "modify")
        author_id: 作者ID
        department: 科室（如果有）
    """
    timestamp: datetime
    record_id: str
    chapter_id: str
    activity_type: str
    author_id: str
    department: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "record_id": self.record_id,
            "chapter_id": self.chapter_id,
            "activity_type": self.activity_type,
            "author_id": self.author_id,
            "department": self.department,
        }


@dataclass
class NightHotspot:
    """
    夜间活动热点

    Attributes:
        time_slot: 时间段（如 "22:00-23:00"）
        department: 科室
        author_id: 作者ID
        activity_count: 活动数量
        night_ratio: 夜间活动占比
    """
    time_slot: str
    department: Optional[str]
    author_id: Optional[str]
    activity_count: int
    night_ratio: float

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "time_slot": self.time_slot,
            "department": self.department,
            "author_id": self.author_id,
            "activity_count": self.activity_count,
            "night_ratio": self.night_ratio,
        }


class NightActivityDetector:
    """
    夜间突击补写检测器

    检测在夜间（默认 22:00-05:00）集中创建或大量修改病历的行为。
    这种模式通常表明存在突击补写或下班后集中处理病历的情况。

    Attributes:
        night_start: 夜间开始时间（小时），默认为 22
        night_end: 夜间结束时间（小时），默认为 5
    """

    def __init__(
        self,
        night_start: int = 22,
        night_end: int = 5,
        unusual_night_ratio_threshold: float = 0.5,
        night_spike_threshold: float = 2.0,
    ) -> None:
        """
        初始化夜间活动检测器

        Args:
            night_start: 夜间开始时间（小时），默认为 22
            night_end: 夜间结束时间（小时），默认为 5
            unusual_night_ratio_threshold: 异常夜间活动占比阈值，默认为 0.5（50%）
            night_spike_threshold: 夜间峰值倍数阈值，默认为 2.0（相比基线2倍）
        """
        self.night_start = night_start
        self.night_end = night_end
        self.unusual_night_ratio_threshold = unusual_night_ratio_threshold
        self.night_spike_threshold = night_spike_threshold
        self._night_activities: list[NightActivity] = []
        self._department_baseline: dict[str, float] = {}  # 科室历史夜间占比基线
        self._night_hotspots: list[NightHotspot] = []

    def _is_night_time(self, dt: datetime) -> bool:
        """
        判断时间是否在夜间时段

        Args:
            dt: 待判断的时间

        Returns:
            bool: 如果在夜间时段返回 True
        """
        hour = dt.hour
        # 夜间时段：22:00-23:59 或 00:00-05:00
        # night_end=5 表示 00:00-05:00 (5点及之前都算夜间)
        if self.night_start > self.night_end:
            # 跨夜时段（如 22:00 - 05:00）
            return hour >= self.night_start or hour <= self.night_end
        else:
            # 非跨夜时段（较少见）
            return self.night_start <= hour < self.night_end

    def _get_time_slot(self, dt: datetime) -> str:
        """
        获取时间所属的小时时段

        Args:
            dt: 时间

        Returns:
            str: 时段字符串，如 "22:00-23:00"
        """
        hour = dt.hour
        next_hour = (hour + 1) % 24
        return f"{hour:02d}:00-{next_hour:02d}:00"

    def _get_department_from_chapter(self, chapter: EmrChapter) -> Optional[str]:
        """
        从章节获取科室信息

        目前通过 author_id 的前缀来模拟科室信息。
        实际实现时可从其他字段或外部映射获取。

        Args:
            chapter: 病历章节

        Returns:
            Optional[str]: 科室信息，如果无法获取则返回 None
        """
        # 模拟：author_id 格式为 "DEPT_INTERNAL_R001" 或 "DEPT_SURGERY_doc001" 或纯 author_id
        if "_" in chapter.author_id:
            parts = chapter.author_id.split("_")
            if len(parts) >= 2 and parts[0].startswith("DEPT"):
                # 组合所有以 DEPT 开头的连续部分，或紧跟在 DEPT 后的非用户ID部分
                dept_parts = []
                for i, p in enumerate(parts):
                    if i == 0:
                        # 第一个部分必须是 DEPT 开头
                        if p.startswith("DEPT"):
                            dept_parts.append(p)
                        else:
                            break
                    else:
                        # 后续部分：如果看起来像部门名称的一部分（不含doc/r和纯数字），则加入
                        # 使用 lower() 进行大小写不敏感比较
                        p_lower = p.lower()
                        if p_lower.startswith("doc") or p_lower.startswith("r") or p.isdigit():
                            # 这看起来像是用户ID，停止
                            break
                        dept_parts.append(p)
                if dept_parts:
                    return "_".join(dept_parts)
        return None

    def detect_night_modifications(
        self, records: list[EmrTimestampRecord]
    ) -> list[NightActivity]:
        """
        识别在夜间创建或大量修改的病历

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[NightActivity]: 夜间活动列表
        """
        self._night_activities = []

        for record in records:
            for chapter in record.chapters:
                # 检查创建时间是否在夜间
                if self._is_night_time(chapter.created_time):
                    department = self._get_department_from_chapter(chapter)
                    activity = NightActivity(
                        timestamp=chapter.created_time,
                        record_id=record.record_id,
                        chapter_id=chapter.chapter_id,
                        activity_type="create",
                        author_id=chapter.author_id,
                        department=department,
                    )
                    self._night_activities.append(activity)

                # 检查修改时间是否在夜间（且与创建时间不同）
                if (
                    chapter.modified_time is not None
                    and chapter.modified_time != chapter.created_time
                    and self._is_night_time(chapter.modified_time)
                ):
                    department = self._get_department_from_chapter(chapter)
                    activity = NightActivity(
                        timestamp=chapter.modified_time,
                        record_id=record.record_id,
                        chapter_id=chapter.chapter_id,
                        activity_type="modify",
                        author_id=chapter.author_id,
                        department=department,
                    )
                    self._night_activities.append(activity)

        return self._night_activities

    def calculate_night_ratio(
        self,
        author_id: Optional[str] = None,
        department: Optional[str] = None,
    ) -> float:
        """
        计算单个科室/医生的夜间修改占比

        占比计算方式：
        - 当指定 author_id 时：该作者的夜间活动数 / 所有夜间活动数
        - 当指定 department 时：该科室的夜间活动数 / 所有夜间活动数

        Args:
            author_id: 作者ID（可选）
            department: 科室（可选）

        Returns:
            float: 夜间活动占比 (0-1)
        """
        if not self._night_activities:
            return 0.0

        total_night_activities = len(self._night_activities)

        # 计算匹配的夜间活动数（分子）
        if author_id is not None:
            # 按作者过滤时，分子是作者的夜间活动数
            filtered = [a for a in self._night_activities if a.author_id == author_id]
        elif department is not None:
            # 按科室过滤时，分子是科室的夜间活动数
            filtered = [a for a in self._night_activities if a.department == department]
        else:
            filtered = self._night_activities

        night_count = len(filtered)

        if total_night_activities == 0:
            return 0.0

        return night_count / total_night_activities

    def set_department_baseline(
        self, department: str, baseline_ratio: float
    ) -> None:
        """
        设置科室夜间活动历史基线

        Args:
            department: 科室名称
            baseline_ratio: 基线夜间活动占比 (0-1)
        """
        self._department_baseline[department] = baseline_ratio

    def detect_department_night_spike(
        self,
        department: str,
        observed_night_ratio: Optional[float] = None,
    ) -> bool:
        """
        对比科室历史夜间修改基线，检测异常高峰

        Args:
            department: 科室名称
            observed_night_ratio: 观测到的夜间占比（如果为 None，则从当前数据计算）

        Returns:
            bool: 如果检测到异常高峰返回 True
        """
        if department not in self._department_baseline:
            # 没有基线数据，无法检测
            return False

        if observed_night_ratio is None:
            observed_night_ratio = self.calculate_night_ratio(department=department)

        baseline = self._department_baseline[department]

        # 如果观测值是基线的 night_spike_threshold 倍，则为异常高峰
        if baseline > 0:
            ratio = observed_night_ratio / baseline
            return ratio >= self.night_spike_threshold
        else:
            # 基线为0，如果观测值大于阈值，则为异常
            return observed_night_ratio >= self.unusual_night_ratio_threshold

    def is_unusual_night_activity(
        self,
        night_ratio: Optional[float] = None,
        activity_count: Optional[int] = None,
        is_weekend: bool = False,
    ) -> bool:
        """
        结合修改量和时间段，判断是否异常

        Args:
            night_ratio: 夜间活动占比（如果为 None，则从当前数据计算）
            activity_count: 夜间活动数量（如果为 None，则从当前数据计算）
            is_weekend: 是否为周末

        Returns:
            bool: 如果判断为异常夜间活动返回 True
        """
        if night_ratio is None:
            night_ratio = self.calculate_night_ratio()
        if activity_count is None:
            activity_count = len(self._night_activities)

        # 阈值调整：周末时稍微放宽（医生周末可能不值班）
        # 放宽意味着降低阈值，让更多的夜间活动被判定为异常
        threshold = self.unusual_night_ratio_threshold
        if is_weekend:
            threshold = max(0.0, threshold - 0.1)

        # 如果夜间占比超过阈值
        if night_ratio >= threshold:
            return True

        # 如果夜间活动数量异常多（>20）且占比不低（>30%）
        if activity_count > 20 and night_ratio >= 0.3:
            return True

        return False

    def get_night_hotspots(self) -> list[NightHotspot]:
        """
        返回夜间活动热点列表（时间段 + 科室 + 数量）

        Returns:
            list[NightHotspot]: 按活动数量降序排列的热点列表
        """
        if not self._night_activities:
            return []

        # 按时间段和科室聚合
        slot_department_activities: dict[tuple[str, str], list[NightActivity]] = (
            defaultdict(list)
        )

        for activity in self._night_activities:
            time_slot = self._get_time_slot(activity.timestamp)
            department = activity.department or "UNKNOWN"
            slot_department_activities[(time_slot, department)].append(activity)

        # 转换为热点列表
        self._night_hotspots = []
        for (time_slot, department), activities in slot_department_activities.items():
            # 计算该科室的夜间活动占比
            night_ratio = self.calculate_night_ratio(department=department)

            hotspot = NightHotspot(
                time_slot=time_slot,
                department=department,
                author_id=None,  # 按科室聚合，不显示具体作者
                activity_count=len(activities),
                night_ratio=night_ratio,
            )
            self._night_hotspots.append(hotspot)

        # 按活动数量降序排序
        self._night_hotspots.sort(key=lambda h: h.activity_count, reverse=True)

        return self._night_hotspots

    def get_night_activity_summary(self) -> dict:
        """
        获取夜间活动摘要统计

        Returns:
            dict: 包含各种统计信息的字典
        """
        if not self._night_activities:
            return {
                "total_night_activities": 0,
                "night_create_count": 0,
                "night_modify_count": 0,
                "unique_departments": 0,
                "unique_authors": 0,
                "night_ratio": 0.0,
            }

        create_count = len([a for a in self._night_activities if a.activity_type == "create"])
        modify_count = len([a for a in self._night_activities if a.activity_type == "modify"])
        departments = set(a.department for a in self._night_activities if a.department)
        authors = set(a.author_id for a in self._night_activities)

        return {
            "total_night_activities": len(self._night_activities),
            "night_create_count": create_count,
            "night_modify_count": modify_count,
            "unique_departments": len(departments),
            "unique_authors": len(authors),
            "night_ratio": self.calculate_night_ratio(),
        }

    def detect(
        self, records: list[EmrTimestampRecord]
    ) -> list[TimestampAnomaly]:
        """
        检测夜间突击补写，返回异常列表

        Args:
            records: 病历时间戳记录列表

        Returns:
            list[TimestampAnomaly]: 时间戳异常列表
        """
        if not records:
            return []

        # 运行检测
        self.detect_night_modifications(records)

        # 获取摘要统计
        summary = self.get_night_activity_summary()
        anomalies: list[TimestampAnomaly] = []

        # 如果夜间活动比例异常
        if self.is_unusual_night_activity(night_ratio=summary["night_ratio"]):
            affected_records = list(set(a.record_id for a in self._night_activities))

            evidence = {
                "total_night_activities": summary["total_night_activities"],
                "night_create_count": summary["night_create_count"],
                "night_modify_count": summary["night_modify_count"],
                "night_ratio": summary["night_ratio"],
                "unique_departments": summary["unique_departments"],
                "unique_authors": summary["unique_authors"],
                "night_period": f"{self.night_start}:00-{self.night_end}:00",
                "hotspots": [h.to_dict() for h in self.get_night_hotspots()[:10]],
            }

            # 计算严重程度
            # 基于夜间活动占比和数量
            base_severity = int(summary["night_ratio"] * 8) + 2
            if summary["total_night_activities"] > 50:
                base_severity = min(10, base_severity + 2)
            elif summary["total_night_activities"] > 20:
                base_severity = min(10, base_severity + 1)

            anomaly = create_timestamp_anomaly(
                anomaly_type=AnomalyType.NIGHT_RUSH,
                severity=base_severity,
                description=(
                    f"检测到夜间突击补写嫌疑：{summary['total_night_activities']}次夜间活动，"
                    f"夜间活动占比 {summary['night_ratio']:.1%}，"
                    f"涉及 {summary['unique_departments']} 个科室、{summary['unique_authors']} 名医生"
                ),
                affected_records=affected_records[:50],  # 限制数量
                evidence=evidence,
            )
            anomalies.append(anomaly)

        # 检测各科室的夜间活动峰值
        for department in set(a.department for a in self._night_activities if a.department):
            if department and department in self._department_baseline:
                dept_night_ratio = self.calculate_night_ratio(department=department)
                if self.detect_department_night_spike(department, dept_night_ratio):
                    dept_activities = [
                        a for a in self._night_activities if a.department == department
                    ]
                    affected_records = list(set(a.record_id for a in dept_activities))

                    evidence = {
                        "department": department,
                        "baseline_night_ratio": self._department_baseline[department],
                        "observed_night_ratio": dept_night_ratio,
                        "spike_ratio": dept_night_ratio / self._department_baseline[department]
                        if self._department_baseline[department] > 0
                        else float("inf"),
                        "night_activity_count": len(dept_activities),
                    }

                    severity = min(10, int(dept_night_ratio * 8) + 3)

                    anomaly = create_timestamp_anomaly(
                        anomaly_type=AnomalyType.NIGHT_RUSH,
                        severity=severity,
                        description=(
                            f"科室 {department} 夜间活动异常高峰："
                            f"观测夜间占比 {dept_night_ratio:.1%}，"
                            f"历史基线 {self._department_baseline[department]:.1%}，"
                            f"峰值倍数 {evidence['spike_ratio']:.1f}x"
                        ),
                        affected_records=affected_records[:20],
                        evidence=evidence,
                    )
                    anomalies.append(anomaly)

        # 按严重程度排序
        anomalies.sort(key=lambda a: a.severity, reverse=True)

        return anomalies


# 便捷函数
def detect_night_rush(
    records: list[EmrTimestampRecord],
    night_start: int = 22,
    night_end: int = 5,
) -> list[TimestampAnomaly]:
    """
    便捷函数：检测夜间突击补写

    Args:
        records: 病历时间戳记录列表
        night_start: 夜间开始时间（小时）
        night_end: 夜间结束时间（小时）

    Returns:
        list[TimestampAnomaly]: 时间戳异常列表
    """
    detector = NightActivityDetector(night_start=night_start, night_end=night_end)
    return detector.detect(records)