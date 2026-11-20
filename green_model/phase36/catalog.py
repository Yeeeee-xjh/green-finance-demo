"""Curated Phase 3.6 source and rule specifications.

This module contains research data only.  Every record is anchored to a local
copy of an official public source and a precise locator.  Derived review aids
are explicitly labelled ``source_derived``; they are never represented as
verbatim regulatory requirements.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SOURCE_SPECS = {
    "cement_permit": {
        "path": "data/industry_master/sources/phase36/3011/HJ847_2017.pdf",
        "name": "排污许可证申请与核发技术规范 水泥工业",
        "issuer": "原环境保护部",
        "standard_no": "HJ 847-2017",
        "version": "HJ 847-2017",
        "url": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/pwxk/201708/W020170802617396676231.pdf",
        "published_at": "2017-07-27", "effective_at": "2017-07-27",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_monitor": {
        "path": "data/industry_master/sources/phase36/3011/HJ848_2017.pdf",
        "name": "排污单位自行监测技术指南 水泥工业",
        "issuer": "原环境保护部",
        "standard_no": "HJ 848-2017", "version": "HJ 848-2017",
        "url": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/201710/t20171016_423453.shtml",
        "published_at": "2017-09-19", "effective_at": "2017-11-01",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_coprocess": {
        "path": "data/industry_master/sources/phase36/3011/HJ662_2013.pdf",
        "name": "水泥窑协同处置固体废物环境保护技术规范",
        "issuer": "原环境保护部",
        "standard_no": "HJ 662-2013", "version": "HJ 662-2013",
        "url": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/gthw/qtxgbz/201401/W020140107588398961387.pdf",
        "published_at": "2013-12-10", "effective_at": "2014-03-01",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_coprocess_emission": {
        "path": "data/industry_master/sources/phase36/3011/GB30485_2013.pdf",
        "name": "水泥窑协同处置固体废物污染控制标准",
        "issuer": "原环境保护部、原国家质量监督检验检疫总局",
        "standard_no": "GB 30485-2013", "version": "GB 30485-2013",
        "url": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/gthw/gtfwwrkzbz/201312/W020131231371635260646.pdf",
        "published_at": "2013-12-27", "effective_at": "2014-03-01",
        "mandatory": True, "status": "full_text_obtained",
    },
    "cement_air": {
        "path": "data/industry_master/sources/phase36/3011/GB4915_2013_with_2025_amendment.pdf",
        "name": "水泥工业大气污染物排放标准修改单（2025年修改）",
        "issuer": "生态环境部、国家市场监督管理总局",
        "standard_no": "GB 4915-2013/XG2-2025", "version": "2025年修改单（现行）",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202602/W020260224570879487364.pdf",
        "published_at": "2026-02-24", "effective_at": "2026-04-01",
        "mandatory": True, "status": "full_text_obtained",
    },
    "cement_energy_standard": {
        "path": "data/industry_master/sources/phase36/3011/GB16780_2021_metadata.html",
        "name": "水泥单位产品能源消耗限额（官方标准登记信息）",
        "issuer": "国家市场监督管理总局、国家标准化管理委员会",
        "standard_no": "GB 16780-2021", "version": "GB 16780-2021",
        "url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=A98F40B6D901C95820E0B5DFDC3FCFF9",
        "published_at": "2021-10-11", "effective_at": "2022-11-01",
        "mandatory": True, "status": "official_summary_only",
        "limitation": "仅取得官方登记信息；不从元数据生成能耗限额数值。",
    },
    "cement_ultra": {
        "path": "data/industry_master/sources/phase36/3011/cement_ultra_low_opinion_2024.pdf",
        "name": "关于推进实施水泥行业超低排放的意见",
        "issuer": "生态环境部等部门", "document_no": "环大气〔2024〕5号",
        "version": "环大气〔2024〕5号",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202401/W020240119512650483366.pdf",
        "published_at": "2024-01-15", "effective_at": "2024-01-15",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_ultra_assess": {
        "path": "data/industry_master/sources/phase36/3011/cement_ultra_low_assessment_2024.pdf",
        "name": "水泥企业超低排放评估监测技术指南",
        "issuer": "生态环境部办公厅", "version": "2024年6月版",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202406/W020240606511905961090.pdf",
        "published_at": "2024-06-05", "effective_at": "2024-06-05",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_eia": {
        "path": "data/industry_master/sources/phase36/3011/cement_eia_approval_2024.pdf",
        "name": "水泥制造建设项目环境影响评价文件审批原则（2024年版）",
        "issuer": "生态环境部办公厅", "version": "2024年版",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk05/202312/W020231208598594651587.pdf",
        "published_at": "2023-12-05", "effective_at": "2023-12-05",
        "mandatory": False, "status": "full_text_obtained",
        "limitation": "原件为多行业合集；3011仅使用PDF第16—22页（印刷页18—24）的水泥章节。",
    },
    "cement_energy_manual": {
        "path": "data/industry_master/sources/phase36/3011/cement_energy_inspection_manual.pdf",
        "name": "水泥行业能耗专项监察工作手册",
        "issuer": "工业和信息化部", "version": "2023年4月版",
        "url": "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/20236/204f3a678ad340e0939a16e1d35fd0a2.pdf",
        "published_at": "2023-04-01", "effective_at": "2023-04-01",
        "mandatory": False, "status": "full_text_obtained",
    },
    "cement_decarbon": {
        "path": "data/industry_master/sources/phase36/3011/cement_decarbonization_2024.pdf",
        "name": "水泥行业节能降碳专项行动计划",
        "issuer": "国家发展改革委等部门", "document_no": "发改环资〔2024〕733号",
        "version": "发改环资〔2024〕733号",
        "url": "https://www.ndrc.gov.cn/xwdt/tzgg/202406/t20240607_1386765_ext.html",
        "published_at": "2024-05-27", "effective_at": "2024-05-27",
        "mandatory": False, "status": "full_text_obtained",
    },
    "steel_decarbon": {
        "path": "data/industry_master/sources/phase36/3110/steel_decarbonization_2024.pdf",
        "name": "钢铁行业节能降碳专项行动计划",
        "issuer": "国家发展改革委等部门", "document_no": "发改环资〔2024〕730号",
        "version": "发改环资〔2024〕730号",
        "url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202406/P020240607588410867952.pdf",
        "published_at": "2024-05-27", "effective_at": "2024-05-27",
        "mandatory": False, "status": "full_text_obtained",
    },
    "wind_standards": {
        "path": "data/industry_master/sources/phase36/4415/NEA_current_standards_catalogue_2023.pdf",
        "name": "电力建设工程现行管理文件及技术标准名录（2023版）",
        "issuer": "国家能源局电力可靠性管理和工程质量监督中心",
        "version": "2023版",
        "url": "https://prpq.nea.gov.cn/uploads/file1/20240911/66e1071abaa30.pdf",
        "published_at": "2023-08-31", "effective_at": "2023-08-31",
        "mandatory": False, "status": "full_text_obtained",
        "limitation": "名录证明标准引用及当时现行状态，不替代标准全文，不据此生成技术阈值。",
    },
    "wind_ccer": {
        "path": "data/industry_master/sources/rework_wind/CCER-01-002-V01.pdf",
        "name": "温室气体自愿减排项目方法学 并网海上风力发电",
        "issuer": "生态环境部", "standard_no": "CCER-01-002-V01",
        "version": "CCER-01-002-V01",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202310/W020231024631537178788.pdf",
        "published_at": "2023-10-24", "effective_at": "2023-10-24",
        "mandatory": False, "status": "full_text_obtained",
        "limitation": "仅适用于离岸30公里以外或者水深大于30米的并网海上风电项目；不得套给全部4415项目。",
    },
}


def item(module: str, name: str, text: str, source: str, locator: str,
         derivation: str = "source_derived", **extra):
    return {
        "module": module, "name": name, "text": text, "source_key": source,
        "locator": locator, "derivation_type": derivation, **extra,
    }


def _cement_items():
    rows = []
    for name, text in [
        ("原料破碎与预均化", "石灰石等原料经破碎、筛分、输送并进入堆场或均化设施；核对生产线范围、台时产量与堆场容量。"),
        ("生料制备", "原料进入球磨、辊压或立式生料磨并完成配料和均化；设备、产能和能源计量口径须与申报信息一致。"),
        ("煤粉制备", "燃料经球磨或立磨制成煤粉并输送至烧成系统；燃料种类、灰分、硫分、挥发分与热值应按要求填报。"),
        ("预热分解与熟料煅烧", "预热器、分解炉和水泥窑构成熟料烧成核心环节，工艺与设施参数须逐线对应。"),
        ("熟料冷却与余热利用", "熟料经冷却机冷却，配套余热锅炉、汽轮机和发电机的，应区分生产设施和余热发电边界。"),
        ("水泥粉磨、包装与散装", "熟料、石膏及混合材经破碎、粉磨、选粉后包装或散装出厂，独立粉磨站与完整熟料线应分别定标。"),
    ]:
        rows.append(item("process", name, text, "cement_permit", "PDF第6—9页，表1及4.3—4.5", "source_derived"))
    for name, text in [
        ("原料破碎设备", "颚式、锤式或冲击式破碎机及筛分、输送设备，核对型号、台时产量和实际安装位置。"),
        ("生料粉磨设备", "球磨机、辊压机或立式生料磨，核对磨体/磨盘参数、产能和电耗计量点。"),
        ("煤粉制备设备", "煤磨及输送、喷入设施，核对燃料边界、运行记录和安全环保配套。"),
        ("预热器", "熟料煅烧系统预热器，核对列数、级数及与生产线的对应关系。"),
        ("分解炉", "熟料煅烧系统分解炉，核对有效容积及低氮燃烧等改造边界。"),
        ("水泥窑", "回转窑为熟料烧成核心设备，核对筒体参数、设计产能、投产和改造时间。"),
        ("篦式冷却机", "用于熟料冷却并影响热回收效率，核对面积、改造内容与运行台账。"),
        ("水泥粉磨设备", "球磨机、辊压机、选粉机或立式水泥磨，核对设备组合与粉磨站边界。"),
        ("余热发电系统", "SP/PH或AQC锅炉、汽轮机、发电机和冷却塔，核对装机容量、运行时间和发电量。"),
    ]:
        rows.append(item("equipment", name, text, "cement_permit", "PDF第6—7页，表1", "source_derived"))
    rows += [
        item("route", "熟料—水泥完整生产线", "包含原料处理、生料制备、熟料煅烧、冷却和水泥粉磨包装；能耗与排污许可按完整生产线边界核验。", "cement_energy_manual", "PDF第4—6页，第一部分及能耗统计范围"),
        item("route", "独立水泥粉磨站", "从熟料、石膏和混合材进入厂区至水泥出厂，不含熟料烧成；不得套用完整生产线全部工序事实。", "cement_energy_manual", "PDF第4—6页，监察对象及电耗统计范围"),
        item("route", "水泥窑协同处置固体废物（条件路线）", "仅在项目实际包含固体废物贮存、预处理和入窑处置时启用，并追加HJ 662和GB 30485核验。", "cement_permit", "PDF第5—10页，3.1、4.3及4.5"),
    ]
    standards = [
        ("cement_permit", "HJ 847-2017", "排污许可证申请与核发技术规范 水泥工业", "水泥（熟料）制造和独立粉磨站排污许可管理。", "PDF第1页，封面标准号与标准名称"),
        ("cement_monitor", "HJ 848-2017", "排污单位自行监测技术指南 水泥工业", "按实际生产单元、排放口和污染因子确定监测。", "PDF第1页，封面标准号与标准名称"),
        ("cement_coprocess", "HJ 662-2013", "水泥窑协同处置固体废物环境保护技术规范", "仅适用于实际开展水泥窑协同处置的项目。", "PDF第1页，封面标准号与标准名称"),
        ("cement_coprocess_emission", "GB 30485-2013", "水泥窑协同处置固体废物污染控制标准", "仅适用于实际开展协同处置的设施和排放。", "PDF第1页，封面标准号与标准名称"),
        ("cement_air", "GB 4915-2013/XG2-2025", "水泥工业大气污染物排放标准及现行修改单", "按设施、含氧量、区域和生效时间核验。", "PDF第1页公告及第3页修改单标题"),
        ("cement_energy_standard", "GB 16780-2021", "水泥单位产品能源消耗限额", "仅登记官方元数据；全文数值不在本包中补写。", "官方元数据页，标准号GB 16780-2021及实施日期"),
    ]
    for src, no, name, text, locator in standards:
        rows.append(item("standard", name, text, src, locator, "policy_explicit", standard_no=no,
                         full_text_status=SOURCE_SPECS[src]["status"], applicability=text))
    indicators = [
        ("水泥窑及窑尾余热利用系统颗粒物浓度", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1"),
        ("水泥窑及窑尾余热利用系统二氧化硫浓度", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1"),
        ("水泥窑及窑尾余热利用系统氮氧化物浓度", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1"),
        ("氨水消耗量", "kg/t熟料", "cement_ultra", "PDF第4页，氨逃逸控制要求"),
        ("自动监测数据传输有效率", "%", "cement_ultra_assess", "PDF第3页，评估基本条件"),
        ("CEMS有效数据时间符合率", "%", "cement_ultra_assess", "PDF第8页，连续监测评估"),
        ("评估监测生产负荷", "%", "cement_ultra_assess", "PDF第14页，现场监测工况"),
        ("清洁运输比例", "%", "cement_decarbon", "PDF第3页，二（四）"),
        ("替代燃料技术生产线比例", "%", "cement_decarbon", "PDF第3页，二（三）"),
        ("关键工序数控化率", "%", "cement_decarbon", "PDF第4页，二（六）"),
    ]
    for name, unit, src, loc in indicators:
        rows.append(item("indicator", name, f"按{SOURCE_SPECS[src]['name']}明文口径核对{name}，不得用企业口号或非同口径数据替代。", src, loc,
                         "policy_explicit", unit=unit, stage="贷前/贷中及贷后持续核验", scope="按来源条款限定的设施、企业或政策目标范围"))
    thresholds = [
        ("窑尾颗粒物超低排放", 10, "<=", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1", "水泥窑及窑尾余热利用系统；基准含氧量10%"),
        ("窑尾二氧化硫超低排放", 35, "<=", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1", "水泥窑及窑尾余热利用系统；基准含氧量10%"),
        ("窑尾氮氧化物超低排放", 50, "<=", "mg/m³", "cement_ultra", "PDF第10页（印刷页12）表1", "水泥窑及窑尾余热利用系统；基准含氧量10%"),
        ("氨水消耗控制", 3.5, "<", "kg/t熟料", "cement_ultra", "PDF第4页，氨逃逸控制要求", "采用氨水作为脱硝剂且折算为20%氨水的熟料生产线"),
        ("自动监测数据传输有效率", 95, ">=", "%", "cement_ultra_assess", "PDF第3页，评估基本条件", "申请超低排放评估的企业"),
        ("CEMS有效数据时间符合率", 95, ">=", "%", "cement_ultra_assess", "PDF第8页，连续30日数据要求", "申请超低排放评估的排口，连续30日"),
        ("评估监测生产负荷", 90, ">=", "%", "cement_ultra_assess", "PDF第14页，现场监测工况", "现场评估监测期间相应设计生产能力"),
        ("独立热源烘干设备颗粒物限值", 10, "<=", "mg/m³", "cement_air", "PDF第4—5页，修改单表1", "采用独立热源的烘干设备，自2026-04-01起"),
        ("独立热源烘干设备二氧化硫限值", 50, "<=", "mg/m³", "cement_air", "PDF第4—5页，修改单表1", "采用独立热源的烘干设备，自2026-04-01起"),
        ("独立热源烘干设备氮氧化物限值", 80, "<=", "mg/m³", "cement_air", "PDF第4—5页，修改单表1", "采用独立热源的烘干设备，自2026-04-01起"),
        ("独立热源烘干设备氨限值", 8, "<=", "mg/m³", "cement_air", "PDF第4—5页，修改单表1", "采用独立热源的烘干设备，自2026-04-01起"),
    ]
    for name, value, op, unit, src, loc, scope in thresholds:
        rows.append(item("threshold", name, f"{name}：{op}{value}{unit}；只在“{scope}”范围应用。", src, loc, "policy_explicit",
                         value=value, operator=op, unit=unit, scope=scope, effective_at=SOURCE_SPECS[src]["effective_at"]))
    permits = [
        ("建设项目环境影响评价审批", "建设前", "项目须按水泥制造审批原则及环评分类要求完成相应环境影响评价与审批。", "cement_eia", "PDF第16—22页（印刷页18—24），第1—15条"),
        ("产能置换与新增产能约束核验", "立项/环评前", "核对产能置换、落后产能淘汰及重点区域新增熟料产能限制等政策前提。", "cement_eia", "PDF第16页（印刷页18），第2条"),
        ("固定资产投资项目节能审查", "建设前", "新建和改扩建项目应落实节能审查及单位产品能耗要求，审查意见作为后续核验依据。", "cement_decarbon", "PDF第1—2页，二（一）—（二）"),
        ("水泥工业排污许可", "投产排污前及运行期", "水泥（熟料）制造或独立粉磨站按HJ847填报并取得、变更和执行排污许可证。", "cement_permit", "PDF第4—6页，1及4.1—4.2"),
        ("危险废物经营许可（条件适用）", "协同处置危险废物前", "仅对实际协同处置危险废物的项目核对经营许可及其核准范围，不适用于普通水泥线。", "cement_permit", "PDF第5页，规范性引用文件及协同处置范围"),
    ]
    for name, stage, text, src, loc in permits:
        rows.append(item("permit", name, text, src, loc, "policy_explicit", stage=stage, region="全国；同时核对属地更严规定"))
    documents = [
        ("环境影响报告书（表）及批复", "建设前", "核对项目边界、产能、选址、污染防治、温室气体和审批条件。", "cement_eia", "PDF第16—22页，第1—15条"),
        ("产能置换方案及落实证明", "建设前", "核对产能置换来源、规模和落实状态，不以企业说明替代主管部门公开或确认材料。", "cement_eia", "PDF第16页（印刷页18），第2条"),
        ("节能审查意见及落实材料", "建设/投产", "核对审查口径、单位产品能耗、主要设备和项目实际建设的一致性。", "cement_decarbon", "PDF第1—2页，二（一）—（二）"),
        ("排污许可证申请表及许可证", "投产排污前/运行期", "包含基本信息、产品产能、生产设施、原燃料、排放口及许可限值。", "cement_permit", "PDF第5—10页，4.1—4.5"),
        ("自行监测方案和原始监测记录", "运行期", "按排放口、因子和频次提供方案、自动/手工监测原始数据及质控记录。", "cement_monitor", "PDF第4—9页，4—6章"),
        ("环境管理台账及许可证执行报告", "运行期", "提供生产、燃料、治理设施、排放及异常工况台账与执行报告。", "cement_permit", "PDF第25页起，第8章"),
        ("能耗自查报告及生产能源台账", "能效核验", "提供分生产线产量、燃料、电力、设备和计量器具台账并保持勾稽一致。", "cement_energy_manual", "PDF第4—13页，二至五及附件1"),
    ]
    for name, stage, text, src, loc in documents:
        rows.append(item("document", name, text, src, loc, "policy_explicit", stage=stage))
    evidence = [
        ("生产线与产能边界", "生产线清单、设计产能、投产时间与主要设备应跨文件一致。", "cement_permit", "PDF第6—8页，表1及4.3"),
        ("原燃料及替代燃料", "原燃料种类、年用量、成分和热值与采购、计量及生产台账相互印证。", "cement_permit", "PDF第8—9页，4.4"),
        ("污染排放口与治理设施", "排放口、产污环节、污染物、治理工艺和监测点一一对应。", "cement_permit", "PDF第9—10页，4.5"),
        ("环评项目边界", "核对环评批复、总图、生产线和本次融资建设内容的范围一致性。", "cement_eia", "PDF第16—22页，第1—15条"),
        ("产能置换落实", "主管部门公开/确认信息与项目规模、淘汰产能和时间节点相互核对。", "cement_eia", "PDF第16页（印刷页18），第2条"),
        ("单位产品能耗", "能源计量原始记录、月报年报、产品产量和计算边界可追溯。", "cement_energy_manual", "PDF第7—11页，四至五"),
        ("超低排放监测", "CEMS、手工监测、工况和质控记录共同证明相应设施排放水平。", "cement_ultra_assess", "PDF第7—15页，连续监测与现场监测"),
        ("氨水消耗与脱硝运行", "氨水采购、浓度、使用量、熟料产量和脱硝设施运行记录勾稽。", "cement_ultra", "PDF第4页，氨逃逸控制要求"),
        ("清洁运输比例", "运输方式、车辆船舶清单、运量凭证与平台记录支持计算。", "cement_decarbon", "PDF第3页，二（四）"),
        ("协同处置适用性", "固废类别、接收、贮存、预处理、投加和污染控制证据完整，普通生产线不得冒用。", "cement_coprocess", "PDF第5—13页，4—8章"),
        ("贷后建设与投运实绩", "合同、发票、进度、验收、设备运行和绩效数据按同一项目边界持续比对。", "cement_decarbon", "PDF第6页，四（二）—（三）"),
    ]
    for name, text, src, loc in evidence:
        rows.append(item("evidence", name, text, src, loc, "source_derived", acceptable=text,
                         unacceptable="仅企业自述、宣传稿或无法定位到本项目的汇总数据", stage="贷前/贷中/贷后按事项触发"))
    risks = [
        ("产能边界错配", "融资项目、环评批复和置换产能范围不一致。", "先对齐生产线、规模和建设内容，再判断是否真实冲突。", "cement_eia", "PDF第16页，第1—2条"),
        ("单位产品能耗口径错配", "将全厂总耗、熟料耗和水泥粉磨耗混用会造成错误对标。", "核对工段、产品、统计期、替代燃料与分母产量。", "cement_energy_manual", "PDF第5—10页，三至五"),
        ("排放设施错配", "将窑尾、窑头、烘干或粉磨排口套用同一限值。", "按设施、基准含氧量、区域和生效日期匹配规则。", "cement_ultra", "PDF第9—11页，表1"),
        ("监测数据有效性不足", "仅有均值或截图但缺少连续性、传输率、校准和工况证据。", "调取原始时序数据、质控记录和生产负荷。", "cement_ultra_assess", "PDF第3、7—15页"),
        ("协同处置条件误套", "普通水泥线与协同处置线材料、许可和污染物范围不同。", "先确认是否实际协同处置及废物类别，再启用专项规则。", "cement_coprocess", "PDF第4—8页，1—6章"),
        ("替代燃料绩效不可追溯", "只披露比例或减排口号但采购、热值和投加记录无法对应。", "核对来源、计量、热值、投加和产量台账。", "cement_decarbon", "PDF第2—3页，二（三）"),
        ("节能改造资金用途偏离", "设备合同、发票与实际安装运行范围不一致。", "穿透到设备型号、安装位置、付款和投运记录。", "cement_energy_manual", "PDF第10—13页，五及附件1"),
        ("贷后绩效未兑现", "建设完成但能耗、排放或清洁运输目标持续偏离。", "按基准—目标—实际持续监测并触发人工复核。", "cement_decarbon", "PDF第1—6页，主要目标及监督管理"),
    ]
    for name, text, review, src, loc in risks:
        rows.append(item("risk", name, text, src, loc, "source_derived", category="行业技术与合规落实", review_focus=review))
    terms = [
        ("熟料", "水泥生产的中间产品；熟料产量与水泥产量不可作为同一统计分母。"),
        ("独立粉磨站", "不含熟料煅烧、以熟料等入厂后粉磨生产水泥的企业或生产线。"),
        ("预分解系统", "由预热器和分解炉等构成、在入窑前完成主要碳酸盐分解的系统。"),
        ("可比熟料综合煤耗", "按适用能耗标准调整后用于熟料生产能效对标的单位产品煤耗指标。"),
        ("许可排放限值", "排污许可证规定的最大排放浓度或排放量，须区分两种口径。"),
        ("超低排放", "满足专项意见对有组织、无组织和清洁运输等改造与评估要求的状态，不等同仅一项排口达标。"),
        ("CEMS有效数据时间符合率", "连续监测数据满足有效性判定的时段占统计时段的比例。"),
        ("水泥窑协同处置", "利用水泥窑高温等工艺条件对固体废物进行无害化处置并纳入水泥生产过程。"),
    ]
    for name, text in terms:
        rows.append(item("term", name, text, "cement_permit", "PDF第4—10页，术语、表1及相关条款", "source_derived", usage="辅助阅读；具体适用边界以对应来源条款为准。"))
    postloan = [
        ("单位产品能耗及统计口径", "按生产线持续核对能源消耗、产品产量和计算边界。", "月度台账、年度复核；银行频率依合同", "能源计量原始记录、生产月报年报和能耗计算表", "cement_energy_manual", "PDF第9—13页，现场监察及附件1"),
        ("主要排口排放与监测有效性", "跟踪窑尾等主要排口浓度、数据传输和有效时段。", "连续监测、月度汇总、异常触发", "CEMS原始数据、质控校准、工况与执行报告", "cement_ultra_assess", "PDF第3、7—15页"),
        ("改造设备投运与绩效兑现", "对合同设备、安装、验收、运行小时和节能减排实绩进行B-T-A比对。", "建设期节点及投运后季度/年度", "合同发票、验收、设备台账、能耗排放实绩", "cement_decarbon", "PDF第1—6页，重点任务及监督管理"),
    ]
    for name, text, frequency, evidence_obj, src, loc in postloan:
        rows.append(item("postloan", name, text, src, loc, "source_derived", frequency=frequency, evidence_object=evidence_obj))
    return rows


def _iron_items():
    rows = []
    # Existing Phase 3.5 records remain; these rows close the density gaps with
    # scoped content from the current official sources.
    process_rows = [
        ("原燃料贮存、筛分与上料", "原料系统包括贮矿、槽下筛分、称量和上料；须将设施、排放口和物料台账对应到炼铁生产线。", "iron_air", "PDF第4—6页，3.7及表1—2"),
        ("煤粉制备与喷吹", "煤粉系统包括磨煤、输送和喷吹设备；核对燃料投入、设备运行和产排污环节。", "iron_air", "PDF第4—6页，3.8及表1—2"),
        ("热风制备与鼓风", "热风炉加热鼓风并向高炉供风，热风炉排气筒的污染物与高炉其他设施分开核验。", "iron_air", "PDF第5—6页，3.6、4.2及表2"),
        ("高炉还原与熔炼", "炉料由炉顶加入、下部鼓风，经历加热、还原、熔化和造渣，形成生铁与高炉渣。", "iron_air", "PDF第4页，3.1"),
        ("出铁、渣铁分离与烟气收集", "出铁场属于独立产排污环节，应核对集气、除尘、排口和运行记录。", "iron_air", "PDF第6页，表2原料系统/高炉出铁场"),
        ("高炉煤气回收与余能利用", "副产煤气及炉顶压力等余能的回收利用须与能源台账、设备运行和发电量对应。", "steel_decarbon", "PDF第3页，二（四）"),
    ]
    for name, text, src, loc in process_rows:
        rows.append(item("process", name, text, src, loc, "source_derived"))
    equipment_rows = [
        ("贮矿仓与槽下筛分设备", "原料贮存、筛分、称量和上料设施，核对处理能力与产能匹配。", "iron_air", "PDF第4—6页，3.7及表1—2"),
        ("煤磨、输送与喷吹设备", "煤粉制备系统设备，核对燃料边界、设备状态和粉尘治理。", "iron_air", "PDF第4—6页，3.8及表1—2"),
        ("热风炉", "高炉供风系统的蓄热式换热装置，核对排口与颗粒物、二氧化硫和氮氧化物。", "iron_air", "PDF第5页，3.6"),
        ("出铁场集气除尘设施", "出铁场烟气收集与除尘系统，核对罩口、管道、除尘器和排气筒边界。", "iron_air", "PDF第6页，表2"),
        ("封闭式机械化料场", "行动计划明确推广封闭式机械化料场，核对本次改造设备和实际投运范围。", "steel_decarbon", "PDF第3页，二（三）"),
        ("高炉炉顶余压/煤气利用设备", "用于高炉炉顶均压煤气和副产煤气等余能回收，不能用设计参数替代实际运行。", "steel_decarbon", "PDF第3页，二（四）"),
        ("制氧机、空压机、水泵、风机和变压器", "行动计划列明的通用用能设备，需对照先进、节能和准入水平核验更新。", "steel_decarbon", "PDF第3页，二（三）"),
        ("能耗在线监测与智慧能源管理系统", "采集生产过程能耗和碳排放数据，核对计量点、数据链路和原始记录。", "steel_decarbon", "PDF第4—5页，二（七）"),
    ]
    for name, text, src, loc in equipment_rows:
        rows.append(item("equipment", name, text, src, loc, "source_derived"))
    rows += [
        item("route", "富氢碳循环氧气高炉路线（条件路线）", "在现有高炉开展富氢碳循环氧气高炉低碳冶金；只有项目材料明确该技术和边界时启用。", "steel_decarbon", "PDF第4页，二（六）", "source_derived"),
        item("standard", "粗钢生产主要工序单位产品能源消耗限额", "只用于识别GB 21256-2025的现行状态、实施日期和替代关系；公开渠道未取得全文，不从元数据补写2025版能耗数值。", "iron_energy_standard", "官方元数据页，标准号GB 21256-2025、实施日期2026-07-01及替代关系", "policy_explicit",
             standard_no="GB 21256-2025", full_text_status="official_summary_only", applicability="高炉、转炉、电弧炉等粗钢生产主要工序；具体能耗要求待取得标准全文后核对"),
        item("standard", "企业温室气体排放核算与报告指南 钢铁行业", "按企业核算边界组织钢铁行业温室气体数据，不替代高炉工序能耗或排放限值。", "iron_carbon_accounting", "PDF第1—8页，适用范围、核算边界与数据质量", "policy_explicit",
             standard_no="CETS—AG—03.01—V01—2024", full_text_status="full_text_obtained", applicability="适用主体的企业级温室气体核算与报告"),
    ]
    indicator_rows = [
        ("高炉工序单位产品能耗同比降幅", "%", "到2025年底，高炉工序单位产品能耗比2023年降低1%以上。", "steel_decarbon", "PDF第1页，主要目标"),
        ("热风炉颗粒物排放浓度", "mg/m³", "按热风炉排气筒和适用的一般/特别限值核验。", "iron_air", "PDF第5—6页，3.4及表2—3"),
        ("热风炉二氧化硫排放浓度", "mg/m³", "按热风炉排气筒和适用区域、时间核验。", "iron_air", "PDF第5—6页，3.4及表2—3"),
        ("热风炉氮氧化物排放浓度", "mg/m³", "按以NO2计的标准状态干气体浓度核验。", "iron_air", "PDF第5—6页，3.4及表2—3"),
        ("原料、煤粉及出铁场颗粒物浓度", "mg/m³", "按具体生产设施排气筒和适用限值核验。", "iron_air", "PDF第6页，表2—3"),
        ("余热余压余能自发电率变化", "百分点", "到2025年底钢铁行业余热余压余能自发电率比2023年提高3个百分点以上；属行业目标。", "steel_decarbon", "PDF第1页，主要目标"),
    ]
    for name, unit, text, src, loc in indicator_rows:
        rows.append(item("indicator", name, text, src, loc, "policy_explicit", unit=unit,
                         scope="按来源限定的工序、设施或行业目标范围", stage="贷前基线/贷中落实/贷后实绩"))
    permits = [
        ("钢铁冶炼项目产能置换前置核验", "立项/建设前", "严禁以机械加工、铸造或铁合金名义新增钢铁产能，并核验产能置换。", "PDF第1—2页，二（一）—（二）"),
        ("固定资产投资项目节能审查", "建设前", "新建和改扩建钢铁冶炼项目严格实施节能审查，主要用能设备达到适用能效要求。", "PDF第2页，二（二）"),
        ("建设项目环境影响评价审批", "建设前", "新建和改扩建项目严格实施环评审批，并核对总量控制和区域削减等要求。", "PDF第2页，二（二）"),
        ("煤炭消费减量替代及污染物总量/区域削减条件", "建设前", "不符合煤炭消费减量替代、重点污染物总量控制或区域削减要求的项目不得据此进入通过状态。", "PDF第2页，二（二）"),
    ]
    for name, stage, text, loc in permits:
        rows.append(item("permit", name, text, "steel_decarbon", loc, "policy_explicit", stage=stage,
                         region="全国；大气污染防治重点区域和属地更严要求另核"))
    documents = [
        ("项目必要性与可行性评估材料", "新建/改扩建论证", "对应行动计划提出的新建钢铁冶炼项目必要性和可行性评估论证。", "PDF第2页，二（二）"),
        ("产能置换方案及落实证明", "建设前", "证明产能来源、规模和置换落实，防止以其他名义新增钢铁产能。", "PDF第1—2页，二（一）—（二）"),
        ("节能审查意见及落实材料", "建设/投产", "将设备、工序能效和审查条件对应到本次建设范围。", "PDF第2页，二（二）"),
        ("环境影响评价文件及批复", "建设前", "核对项目边界、污染治理、总量控制及区域削减条件。", "PDF第2页，二（二）"),
        ("主要用能设备更新清单", "技改融资核验", "列明电机、锅炉、制氧机、空压机、水泵、风机、变压器等设备型号、位置和更新状态。", "PDF第3页，二（三）"),
    ]
    for name, stage, text, loc in documents:
        rows.append(item("document", name, text, "steel_decarbon", loc, "policy_explicit", stage=stage))
    evidence = [
        ("产能置换与项目规模", "项目产能、置换来源、设备能力与审批文件一致。", "steel_decarbon", "PDF第1—2页，二（一）—（二）"),
        ("高炉工序能源边界", "能源计量点、输入输出、吨铁产量和统计期间可追溯。", "iron_energy", "PDF第5页炼铁行及第7页注释"),
        ("原燃料与炉料记录", "矿石、焦炭、喷吹煤等采购、计量和生产领用记录勾稽。", "iron_permit", "PDF第6—10页，4.2—4.4"),
        ("热风炉排放证据", "排气筒、污染因子、监测原始值、工况和适用限值逐项对应。", "iron_air", "PDF第5—7页，3.4、4—5章"),
        ("出铁场与原料系统除尘", "设施清单、集气罩、除尘器、排口及运行台账形成闭环。", "iron_air", "PDF第6页，表2—3"),
        ("治理设施运行", "运行时间、参数、耗材和异常记录与生产负荷相匹配。", "iron_monitor", "PDF第10—11页，5—6章"),
        ("余能回收与自发电", "煤气/余压输入、设备运行、发电量和结算记录交叉验证。", "steel_decarbon", "PDF第3页，二（四）"),
        ("设备更新资金用途", "合同、发票、设备铭牌、安装位置、验收和付款对象一致。", "steel_decarbon", "PDF第3页，二（三）"),
        ("碳排放核算边界", "组织边界、排放源、活动数据、排放因子和凭证可追溯。", "iron_carbon_accounting", "PDF第1—12页，核算边界与数据质量"),
        ("贷后能效兑现", "基准年、政策目标、实际工序能耗和改造投运时间保持同口径。", "steel_decarbon", "PDF第1、7页，主要目标及监督管理"),
        ("清洁运输与新能源改造", "运量、运输方式和车辆机械清单支持所披露的清洁运输成效。", "steel_decarbon", "PDF第3页，二（三）"),
    ]
    for name, text, src, loc in evidence:
        rows.append(item("evidence", name, text, src, loc, "source_derived", acceptable=text,
                         unacceptable="企业口头说明、无法对应本项目的全厂汇总或无原始凭证截图", stage="按项目和贷后节点触发"))
    risks = [
        ("产能置换边界不实", "以技改或其他行业名义新增冶炼产能。", "核对产能、设备和主管部门置换信息。", "steel_decarbon", "PDF第1—2页"),
        ("新改扩建能效条件不落实", "项目方案承诺标杆水平，但设备选型或实绩不能支持。", "对齐节能审查、设备参数和投运实绩。", "steel_decarbon", "PDF第2页"),
        ("一般排放限值错误套用", "忽略特别排放地区、属地标准或许可证更严要求。", "按所在地、设施和时间筛选适用规则。", "iron_air", "PDF第3、6页，前言及4.4"),
        ("排污许可证边界遗漏", "只核对高炉主体而遗漏原料、煤粉、出铁场或配套排口。", "用生产设施—排放口—污染因子矩阵复核。", "iron_permit", "PDF第6—15页，4—5章"),
        ("治理设施与生产负荷脱节", "治理设施记录缺失或停运时仍以平均数据宣称达标。", "比对生产、治理和监测时序。", "iron_monitor", "PDF第10—11页，5—6章"),
        ("节能设备替换未真实投运", "发票合同存在但设备型号、安装位置或运行时间不对应。", "穿透核对铭牌、验收和运行记录。", "steel_decarbon", "PDF第3页，二（三）"),
        ("余能利用绩效重复计算", "煤气、余压或余热收益在多个项目/指标中重复归集。", "核对计量边界、发电结算和归属期间。", "steel_decarbon", "PDF第3页，二（四）"),
        ("企业碳总量替代工序指标", "企业总排放不能直接证明高炉吨铁能耗或排放强度。", "分开企业核算边界和高炉工序边界。", "iron_carbon_accounting", "PDF第1—12页"),
    ]
    for name, text, review, src, loc in risks:
        rows.append(item("risk", name, text, src, loc, "source_derived", category="行业技术与合规落实", review_focus=review))
    terms = [
        ("出铁场", "高炉铁水和炉渣排出、分离及转运的作业区域，对应独立粉尘产排污环节。", "iron_air", "PDF第6页，表2"),
        ("煤粉喷吹", "将制备后的煤粉输送并喷入高炉的燃料替代和冶炼工艺环节。", "iron_air", "PDF第4—6页，3.8及表2"),
        ("高炉煤气", "高炉冶炼产生的副产煤气，可回收用于燃料或发电，须明确计量边界。", "steel_decarbon", "PDF第3页，二（四）"),
        ("余热余压余能自发电率", "利用生产过程余热、余压和副产煤气等自发电量的行业绩效指标。", "steel_decarbon", "PDF第1、3页"),
        ("高炉—转炉长流程", "以高炉炼铁、转炉炼钢为核心的钢铁生产流程，和电炉短流程分开定标。", "steel_decarbon", "PDF第4页，二（五）—（六）"),
        ("富氢碳循环氧气高炉", "在高炉路线中引入富氢和碳循环氧气等技术的低碳冶金方向，非所有高炉项目默认配置。", "steel_decarbon", "PDF第4页，二（六）"),
        ("能效标杆水平", "政策用于引导先进产能的对标水平，须按对应年度文件和统计口径解释。", "steel_decarbon", "PDF第1—2、5页"),
        ("环保绩效A级", "重点行业绩效分级中的A级水平，不能仅凭排放达标或企业自评认定。", "steel_decarbon", "PDF第2、5页"),
    ]
    for name, text, src, loc in terms:
        rows.append(item("term", name, text, src, loc, "source_derived", usage="辅助阅读；适用条件以原政策/标准为准。"))
    rows.append(item("postloan", "高炉工序能耗同比变化", "以2023年同口径基准与贷后实际单位产品能耗比较，保留产量、能源和计算边界。",
                     "steel_decarbon", "PDF第1页，主要目标", "source_derived", frequency="月度台账、年度同口径复核",
                     evidence_object="工序能源计量、产量、能耗计算与节能审查落实材料"))
    rows.append(item("postloan", "余热余压余能回收系统运行与自发电兑现", "跟踪回收设备实际投运、可利用余能输入、自发电量及与2023年同口径基准的变化；政策“提高3个百分点以上”为行业目标，不直接作为单户通过阈值。",
                     "steel_decarbon", "PDF第1页主要目标及第3页二（四）", "source_derived", frequency="月度运行监测、年度同口径复核",
                     evidence_object="余能回收设备台账、运行记录、输入能源计量、自发电量与结算记录"))
    return rows


def _wind_items():
    rows = []
    processes = [
        ("海上风电方法学适用性筛选", "先核对是否离岸30公里以外或水深大于30米，再决定是否启用CCER海上风电规则。", "PDF第1页，2适用条件"),
        ("项目边界确定", "边界包括项目发电及配套设施和所在区域电网发电设施，需确认设备和地理边界。", "PDF第2页，5.1及图1"),
        ("计入期确定", "以并网发电日期为寿命期开始，计入期在寿命期内且最长不超过10年。", "PDF第2页，5.2"),
        ("净上网电量核算", "上网电量减去下网电量形成净上网电量，两个计量点和结算凭证分别核对。", "PDF第3页，公式（2）"),
        ("基准线与减排量核算", "净上网电量乘区域电网组合边际排放因子形成基准线排放，再扣减项目排放。", "PDF第3—4页，6.3—6.6"),
        ("监测、校准与数据归档", "制定监测方案，持续采集电量，校准电能表，交叉核对结算凭证并归档。", "PDF第5—7页，7.2—7.3"),
    ]
    for name, text, loc in processes:
        rows.append(item("process", name, text, "wind_ccer", loc, "source_derived"))
    equipment = [
        ("风力发电机组", "项目发电核心设备，核对机组数量、型号、容量、并网日期和项目边界。", "PDF第1—2页，1、5.1"),
        ("塔架与基础", "风机支撑及基础工程，标准名录列有设计、施工和安全监测规范。", "名录PDF第166—171页（印刷页155—160），6.2.1及6.2.2.1"),
        ("风轮叶片与变桨系统", "机组能量捕获和控制部件，标准名录列有叶片、变桨系统检修和技术规范。", "名录PDF第168—171页（印刷页157—160），6.2.2.1"),
        ("发电机、变流器与控制系统", "机组电气转换和控制设备，核对型号、改造范围和实际投运。", "名录PDF第167—171页（印刷页156—160），6.2.2.1"),
        ("升压变压器", "将机组/场内集电电压升高并接入电网，范围须与升压站和送出工程对应。", "名录PDF第167页（印刷页156），6.2.2.1第1项"),
        ("场内集电线路", "汇集机组电能至升压站的线路，不与场外送出工程或其他主体资产混同。", "名录PDF第170—172页（印刷页159—161），集电系统相关标准"),
        ("并网计量电能表", "在并网协议明确的上、下网计量点连续监测，准确度和校准须满足方法学。", "PDF第5—8页，表4—5及8.3—8.4"),
        ("监控、功率控制与数据系统", "风电场监控、功率控制和数据质量系统用于运行及贷后实绩核验。", "名录PDF第168—171页（印刷页157—160），监控和功率控制标准"),
    ]
    for name, text, loc in equipment:
        src = "wind_ccer" if "PDF第" in loc and not loc.startswith("名录") else "wind_standards"
        rows.append(item("equipment", name, text, src, loc, "source_derived"))
    rows.append(item("route", "CCER适用的并网海上风电路线（条件路线）", "仅对离岸30公里以外或水深大于30米的并网海上风电项目启用减排量核算、监测和核查规则。",
                     "wind_ccer", "PDF第1页，2适用条件", "source_derived"))
    standards = [
        ("GB 51096-2015", "风力发电场设计规范", "名录PDF第166页（印刷页155），6.2.1第1项"),
        ("GB/T 18451.1-2022", "风力发电机组 设计要求", "名录PDF第167页（印刷页156），6.2.2.1第3项"),
        ("GB/T 19963.1-2021", "风电场接入电力系统技术规定 第1部分：陆上风电", "名录PDF第167页（印刷页156），6.2.2.1第8项"),
        ("GB/T 31997-2015", "风力发电场项目建设工程验收规程", "名录PDF第168页（印刷页157），6.2.2.1第24项"),
        ("DL/T 666-2012", "风力发电场运行规程", "名录PDF第168页（印刷页157），6.2.2.1第37项"),
        ("DL/T 796-2012", "风力发电机组安全规程", "名录PDF第168页（印刷页157），6.2.2.1第39项"),
        ("DL/T 797-2012", "风力发电检修规程", "名录PDF第168页（印刷页157），6.2.2.1第40项"),
        ("NB/T 10640-2021", "风电场运行风险管理规程", "名录PDF第170页（印刷页159），6.2.2.1第101项"),
    ]
    for no, name, loc in standards:
        rows.append(item("standard", name, "该来源仅证明标准引用和名录状态；技术条款、阈值和适用版本仍须取得标准全文后核对。",
                         "wind_standards", loc, "policy_explicit", standard_no=no, full_text_status="official_summary_only",
                         applicability="风电设计、接网、验收、运行、安全、检修或风险管理；按项目活动选用"))
    indicators = [
        ("海上风电方法学空间适用条件", "km/m", "离岸距离或水深决定CCER方法学是否适用。", "PDF第1页，2适用条件"),
        ("项目净上网电量", "MWh", "上网电量减去下网电量，按并网协议计量点采集。", "PDF第3页，公式（2）"),
        ("基准线排放量", "tCO2", "净上网电量乘项目所在区域电网组合边际排放因子。", "PDF第3页，公式（1）"),
        ("项目排放量", "tCO2", "方法学将风力发电机组维护车辆使用化石燃料产生的项目排放视为很小，在核算中取0。", "PDF第2页，5.3表1"),
        ("项目减排量", "tCO2", "基准线排放量扣除项目排放量；方法学项目排放按规定处理。", "PDF第4页，公式（4）"),
        ("电能表准确度等级", "级", "上、下网计量电能表准确度等级不低于0.5级。", "PDF第5页，表4—5"),
        ("监测数据完整性", "月/记录", "上、下网电量连续监测并至少每月记录一次，与结算凭证交叉核对。", "PDF第5—7页，表4—5及7.3"),
    ]
    for name, unit, text, loc in indicators:
        rows.append(item("indicator", name, text, "wind_ccer", loc, "policy_explicit", unit=unit,
                         scope="仅CCER方法学适用的并网海上风电项目", stage="项目设计/实施/贷后核查"))
    thresholds = [
        ("离岸距离适用条件", 30, ">", "km", "离岸30公里以外；与水深条件为二选一", "PDF第1页，2适用条件"),
        ("水深适用条件", 30, ">", "m", "水深大于30米；与离岸距离条件为二选一", "PDF第1页，2适用条件"),
        ("项目计入期上限", 10, "<=", "年", "CCER项目计入期，且须在项目寿命期内", "PDF第2页，5.2"),
        ("电能表准确度等级", 0.5, "<=", "级", "上、下网计量点电能表；数值越小准确度越高", "PDF第5页，表4—5"),
        ("电能表校准最长间隔", 12, "<=", "月", "项目运行期间由具备CNAS或CMA资质的第三方校准", "PDF第6页，7.3.2.1"),
        ("异常电能表校准期限", 30, "<=", "天", "误差超限或故障时触发", "PDF第6页，7.3.2.2"),
        ("末期登记后数据保存期限", 10, ">=", "年", "项目设计和实施阶段全部数据、信息电子存档", "PDF第6页，7.3.3.1"),
    ]
    for name, value, op, unit, scope, loc in thresholds:
        rows.append(item("threshold", name, f"{name}{op}{value}{unit}；{scope}。", "wind_ccer", loc, "policy_explicit",
                         value=value, operator=op, unit=unit, scope="仅CCER-01-002-V01适用的并网海上风电项目；" + scope,
                         effective_at="2023-10-24"))
    docs = [
        ("CCER项目设计文件与监测计划", "项目设计/登记", "明确边界、计入期、监测点、参数、程序、职责和数据管理。", "PDF第4—7页，7.1—7.3"),
        ("用海批复及海域使用论证报告", "适用性审定", "用于证明离岸距离、水深、项目地理边界和用海合规。", "PDF第7页，8.1—8.2"),
        ("电能表检定校准报告", "建设/运行", "安装前检定，运行期按要求由有资质第三方校准并留存报告。", "PDF第6—7页，7.3.2"),
    ]
    for name, stage, text, loc in docs:
        rows.append(item("document", name, text, "wind_ccer", loc, "policy_explicit", stage=stage))
    evidence = [
        ("离岸距离与水深", "用海批复、论证报告、等深线或测绘材料证明方法学适用性。", "PDF第7页，8.1.1"),
        ("项目地理边界", "批复、可研、电力接线图与坐标资料证明边界和设备设施。", "PDF第7页，8.2"),
        ("项目并网日期", "并网记录和调度/结算资料证明寿命期开始时间。", "PDF第2页，5.2.1"),
        ("上网电量", "主表读数、检定校准和结算凭证交叉核对。", "PDF第5、8页，表4及表8"),
        ("下网电量", "下网表读数、检定校准和结算凭证交叉核对。", "PDF第5、8页，表5及表8"),
        ("电能表准确度", "铭牌、检定和校准报告证明准确度与有效期。", "PDF第5—6页，表4—5及7.3.2"),
        ("区域电网排放因子", "使用生态环境部组织公布的适用年度/最近可得官方数据。", "PDF第6、8页，表6—8"),
        ("监测计划执行", "监测方案、职责、原始台账和异常校正记录相互对应。", "PDF第6—7页，7.3"),
        ("项目设施清单", "风机及配套设施清单与可研、环评、接线图和现场一致。", "PDF第2、7页，5.1及8.2"),
        ("减排量核算链", "净电量、排放因子、基准线和减排量逐层可复算。", "PDF第3—4页，6.3—6.6"),
        ("贷后数据归档", "电子原始数据、结算凭证、检定校准和维护记录可追溯。", "PDF第6—7页，7.3.3"),
    ]
    for name, text, loc in evidence:
        rows.append(item("evidence", name, text, "wind_ccer", loc, "source_derived", acceptable=text,
                         unacceptable="仅企业汇总、宣传材料或无法对应计量点/本项目边界的数据", stage="CCER条件适用项目的设计、实施和核查"))
    risks = [
        ("方法学适用条件误套", "将陆上或不满足距离/水深条件的海上风电套用CCER方法学。", "先核对距离、水深和并网海上属性。", "PDF第1页，2"),
        ("项目与配套设施边界遗漏", "风机、集电、升压或送出设施在不同材料中范围不一致。", "用坐标、接线图和设备清单分层核对。", "PDF第2、7页，5.1及8.2"),
        ("上网电量与下网电量混用", "只取上网结算量而遗漏下网电量会高估净上网电量。", "分别核对两个计量点及公式。", "PDF第3、5、8页"),
        ("计量设备未校准", "电能表逾期校准、误差超限或故障但未按规定处理。", "核对检定校准期限、资质和保守校正。", "PDF第6—7页，7.3.2—7.3.4"),
        ("区域电网排放因子年份错误", "使用非官方、错误区域或错误年度因子。", "核对上传核查报告时的官方可得数据。", "PDF第6、8页，表6—8"),
        ("计入期越界", "计入期超过10年或超出项目寿命期。", "核对并网日期、退役安排和申请期间。", "PDF第2页，5.2"),
        ("原始数据不可追溯", "只有汇总表而缺少读数、凭证、校准和责任人记录。", "穿透核对原始台账与电子归档。", "PDF第6—7页，7.3.3"),
        ("减排量重复归属", "同一电量或减排量被不同融资/项目边界重复主张。", "核对项目登记、计量点、期间和权益归属。", "PDF第2—4页，5—6章"),
    ]
    for name, text, review, loc in risks:
        rows.append(item("risk", name, text, "wind_ccer", loc, "source_derived", category="绿色主张可信性", review_focus=review))
    terms = [
        ("并网海上风力发电", "在海域开展、与电网物理连接并建立调度关系的风力发电活动。", "PDF第1页，4.1—4.2"),
        ("项目边界", "包括项目发电及配套设施，以及方法学规定的所在区域电网发电设施。", "PDF第2页，5.1"),
        ("项目计入期", "可申请项目减排量登记的时间期限，须位于项目寿命期限内。", "PDF第2页，5.2"),
        ("净上网电量", "项目输送至区域电网的上网电量减去区域电网输送至项目的下网电量。", "PDF第3页，公式（2）"),
        ("组合边际排放因子", "电量边际与容量边际排放因子按方法学权重组合的区域电网因子。", "PDF第3页，公式（3）"),
        ("基准线排放量", "没有该项目时由区域电网其他并网发电厂替代生产电量对应的排放。", "PDF第3页，6.1、6.3"),
        ("额外性", "项目相对于基准线情景的额外减排属性；符合本方法学适用条件的项目免予论证。", "PDF第3页，6.2"),
        ("保守性校正", "计量设备未校准、延迟校准或误差超限时，对电量采用不高估减排量的调整。", "PDF第7页，7.3.4"),
    ]
    for name, text, loc in terms:
        rows.append(item("term", name, text, "wind_ccer", loc, "source_derived", usage="辅助阅读；仅在相应方法学边界使用。"))
    postloan = [
        ("月度净上网电量", "连续监测上、下网电量并计算净上网电量。", "连续监测，至少每月记录一次", "电能表读数和电量结算凭证", "PDF第5页，表4—5"),
        ("电能表校准与异常处置", "跟踪年度校准、故障、误差超限及保守校正。", "至少年度校准；异常30天内处理", "检定校准、维修更换和校正计算记录", "PDF第6—7页，7.3.2—7.3.4"),
        ("减排量核算与数据归档", "按年度可复算基准线和减排量并保留全链路证据。", "减排量登记/核查期；数据保存不少于规定年限", "核算报告、官方排放因子、原始台账与归档清单", "PDF第3—8页，6—8章"),
    ]
    for name, text, freq, evidence_obj, loc in postloan:
        rows.append(item("postloan", name, text, "wind_ccer", loc, "source_derived", frequency=freq, evidence_object=evidence_obj))
    return rows


SHOWCASE_ITEMS = {
    "3011": _cement_items(),
    "3110": _iron_items(),
    "4415": _wind_items(),
}

SOURCE_ALIASES = {
    "iron_air": "炼铁工业大气污染物排放标准",
    "iron_energy": "工业重点领域能效标杆水平和基准水平（2023年版）",
    "iron_energy_standard": "粗钢生产主要工序单位产品能源消耗限额（现行标准登记信息）",
    "iron_permit": "排污许可证申请与核发技术规范 钢铁工业",
    "iron_monitor": "排污单位自行监测技术指南 钢铁工业及炼焦化学工业",
    "iron_carbon_accounting": "企业温室气体排放核算与报告指南 钢铁行业",
}
