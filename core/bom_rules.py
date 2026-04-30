"""
BOM 通用规则层 — 供所有 BOM 分析脚本共享的**标准分类规则**。

设计原则:
  ★ 规则只识别**零件类别/功能**, 不包含任何机型代号、品牌名、具体 PN。
  ★ 具体型号 (主控/驱动 IC/RAM/ROM 的 PN) 由 components_lib.csv 的
    model_numbers 字段维护, Stage 4 查价时按桶 + model_numbers 精确匹配。
  ★ 本文件可公开 / 跨项目复用; components_lib.csv 则按机型维护 (含供应商价)。

提供:
  - KEYWORD_RULES: 标准 BOM 词汇 → (桶, lib_hint, note) 映射
  - AUX_PATTERN / aux_price(): 辅料识别 + 分档兜底价
  - classify(name, spec, region): 单行归桶 + 给出 lib 查价 hint
  - is_aggregate(note): 判断是否为聚合件 (整机合计一次)

消费者:
  - scripts/analyze_c33.py (自家 BOM 细粒度分析, 内部)
  - scripts/gen_teardown.py (LLM 产出的竞品 BOM 二次归桶 + 查价提示)
  - scripts/analyze_*.py (其他机型扩展)
"""
from __future__ import annotations

import re

# ── 辅料关键词 (小件跨桶识别) ─────────────────────────────────
# 匹配时按辅料低价估算, 避免被高价主件型号污染
AUX_PATTERN = re.compile(
    r"硅胶|硅橡胶|O型圈|挡圈|卡簧|垫片|弹簧|泡棉|EVA|海绵|遮光棉|保护膜|"
    r"消音棉|防水圈|减震|过线圈|拉簧|介子|胶套|胶塞|喇叭套|磁铁|磁环|"
    r"(支架|盖板|下壳|上壳|前盖|后盖|面盖|装饰片|装饰件|固定盖|定位支架)$|"
    r"(风道|风机压盖|风机.*盖|流道|消音)|"
    r"导柱|导向|转轴|卡扣|脚垫|"
    r"(贴纸|铭牌|指引贴|提示贴|标贴|丝印|膜片)|"
    r"螺丝|螺母|锁扣|"
    r"(连接线|端子|线束|硅胶套|EVA棉|水管|气管|接头|软管|转接管|排水门|进水门)|"
    r"(过滤网|滤网|过滤支架|刮条|活塞杆|轴套|密封条|密封胶|密封圈|密封塞)"
)
AUX_PRICE_MICRO = 0.1   # 贴纸/铭牌/丝印
AUX_PRICE_TINY  = 0.3   # 螺丝/螺母/O型圈
AUX_PRICE_SMALL = 0.8   # 硅胶圈/泡棉/小支架
AUX_PRICE_MID   = 2.0   # 普通注塑小件/连接线/管路
AUX_PRICE_LARGE = 5.0   # 大件注塑盖板/长风道

# ── 关键词 → 桶归类规则 (仅用于分类 + 查价 hint, 不直接定价) ──────────────
# (regex, bucket, lib_key_hint, note)
# lib_key_hint: 用于在 components_lib.csv 中定位对应条目的 name/model 子串
# note: 带 "(聚合)" 的规则表示整机合计一次, 不按 qty 累加
KEYWORD_RULES: list[tuple[str, str, str, str]] = [
    # 电池
    (r"锂电池|电池包|18650", "energy", "锂电池包", "电池包"),
    (r"BMS|电池保护板|充放电保护",       "energy", "BMS保护板", "BMS"),
    (r"电池.*连接线|电池.*线束|电池卡扣", "energy", "BMS保护板", "电池辅助件(聚合)"),
    # 结构CMF — LDS 周边装饰件 (必须放在 LDS/雷达 规则之前)
    (r"LDS盖|LDS装饰|LDS硅胶|LDS.*硅胶|LDS.*装饰|LDS.*盖|激光雷达.*(盖|硅胶|装饰)",
     "structure_cmf", "LDS装饰", "LDS装饰件"),
    # 感知
    (r"LDS组件|LDS模组|激光雷达|雷达",           "perception", "LDS激光雷达", "激光雷达(聚合)"),
    (r"TOF模块|ToF模组|dToF模块|dToF|ToF",       "perception", "TOF模块", "ToF模块"),
    (r"沿墙.*(激光|组件)|右沿墙|左沿墙",  "perception", "沿墙线激光模块", "沿墙线激光(聚合)"),
    (r"线激光|结构光|前视.*模组|RGB.*模组", "perception", "前视线激光", "前视避障(聚合)"),
    (r"超声波",                            "perception", "超声波模块", "超声波"),
    (r"IMU|陀螺仪.*加速|六轴传感器|加速度.*陀螺", "perception", "IMU", "IMU"),
    (r"红外发射管",                  "perception", "红外发射管", "红外发射"),
    (r"红外镜片|回充镜片",           "perception", "回充信号接收", "回充镜片"),
    (r"地毯识别|沿墙传感",           "perception", "超声波模块", "地毯/沿墙"),
    (r"碰撞.*PCB|碰撞传感|碰撞开关", "perception", "碰撞传感组件", "碰撞传感(聚合)"),
    (r"麦克风|MIC模组",              "perception", "麦克风", "麦克风"),
    (r"霍尔开关IC|霍尔检测|霍尔板",  "perception", "霍尔开关", "霍尔开关"),
    (r"地检|下视",                   "perception", "地检", "下视/地检(聚合)"),
    # 清洁
    # 拖布按形态分 3 类: 履带/滚筒/双转盘. 录入必须指明形态, 不接受裸"拖布"
    (r"履带拖布|宽幅.*拖布",         "cleaning", "履带拖布", "履带拖布(聚合)"),
    (r"滚筒拖布|短滚筒.*拖布",       "cleaning", "滚筒拖布", "滚筒拖布(聚合)"),
    (r"双转盘拖布|圆盘拖布|拖布.*圆盘", "cleaning", "双转盘拖布", "双转盘拖布(聚合)"),
    (r"拖布支架|拖布盘|拖布机械臂|拖布安装|拖布抬升|拖布伸缩|拖布震动|拖布电机|拖布.*防滑|拖布.*胶",
     "cleaning", "拖布支架", "拖布系统(聚合)"),
    (r"浮动中扫|滚刷.*电机|滚刷盖板|滚刷组件|滚刷本体|^主滚刷$|零缠绕滚刷",
     "cleaning", "浮动中扫", "滚刷系统(聚合)"),
    (r"主机边扫|边扫包胶|边扫组件|边刷电机|^边刷$", "cleaning", "边扫组件", "边刷(聚合)"),
    (r"^主机风机\|\||^风机\|\||主机风机、|主机吸尘风机",
     "power_motion", "主机吸尘风机", "吸尘风机"),
    (r"注清水泵|清水泵|加清泵",              "cleaning", "注清水泵", "注清水泵"),
    (r"清水盒|机身水箱|主机清水箱|^清水箱$",                     "cleaning", "清水盒", "主机水箱(聚合)"),
    (r"污水盒|主机污水箱|^污水箱$",                              "cleaning", "污水盒", "主机污水盒(聚合)"),
    (r"污水吸气|吸污管|吸污水管|^污水泵$",            "cleaning", "污水盒", "吸污管路(聚合)"),
    (r"进水阀",                              "cleaning", "清水盒", "进水阀(聚合)"),
    (r"主机尘盒|尘盒组件|尘盒上壳|尘盒底壳|尘盒面壳|尘盒.*本体|尘盒.*盖|尘盒.*轴|尘盒.*按",
     "cleaning", "主机尘盒", "主机尘盒(聚合)"),
    # 基站
    (r"基站电源板",                              "dock_station", "基站电源板", "基站电源板"),
    (r"集尘风机组件",                            "dock_station", "基站集尘风机", "集尘风机组件(聚合)"),
    (r"消音腔组件|过滤网组件|过滤支架组件",       "dock_station", "基站集尘风机", "消音腔/过滤网(聚合)"),
    (r"集尘风机|集尘电机",                       "dock_station", "基站集尘风机", "集尘风机"),
    (r"集尘管|集尘转接|集尘腔|集尘袋|集尘.*面盖","dock_station", "集尘管路", "集尘管路/袋(聚合)"),
    (r"水加热|高温.*洗|100.?C.*洗|100°C.*洗|高温热水",
     "dock_station", "水加热", "水加热"),
    (r"热风烘干|烘干模组|烘干风机.*加热|烘干舱",
     "dock_station", "热风烘干", "热风烘干"),
    (r"UV.*灯|紫外.*杀菌|UV.*杀菌|UV.?LED",
     "dock_station", "UV", "UV杀菌"),
    (r"基站.*水泵|抽水泵|排水泵|活水.*泵",
     "dock_station", "基站水泵", "基站水泵"),
    (r"加热烘干|烘干风扇|加热PTC|PTC模组|PTC加热","dock_station", "PTC加热", "加热烘干(聚合)"),
    (r"污水气泵|污水泵.*组件|污水顶杆|排污顶杆|顶杆电机",
     "dock_station", "污水气泵", "污水气泵(聚合)"),
    (r"顶杆减速电机",                            "dock_station", "顶杆减速电机", "顶杆电机"),
    (r"顶杆检测线|顶杆.*(开关|霍尔|传感)",        "dock_station", "基站传感开关", "顶杆检测(聚合)"),
    (r"顶杆|升降齿条|升降.*齿",                  "dock_station", "顶杆机构", "顶杆机构(聚合)"),
    (r"电磁阀",                                  "dock_station", "电磁阀", "电磁阀"),
    (r"清洗盘|清洗水泵|清洗.*拖布",              "dock_station", "清洗盘", "清洗盘(聚合)"),
    (r"基站.*清水|清水桶",                       "dock_station", "基站清水桶", "基站清水桶(聚合)"),
    (r"基站.*污水|污水桶|污水槽",                "dock_station", "基站污水桶", "基站污水桶(聚合)"),
    (r"充电弹片|回充组件|红外回充组件|充电极片|充电线",
     "dock_station", "充电弹片", "回充/充电(聚合)"),
    (r"^AC电源线|基站电源线|基站.*220V",         "dock_station", "AC电源线", "基站AC供电"),
    (r"基站上盖|基站后盖|基站底壳|基站中壳|基站隔板|基站.*盖板|基站尘盖|基站外壳|基站裸机",
     "dock_station", "基站外壳", "基站外壳(聚合)"),
    (r"基站.*PCBA|基站顶杆开关板|基站.*霍尔.*板|基站按键灯板|回充.*PCB|基站.*PCB",
     "dock_station", "基站子PCBA", "基站子PCBA(聚合)"),
    (r"^(轻触开关|微动开关|水位检测|浮球|霍尔开关|磁铁座)|基站.*(按键|指示灯|LED灯珠)",
     "dock_station", "基站传感开关", "基站传感开关(聚合)"),
    (r"(水桶|水箱|水泵|水路).*(轴|轴芯|弹簧|防折|顶针|按键|卡扣)|排水门|进水门",
     "dock_station", "基站水路杂件", "基站水路杂件(聚合)"),
    # 动力
    (r"履带抬升|底盘升降|底盘抬升",
     "power_motion", "底盘升降", "底盘升降电机"),
    (r"履带牙箱|履带.*电机|履带.*组件|履带驱动",
     "power_motion", "履带驱动", "履带驱动(聚合)"),
    (r"驱动轮.*电机|驱动轮.*编码|驱动轮",         "power_motion", "履带驱动", "驱动轮电机"),
    (r"边轮|左边轮|右边轮",                       "power_motion", "边轮组件", "边轮组件(聚合)"),
    (r"万向轮",                                   "power_motion", "万向轮", "万向轮"),
    (r"底盘升降|升降机构|越障.*导轨|越障底盘",    "power_motion", "驱动", "底盘升降"),
    # 算力&电子 (规则只识别类别, 具体 PN/型号由 components_lib.csv 的 model_numbers 字段维护)
    (r"主控芯片|主控\s*SoC|^SoC$|应用处理器|AP芯片",
     "compute_electronics", "主控SoC", "主控SoC"),
    (r"主控IC|^MCU$|单片机|协处理器",            "compute_electronics", "MCU", "MCU"),
    (r"DDR|LPDDR|^RAM$|内存颗粒|运行内存",       "compute_electronics", "RAM", "RAM"),
    (r"EMMC|eMMC|闪存|^ROM$|存储颗粒",           "compute_electronics", "ROM", "ROM"),
    (r"贴片PMU|PMIC|PMU|电源管理IC",             "compute_electronics", "PMIC", "PMU/PMIC"),
    (r"无线模组|WIFI|Wi-Fi|RF天线|WIFI天线|蓝牙.*模组|BT模组",
     "compute_electronics", "WIFI/BT模组", "Wi-Fi/BT"),
    (r"DCDC\s*IC|DC-DC|开关电源IC",              "compute_electronics", "DCDC", "DCDC"),
    (r"充电IC|充电管理IC",                       "compute_electronics", "充电IC", "充电IC"),
    (r"电机驱动IC|马达驱动IC|H桥驱动",           "compute_electronics", "马达驱动", "马达驱动"),
    (r"功放IC|音频功放",                         "compute_electronics", "功放IC", "功放IC"),
    (r"喇叭",                                    "compute_electronics", "喇叭", "喇叭"),
    (r"^PCBA$|^PCBA组件$",                       "compute_electronics", "主板PCB", "PCBA模组"),
    (r"主板\s*PCB|^MAIN.*PCB|主控板",            "compute_electronics", "主板PCB", "主板PCB"),
    (r"^PCB、|^PCB$|^小PCB|子板PCB",             "compute_electronics", "小PCB", "小PCB"),
    (r"贴片电阻|贴片电容|贴片磁珠|贴片功率电感|贴片电感|贴片铝电解|贴片电解电容|电阻、贴片|电容、贴片|磁珠|阻容",
     "compute_electronics", "阻容器件", "阻容器件(聚合)"),
    (r"贴片插座|USB座子|RF天线座|贴片按键|贴片LED|贴片三极管|三极管、|二极管、|晶振|无源晶振|TVS管|ESD管|MOS管|轨到轨运放|运放IC|贴片LDO|模拟开关|板上小IC",
     "compute_electronics", "板上小IC", "板上IC与连接器(聚合)"),
    # 结构 CMF
    (r"面壳|主机上盖|主机底盘|主机底壳|保险杠.*胶条|保险杠底盖|保险杠$",
     "structure_cmf", "主机上盖", "主机外壳CMF(聚合)"),
    (r"模具摊销|注塑模具",                       "structure_cmf", "模具摊销", "模具摊销"),
    (r"整机紧固件|螺丝.*合计|紧固件汇总",         "structure_cmf", "整机紧固件", "整机紧固件(聚合)"),
    # MVA/包材
    (r"包装|外箱|彩箱|中托|上托|下托|保护袋|封口|干燥剂|说明书|SN码|mes码|包装材料|基站包材|主机包材|整机包材",
     "mva_software", "包装材料", "包材/标签(聚合)"),
    (r"组装.*人工|组装.*外协|Assembly",           "mva_software", "组装人工", "组装人工"),
    (r"SLAM.*版税|SLAM.*授权|导航.*版税|导航.*授权",
     "mva_software", "SLAM版税", "SLAM版税"),
    (r"OS.*授权|固件.*授权|OS.*license",          "mva_software", "OS授权", "OS授权"),
    (r"QA.*检测|出厂.*检测",                      "mva_software", "QA", "QA检测"),
    (r"物流|运保|仓储.*运输",                     "mva_software", "物流", "物流/运保"),
]

# ── 每桶兜底价(元/件) — 当辅料/规则都未命中时的最后兜底 ────────────
BUCKET_DEFAULT_PRICE = {
    "compute_electronics": 0.5,
    "perception":          2.0,
    "power_motion":        3.0,
    "cleaning":             2.0,
    "dock_station":        1.5,
    "energy":              5.0,
    "structure_cmf":       0.6,
    "mva_software":        1.0,
}


def _parse_size_mm(spec: str) -> float:
    m = re.findall(r"(\d{2,4})[xX×\*](\d{2,4})(?:[xX×\*]\d{2,4})?", spec or "")
    if not m:
        return 0.0
    return max(max(float(a), float(b)) for a, b in m)


def aux_price(name: str, spec: str = "") -> float:
    """对辅料按文字/尺寸分档给价。"""
    blob = name + (spec or "")
    if re.search(r"^(贴纸|标贴|铭牌|指引贴|提示贴|SN码|mes码|丝印|膜片|保护膜)", name):
        return AUX_PRICE_MICRO
    if re.search(r"螺丝|螺母|介子|O型圈|挡圈|卡簧|锁扣", blob):
        return AUX_PRICE_TINY
    if re.search(r"硅胶|硅橡胶|橡胶|密封圈|密封条|胶套|胶塞|EVA|泡棉|海绵|消音棉|刮条", blob):
        return AUX_PRICE_SMALL
    size_mm = _parse_size_mm(spec)
    is_hard_large = (
        size_mm >= 200 or
        re.search(
            r"(基站.*(底板|背板|隔板|上盖|后盖|底壳)|大盖板|主支架|"
            r"(进|排|过|溢)水门|(清水|污水).*(桶|槽)|底盘$|面壳)",
            name,
        )
    )
    if is_hard_large and not re.search(r"硅胶|橡胶|泡棉|海绵|EVA|消音棉", blob):
        return AUX_PRICE_LARGE
    if re.search(r"(支架|盖板|装饰|固定盖|定位支架|下壳|上壳|面盖|"
                 r"风道|流道|转接|接头|连接线|线束|水管|气管|软管|端子)", name):
        return AUX_PRICE_MID
    if re.search(r"弹簧|转轴|导柱|活塞杆|轴套|喇叭套|减震|脚垫|磁铁|磁环", blob):
        return AUX_PRICE_SMALL
    return AUX_PRICE_MID


def classify(name: str, spec: str = "", region: str = "robot") -> tuple[str | None, str, str]:
    """零件归桶 + 给出 lib 查价 hint。

    返回 (bucket, lib_hint, note)。未命中返回 (None, "", "")。
    region ∈ {"robot", "dock", "package"}, 用于区域性修正。
    """
    blob = f"{name}||{spec or ''}"
    if region == "package":
        return "mva_software", "包装材料", "包材/标签(聚合)"
    for pat, bucket, hint, note in KEYWORD_RULES:
        if re.search(pat, blob):
            # 基站区域内的动力/清洁规则 → 归基站
            if region == "dock" and bucket in ("cleaning", "power_motion"):
                bucket = "dock_station"
            return bucket, hint, note
    return None, "", ""


def is_aggregate(note: str) -> bool:
    """带 (聚合) 标记的件, 整机合计一次, 不按 qty 累加。"""
    return "(聚合)" in (note or "")


def is_aux(name: str) -> bool:
    """判断是否为辅料件。"""
    return bool(AUX_PATTERN.search(name or "")) and not re.search(
        r"^(基站电源板|基站主控|主机风机|主控芯片|主控IC|电机|水泵|气泵|"
        r"风机$|电池|锂电池|雷达|LDS|TOF模块|超声波模块|PCBA|PCB|IMU)",
        name or ""
    )
