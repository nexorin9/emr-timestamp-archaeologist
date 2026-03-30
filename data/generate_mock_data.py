#!/usr/bin/env python3
"""
EMR Timestamp Archaeologist - Mock Data Generator
生成用于测试的模拟病历时间戳数据集（包含正常、异常、混合场景）
"""

import os
import sys
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

# Add src/py to path for imports (same pattern as test files)
script_dir = Path(__file__).parent
src_py_path = script_dir.parent / "src" / "py"
sys.path.insert(0, str(src_py_path))

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
)


def generate_id() -> str:
    """生成唯一ID"""
    return str(uuid.uuid4())[:8]


def random_patient_id() -> str:
    """生成患者ID"""
    return f"P{random.randint(10000, 99999)}"


def random_visit_id() -> str:
    """生成就诊ID"""
    return f"V{random.randint(100000, 999999)}"


def random_record_id() -> str:
    """生成病历记录ID"""
    return f"R{generate_id().upper()}"


def random_author_id() -> str:
    """生成作者ID（格式：科室缩写_工号）"""
    departments = ["心内", "神外", "骨科", "妇产", "儿科", "急诊", "ICU", "麻醉", "放射", "检验"]
    dept = random.choice(departments)
    code = random.randint(1000, 9999)
    return f"{dept}_{code}"


def generate_chapter_names() -> list[str]:
    """生成章节名称列表（按标准病历顺序）"""
    return [
        "入院记录",
        "首次病程",
        "日常病程",
        "手术记录",
        "麻醉记录",
        "术后病程",
        "出院记录",
        "知情同意",
    ]


def normal_time_distribution() -> datetime:
    """
    生成符合实际医院工作流程的正常时间分布
    - 工作时间（8:00-18:00）概率更高
    - 夜班时间（22:00-06:00）概率较低
    """
    hour = random.choices(
        range(24),
        weights=[0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 2.0, 3.0,
                 4.0, 4.0, 4.0, 3.0, 3.0, 3.0, 3.0, 3.0,
                 3.0, 4.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5]
    )[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    # 随机选择基准日期（近3个月内）
    days_ago = random.randint(0, 90)
    base_date = datetime.now() - timedelta(days=days_ago)

    return base_date.replace(hour=hour, minute=minute, second=second)


def business_time_distribution() -> datetime:
    """生成业务时间（通常是工作时间）"""
    hour = random.choices(
        range(24),
        weights=[0.1, 0.1, 0.1, 0.1, 0.1, 0.5, 2.0, 4.0,
                 4.0, 4.0, 4.0, 3.0, 3.0, 3.0, 3.0, 3.0,
                 3.0, 4.0, 4.0, 3.0, 2.0, 1.0, 0.5, 0.2]
    )[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    days_ago = random.randint(0, 90)
    base_date = datetime.now() - timedelta(days=days_ago)

    return base_date.replace(hour=hour, minute=minute, second=second)


def night_time_distribution() -> datetime:
    """生成夜间时间（22:00-05:00）"""
    hour = random.randint(22, 23)
    if hour == 23:
        minute = random.randint(0, 59)
    else:
        minute = random.randint(0, 59)

    second = random.randint(0, 59)

    days_ago = random.randint(0, 90)
    base_date = datetime.now() - timedelta(days=days_ago)

    return base_date.replace(hour=hour, minute=minute, second=second)


def early_morning_time() -> datetime:
    """生成凌晨时间（00:00-05:00）"""
    hour = random.randint(0, 4)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    days_ago = random.randint(0, 90)
    base_date = datetime.now() - timedelta(days=days_ago)

    return base_date.replace(hour=hour, minute=minute, second=second)


def generate_normal_records(n: int = 100) -> list[EmrTimestampRecord]:
    """
    生成正常时间分布的病历记录

    Args:
        n: 生成记录数量

    Returns:
        正常时间分布的病历记录列表
    """
    records = []
    for _ in range(n):
        patient_id = random_patient_id()
        visit_id = random_visit_id()
        record_id = random_record_id()
        record_type = random.choice(["入院", "手术", "急诊", "普通"])

        # 业务时间
        business_time = business_time_distribution()

        # 生成章节（时间略有先后，符合正常医疗流程）
        chapters = []
        base_time = business_time
        chapter_names = generate_chapter_names()

        # 入院记录最早
        created_time = base_time - timedelta(hours=random.randint(1, 4))
        chapters.append(EmrChapter(
            chapter_id=f"{record_id}_C1",
            chapter_name=chapter_names[0],
            chapter_order=1,
            created_time=created_time,
            modified_time=created_time + timedelta(minutes=random.randint(5, 30)),
            author_id=random_author_id()
        ))

        # 后续章节顺序创建
        for i, name in enumerate(chapter_names[1:], start=2):
            created_time = base_time + timedelta(hours=random.randint(0, 48) + i * 0.5)
            modified_time = created_time + timedelta(minutes=random.randint(5, 60))
            chapters.append(EmrChapter(
                chapter_id=f"{record_id}_C{i}",
                chapter_name=name,
                chapter_order=i,
                created_time=created_time,
                modified_time=modified_time,
                author_id=random_author_id()
            ))

        records.append(EmrTimestampRecord(
            patient_id=patient_id,
            visit_id=visit_id,
            record_id=record_id,
            record_type=record_type,
            chapters=chapters,
            business_time=business_time
        ))

    return records


def generate_batch_records(n: int = 20, batch_size: int = 5) -> list[EmrTimestampRecord]:
    """
    生成批处理痕迹记录（多份病历同一时间戳）

    Args:
        n: 生成批次数
        batch_size: 每批的病历数量

    Returns:
        包含批处理痕迹的病历记录列表
    """
    records = []
    for _ in range(n):
        # 所有病历使用完全相同的时间戳
        batch_time = normal_time_distribution()

        for i in range(batch_size):
            patient_id = random_patient_id()
            visit_id = random_visit_id()
            record_id = random_record_id()
            record_type = random.choice(["入院", "手术", "急诊", "普通"])

            chapters = []
            base_time = batch_time
            chapter_names = generate_chapter_names()

            for j, name in enumerate(chapter_names, start=1):
                created_time = base_time + timedelta(seconds=random.randint(-2, 2))
                modified_time = created_time + timedelta(minutes=random.randint(5, 30))
                chapters.append(EmrChapter(
                    chapter_id=f"{record_id}_C{j}",
                    chapter_name=name,
                    chapter_order=j,
                    created_time=created_time,
                    modified_time=modified_time,
                    author_id=random_author_id()
                ))

            records.append(EmrTimestampRecord(
                patient_id=patient_id,
                visit_id=visit_id,
                record_id=record_id,
                record_type=record_type,
                chapters=chapters,
                business_time=batch_time
            ))

    return records


def generate_night_rush_records(n: int = 30, night_ratio: float = 0.8) -> list[EmrTimestampRecord]:
    """
    生成夜间突击补写记录

    Args:
        n: 生成记录数量
        night_ratio: 夜间修改比例

    Returns:
        包含夜间突击补写的病历记录列表
    """
    records = []
    for _ in range(n):
        patient_id = random_patient_id()
        visit_id = random_visit_id()
        record_id = random_record_id()
        record_type = random.choice(["入院", "手术", "急诊", "普通"])

        # 业务时间（白天）
        business_time = business_time_distribution()

        # 生成章节，大部分章节在夜间创建
        chapters = []
        chapter_names = generate_chapter_names()

        # 入院记录时间正常
        day_time = business_time - timedelta(hours=random.randint(1, 4))
        chapters.append(EmrChapter(
            chapter_id=f"{record_id}_C1",
            chapter_name=chapter_names[0],
            chapter_order=1,
            created_time=day_time,
            modified_time=day_time + timedelta(minutes=random.randint(5, 30)),
            author_id=random_author_id()
        ))

        # 后续章节大部分在夜间创建
        for i, name in enumerate(chapter_names[1:], start=2):
            if random.random() < night_ratio:
                # 夜间时间
                created_time = night_time_distribution()
            else:
                # 白天时间
                created_time = business_time + timedelta(hours=random.randint(1, 12))

            modified_time = created_time + timedelta(minutes=random.randint(5, 60))

            # 夜间创建的章节，modified_time 往往更晚（突击补写）
            if created_time.hour >= 22 or created_time.hour < 5:
                modified_time = created_time + timedelta(hours=random.randint(1, 3))

            chapters.append(EmrChapter(
                chapter_id=f"{record_id}_C{i}",
                chapter_name=name,
                chapter_order=i,
                created_time=created_time,
                modified_time=modified_time,
                author_id=random_author_id()
            ))

        records.append(EmrTimestampRecord(
            patient_id=patient_id,
            visit_id=visit_id,
            record_id=record_id,
            record_type=record_type,
            chapters=chapters,
            business_time=business_time
        ))

    return records


def generate_time_contradiction_records(n: int = 20) -> list[EmrTimestampRecord]:
    """
    生成时间矛盾记录（手术记录早于手术开始）

    Args:
        n: 生成记录数量

    Returns:
        包含时间矛盾的病历记录列表
    """
    records = []
    for _ in range(n):
        patient_id = random_patient_id()
        visit_id = random_visit_id()
        record_id = random_record_id()
        record_type = "手术"

        # 手术开始时间（业务时间）
        surgery_start = business_time_distribution()

        chapters = []
        chapter_names = generate_chapter_names()

        # 入院记录
        created_time = surgery_start - timedelta(hours=random.randint(4, 24))
        chapters.append(EmrChapter(
            chapter_id=f"{record_id}_C1",
            chapter_name=chapter_names[0],
            chapter_order=1,
            created_time=created_time,
            modified_time=created_time + timedelta(minutes=random.randint(5, 30)),
            author_id=random_author_id()
        ))

        # 手术记录时间矛盾：创建时间早于手术开始
        # 这是核心的时间矛盾场景
        surgery_record_time = surgery_start - timedelta(hours=random.randint(1, 6))
        chapters.append(EmrChapter(
            chapter_id=f"{record_id}_C4",  # 手术记录通常是第4章
            chapter_name="手术记录",
            chapter_order=4,
            created_time=surgery_record_time,  # 早于手术开始！
            modified_time=surgery_record_time + timedelta(minutes=random.randint(30, 120)),
            author_id=random_author_id()
        ))

        # 麻醉记录时间矛盾：同样早于手术开始
        anesthesia_time = surgery_start - timedelta(minutes=random.randint(30, 120))
        chapters.append(EmrChapter(
            chapter_id=f"{record_id}_C5",
            chapter_name="麻醉记录",
            chapter_order=5,
            created_time=anesthesia_time,
            modified_time=anesthesia_time + timedelta(minutes=random.randint(15, 60)),
            author_id=random_author_id()
        ))

        # 其他章节在手术结束后正常创建
        for i, name in enumerate(chapter_names, start=1):
            if name in ["手术记录", "麻醉记录", "入院记录"]:
                continue

            created_time = surgery_start + timedelta(hours=random.randint(0, 24))
            modified_time = created_time + timedelta(minutes=random.randint(5, 60))
            chapters.append(EmrChapter(
                chapter_id=f"{record_id}_C{i}",
                chapter_name=name,
                chapter_order=i,
                created_time=created_time,
                modified_time=modified_time,
                author_id=random_author_id()
            ))

        # 按 chapter_order 排序
        chapters.sort(key=lambda c: c.chapter_order)

        records.append(EmrTimestampRecord(
            patient_id=patient_id,
            visit_id=visit_id,
            record_id=record_id,
            record_type=record_type,
            chapters=chapters,
            business_time=surgery_start
        ))

    return records


def generate_mixed_records(n: int = 200) -> list[EmrTimestampRecord]:
    """
    生成混合数据集（正常+各类异常）

    Args:
        n: 生成记录总数量

    Returns:
        混合数据集（正常+批处理+夜间+时间矛盾）
    """
    # 按比例分配：60%正常，20%批处理，10%夜间，10%时间矛盾
    normal_count = int(n * 0.6)
    batch_count = int(n * 0.2)
    night_count = int(n * 0.1)
    contradiction_count = n - normal_count - batch_count - night_count

    records = []
    records.extend(generate_normal_records(normal_count))
    records.extend(generate_batch_records(batch_count, batch_size=random.randint(3, 8)))
    records.extend(generate_night_rush_records(night_count, night_ratio=0.85))
    records.extend(generate_time_contradiction_records(contradiction_count))

    # 打乱顺序
    random.shuffle(records)
    return records


def record_to_dict(record: EmrTimestampRecord) -> dict[str, Any]:
    """将 EmrTimestampRecord 转换为字典"""
    return {
        "patient_id": record.patient_id,
        "visit_id": record.visit_id,
        "record_id": record.record_id,
        "record_type": record.record_type,
        "business_time": record.business_time.strftime("%Y-%m-%d %H:%M:%S") if record.business_time else None,
        "chapters": [
            {
                "chapter_id": c.chapter_id,
                "chapter_name": c.chapter_name,
                "chapter_order": c.chapter_order,
                "created_time": c.created_time.strftime("%Y-%m-%d %H:%M:%S"),
                "modified_time": c.modified_time.strftime("%Y-%m-%d %H:%M:%S"),
                "author_id": c.author_id
            }
            for c in record.chapters
        ]
    }


def export_to_xml(records: list[EmrTimestampRecord], filepath: str) -> None:
    """
    导出为 XML 格式

    Args:
        records: 病历记录列表
        filepath: 输出文件路径
    """
    root = Element("emr_records")
    root.set("total", str(len(records)))
    root.set("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    for record in records:
        record_elem = SubElement(root, "record")
        record_elem.set("record_id", record.record_id)

        patient_elem = SubElement(record_elem, "patient_id")
        patient_elem.text = record.patient_id

        visit_elem = SubElement(record_elem, "visit_id")
        visit_elem.text = record.visit_id

        record_type_elem = SubElement(record_elem, "record_type")
        record_type_elem.text = record.record_type

        if record.business_time:
            business_time_elem = SubElement(record_elem, "business_time")
            business_time_elem.text = record.business_time.strftime("%Y-%m-%d %H:%M:%S")

        chapters_elem = SubElement(record_elem, "chapters")

        for chapter in record.chapters:
            chapter_elem = SubElement(chapters_elem, "chapter")
            chapter_elem.set("chapter_id", chapter.chapter_id)

            name_elem = SubElement(chapter_elem, "chapter_name")
            name_elem.text = chapter.chapter_name

            order_elem = SubElement(chapter_elem, "chapter_order")
            order_elem.text = str(chapter.chapter_order)

            created_elem = SubElement(chapter_elem, "created_time")
            created_elem.text = chapter.created_time.strftime("%Y-%m-%d %H:%M:%S")

            modified_elem = SubElement(chapter_elem, "modified_time")
            modified_elem.text = chapter.modified_time.strftime("%Y-%m-%d %H:%M:%S")

            author_elem = SubElement(chapter_elem, "author_id")
            author_elem.text = chapter.author_id

    # 写入文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(tostring(root, encoding="unicode", xml_declaration=False))


def export_to_json(records: list[EmrTimestampRecord], filepath: str) -> None:
    """
    导出为 JSON 格式

    Args:
        records: 病历记录列表
        filepath: 输出文件路径
    """
    import json

    data = {
        "total": len(records),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": [record_to_dict(r) for r in records]
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_to_csv(records: list[EmrTimestampRecord], filepath: str) -> None:
    """
    导出为 CSV 格式

    Args:
        records: 病历记录列表
        filepath: 输出文件路径
    """
    import csv

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        # 写入表头
        writer.writerow([
            "record_id", "patient_id", "visit_id", "record_type",
            "chapter_id", "chapter_name", "chapter_order",
            "created_time", "modified_time", "author_id",
            "business_time"
        ])

        # 写入数据
        for record in records:
            for chapter in record.chapters:
                writer.writerow([
                    record.record_id,
                    record.patient_id,
                    record.visit_id,
                    record.record_type,
                    chapter.chapter_id,
                    chapter.chapter_name,
                    chapter.chapter_order,
                    chapter.created_time.strftime("%Y-%m-%d %H:%M:%S"),
                    chapter.modified_time.strftime("%Y-%m-%d %H:%M:%S"),
                    chapter.author_id,
                    record.business_time.strftime("%Y-%m-%d %H:%M:%S") if record.business_time else ""
                ])


def main():
    """主函数：生成所有示例数据"""
    import os

    # 确保 data 目录存在
    data_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = data_dir  # 直接使用 data_dir
    os.makedirs(output_dir, exist_ok=True)

    print("EMR Timestamp Archaeologist - Mock Data Generator")
    print("=" * 50)

    # 生成正常数据
    print("Generating normal records...")
    normal_records = generate_normal_records(100)
    normal_xml_path = os.path.join(output_dir, "sample_normal.xml")
    export_to_xml(normal_records, normal_xml_path)
    print(f"  -> {normal_xml_path} ({len(normal_records)} records)")

    # 生成异常数据（混合）
    print("Generating anomaly records (mixed)...")
    anomaly_records = generate_mixed_records(100)
    anomaly_xml_path = os.path.join(output_dir, "sample_anomalies.xml")
    export_to_xml(anomaly_records, anomaly_xml_path)
    print(f"  -> {anomaly_xml_path} ({len(anomaly_records)} records)")

    # 生成 JSON 格式混合数据
    print("Generating JSON format...")
    mixed_json_path = os.path.join(output_dir, "sample_mixed.json")
    export_to_json(anomaly_records, mixed_json_path)
    print(f"  -> {mixed_json_path}")

    # 生成 CSV 格式（从正常数据）
    print("Generating CSV format...")
    csv_path = os.path.join(output_dir, "sample_normal.csv")
    export_to_csv(normal_records, csv_path)
    print(f"  -> {csv_path}")

    print("=" * 50)
    print("Mock data generation complete!")


if __name__ == "__main__":
    main()