"""
单元测试：EMR 时间戳考古器 - 数据模型
测试 EmrChapter、EmrTimestampRecord、StratumEntry、TimestampAnomaly、AnomalyType
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 添加 src/py 到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    StratumEntry,
    TimestampAnomaly,
    create_emr_chapter,
    create_timestamp_anomaly,
)


class TestEmrChapter:
    """测试 EmrChapter 数据类"""

    def test_create_valid_chapter(self) -> None:
        """测试创建有效章节"""
        now = datetime.now()
        chapter = EmrChapter(
            chapter_id="ch-001",
            chapter_name="病程记录",
            chapter_order=0,
            created_time=now,
            modified_time=now,
            author_id="doctor-001",
        )
        assert chapter.chapter_id == "ch-001"
        assert chapter.chapter_name == "病程记录"
        assert chapter.chapter_order == 0
        assert chapter.created_time == now
        assert chapter.author_id == "doctor-001"

    def test_chapter_empty_id_raises(self) -> None:
        """测试空chapter_id抛出异常"""
        now = datetime.now()
        with pytest.raises(ValueError, match="chapter_id 不能为空"):
            EmrChapter(
                chapter_id="",
                chapter_name="病程记录",
                chapter_order=0,
                created_time=now,
                modified_time=now,
                author_id="doctor-001",
            )

    def test_chapter_empty_name_raises(self) -> None:
        """测试空chapter_name抛出异常"""
        now = datetime.now()
        with pytest.raises(ValueError, match="chapter_name 不能为空"):
            EmrChapter(
                chapter_id="ch-001",
                chapter_name="",
                chapter_order=0,
                created_time=now,
                modified_time=now,
                author_id="doctor-001",
            )

    def test_chapter_negative_order_raises(self) -> None:
        """测试负数章节顺序抛出异常"""
        now = datetime.now()
        with pytest.raises(ValueError, match="chapter_order 必须为非负整数"):
            EmrChapter(
                chapter_id="ch-001",
                chapter_name="病程记录",
                chapter_order=-1,
                created_time=now,
                modified_time=now,
                author_id="doctor-001",
            )

    def test_time_gap_to(self) -> None:
        """测试计算两个章节的时间差"""
        now = datetime.now()
        ch1 = EmrChapter(
            chapter_id="ch-001",
            chapter_name="入院记录",
            chapter_order=0,
            created_time=now,
            modified_time=now,
            author_id="doctor-001",
        )
        ch2 = EmrChapter(
            chapter_id="ch-002",
            chapter_name="病程记录",
            chapter_order=1,
            created_time=now + timedelta(hours=2),
            modified_time=now + timedelta(hours=2),
            author_id="doctor-001",
        )
        assert ch1.time_gap_to(ch2) == 7200.0  # 2小时 = 7200秒


class TestEmrTimestampRecord:
    """测试 EmrTimestampRecord 数据类"""

    def test_create_valid_record(self) -> None:
        """测试创建有效病历记录"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            business_time=now,
        )
        assert record.patient_id == "P-001"
        assert record.visit_id == "V-001"
        assert record.record_id == "R-001"
        assert record.record_type == "入院记录"
        assert record.business_time == now
        assert len(record.chapters) == 0

    def test_record_empty_patient_id_raises(self) -> None:
        """测试空patient_id抛出异常"""
        with pytest.raises(ValueError, match="patient_id 不能为空"):
            EmrTimestampRecord(
                patient_id="",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
            )

    def test_record_chapters_must_be_consecutive(self) -> None:
        """测试章节顺序必须连续"""
        now = datetime.now()
        chapters = [
            EmrChapter(
                chapter_id="ch-001",
                chapter_name="第一章",
                chapter_order=0,
                created_time=now,
                modified_time=now,
                author_id="doctor-001",
            ),
            EmrChapter(
                chapter_id="ch-003",
                chapter_name="第三章",  # 跳过了 order=1
                chapter_order=2,
                created_time=now + timedelta(hours=1),
                modified_time=now + timedelta(hours=1),
                author_id="doctor-001",
            ),
        ]
        with pytest.raises(ValueError, match="章节顺序不连续"):
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=chapters,
            )

    def test_add_chapter_maintains_consecutive_order(self) -> None:
        """测试添加章节后保持顺序连续"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
        )

        ch1 = EmrChapter(
            chapter_id="ch-001",
            chapter_name="第一章",
            chapter_order=0,
            created_time=now,
            modified_time=now,
            author_id="doctor-001",
        )
        ch2 = EmrChapter(
            chapter_id="ch-002",
            chapter_name="第二章",
            chapter_order=1,
            created_time=now + timedelta(hours=1),
            modified_time=now + timedelta(hours=1),
            author_id="doctor-001",
        )

        record.add_chapter(ch1)
        record.add_chapter(ch2)
        assert len(record.chapters) == 2

    def test_add_chapter_breaks_order_raises(self) -> None:
        """测试添加章节破坏连续性时抛出异常"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
        )

        ch1 = EmrChapter(
            chapter_id="ch-001",
            chapter_name="第一章",
            chapter_order=0,
            created_time=now,
            modified_time=now,
            author_id="doctor-001",
        )
        ch3 = EmrChapter(
            chapter_id="ch-003",
            chapter_name="第三章",
            chapter_order=2,
            created_time=now + timedelta(hours=2),
            modified_time=now + timedelta(hours=2),
            author_id="doctor-001",
        )

        record.add_chapter(ch1)
        with pytest.raises(ValueError, match="添加章节后章节顺序不连续"):
            record.add_chapter(ch3)

    def test_get_earliest_chapter(self) -> None:
        """测试获取最早创建的章节"""
        now = datetime.now()
        ch1 = EmrChapter(
            chapter_id="ch-001",
            chapter_name="第一章",
            chapter_order=0,
            created_time=now + timedelta(hours=2),
            modified_time=now + timedelta(hours=2),
            author_id="doctor-001",
        )
        ch2 = EmrChapter(
            chapter_id="ch-002",
            chapter_name="第二章",
            chapter_order=1,
            created_time=now,
            modified_time=now,
            author_id="doctor-001",
        )
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[ch1, ch2],
        )
        earliest = record.get_earliest_chapter()
        assert earliest is not None
        assert earliest.chapter_id == "ch-002"

    def test_get_latest_chapter(self) -> None:
        """测试获取最晚修改的章节"""
        now = datetime.now()
        ch1 = EmrChapter(
            chapter_id="ch-001",
            chapter_name="第一章",
            chapter_order=0,
            created_time=now,
            modified_time=now + timedelta(hours=1),
            author_id="doctor-001",
        )
        ch2 = EmrChapter(
            chapter_id="ch-002",
            chapter_name="第二章",
            chapter_order=1,
            created_time=now,
            modified_time=now + timedelta(hours=2),
            author_id="doctor-001",
        )
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[ch1, ch2],
        )
        latest = record.get_latest_chapter()
        assert latest is not None
        assert latest.chapter_id == "ch-002"


class TestStratumEntry:
    """测试 StratumEntry 数据类"""

    def test_create_valid_stratum_entry(self) -> None:
        """测试创建有效地层条目"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=1,
            anomaly_flags=["BATCH_PROCESSING"],
        )
        assert entry.record_id == "R-001"
        assert entry.chapter_id == "ch-001"
        assert entry.timestamp == now
        assert entry.stratum_layer == 1
        assert "BATCH_PROCESSING" in entry.anomaly_flags

    def test_stratum_empty_record_id_raises(self) -> None:
        """测试空record_id抛出异常"""
        now = datetime.now()
        with pytest.raises(ValueError, match="record_id 不能为空"):
            StratumEntry(
                record_id="",
                chapter_id="ch-001",
                timestamp=now,
                stratum_layer=1,
            )

    def test_stratum_negative_layer_raises(self) -> None:
        """测试负数地层序号抛出异常"""
        now = datetime.now()
        with pytest.raises(ValueError, match="stratum_layer 必须为非负整数"):
            StratumEntry(
                record_id="R-001",
                chapter_id="ch-001",
                timestamp=now,
                stratum_layer=-1,
            )

    def test_add_anomaly_flag(self) -> None:
        """测试添加异常标记"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=1,
        )
        entry.add_anomaly_flag("NIGHT_RUSH")
        assert entry.has_anomaly_flag("NIGHT_RUSH")
        # 添加重复标记不生效
        entry.add_anomaly_flag("NIGHT_RUSH")
        assert len(entry.anomaly_flags) == 1


class TestTimestampAnomaly:
    """测试 TimestampAnomaly 数据类"""

    def test_create_valid_anomaly(self) -> None:
        """测试创建有效异常"""
        anomaly = TimestampAnomaly(
            anomaly_type=AnomalyType.BATCH_PROCESSING,
            severity=7,
            description="检测到批处理痕迹",
            affected_records=["R-001", "R-002"],
            evidence={"identical_count": 5, "time_window": "2024-01-01 10:00:00"},
        )
        assert anomaly.anomaly_type == AnomalyType.BATCH_PROCESSING
        assert anomaly.severity == 7
        assert len(anomaly.affected_records) == 2

    def test_anomaly_invalid_type_raises(self) -> None:
        """测试无效异常类型抛出异常"""
        with pytest.raises(ValueError, match="anomaly_type 必须是 AnomalyType"):
            TimestampAnomaly(
                anomaly_type="batch_processing",  # 错误：应该是枚举类型
                severity=7,
                description="测试",
            )

    def test_anomaly_invalid_severity_raises(self) -> None:
        """测试无效严重程度抛出异常"""
        with pytest.raises(ValueError, match="severity 必须在 0-10 范围内"):
            TimestampAnomaly(
                anomaly_type=AnomalyType.BATCH_PROCESSING,
                severity=15,  # 超出范围
                description="测试",
            )

    def test_anomaly_severity_label(self) -> None:
        """测试严重程度标签"""
        test_cases = [
            (9, "严重"),
            (7, "中等"),
            (4, "轻微"),
            (1, "提示"),
        ]
        for severity, expected_label in test_cases:
            anomaly = TimestampAnomaly(
                anomaly_type=AnomalyType.BATCH_PROCESSING,
                severity=severity,
                description="测试",
            )
            assert anomaly.severity_label == expected_label

    def test_anomaly_to_dict(self) -> None:
        """测试转换为字典"""
        anomaly = TimestampAnomaly(
            anomaly_type=AnomalyType.NIGHT_RUSH,
            severity=6,
            description="夜间突击补写",
            affected_records=["R-001"],
            evidence={"night_hour": 3},
        )
        d = anomaly.to_dict()
        assert d["anomaly_type"] == "night_rush"
        assert d["severity"] == 6
        assert d["severity_label"] == "中等"
        assert d["description"] == "夜间突击补写"
        assert "R-001" in d["affected_records"]


class TestAnomalyTypeEnum:
    """测试 AnomalyType 枚举"""

    def test_all_anomaly_types_exist(self) -> None:
        """测试所有异常类型都存在"""
        expected_types = [
            "BATCH_PROCESSING",
            "NIGHT_RUSH",
            "TIME_CONTRADICTION",
            "SUSPICIOUS_SEQUENCE",
            "ANCHOR_VIOLATION",
        ]
        actual_types = [t.name for t in AnomalyType]
        for expected in expected_types:
            assert expected in actual_types

    def test_anomaly_type_values(self) -> None:
        """测试异常类型值"""
        assert AnomalyType.BATCH_PROCESSING.value == "batch_processing"
        assert AnomalyType.NIGHT_RUSH.value == "night_rush"
        assert AnomalyType.TIME_CONTRADICTION.value == "time_contradiction"
        assert AnomalyType.SUSPICIOUS_SEQUENCE.value == "suspicious_sequence"
        assert AnomalyType.ANCHOR_VIOLATION.value == "anchor_violation"


class TestConvenienceConstructors:
    """测试便捷构造函数"""

    def test_create_emr_chapter(self) -> None:
        """测试便捷创建章节"""
        now = datetime.now()
        chapter = create_emr_chapter(
            chapter_name="手术记录",
            created_time=now,
            author_id="surgeon-001",
            modified_time=now + timedelta(hours=1),
        )
        assert chapter.chapter_name == "手术记录"
        assert chapter.author_id == "surgeon-001"
        assert chapter.modified_time == now + timedelta(hours=1)
        # 自动生成的 ID 应该是 UUID 格式
        assert len(chapter.chapter_id) == 36

    def test_create_timestamp_anomaly(self) -> None:
        """测试便捷创建异常"""
        anomaly = create_timestamp_anomaly(
            anomaly_type=AnomalyType.BATCH_PROCESSING,
            severity=8,
            description="批处理痕迹",
            affected_records=["R-001"],
            evidence={"count": 10},
        )
        assert anomaly.anomaly_type == AnomalyType.BATCH_PROCESSING
        assert anomaly.severity == 8
        assert len(anomaly.affected_records) == 1
