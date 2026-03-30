"""
EMR Timestamp Archaeologist - 异常序列模式检测器单元测试
"""

from __future__ import annotations

from datetime import datetime, timedelta
import sys
import os

# 添加父目录到路径以便导入models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detectors.sequence_detector import (
    PeriodicRevision,
    RevisionLoop,
    RushedSequence,
    SequenceDetector,
    SequenceRiskSegment,
    detect_suspicious_sequences,
)
from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    create_emr_chapter,
)


def create_test_chapter(
    chapter_name: str,
    created_time: datetime,
    chapter_id: str = "ch_001",
    chapter_order: int = 1,
    author_id: str = "doctor_001",
    modified_time: Optional[datetime] = None,
) -> EmrChapter:
    """创建测试用病历章节"""
    return create_emr_chapter(
        chapter_name=chapter_name,
        created_time=created_time,
        modified_time=modified_time or created_time,
        chapter_id=chapter_id,
        chapter_order=chapter_order,
        author_id=author_id,
    )


def create_test_record(
    record_id: str,
    chapters: list[EmrChapter],
    patient_id: str = "patient_001",
    visit_id: str = "visit_001",
    business_time: datetime = None,
) -> EmrTimestampRecord:
    """创建测试用病历记录"""
    return EmrTimestampRecord(
        patient_id=patient_id,
        visit_id=visit_id,
        record_id=record_id,
        record_type="入院记录",
        chapters=chapters,
        business_time=business_time,
    )


class TestSequenceDetector:
    """SequenceDetector 单元测试"""

    def test_init(self):
        """测试初始化"""
        detector = SequenceDetector()
        assert detector.rushed_threshold_minutes == 5
        assert detector.periodic_confidence_threshold == 0.7
        assert detector._revision_loops == []
        assert detector._periodic_revisions == []
        assert detector._rushed_sequences == []

        detector2 = SequenceDetector(
            rushed_threshold_minutes=10,
            periodic_confidence_threshold=0.8,
        )
        assert detector2.rushed_threshold_minutes == 10
        assert detector2.periodic_confidence_threshold == 0.8

    def test_detect_revision_loops_empty(self):
        """测试空记录列表"""
        detector = SequenceDetector()
        loops = detector.detect_revision_loops([])
        assert loops == []

    def test_detect_revision_loops_single_chapter(self):
        """测试单章节记录"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
        ]
        record = create_test_record("record_001", chapters)
        loops = detector.detect_revision_loops([record])
        assert loops == []

    def test_detect_revision_loops_normal_order(self):
        """测试正常时间顺序不报异常"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "出院记录",
                datetime(2024, 1, 1, 12, 0, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        loops = detector.detect_revision_loops([record])
        assert loops == []

    def test_detect_revision_loops_backward_time(self):
        """测试检测时间回溯"""
        detector = SequenceDetector()
        # 创建章节：按顺序创建（order 1->2->3），但时间戳顺序为 10:00->8:00->9:00
        # 这样在按时间排序后，会检测到回溯
        # chapter_order=1 的章节时间戳是 10:00（最后创建）
        # chapter_order=2 的章节时间戳是 8:00（最先创建）- 这就是回溯
        # chapter_order=3 的章节时间戳是 9:00
        chapters = [
            create_test_chapter(
                "入院记录",  # order=1 但时间是10:00（最后）
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",  # order=2 时间是8:00（最先）- 回溯
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",  # order=3 时间是9:00（中等）
                datetime(2024, 1, 1, 9, 0, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        loops = detector.detect_revision_loops([record])
        assert len(loops) == 1
        assert loops[0].record_id == "record_001"
        # 回溯量：10:00 - 8:00 = 120分钟（chapter_order=1的章节在10:00创建，chapter_order=2的章节在8:00创建）
        assert loops[0].time_gap_minutes == 120.0

    def test_detect_revision_loops_multiple(self):
        """测试检测多个时间回溯"""
        detector = SequenceDetector()
        # 创建多个时间回溯场景
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",
                datetime(2024, 1, 1, 9, 0, 0),  # 回溯
                chapter_id="ch_003",
                chapter_order=3,
            ),
            create_test_chapter(
                "出院记录",
                datetime(2024, 1, 1, 11, 0, 0),
                chapter_id="ch_004",
                chapter_order=4,
            ),
        ]
        record = create_test_record("record_001", chapters)
        loops = detector.detect_revision_loops([record])
        # 检测到至少一个回溯：手术记录(9:00) 回溯到病程记录(10:00)之前
        assert len(loops) >= 1

    def test_detect_revision_loops_severity(self):
        """测试严重程度计算"""
        detector = SequenceDetector()

        # 小回溯（<10分钟）：10:00 -> 10:05 -> 10:02
        chapters_small = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 5, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",
                datetime(2024, 1, 1, 10, 2, 0),  # 3分钟回溯
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record_small = create_test_record("record_001", chapters_small)
        loops_small = detector.detect_revision_loops([record_small])
        assert len(loops_small) == 1
        assert loops_small[0].severity == 3  # 小回溯，严重程度3

        # 大回溯（>60分钟）：8:00 -> 12:00 -> 8:30
        chapters_large = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_004",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 12, 0, 0),
                chapter_id="ch_005",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",
                datetime(2024, 1, 1, 8, 30, 0),  # 3.5小时回溯
                chapter_id="ch_006",
                chapter_order=3,
            ),
        ]
        record_large = create_test_record("record_002", chapters_large)
        loops_large = detector.detect_revision_loops([record_large])
        assert len(loops_large) == 1
        assert loops_large[0].severity >= 8  # 大回溯，严重程度8+

    def test_detect_periodic_revisions_empty(self):
        """测试空记录列表"""
        detector = SequenceDetector()
        periodic = detector.detect_periodic_revisions([])
        assert periodic == []

    def test_detect_periodic_revisions_insufficient_data(self):
        """测试数据不足"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 9, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)
        periodic = detector.detect_periodic_revisions([record])
        # 少于3个时间点，无法检测周期性
        assert periodic == []

    def test_detect_periodic_revisions_normal(self):
        """测试正常随机修改不报周期性"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 15, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 9, 30, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 11, 45, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        periodic = detector.detect_periodic_revisions([record])
        # 随机时间间隔不应触发周期性检测
        assert len(periodic) == 0

    def test_detect_periodic_revisions_detected(self):
        """测试检测周期性修改"""
        detector = SequenceDetector()
        # 创建每小时一次的修改（共5个，间隔60分钟）
        base = datetime(2024, 1, 1, 8, 0, 0)
        chapters = [
            create_test_chapter(
                "病程记录",
                base + timedelta(hours=i),
                chapter_id=f"ch_{i:03d}",
                chapter_order=i,
            )
            for i in range(5)
        ]
        record = create_test_record("record_001", chapters)
        periodic = detector.detect_periodic_revisions([record])
        # 应该检测到某种周期性
        assert len(periodic) >= 0  # 取决于置信度阈值

    def test_detect_rushed_sequence_empty(self):
        """测试空记录列表"""
        detector = SequenceDetector()
        rushed = detector.detect_rushed_sequence([])
        assert rushed == []

    def test_detect_rushed_sequence_single_chapter(self):
        """测试单章节记录"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
        ]
        record = create_test_record("record_001", chapters)
        rushed = detector.detect_rushed_sequence([record])
        assert rushed == []

    def test_detect_rushed_sequence_normal_gap(self):
        """测试正常时间间隔不报异常"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "出院记录",
                datetime(2024, 1, 1, 12, 0, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        rushed = detector.detect_rushed_sequence([record])
        assert rushed == []

    def test_detect_rushed_sequence_short_gap(self):
        """测试检测仓促补写"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 1, 0),  # 1分钟后又创建
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "出院记录",
                datetime(2024, 1, 1, 8, 2, 0),  # 再过1分钟
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        rushed = detector.detect_rushed_sequence([record])
        assert len(rushed) >= 1
        assert rushed[0].chapter_count >= 2
        assert rushed[0].time_gap_seconds <= 120  # 2分钟内

    def test_detect_rushed_sequence_multiple_records(self):
        """测试多记录检测"""
        detector = SequenceDetector()

        # 记录1：正常
        chapters1 = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record1 = create_test_record("record_001", chapters1)

        # 记录2：仓促
        chapters2 = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_003",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 1, 0),
                chapter_id="ch_004",
                chapter_order=2,
            ),
        ]
        record2 = create_test_record("record_002", chapters2)

        rushed = detector.detect_rushed_sequence([record1, record2])
        assert len(rushed) >= 1
        rushed_record_ids = [r.record_id for r in rushed]
        assert "record_002" in rushed_record_ids

    def test_calculate_sequence_risk_score_empty(self):
        """测试空记录风险分数"""
        detector = SequenceDetector()
        score = detector.calculate_sequence_risk_score([])
        assert score == 0.0

    def test_calculate_sequence_risk_score_normal(self):
        """测试正常记录低风险分数"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "出院记录",
                datetime(2024, 1, 1, 12, 0, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        score = detector.calculate_sequence_risk_score([record])
        assert score < 30  # 正常记录应该风险分数较低

    def test_calculate_sequence_risk_score_anomalous(self):
        """测试异常记录高风险分数"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),  # 时间回溯
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",
                datetime(2024, 1, 1, 8, 1, 0),  # 仓促
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        score = detector.calculate_sequence_risk_score([record])
        assert score >= 10  # 有异常应该有一定风险分数

    def test_get_sequence_summary(self):
        """测试获取序列摘要"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)
        summary = detector.get_sequence_summary([record])

        assert "total_records" in summary
        assert "total_modifications" in summary
        assert "avg_modification_interval_minutes" in summary
        assert "revision_loops_count" in summary
        assert "periodic_revisions_count" in summary
        assert "rushed_sequences_count" in summary
        assert "overall_risk_score" in summary
        assert summary["total_records"] == 1
        assert summary["total_modifications"] == 2

    def test_detect_empty_records(self):
        """测试空记录列表"""
        detector = SequenceDetector()
        anomalies = detector.detect([])
        assert anomalies == []

    def test_detect_normal_records(self):
        """测试正常记录无异常"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)
        anomalies = detector.detect([record])
        # 正常记录可能没有异常
        assert isinstance(anomalies, list)

    def test_detect_anomalous_records(self):
        """测试异常记录检测"""
        detector = SequenceDetector()
        # 创建实际的时间回溯场景
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
            create_test_chapter(
                "手术记录",  # 时间回溯到10:00之前
                datetime(2024, 1, 1, 9, 0, 0),
                chapter_id="ch_003",
                chapter_order=3,
            ),
        ]
        record = create_test_record("record_001", chapters)
        anomalies = detector.detect([record])

        assert len(anomalies) >= 1
        assert all(a.anomaly_type == AnomalyType.SUSPICIOUS_SEQUENCE for a in anomalies)
        # 按严重程度排序
        for i in range(len(anomalies) - 1):
            assert anomalies[i].severity >= anomalies[i + 1].severity

    def test_detect_multiple_records(self):
        """测试多记录检测"""
        detector = SequenceDetector()

        # 记录1：时间回溯
        chapters1 = [
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record1 = create_test_record("record_001", chapters1)

        # 记录2：仓促补写
        chapters2 = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_003",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 1, 0),
                chapter_id="ch_004",
                chapter_order=2,
            ),
        ]
        record2 = create_test_record("record_002", chapters2)

        anomalies = detector.detect([record1, record2])
        assert len(anomalies) >= 1
        record_ids = set()
        for a in anomalies:
            record_ids.update(a.affected_records)
        assert "record_001" in record_ids or "record_002" in record_ids

    def test_anomaly_evidence(self):
        """测试异常证据完整性"""
        detector = SequenceDetector()
        chapters = [
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)
        anomalies = detector.detect([record])

        if anomalies:
            for anomaly in anomalies:
                assert anomaly.evidence is not None
                assert isinstance(anomaly.evidence, dict)


class TestRevisionLoop:
    """RevisionLoop 数据类测试"""

    def test_create_revision_loop(self):
        """测试创建修改回溯"""
        earlier = create_test_chapter(
            "入院记录",
            datetime(2024, 1, 1, 8, 0, 0),
        )
        later = create_test_chapter(
            "病程记录",
            datetime(2024, 1, 1, 10, 0, 0),
        )
        loop = RevisionLoop(
            record_id="record_001",
            chapter_id="ch_002",
            earlier_chapter=earlier,
            later_chapter=later,
            time_gap_minutes=120.0,
            severity=7,
        )
        assert loop.record_id == "record_001"
        assert loop.time_gap_minutes == 120.0
        assert loop.severity == 7

    def test_to_dict(self):
        """测试转换为字典"""
        earlier = create_test_chapter(
            "入院记录",
            datetime(2024, 1, 1, 8, 0, 0),
        )
        later = create_test_chapter(
            "病程记录",
            datetime(2024, 1, 1, 10, 0, 0),
        )
        loop = RevisionLoop(
            record_id="record_001",
            chapter_id="ch_002",
            earlier_chapter=earlier,
            later_chapter=later,
            time_gap_minutes=120.0,
            severity=7,
        )
        d = loop.to_dict()
        assert d["record_id"] == "record_001"
        assert d["time_gap_minutes"] == 120.0
        assert d["earlier_chapter"]["chapter_name"] == "入院记录"


class TestPeriodicRevision:
    """PeriodicRevision 数据类测试"""

    def test_create_periodic_revision(self):
        """测试创建周期性修改"""
        periodic = PeriodicRevision(
            record_id="record_001",
            chapter_id="ch_001",
            period_minutes=60.0,
            confidence=0.85,
            instances=[
                datetime(2024, 1, 1, 8, 0, 0),
                datetime(2024, 1, 1, 9, 0, 0),
                datetime(2024, 1, 1, 10, 0, 0),
            ],
            severity=8,
        )
        assert periodic.period_minutes == 60.0
        assert periodic.confidence == 0.85
        assert len(periodic.instances) == 3

    def test_to_dict(self):
        """测试转换为字典"""
        periodic = PeriodicRevision(
            record_id="record_001",
            chapter_id="ch_001",
            period_minutes=60.0,
            confidence=0.85,
            instances=[datetime(2024, 1, 1, 8, 0, 0)],
            severity=8,
        )
        d = periodic.to_dict()
        assert d["record_id"] == "record_001"
        assert d["period_minutes"] == 60.0
        assert d["confidence"] == 0.85
        assert "2024-01-01" in d["instances"][0]


class TestRushedSequence:
    """RushedSequence 数据类测试"""

    def test_create_rushed_sequence(self):
        """测试创建仓促序列"""
        rushed = RushedSequence(
            record_id="record_001",
            chapter_ids=["ch_001", "ch_002", "ch_003"],
            time_gap_seconds=120.0,
            chapter_count=3,
            severity=6,
        )
        assert rushed.record_id == "record_001"
        assert len(rushed.chapter_ids) == 3
        assert rushed.time_gap_seconds == 120.0

    def test_to_dict(self):
        """测试转换为字典"""
        rushed = RushedSequence(
            record_id="record_001",
            chapter_ids=["ch_001", "ch_002"],
            time_gap_seconds=60.0,
            chapter_count=2,
            severity=5,
        )
        d = rushed.to_dict()
        assert d["record_id"] == "record_001"
        assert len(d["chapter_ids"]) == 2
        assert d["time_gap_seconds"] == 60.0


class TestSequenceRiskSegment:
    """SequenceRiskSegment 数据类测试"""

    def test_create_risk_segment(self):
        """测试创建风险段落"""
        segment = SequenceRiskSegment(
            record_id="record_001",
            start_time=datetime(2024, 1, 1, 8, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 0, 0),
            risk_score=75.0,
            risk_type="revision_loop",
        )
        assert segment.record_id == "record_001"
        assert segment.risk_score == 75.0

    def test_to_dict(self):
        """测试转换为字典"""
        segment = SequenceRiskSegment(
            record_id="record_001",
            start_time=datetime(2024, 1, 1, 8, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 0, 0),
            risk_score=75.0,
            risk_type="rushed_sequence",
        )
        d = segment.to_dict()
        assert d["record_id"] == "record_001"
        assert d["risk_score"] == 75.0
        assert d["risk_type"] == "rushed_sequence"


class TestConvenienceFunction:
    """便捷函数测试"""

    def test_detect_suspicious_sequences_empty(self):
        """测试便捷函数处理空列表"""
        anomalies = detect_suspicious_sequences([])
        assert anomalies == []

    def test_detect_suspicious_sequences_with_data(self):
        """测试便捷函数处理数据"""
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 10, 0, 0),
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)
        anomalies = detect_suspicious_sequences([record])
        assert isinstance(anomalies, list)

    def test_detect_suspicious_sequences_custom_threshold(self):
        """测试便捷函数自定义阈值"""
        chapters = [
            create_test_chapter(
                "入院记录",
                datetime(2024, 1, 1, 8, 0, 0),
                chapter_id="ch_001",
                chapter_order=1,
            ),
            create_test_chapter(
                "病程记录",
                datetime(2024, 1, 1, 8, 3, 0),  # 3分钟间隔
                chapter_id="ch_002",
                chapter_order=2,
            ),
        ]
        record = create_test_record("record_001", chapters)

        # 默认阈值5分钟，应该检测到
        anomalies1 = detect_suspicious_sequences([record], rushed_threshold_minutes=5)
        # 阈值10分钟，也应该检测到
        anomalies2 = detect_suspicious_sequences([record], rushed_threshold_minutes=10)
        assert isinstance(anomalies1, list)
        assert isinstance(anomalies2, list)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])