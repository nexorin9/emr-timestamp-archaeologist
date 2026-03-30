"""
单元测试：EMR 时间戳考古器 - 夜间突击补写检测器
测试 NightActivityDetector 类的夜间活动检测场景
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# 添加 src/py 到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from detectors.night_detector import (
    NightActivity,
    NightActivityDetector,
    NightHotspot,
)
from models import AnomalyType, EmrChapter, EmrTimestampRecord


class TestNightDetectorInit:
    """测试 NightActivityDetector 初始化"""

    def test_default_night_hours(self) -> None:
        """测试默认夜间时段"""
        detector = NightActivityDetector()
        assert detector.night_start == 22
        assert detector.night_end == 5

    def test_custom_night_hours(self) -> None:
        """测试自定义夜间时段"""
        detector = NightActivityDetector(night_start=21, night_end=6)
        assert detector.night_start == 21
        assert detector.night_end == 6


class TestIsNightTime:
    """测试 _is_night_time 方法"""

    def test_night_start_hour(self) -> None:
        """测试夜间开始时间（22:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 22, 0, 0)
        assert detector._is_night_time(dt) is True

    def test_late_night_hour(self) -> None:
        """测试深夜时间（23:30）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 23, 30, 0)
        assert detector._is_night_time(dt) is True

    def test_early_morning_hour(self) -> None:
        """测试凌晨时间（03:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 3, 0, 0)
        assert detector._is_night_time(dt) is True

    def test_morning_hour(self) -> None:
        """测试早晨时间（08:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 8, 0, 0)
        assert detector._is_night_time(dt) is False

    def test_afternoon_hour(self) -> None:
        """测试下午时间（14:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 14, 0, 0)
        assert detector._is_night_time(dt) is False

    def test_edge_case_end_hour(self) -> None:
        """测试夜间结束时间边界（05:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 5, 0, 0)
        assert detector._is_night_time(dt) is True

    def test_edge_case_after_end(self) -> None:
        """测试夜间结束后时间（06:00）"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 6, 0, 0)
        assert detector._is_night_time(dt) is False


class TestGetTimeSlot:
    """测试 _get_time_slot 方法"""

    def test_standard_slot(self) -> None:
        """测试标准时段"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 22, 0, 0)
        assert detector._get_time_slot(dt) == "22:00-23:00"

    def test_midnight_slot(self) -> None:
        """测试午夜时段"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 0, 0, 0)
        assert detector._get_time_slot(dt) == "00:00-01:00"

    def test_wrap_around_slot(self) -> None:
        """测试跨天时段"""
        detector = NightActivityDetector()
        dt = datetime(2024, 1, 1, 23, 0, 0)
        assert detector._get_time_slot(dt) == "23:00-00:00"


class TestGetDepartmentFromChapter:
    """测试 _get_department_from_chapter 方法"""

    def test_department_in_author_id(self) -> None:
        """测试作者ID包含科室信息"""
        detector = NightActivityDetector()
        chapter = EmrChapter(
            chapter_id="ch-1",
            chapter_name="病程记录",
            chapter_order=0,
            created_time=datetime(2024, 1, 1, 10, 0, 0),
            modified_time=datetime(2024, 1, 1, 10, 0, 0),
            author_id="DEPT_INTERNAL_R001",
        )
        dept = detector._get_department_from_chapter(chapter)
        assert dept == "DEPT_INTERNAL"

    def test_no_department_in_author_id(self) -> None:
        """测试作者ID不包含科室信息"""
        detector = NightActivityDetector()
        chapter = EmrChapter(
            chapter_id="ch-1",
            chapter_name="病程记录",
            chapter_order=0,
            created_time=datetime(2024, 1, 1, 10, 0, 0),
            modified_time=datetime(2024, 1, 1, 10, 0, 0),
            author_id="doctor-001",
        )
        dept = detector._get_department_from_chapter(chapter)
        assert dept is None


class TestDetectNightModifications:
    """测试 detect_night_modifications 方法"""

    def _create_record(
        self,
        record_id: str,
        created_time: datetime,
        modified_time: datetime | None = None,
        author_id: str = "DEPT_INTERNAL_doc001",
    ) -> EmrTimestampRecord:
        """辅助方法：创建病历记录"""
        mtime = modified_time if modified_time is not None else created_time
        chapters = [
            EmrChapter(
                chapter_id=f"{record_id}-ch-0",
                chapter_name="第一章",
                chapter_order=0,
                created_time=created_time,
                modified_time=mtime,
                author_id=author_id,
            )
        ]
        return EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id=record_id,
            record_type="入院记录",
            chapters=chapters,
        )

    def test_no_records(self) -> None:
        """测试空记录列表"""
        detector = NightActivityDetector()
        activities = detector.detect_night_modifications([])
        assert activities == []

    def test_no_night_activity(self) -> None:
        """测试没有夜间活动"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 10, 0, 0),  # 白天
                datetime(2024, 1, 1, 10, 0, 0),
            )
        ]
        activities = detector.detect_night_modifications(records)
        assert activities == []

    def test_night_create(self) -> None:
        """测试夜间创建"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 23, 0, 0),  # 夜间
                datetime(2024, 1, 1, 23, 0, 0),
            )
        ]
        activities = detector.detect_night_modifications(records)
        assert len(activities) == 1
        assert activities[0].activity_type == "create"
        assert activities[0].record_id == "R-001"

    def test_night_modify(self) -> None:
        """测试夜间修改"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 10, 0, 0),  # 白天创建
                datetime(2024, 1, 1, 23, 0, 0),  # 夜间修改
            )
        ]
        activities = detector.detect_night_modifications(records)
        assert len(activities) == 1
        assert activities[0].activity_type == "modify"

    def test_both_create_and_modify_at_night(self) -> None:
        """测试夜间同时有创建和修改"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 23, 0, 0),  # 夜间创建
                datetime(2024, 1, 1, 23, 30, 0),  # 夜间修改
            )
        ]
        activities = detector.detect_night_modifications(records)
        assert len(activities) == 2
        types = {a.activity_type for a in activities}
        assert types == {"create", "modify"}

    def test_multiple_records(self) -> None:
        """测试多条记录"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 23, 0, 0),
            ),
            self._create_record(
                "R-002",
                datetime(2024, 1, 1, 2, 0, 0),  # 凌晨
            ),
            self._create_record(
                "R-003",
                datetime(2024, 1, 1, 10, 0, 0),  # 白天
            ),
        ]
        activities = detector.detect_night_modifications(records)
        assert len(activities) == 2  # 只有2个夜间活动

    def test_department_extraction(self) -> None:
        """测试科室信息提取"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 23, 0, 0),
                author_id="DEPT_SURGERY_doc001",
            )
        ]
        activities = detector.detect_night_modifications(records)
        assert len(activities) == 1
        assert activities[0].department == "DEPT_SURGERY"


class TestCalculateNightRatio:
    """测试 calculate_night_ratio 方法"""

    def _create_detector_with_activities(
        self,
        activities: list[NightActivity],
    ) -> NightActivityDetector:
        """辅助方法：创建带活动的检测器"""
        detector = NightActivityDetector()
        detector._night_activities = activities
        return detector

    def test_no_activities(self) -> None:
        """测试无活动时"""
        detector = self._create_detector_with_activities([])
        ratio = detector.calculate_night_ratio()
        assert ratio == 0.0

    def test_all_night_activities(self) -> None:
        """测试全部是夜间活动"""
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            )
        ]
        detector = self._create_detector_with_activities(activities)
        ratio = detector.calculate_night_ratio()
        assert ratio == 1.0

    def test_filter_by_author(self) -> None:
        """测试按作者过滤"""
        # 场景：doc-001 有3个夜间活动，doc-002 有1个夜间活动
        # 当过滤 author_id="doc-001" 时，比率为 3/(3+1) = 0.75
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 30, 0),
                record_id="R-002",
                chapter_id="ch-2",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 22, 0, 0),
                record_id="R-003",
                chapter_id="ch-3",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_B",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-004",
                chapter_id="ch-4",
                activity_type="create",
                author_id="doc-002",
                department="DEPT_A",
            ),
        ]
        detector = self._create_detector_with_activities(activities)
        ratio = detector.calculate_night_ratio(author_id="doc-001")
        assert ratio == 0.75  # doc-001 有3个夜间活动，总共4个夜间活动

    def test_filter_by_department(self) -> None:
        """测试按科室过滤"""
        # 场景：DEPT_A 有2个夜间活动，DEPT_B 有1个夜间活动
        # 当过滤 department="DEPT_A" 时，比率为 2/(2+1) = 0.667
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 30, 0),
                record_id="R-002",
                chapter_id="ch-2",
                activity_type="create",
                author_id="doc-002",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 22, 0, 0),
                record_id="R-003",
                chapter_id="ch-3",
                activity_type="create",
                author_id="doc-003",
                department="DEPT_B",
            ),
        ]
        detector = self._create_detector_with_activities(activities)
        ratio = detector.calculate_night_ratio(department="DEPT_A")
        assert abs(ratio - 0.667) < 0.001  # DEPT_A 有2个夜间活动，总共3个夜间活动


class TestDepartmentBaseline:
    """测试科室基线相关方法"""

    def test_set_baseline(self) -> None:
        """测试设置基线"""
        detector = NightActivityDetector()
        detector.set_department_baseline("DEPT_A", 0.3)
        assert detector._department_baseline["DEPT_A"] == 0.3

    def test_detect_spike_above_threshold(self) -> None:
        """测试检测超过阈值的峰值"""
        detector = NightActivityDetector(night_spike_threshold=2.0)
        detector.set_department_baseline("DEPT_A", 0.2)
        # 观测值0.5是基线0.2的2.5倍
        result = detector.detect_department_night_spike("DEPT_A", 0.5)
        assert result is True

    def test_detect_spike_below_threshold(self) -> None:
        """测试检测未超过阈值的峰值"""
        detector = NightActivityDetector(night_spike_threshold=2.0)
        detector.set_department_baseline("DEPT_A", 0.2)
        # 观测值0.3是基线0.2的1.5倍
        result = detector.detect_department_night_spike("DEPT_A", 0.3)
        assert result is False

    def test_detect_spike_no_baseline(self) -> None:
        """测试没有基线时返回False"""
        detector = NightActivityDetector()
        result = detector.detect_department_night_spike("DEPT_UNKNOWN", 0.5)
        assert result is False


class TestIsUnusualNightActivity:
    """测试 is_unusual_night_activity 方法"""

    def test_high_night_ratio_is_unusual(self) -> None:
        """测试高夜间占比为异常"""
        detector = NightActivityDetector(unusual_night_ratio_threshold=0.5)
        assert detector.is_unusual_night_activity(night_ratio=0.6) is True

    def test_low_night_ratio_is_normal(self) -> None:
        """测试低夜间占比为正常"""
        detector = NightActivityDetector(unusual_night_ratio_threshold=0.5)
        assert detector.is_unusual_night_activity(night_ratio=0.3) is False

    def test_high_count_low_ratio_unusual(self) -> None:
        """测试高数量低占比为异常"""
        detector = NightActivityDetector()
        # 活动数>20 且 占比>30%
        assert (
            detector.is_unusual_night_activity(
                night_ratio=0.35, activity_count=25
            )
            is True
        )

    def test_weekend_threshold_relaxed(self) -> None:
        """测试周末阈值放宽"""
        detector = NightActivityDetector(unusual_night_ratio_threshold=0.5)
        # 周末占比0.55视为异常（阈值放宽到0.6）
        assert (
            detector.is_unusual_night_activity(
                night_ratio=0.55, is_weekend=True
            )
            is True
        )


class TestGetNightHotspots:
    """测试 get_night_hotspots 方法"""

    def _create_detector_with_activities(
        self,
        activities: list[NightActivity],
    ) -> NightActivityDetector:
        """辅助方法：创建带活动的检测器"""
        detector = NightActivityDetector()
        detector._night_activities = activities
        return detector

    def test_no_activities(self) -> None:
        """测试无活动时"""
        detector = self._create_detector_with_activities([])
        hotspots = detector.get_night_hotspots()
        assert hotspots == []

    def test_single_hotspot(self) -> None:
        """测试单个热点"""
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 30, 0),
                record_id="R-002",
                chapter_id="ch-2",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
        ]
        detector = self._create_detector_with_activities(activities)
        hotspots = detector.get_night_hotspots()
        assert len(hotspots) == 1
        assert hotspots[0].time_slot == "23:00-00:00"
        assert hotspots[0].activity_count == 2

    def test_multiple_hotspots_sorted(self) -> None:
        """测试多个热点并排序"""
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 22, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-002",
                chapter_id="ch-2",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-003",
                chapter_id="ch-3",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-004",
                chapter_id="ch-4",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
        ]
        detector = self._create_detector_with_activities(activities)
        hotspots = detector.get_night_hotspots()
        # 应该按活动数量降序排列
        assert hotspots[0].time_slot == "23:00-00:00"
        assert hotspots[0].activity_count == 3
        assert hotspots[1].time_slot == "22:00-23:00"
        assert hotspots[1].activity_count == 1


class TestDetect:
    """测试 detect 方法"""

    def _create_record(
        self,
        record_id: str,
        created_time: datetime,
        modified_time: datetime | None = None,
        author_id: str = "DEPT_INTERNAL_doc001",
    ) -> EmrTimestampRecord:
        """辅助方法：创建病历记录"""
        mtime = modified_time if modified_time is not None else created_time
        chapters = [
            EmrChapter(
                chapter_id=f"{record_id}-ch-0",
                chapter_name="第一章",
                chapter_order=0,
                created_time=created_time,
                modified_time=mtime,
                author_id=author_id,
            )
        ]
        return EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id=record_id,
            record_type="入院记录",
            chapters=chapters,
        )

    def test_no_records(self) -> None:
        """测试空记录列表"""
        detector = NightActivityDetector()
        anomalies = detector.detect([])
        assert anomalies == []

    def test_no_anomalies(self) -> None:
        """测试无异常情况"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 10, 0, 0),  # 白天
            )
        ]
        anomalies = detector.detect(records)
        assert anomalies == []

    def test_detects_night_rush_anomaly(self) -> None:
        """测试检测到夜间突击补写异常"""
        detector = NightActivityDetector()
        # 创建大量夜间活动
        records = [
            self._create_record(
                f"R-{i:03d}",
                datetime(2024, 1, 1, 23, 0, 0),  # 夜间
            )
            for i in range(30)
        ]
        anomalies = detector.detect(records)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.NIGHT_RUSH
        assert 0 <= anomalies[0].severity <= 10

    def test_anomaly_description_contains_details(self) -> None:
        """测试异常描述包含详细信息"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                "R-001",
                datetime(2024, 1, 1, 23, 0, 0),
                author_id="DEPT_SURGERY_doc001",
            )
            for _ in range(5)
        ]
        anomalies = detector.detect(records)
        desc = anomalies[0].description
        assert "夜间突击补写" in desc or "night" in desc.lower()

    def test_anomaly_evidence_contains_stats(self) -> None:
        """测试异常证据包含统计信息"""
        detector = NightActivityDetector()
        records = [
            self._create_record(
                f"R-{i:03d}",
                datetime(2024, 1, 1, 23, 0, 0),
                author_id="DEPT_SURGERY_doc001",
            )
            for i in range(10)
        ]
        anomalies = detector.detect(records)
        evidence = anomalies[0].evidence
        assert "total_night_activities" in evidence
        assert "night_ratio" in evidence
        assert "unique_departments" in evidence

    def test_department_spike_anomaly(self) -> None:
        """测试科室夜间活动峰值异常"""
        detector = NightActivityDetector(night_spike_threshold=2.0)
        detector.set_department_baseline("DEPT_SURGERY", 0.2)

        records = [
            self._create_record(
                f"R-{i:03d}",
                datetime(2024, 1, 1, 23, 0, 0),  # 夜间 -> 100% 夜间活动
                author_id="DEPT_SURGERY_doc001",
            )
            for i in range(10)
        ]
        anomalies = detector.detect(records)
        # 应该有2个异常：一个是整体夜间异常，一个是科室峰值
        assert len(anomalies) == 2
        dept_anomaly = next(
            a for a in anomalies if "DEPT_SURGERY" in a.description
        )
        assert dept_anomaly.anomaly_type == AnomalyType.NIGHT_RUSH

    def test_severity_based_on_night_ratio(self) -> None:
        """测试严重程度基于夜间活动占比"""
        detector = NightActivityDetector()
        # 高夜间占比 -> 高严重程度
        records_high = [
            self._create_record(
                f"R-{i:03d}",
                datetime(2024, 1, 1, 23, 0, 0),  # 100% 夜间
            )
            for i in range(30)
        ]
        anomalies_high = detector.detect(records_high)

        # 低夜间占比 -> 低严重程度
        records_low = [
            self._create_record(
                f"R-{i:03d}",
                (datetime(2024, 1, 1, 23, 0, 0) if i < 10 else datetime(2024, 1, 1, 10, 0, 0)),
            )
            for i in range(30)
        ]
        anomalies_low = detector.detect(records_low)

        if anomalies_high and anomalies_low:
            assert anomalies_high[0].severity >= anomalies_low[0].severity


class TestNightActivitySummary:
    """测试夜间活动摘要统计"""

    def _create_detector_with_activities(
        self,
        activities: list[NightActivity],
    ) -> NightActivityDetector:
        """辅助方法：创建带活动的检测器"""
        detector = NightActivityDetector()
        detector._night_activities = activities
        return detector

    def test_empty_summary(self) -> None:
        """测试空摘要"""
        detector = self._create_detector_with_activities([])
        summary = detector.get_night_activity_summary()
        assert summary["total_night_activities"] == 0
        assert summary["night_ratio"] == 0.0

    def test_summary_with_activities(self) -> None:
        """测试带活动的摘要"""
        activities = [
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 0, 0),
                record_id="R-001",
                chapter_id="ch-1",
                activity_type="create",
                author_id="doc-001",
                department="DEPT_A",
            ),
            NightActivity(
                timestamp=datetime(2024, 1, 1, 23, 30, 0),
                record_id="R-002",
                chapter_id="ch-2",
                activity_type="modify",
                author_id="doc-001",
                department="DEPT_A",
            ),
        ]
        detector = self._create_detector_with_activities(activities)
        summary = detector.get_night_activity_summary()
        assert summary["total_night_activities"] == 2
        assert summary["night_create_count"] == 1
        assert summary["night_modify_count"] == 1
        assert summary["unique_departments"] == 1
        assert summary["unique_authors"] == 1


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_detect_night_rush_function(self) -> None:
        """测试 detect_night_rush 便捷函数"""
        from detectors.night_detector import detect_night_rush

        chapters = [
            EmrChapter(
                chapter_id=f"ch-{i}",
                chapter_name=f"章节{i}",
                chapter_order=i,
                created_time=datetime(2024, 1, 1, 23, 0, 0),
                modified_time=datetime(2024, 1, 1, 23, 0, 0),
                author_id="DEPT_INTERNAL_doc001",
            )
            for i in range(5)
        ]
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=chapters,
            )
        ]

        anomalies = detect_night_rush(records)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.NIGHT_RUSH