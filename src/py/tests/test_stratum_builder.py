"""
单元测试：EMR 时间戳考古器 - 时序地层图构建器
测试 StratumBuilder、StratumMap、StratumLayer、AnchorLine
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 添加 src/py 到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import EmrChapter, EmrTimestampRecord, StratumEntry
from stratum_builder import (
    AnchorLine,
    StratumBuilder,
    StratumLayer,
    StratumMap,
    build_stratum_map,
    export_visualization_json,
)


class TestStratumEntry:
    """测试 StratumEntry 相关功能（在 stratum_builder 上下文中）"""

    def test_create_stratum_entry(self) -> None:
        """测试创建有效地层条目"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
            anomaly_flags=["NIGHT_RUSH"],
        )
        assert entry.record_id == "R-001"
        assert entry.stratum_layer == 0
        assert "NIGHT_RUSH" in entry.anomaly_flags


class TestAnchorLine:
    """测试 AnchorLine 数据类"""

    def test_create_anchor_line(self) -> None:
        """测试创建锚点"""
        now = datetime.now()
        anchor = AnchorLine(
            anchor_type="手术开始",
            anchor_time=now,
            record_id="R-001",
            label="手术",
        )
        assert anchor.anchor_type == "手术开始"
        assert anchor.anchor_time == now
        assert anchor.label == "手术"

    def test_anchor_default_label(self) -> None:
        """测试锚点默认标签"""
        now = datetime.now()
        anchor = AnchorLine(
            anchor_type="入院时间",
            anchor_time=now,
            record_id="R-001",
        )
        assert anchor.label == "入院时间"


class TestStratumLayer:
    """测试 StratumLayer 数据类"""

    def test_create_stratum_layer(self) -> None:
        """测试创建地层"""
        layer = StratumLayer(layer_number=0)
        assert layer.layer_number == 0
        assert len(layer.entries) == 0

    def test_add_entry(self) -> None:
        """测试添加地层条目"""
        layer = StratumLayer(layer_number=1)
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=1,
        )
        layer.add_entry(entry)
        assert len(layer.entries) == 1

    def test_get_time_range(self) -> None:
        """测试获取时间范围"""
        layer = StratumLayer(layer_number=0)
        now = datetime.now()
        entry1 = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
        )
        entry2 = StratumEntry(
            record_id="R-002",
            chapter_id="ch-002",
            timestamp=now + timedelta(hours=1),
            stratum_layer=0,
        )
        layer.add_entry(entry1)
        layer.add_entry(entry2)

        start, end = layer.get_time_range()
        assert start == now
        assert end == now + timedelta(hours=1)

    def test_get_time_range_empty(self) -> None:
        """测试空地层的时间范围"""
        layer = StratumLayer(layer_number=0)
        start, end = layer.get_time_range()
        assert start is None
        assert end is None


class TestStratumMap:
    """测试 StratumMap 数据类"""

    def test_create_empty_stratum_map(self) -> None:
        """测试创建空地层图"""
        stratum_map = StratumMap()
        assert stratum_map.record_count == 0
        assert stratum_map.chapter_count == 0
        assert len(stratum_map.layers) == 0

    def test_stratum_map_to_dict(self) -> None:
        """测试地层图转字典"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
        )
        layer = StratumLayer(layer_number=0)
        layer.add_entry(entry)

        stratum_map = StratumMap(
            records={},
            all_timestamps=[now],
            layers=[layer],
            record_count=0,
            chapter_count=1,
        )

        d = stratum_map.to_dict()
        assert d["record_count"] == 0
        assert d["chapter_count"] == 1
        assert len(d["layers"]) == 1
        assert len(d["all_timestamps"]) == 1

    def test_stratum_map_to_json(self) -> None:
        """测试地层图转 JSON"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
        )
        layer = StratumLayer(layer_number=0)
        layer.add_entry(entry)

        stratum_map = StratumMap(
            records={},
            all_timestamps=[now],
            layers=[layer],
            record_count=1,
            chapter_count=1,
        )

        json_str = stratum_map.to_json()
        data = json.loads(json_str)
        assert data["record_count"] == 1
        assert data["chapter_count"] == 1

    def test_to_visualization_data(self) -> None:
        """测试生成可视化数据"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
        )
        layer = StratumLayer(layer_number=0)
        layer.add_entry(entry)
        layer.start_time = now
        layer.end_time = now

        stratum_map = StratumMap(
            records={"R-001": record},
            all_timestamps=[now],
            layers=[layer],
            record_count=1,
            chapter_count=1,
        )

        viz_data = stratum_map.to_visualization_data()
        assert "meta" in viz_data
        assert "time_scale" in viz_data
        assert "chapter_layers" in viz_data
        assert "anchor_lines" in viz_data
        assert viz_data["meta"]["record_count"] == 1


class TestStratumBuilder:
    """测试 StratumBuilder 构建器"""

    def test_build_empty_records(self) -> None:
        """测试构建空记录"""
        builder = StratumBuilder()
        stratum_map = builder.build([])
        assert stratum_map.record_count == 0
        assert stratum_map.chapter_count == 0

    def test_build_single_record(self) -> None:
        """测试构建单条记录"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        builder = StratumBuilder()
        stratum_map = builder.build([record])

        assert stratum_map.record_count == 1
        assert stratum_map.chapter_count == 1
        assert len(stratum_map.layers) == 1
        assert stratum_map.layers[0].layer_number == 0
        assert len(stratum_map.all_timestamps) == 1

    def test_build_multiple_records(self) -> None:
        """测试构建多条记录"""
        now = datetime.now()
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=[
                    EmrChapter(
                        chapter_id="ch-001",
                        chapter_name="入院记录",
                        chapter_order=0,
                        created_time=now,
                        modified_time=now,
                        author_id="doctor-001",
                    ),
                ],
            ),
            EmrTimestampRecord(
                patient_id="P-002",
                visit_id="V-002",
                record_id="R-002",
                record_type="入院记录",
                chapters=[
                    EmrChapter(
                        chapter_id="ch-002",
                        chapter_name="入院记录",
                        chapter_order=0,
                        created_time=now + timedelta(hours=1),
                        modified_time=now + timedelta(hours=1),
                        author_id="doctor-002",
                    ),
                ],
            ),
        ]

        builder = StratumBuilder()
        stratum_map = builder.build(records)

        assert stratum_map.record_count == 2
        assert stratum_map.chapter_count == 2
        assert len(stratum_map.layers) == 2  # 两个不同时间点

    def test_assign_stratum_layers(self) -> None:
        """测试地层序号分配"""
        now = datetime.now()
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=[
                    EmrChapter(
                        chapter_id="ch-001",
                        chapter_name="第一章",
                        chapter_order=0,
                        created_time=now,
                        modified_time=now,
                        author_id="doctor-001",
                    ),
                    EmrChapter(
                        chapter_id="ch-002",
                        chapter_name="第二章",
                        chapter_order=1,
                        created_time=now + timedelta(hours=1),
                        modified_time=now + timedelta(hours=1),
                        author_id="doctor-001",
                    ),
                ],
            ),
        ]

        builder = StratumBuilder()
        stratum_map = builder.build(records)

        # 应该有两个地层（两个不同的时间戳）
        assert len(stratum_map.layers) == 2

        # 检查所有条目都被分配了正确的信息
        all_entries = []
        for layer in stratum_map.layers:
            all_entries.extend(layer.entries)
        assert len(all_entries) >= 2  # 至少有两个条目

    def test_add_anchor_line(self) -> None:
        """测试添加锚点"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        builder = StratumBuilder()
        stratum_map = builder.build([record])

        # 在构建后添加锚点
        anchor_time = now - timedelta(hours=2)
        builder.add_anchor_line(
            anchor_type="手术开始",
            anchor_time=anchor_time,
            record_id="R-001",
            label="阑尾切除术",
        )

        assert len(stratum_map.anchor_lines) == 1
        assert stratum_map.anchor_lines[0].anchor_type == "手术开始"
        assert stratum_map.anchor_lines[0].label == "阑尾切除术"

    def test_add_anchor_without_build_raises(self) -> None:
        """测试未调用 build 直接添加锚点会抛出异常"""
        builder = StratumBuilder()
        with pytest.raises(ValueError, match="必须先调用 build"):
            builder.add_anchor_line(
                anchor_type="手术开始",
                anchor_time=datetime.now(),
                record_id="R-001",
            )

    def test_get_stratum_map(self) -> None:
        """测试获取地层图"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        builder = StratumBuilder()
        result_map = builder.build([record])
        retrieved_map = builder.get_stratum_map()

        assert retrieved_map is result_map
        assert retrieved_map is not None
        assert retrieved_map.record_count == 1

    def test_multiple_chapters_same_time(self) -> None:
        """测试同一时间创建多个章节"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="第一章",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
                EmrChapter(
                    chapter_id="ch-002",
                    chapter_name="第二章",
                    chapter_order=1,
                    created_time=now,  # 同一时间
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        builder = StratumBuilder()
        stratum_map = builder.build([record])

        # 同一时间的章节应该在同一地层
        assert len(stratum_map.layers) == 1
        assert len(stratum_map.layers[0].entries) == 2


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_build_stratum_map(self) -> None:
        """测试便捷构建函数"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        stratum_map = build_stratum_map([record])
        assert stratum_map.record_count == 1

    def test_export_visualization_json(self, tmp_path: Path) -> None:
        """测试导出可视化 JSON"""
        now = datetime.now()
        record = EmrTimestampRecord(
            patient_id="P-001",
            visit_id="V-001",
            record_id="R-001",
            record_type="入院记录",
            chapters=[
                EmrChapter(
                    chapter_id="ch-001",
                    chapter_name="入院记录",
                    chapter_order=0,
                    created_time=now,
                    modified_time=now,
                    author_id="doctor-001",
                ),
            ],
        )

        stratum_map = build_stratum_map([record])
        output_path = tmp_path / "viz_data.json"
        export_visualization_json(stratum_map, str(output_path))

        assert output_path.exists()
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "meta" in data
        assert "chapter_layers" in data


class TestVisualizationDataStructure:
    """测试可视化数据结构"""

    def test_time_scale_generation(self) -> None:
        """测试时间刻度生成"""
        now = datetime.now()
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=[
                    EmrChapter(
                        chapter_id="ch-001",
                        chapter_name="第一章",
                        chapter_order=0,
                        created_time=now,
                        modified_time=now,
                        author_id="doctor-001",
                    ),
                    EmrChapter(
                        chapter_id="ch-002",
                        chapter_name="第二章",
                        chapter_order=1,
                        created_time=now + timedelta(hours=2),
                        modified_time=now + timedelta(hours=2),
                        author_id="doctor-001",
                    ),
                    EmrChapter(
                        chapter_id="ch-003",
                        chapter_name="第三章",
                        chapter_order=2,
                        created_time=now + timedelta(hours=4),
                        modified_time=now + timedelta(hours=4),
                        author_id="doctor-001",
                    ),
                ],
            ),
        ]

        stratum_map = build_stratum_map(records)
        viz_data = stratum_map.to_visualization_data()

        # 检查时间刻度
        time_scale = viz_data["time_scale"]
        assert len(time_scale) > 0
        assert all("time" in tick for tick in time_scale)
        assert all("position" in tick for tick in time_scale)
        assert all("label" in tick for tick in time_scale)

    def test_chapter_layers_structure(self) -> None:
        """测试章节层结构"""
        now = datetime.now()
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                business_time=now - timedelta(hours=1),
                chapters=[
                    EmrChapter(
                        chapter_id="ch-001",
                        chapter_name="入院记录",
                        chapter_order=0,
                        created_time=now,
                        modified_time=now,
                        author_id="doctor-001",
                    ),
                ],
            ),
        ]

        stratum_map = build_stratum_map(records)

        # 添加锚点
        builder = StratumBuilder()
        builder.build(records)
        builder.add_anchor_line(
            anchor_type="入院时间",
            anchor_time=now - timedelta(hours=1),
            record_id="R-001",
        )

        viz_data = stratum_map.to_visualization_data()
        chapter_layers = viz_data["chapter_layers"]

        assert len(chapter_layers) >= 1
        for layer in chapter_layers:
            assert "layer_number" in layer
            assert "entries" in layer
            for entry in layer["entries"]:
                assert "record_id" in entry
                assert "chapter_id" in entry
                assert "chapter_name" in entry
                assert "timestamp" in entry
                assert "position" in entry
                assert "has_anomaly" in entry

    def test_anchor_lines_in_viz(self) -> None:
        """测试锚点包含在可视化数据中"""
        now = datetime.now()
        records = [
            EmrTimestampRecord(
                patient_id="P-001",
                visit_id="V-001",
                record_id="R-001",
                record_type="入院记录",
                chapters=[
                    EmrChapter(
                        chapter_id="ch-001",
                        chapter_name="入院记录",
                        chapter_order=0,
                        created_time=now,
                        modified_time=now,
                        author_id="doctor-001",
                    ),
                ],
            ),
        ]

        builder = StratumBuilder()
        stratum_map = builder.build(records)
        builder.add_anchor_line(
            anchor_type="手术开始",
            anchor_time=now - timedelta(hours=2),
            record_id="R-001",
            label="手术",
        )

        viz_data = stratum_map.to_visualization_data()
        anchor_lines = viz_data["anchor_lines"]

        assert len(anchor_lines) == 1
        assert anchor_lines[0]["anchor_type"] == "手术开始"
        assert anchor_lines[0]["label"] == "手术"
        assert "position" in anchor_lines[0]

    def test_anomaly_flags_in_viz(self) -> None:
        """测试异常标记包含在可视化数据中"""
        now = datetime.now()
        entry = StratumEntry(
            record_id="R-001",
            chapter_id="ch-001",
            timestamp=now,
            stratum_layer=0,
            anomaly_flags=["BATCH_PROCESSING", "NIGHT_RUSH"],
        )
        layer = StratumLayer(layer_number=0)
        layer.add_entry(entry)
        layer.start_time = now
        layer.end_time = now

        stratum_map = StratumMap(
            records={},
            all_timestamps=[now],
            layers=[layer],
            record_count=0,
            chapter_count=1,
        )

        viz_data = stratum_map.to_visualization_data()
        chapter_layers = viz_data["chapter_layers"]

        assert len(chapter_layers) == 1
        entries = chapter_layers[0]["entries"]
        assert len(entries) == 1
        assert entries[0]["has_anomaly"] is True
        assert "BATCH_PROCESSING" in entries[0]["anomaly_flags"]
        assert "NIGHT_RUSH" in entries[0]["anomaly_flags"]