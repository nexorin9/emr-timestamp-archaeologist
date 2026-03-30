"""
单元测试：EMR 时间戳考古器 - 批处理痕迹检测器
测试 BatchDetector 类的各种批处理检测场景
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 添加 src/py 到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from detectors.batch_detector import BatchDetector, BatchGroup
from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
)


class TestBatchDetectorInit:
    """测试 BatchDetector 初始化"""

    def test_default_threshold(self) -> None:
        """测试默认阈值"""
        detector = BatchDetector()
        assert detector.threshold_seconds == 60

    def test_custom_threshold(self) -> None:
        """测试自定义阈值"""
        detector = BatchDetector(threshold_seconds=30)
        assert detector.threshold_seconds == 30


class TestIsIdenticalTimestamps:
    """测试 is_identical_timestamps 方法"""

    def test_identical_times(self) -> None:
        """测试完全相同的时间"""
        detector = BatchDetector()
        t1 = datetime(2024, 1, 1, 10, 0, 0)
        t2 = datetime(2024, 1, 1, 10, 0, 0)
        assert detector.is_identical_timestamps(t1, t2) is True

    def test_within_threshold(self) -> None:
        """测试在阈值内的时间差"""
        detector = BatchDetector(threshold_seconds=60)
        t1 = datetime(2024, 1, 1, 10, 0, 0)
        t2 = datetime(2024, 1, 1, 10, 0, 30)  # 30秒差
        assert detector.is_identical_timestamps(t1, t2) is True

    def test_exceeds_threshold(self) -> None:
        """测试超过阈值的时间差"""
        detector = BatchDetector(threshold_seconds=60)
        t1 = datetime(2024, 1, 1, 10, 0, 0)
        t2 = datetime(2024, 1, 1, 10, 2, 0)  # 120秒差
        assert detector.is_identical_timestamps(t1, t2) is False

    def test_none_time(self) -> None:
        """测试 None 时间"""
        detector = BatchDetector()
        t1 = datetime(2024, 1, 1, 10, 0, 0)
        assert detector.is_identical_timestamps(t1, None) is False
        assert detector.is_identical_timestamps(None, t1) is False
        assert detector.is_identical_timestamps(None, None) is False


class TestCalculateBatchScore:
    """测试 calculate_batch_score 方法"""

    def test_zero_count(self) -> None:
        """测试零数量"""
        detector = BatchDetector()
        score = detector.calculate_batch_score(0, 100)
        assert score == 0.0

    def test_zero_total(self) -> None:
        """测试总数为零"""
        detector = BatchDetector()
        score = detector.calculate_batch_score(5, 0)
        assert score == 0.0

    def test_low_count(self) -> None:
        """测试低数量场景（1-2个相同）"""
        detector = BatchDetector()
        score = detector.calculate_batch_score(1, 100)
        assert 0.0 <= score <= 0.5
        assert score > 0  # 应该有分数

    def test_medium_count(self) -> None:
        """测试中等数量场景（3-5个相同）"""
        detector = BatchDetector()
        score3 = detector.calculate_batch_score(3, 100)
        assert 0.0 <= score3 <= 1.0
        assert score3 > 0

        score5 = detector.calculate_batch_score(5, 100)
        assert 0.0 <= score5 <= 1.0
        assert score5 > score3  # 5个应该比3个置信度高

    def test_high_count(self) -> None:
        """测试高数量场景（10+个相同）"""
        detector = BatchDetector()
        score = detector.calculate_batch_score(10, 100)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # 10个相同应该有较高分数

    def test_high_ratio(self) -> None:
        """测试高占比场景"""
        detector = BatchDetector()
        # 5个相同，总共10个 -> 占比50%
        score = detector.calculate_batch_score(5, 10)
        assert 0.0 <= score <= 1.0
        # 高占比应该有较高分数
        score_low_ratio = detector.calculate_batch_score(5, 100)
        assert score > score_low_ratio  # 50%占比应该比5%占比分数高

    def test_score_capped_at_one(self) -> None:
        """测试分数不超过1.0"""
        detector = BatchDetector()
        score = detector.calculate_batch_score(100, 100)
        assert score <= 1.0


class TestDetectBatchPatterns:
    """测试 detect_batch_patterns 方法"""

    def _create_record(
        self,
        record_id: str,
        timestamps: list[datetime],
    ) -> EmrTimestampRecord:
        """辅助方法：创建带章节的病历记录"""
        chapters = []
        for i, ts in enumerate(timestamps):
            chapter = EmrChapter(
                chapter_id=f"{record_id}-ch-{i}",
                chapter_name=f"章节{i}",
                chapter_order=i,
                created_time=ts,
                modified_time=ts,
                author_id="doctor-001",
            )
            chapters.append(chapter)

        return EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id=record_id,
            record_type="入院记录",
            chapters=chapters,
        )

    def test_no_records(self) -> None:
        """测试空记录列表"""
        detector = BatchDetector()
        groups = detector.detect_batch_patterns([])
        assert groups == []
        assert detector.get_batch_groups() == []

    def test_no_batch_pattern(self) -> None:
        """测试没有批处理模式（所有时间都不同）"""
        detector = BatchDetector()
        records = [
            self._create_record("R-001", [datetime(2024, 1, 1, 10, 0, 0)]),
            self._create_record("R-002", [datetime(2024, 1, 1, 11, 0, 0)]),
            self._create_record("R-003", [datetime(2024, 1, 1, 12, 0, 0)]),
        ]
        groups = detector.detect_batch_patterns(records)
        assert groups == []

    def test_single_batch_group(self) -> None:
        """测试单个批处理群组"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        records = [
            self._create_record("R-001", [same_time]),
            self._create_record("R-002", [same_time]),
            self._create_record("R-003", [same_time]),
        ]
        groups = detector.detect_batch_patterns(records)
        assert len(groups) == 1
        assert groups[0].identical_count == 3
        assert groups[0].timestamp == same_time

    def test_multiple_batch_groups(self) -> None:
        """测试多个批处理群组"""
        detector = BatchDetector()
        time1 = datetime(2024, 1, 1, 10, 0, 0)
        time2 = datetime(2024, 1, 1, 11, 0, 0)
        records = [
            self._create_record("R-001", [time1]),
            self._create_record("R-002", [time1]),
            self._create_record("R-003", [time2]),
            self._create_record("R-004", [time2]),
        ]
        groups = detector.detect_batch_patterns(records)
        assert len(groups) == 2

    def test_sorted_by_confidence(self) -> None:
        """测试结果按置信度排序"""
        detector = BatchDetector()
        high_conf_time = datetime(2024, 1, 1, 10, 0, 0)
        low_conf_time = datetime(2024, 1, 1, 11, 0, 0)
        records = [
            self._create_record("R-001", [high_conf_time]),
            self._create_record("R-002", [high_conf_time]),
            self._create_record("R-003", [high_conf_time]),
            self._create_record("R-004", [low_conf_time]),
            self._create_record("R-005", [low_conf_time]),
        ]
        groups = detector.detect_batch_patterns(records)
        # 3个相同的置信度应该高于2个相同的
        assert groups[0].identical_count == 3
        assert groups[1].identical_count == 2

    def test_different_chapters_same_record(self) -> None:
        """测试同一病历不同章节不同时间"""
        detector = BatchDetector()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-0",
                    chapter_name="第一章",
                    chapter_order=0,
                    created_time=datetime(2024, 1, 1, 10, 0, 0),
                    modified_time=datetime(2024, 1, 1, 10, 0, 0),
                    author_id="doctor-001",
                ),
                EmrChapter(
                    chapter_id="ch-1",
                    chapter_name="第二章",
                    chapter_order=1,
                    created_time=datetime(2024, 1, 1, 11, 0, 0),
                    modified_time=datetime(2024, 1, 1, 11, 0, 0),
                    author_id="doctor-001",
                ),
            ],
        )
        groups = detector.detect_batch_patterns([record])
        assert groups == []


class TestFilterSignificantBatches:
    """测试 filter_significant_batches 方法"""

    def test_filter_default_threshold(self) -> None:
        """测试默认阈值（>=3）"""
        detector = BatchDetector()

        # 创建一个包含批处理群组的检测器状态
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        detector._batch_groups = [
            BatchGroup(timestamp=same_time, entries=[("R-001", "ch-1")], identical_count=1, confidence=0.3),
            BatchGroup(timestamp=same_time, entries=[("R-002", "ch-1"), ("R-003", "ch-1")], identical_count=2, confidence=0.5),
            BatchGroup(timestamp=same_time, entries=[("R-004", "ch-1"), ("R-005", "ch-1"), ("R-006", "ch-1")], identical_count=3, confidence=0.7),
        ]

        filtered = detector.filter_significant_batches()
        assert len(filtered) == 1
        assert filtered[0].identical_count == 3

    def test_filter_custom_threshold(self) -> None:
        """测试自定义阈值"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        detector._batch_groups = [
            BatchGroup(timestamp=same_time, entries=[("R-001", "ch-1"), ("R-002", "ch-1")], identical_count=2, confidence=0.5),
            BatchGroup(timestamp=same_time, entries=[("R-003", "ch-1"), ("R-004", "ch-1"), ("R-005", "ch-1")], identical_count=3, confidence=0.7),
        ]

        filtered = detector.filter_significant_batches(min_identical_count=3)
        assert len(filtered) == 1
        assert filtered[0].identical_count == 3

        filtered2 = detector.filter_significant_batches(min_identical_count=2)
        assert len(filtered2) == 2


class TestDetect:
    """测试 detect 方法"""

    def _create_record(
        self,
        record_id: str,
        chapter_ids: list[str],
        timestamps: list[datetime],
    ) -> EmrTimestampRecord:
        """辅助方法：创建病历记录"""
        chapters = [
            EmrChapter(
                chapter_id=cid,
                chapter_name=f"章节{i}",
                chapter_order=i,
                created_time=ts,
                modified_time=ts,
                author_id="doctor-001",
            )
            for i, (cid, ts) in enumerate(zip(chapter_ids, timestamps))
        ]
        return EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id=record_id,
            record_type="入院记录",
            chapters=chapters,
        )

    def test_no_anomalies(self) -> None:
        """测试无异常情况"""
        detector = BatchDetector()
        records = [
            self._create_record("R-001", ["ch-1"], [datetime(2024, 1, 1, 10, 0, 0)]),
            self._create_record("R-002", ["ch-1"], [datetime(2024, 1, 1, 11, 0, 0)]),
        ]
        anomalies = detector.detect(records)
        assert anomalies == []

    def test_returns_timestamp_anomalies(self) -> None:
        """测试返回 TimestampAnomaly 对象"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        records = [
            self._create_record("R-001", ["ch-1"], [same_time]),
            self._create_record("R-002", ["ch-1"], [same_time]),
            self._create_record("R-003", ["ch-1"], [same_time]),
        ]
        anomalies = detector.detect(records)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.BATCH_PROCESSING
        assert 3 <= anomalies[0].severity <= 10
        assert "R-001" in anomalies[0].affected_records
        assert "R-002" in anomalies[0].affected_records
        assert "R-003" in anomalies[0].affected_records

    def test_anomaly_severity_scales_with_confidence(self) -> None:
        """测试异常严重程度与置信度成正比"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)

        # 10个相同 -> 高置信度
        records_high = [
            self._create_record(f"R-{i:03d}", ["ch-1"], [same_time])
            for i in range(10)
        ]
        anomalies_high = detector.detect(records_high)

        # 3个相同 -> 低置信度
        records_low = [
            self._create_record(f"R-{i:03d}", ["ch-1"], [same_time])
            for i in range(3)
        ]
        anomalies_low = detector.detect(records_low)

        # 高置信度的严重程度应该更高
        assert anomalies_high[0].severity >= anomalies_low[0].severity

    def test_anomaly_description_contains_details(self) -> None:
        """测试异常描述包含详细信息"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        records = [
            self._create_record("R-001", ["ch-1"], [same_time]),
            self._create_record("R-002", ["ch-1"], [same_time]),
            self._create_record("R-003", ["ch-1"], [same_time]),
        ]
        anomalies = detector.detect(records)
        desc = anomalies[0].description
        assert "3" in desc  # identical_count
        assert "2024-01-01" in desc  # timestamp

    def test_multiple_anomalies_sorted_by_severity(self) -> None:
        """测试多个异常按严重程度排序"""
        detector = BatchDetector()

        # 创建一个高严重程度和一个低严重程度的批处理
        time1 = datetime(2024, 1, 1, 10, 0, 0)
        time2 = datetime(2024, 1, 1, 11, 0, 0)

        records = [
            # 10个相同 -> 高置信度
            self._create_record(f"R-H-{i:03d}", ["ch-1"], [time1])
            for i in range(10)
        ] + [
            # 3个相同 -> 低置信度
            self._create_record(f"R-L-{i:03d}", ["ch-1"], [time2])
            for i in range(3)
        ]

        anomalies = detector.detect(records)
        assert len(anomalies) == 2
        assert anomalies[0].severity >= anomalies[1].severity

    def test_evidence_contains_required_fields(self) -> None:
        """测试证据信息包含必需字段"""
        detector = BatchDetector()
        same_time = datetime(2024, 1, 1, 10, 0, 0)
        records = [
            self._create_record("R-001", ["ch-1"], [same_time]),
            self._create_record("R-002", ["ch-1"], [same_time]),
            self._create_record("R-003", ["ch-1"], [same_time]),
        ]
        anomalies = detector.detect(records)
        evidence = anomalies[0].evidence

        assert "timestamp" in evidence
        assert "identical_count" in evidence
        assert "confidence" in evidence
        assert "affected_chapters" in evidence
        assert evidence["identical_count"] == 3


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_detect_batch_patterns_function(self) -> None:
        """测试 detect_batch_patterns 便捷函数"""
        from detectors.batch_detector import detect_batch_patterns

        same_time = datetime(2024, 1, 1, 10, 0, 0)
        chapters = [
            EmrChapter(
                chapter_id=f"ch-{i}",
                chapter_name=f"章节{i}",
                chapter_order=i,
                created_time=same_time,
                modified_time=same_time,
                author_id="doctor-001",
            )
            for i in range(3)
        ]
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id=f"R-{i:03d}",
                record_type="入院记录",
                chapters=[chapters[i]],
            )
            for i in range(3)
        ]

        anomalies = detect_batch_patterns(records)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.BATCH_PROCESSING