"""
EMR Timestamp Archaeologist - 检测引擎集成测试
测试 DetectionEngine 的完整流程
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

import pytest

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
    create_timestamp_anomaly,
)
from detection_engine import (
    DetectionEngine,
    DetectorResult,
    DetectionReport,
    create_detection_engine,
    run_detection,
)


def create_test_chapter(
    chapter_name: str,
    created_time: datetime,
    author_id: str = "TEST_AUTHOR",
    modified_time: Optional[datetime] = None,
) -> EmrChapter:
    """创建测试用病历章节"""
    return EmrChapter(
        chapter_id=str(uuid.uuid4()),
        chapter_name=chapter_name,
        chapter_order=0,
        created_time=created_time,
        modified_time=modified_time or created_time,
        author_id=author_id,
    )


def create_test_record(
    record_id: str,
    chapters: list[EmrChapter],
    business_time: Optional[datetime] = None,
) -> EmrTimestampRecord:
    """创建测试用病历记录"""
    # 分配连续的章节顺序
    for i, chapter in enumerate(chapters):
        chapter.chapter_order = i
    return EmrTimestampRecord(
        patient_id="P001",
        visit_id="V001",
        record_id=record_id,
        record_type="测试记录",
        chapters=chapters,
        business_time=business_time,
    )


class TestDetectionEngine:
    """检测引擎测试套件"""

    def test_init(self) -> None:
        """测试引擎初始化"""
        engine = DetectionEngine(llm_enabled=True)
        assert engine.llm_enabled is True
        assert len(engine._detectors) == 0
        assert len(engine._all_anomalies) == 0

        engine = DetectionEngine(llm_enabled=False)
        assert engine.llm_enabled is False

    def test_register_detector(self) -> None:
        """测试检测器注册"""
        engine = DetectionEngine()

        def dummy_detector(records: list[EmrTimestampRecord]) -> list[TimestampAnomaly]:
            return []

        engine.register_detector("dummy", dummy_detector)
        assert "dummy" in engine._detectors

    def test_register_detector_instance(self) -> None:
        """测试检测器实例注册"""
        from detectors import BatchDetector

        engine = DetectionEngine()
        detector = BatchDetector()
        engine.register_detector_instance("batch", detector)
        assert "batch" in engine._detectors

    def test_run_all_detectors_empty(self) -> None:
        """测试空数据检测"""
        engine = DetectionEngine()
        anomalies = engine.run_all_detectors([])
        assert anomalies == []

    def test_run_all_detectors_with_records(self) -> None:
        """测试有数据时的检测"""
        engine = create_detection_engine()

        # 创建正常记录
        now = datetime.now()
        chapters = [
            create_test_chapter("入院记录", now - timedelta(hours=24)),
            create_test_chapter("病程记录", now - timedelta(hours=12)),
            create_test_chapter("出院记录", now),
        ]
        record = create_test_record("R001", chapters)
        records = [record]

        anomalies = engine.run_all_detectors(records)
        assert isinstance(anomalies, list)

    def test_run_all_detectors_error_handling(self) -> None:
        """测试检测器错误处理"""

        def bad_detector(records: list[EmrTimestampRecord]) -> list[TimestampAnomaly]:
            raise ValueError("Test error")

        engine = DetectionEngine()
        engine.register_detector("bad", bad_detector)

        now = datetime.now()
        chapters = [create_test_chapter("测试", now)]
        record = create_test_record("R001", chapters)

        anomalies = engine.run_all_detectors([record])

        # 错误不应该导致崩溃，应该返回空列表
        assert isinstance(anomalies, list)

        # 检查错误是否被记录
        result = engine.get_detector_result("bad")
        assert result is not None
        assert result.error is not None
        assert "Test error" in result.error

    def test_calculate_overall_risk_score_empty(self) -> None:
        """测试空数据风险评分"""
        engine = DetectionEngine()
        score = engine.calculate_overall_risk_score([])
        assert score == 0.0

    def test_calculate_overall_risk_score_normal(self) -> None:
        """测试正常风险评分"""
        engine = DetectionEngine()

        # 创建一些异常
        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 5, "测试异常1", ["R001"]
            ),
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 7, "测试异常2", ["R002", "R003"]
            ),
            create_timestamp_anomaly(
                AnomalyType.TIME_CONTRADICTION, 3, "测试异常3", ["R001"]
            ),
        ]

        score = engine.calculate_overall_risk_score(anomalies)
        assert 0 <= score <= 100
        assert score > 0  # 有异常应该有非零分数

    def test_calculate_overall_risk_score_high_severity(self) -> None:
        """测试高严重程度异常的风险评分"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 9, "严重异常", ["R001", "R002", "R003"]
            ),
        ]

        score = engine.calculate_overall_risk_score(anomalies)
        assert score > 50  # 高严重程度应该有较高分数

    def test_get_risk_level(self) -> None:
        """测试风险等级判定"""
        engine = DetectionEngine()

        assert engine.get_risk_level(0) == "极低"
        assert engine.get_risk_level(15) == "低"
        assert engine.get_risk_level(35) == "中等"
        assert engine.get_risk_level(60) == "高"
        assert engine.get_risk_level(80) == "很高"
        assert engine.get_risk_level(100) == "极高"

    def test_rank_anomalies(self) -> None:
        """测试异常排序"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 3, "低严重", ["R001"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 9, "高严重", ["R002"]
            ),
            create_timestamp_anomaly(
                AnomalyType.TIME_CONTRADICTION, 6, "中严重", ["R003"]
            ),
        ]

        ranked = engine.rank_anomalies(anomalies)

        # 第一个应该是最严重的
        assert ranked[0].severity == 9
        assert ranked[1].severity == 6
        assert ranked[2].severity == 3

    def test_rank_anomalies_same_severity(self) -> None:
        """测试相同严重程度时的排序"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 5, "异常1", ["R001"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 5, "异常2", ["R002", "R003"]
            ),
        ]

        ranked = engine.rank_anomalies(anomalies)

        # 相同严重程度时，受影响记录多的应该排前面
        assert len(ranked[0].affected_records) >= len(ranked[1].affected_records)

    def test_deduplicate_anomalies(self) -> None:
        """测试异常去重"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 8, "异常1", ["R001", "R002"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 5, "异常2", ["R001", "R002"]
            ),
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 7, "异常3", ["R003"]
            ),
        ]

        deduped = engine.deduplicate_anomalies(anomalies)

        # BATCH_PROCESSING 类型应该只有一个（最严重的）
        batch_anomalies = [a for a in deduped if a.anomaly_type == AnomalyType.BATCH_PROCESSING]
        assert len(batch_anomalies) == 1
        assert batch_anomalies[0].severity == 8

        # NIGHT_RUSH 类型应该保留
        night_anomalies = [a for a in deduped if a.anomaly_type == AnomalyType.NIGHT_RUSH]
        assert len(night_anomalies) == 1

    def test_deduplicate_anomalies_subset(self) -> None:
        """测试子集情况下的去重"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 6, "大范围", ["R001", "R002", "R003"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 8, "小范围", ["R001"]
            ),
        ]

        deduped = engine.deduplicate_anomalies(anomalies)

        # 应该保留最严重的，而不是大范围的
        assert len(deduped) == 1
        assert deduped[0].severity == 8

    def test_deduplicate_anomalies_no_overlap(self) -> None:
        """测试无重叠时的去重"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 5, "异常1", ["R001"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 6, "异常2", ["R002"]
            ),
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 7, "异常3", ["R003"]
            ),
        ]

        deduped = engine.deduplicate_anomalies(anomalies)

        # 无重叠的异常都应该保留
        assert len(deduped) == 3

    def test_get_summary_stats(self) -> None:
        """测试统计摘要"""
        engine = create_detection_engine()

        now = datetime.now()
        chapters = [
            create_test_chapter("入院记录", now - timedelta(hours=24)),
            create_test_chapter("病程记录", now - timedelta(hours=12)),
            create_test_chapter("出院记录", now),
        ]
        record = create_test_record("R001", chapters)
        records = [record]

        engine.run_all_detectors(records)
        stats = engine.get_summary_stats()

        assert "total_records" in stats
        assert "total_anomalies" in stats
        assert "anomalies_by_type" in stats
        assert "overall_risk_score" in stats
        assert "risk_level" in stats
        assert stats["total_records"] == 1

    def test_generate_report_data(self) -> None:
        """测试报告生成"""
        engine = create_detection_engine()

        now = datetime.now()
        chapters = [
            create_test_chapter("入院记录", now - timedelta(hours=24)),
            create_test_chapter("病程记录", now - timedelta(hours=12)),
        ]
        record = create_test_record("R001", chapters)
        records = [record]

        engine.run_all_detectors(records)
        report = engine.generate_report_data()

        assert isinstance(report, DetectionReport)
        assert report.total_records == 1
        assert "overall_risk_score" in report.to_dict()
        assert "top_anomalies" in report.to_dict()
        assert "detector_results" in report.to_dict()

    def test_get_anomalies_by_type(self) -> None:
        """测试按类型获取异常"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 5, "batch", ["R001"]
            ),
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH, 7, "night", ["R002"]
            ),
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING, 3, "batch2", ["R003"]
            ),
        ]

        batch_anomalies = engine.get_anomalies_by_type(AnomalyType.BATCH_PROCESSING, anomalies)
        assert len(batch_anomalies) == 2

        night_anomalies = engine.get_anomalies_by_type(AnomalyType.NIGHT_RUSH, anomalies)
        assert len(night_anomalies) == 1

    def test_get_anomalies_by_severity_range(self) -> None:
        """测试按严重程度范围获取异常"""
        engine = DetectionEngine()

        anomalies = [
            create_timestamp_anomaly(AnomalyType.BATCH_PROCESSING, 2, "低", ["R001"]),
            create_timestamp_anomaly(AnomalyType.NIGHT_RUSH, 5, "中", ["R002"]),
            create_timestamp_anomaly(AnomalyType.TIME_CONTRADICTION, 8, "高", ["R003"]),
        ]

        mid_anomalies = engine.get_anomalies_by_severity_range(3, 7, anomalies)
        assert len(mid_anomalies) == 1
        assert mid_anomalies[0].severity == 5

        high_anomalies = engine.get_anomalies_by_severity_range(7, 10, anomalies)
        assert len(high_anomalies) == 1
        assert high_anomalies[0].severity == 8

    def test_get_all_detector_results(self) -> None:
        """测试获取所有检测器结果"""
        engine = create_detection_engine()

        now = datetime.now()
        chapters = [create_test_chapter("测试", now)]
        record = create_test_record("R001", chapters)

        engine.run_all_detectors([record])
        results = engine.get_all_detector_results()

        assert len(results) >= 4  # 至少4个内置检测器
        result_names = [r.detector_name for r in results]
        assert "batch" in result_names
        assert "night" in result_names

    def test_get_detector_result(self) -> None:
        """测试获取指定检测器结果"""
        engine = create_detection_engine()

        now = datetime.now()
        chapters = [create_test_chapter("测试", now)]
        record = create_test_record("R001", chapters)

        engine.run_all_detectors([record])
        result = engine.get_detector_result("batch")

        assert result is not None
        assert result.detector_name == "batch"
        assert isinstance(result.anomalies, list)

    def test_get_detector_result_not_found(self) -> None:
        """测试获取不存在的检测器结果"""
        engine = DetectionEngine()
        result = engine.get_detector_result("nonexistent")
        assert result is None


class TestCreateDetectionEngine:
    """便捷函数测试"""

    def test_create_detection_engine(self) -> None:
        """测试创建预配置检测引擎"""
        engine = create_detection_engine()

        assert engine is not None
        assert len(engine._detectors) >= 4  # 至少4个内置检测器

    def test_run_detection(self) -> None:
        """测试便捷检测函数"""
        now = datetime.now()
        chapters = [
            create_test_chapter("入院记录", now - timedelta(hours=24)),
            create_test_chapter("病程记录", now - timedelta(hours=12)),
        ]
        record = create_test_record("R001", chapters)

        report = run_detection([record])

        assert isinstance(report, DetectionReport)
        assert report.total_records == 1


class TestDetectorResult:
    """检测器结果测试"""

    def test_detector_result_to_dict(self) -> None:
        """测试检测器结果序列化"""
        result = DetectorResult(
            detector_name="test",
            anomalies=[],
            execution_time_ms=100.5,
        )

        d = result.to_dict()
        assert d["detector_name"] == "test"
        assert d["execution_time_ms"] == 100.5
        assert d["anomaly_count"] == 0
        assert d["error"] is None


class TestDetectionReport:
    """检测报告测试"""

    def test_detection_report_to_dict(self) -> None:
        """测试检测报告序列化"""
        report = DetectionReport(
            total_records=10,
            total_anomalies=5,
            overall_risk_score=65.5,
            risk_level="高",
        )

        d = report.to_dict()
        assert d["total_records"] == 10
        assert d["total_anomalies"] == 5
        assert d["overall_risk_score"] == 65.5
        assert d["risk_level"] == "高"
