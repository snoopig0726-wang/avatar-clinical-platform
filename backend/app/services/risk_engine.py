from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RiskRuleType
from app.models.entities import RiskRule
from app.services.core import utc_now
from app.services.text_normalization import normalize_multilingual_text

RISK_RULE_VERSION = "RISK-V1.4"
LEGACY_DEFAULT_RULE_VERSIONS = {
    "RISK-V1.0",
    "RISK-V1.1",
    "RISK-V1.2",
    "RISK-V1.3",
}

RISK_MESSAGE = "内容存在风险，请修改后重试。"
IDENTITY_MESSAGE = "请勿输入姓名、手机号、身份证号、邮箱或其他身份信息。"
CRISIS_MESSAGE = "请先暂停操作，并联系现场医生获得支持。"
SERVICE_UNAVAILABLE_MESSAGE = "风险校验暂时不可用，请稍后重试。"

EXCLUSIONS = ["没有", "不要", "不包含", "禁止", "避免", "去掉", "移除", "排除", "不显示"]
ACTION_CONTEXT = [
    "攻击",
    "伤害",
    "威胁",
    "挥舞",
    "瞄准",
    "使用",
    "生成",
    "手持",
    "拿着",
    "携带",
    "指向",
    "砍",
    "刺",
    "射击",
    "引爆",
]
WEAPON_RISK_CONTEXT = [
    *ACTION_CONTEXT,
    "血",
    "鲜血",
    "血液",
    "血迹",
    "血渍",
    "血痕",
    "血点",
    "血滴",
    "带血",
    "染血",
    "血染",
    "流血",
    "出血",
    "淌血",
    "滴血",
    "伤口",
    "创口",
    "裂口",
    "切口",
    "刀口",
]
VISUAL_CONTEXT = [
    "生成",
    "形象",
    "表情",
    "场景",
    "视觉化",
    "画面",
    "图片",
    "肖像",
    "外观",
    "描绘",
    "添加",
    "变成",
]

DEFAULT_RULES = [
    {
        "rule_code": "R-001",
        "category": "血腥、伤口、自残、身体伤害",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "血腥",
            "鲜血",
            "流血",
            "出血",
            "淌血",
            "滴血",
            "舔血",
            "舐血",
            "血迹",
            "血渍",
            "血痕",
            "血点",
            "血滴",
            "带血",
            "染血",
            "血染",
            "血泊",
            "喷血",
            "溅血",
            "血淋淋",
            "血肉模糊",
            "伤口",
            "开放性伤口",
            "创口",
            "裂口",
            "切口",
            "刀口",
            "刀疤",
            "伤疤",
            "割伤",
            "刀伤",
            "枪伤",
            "烧伤",
            "烫伤",
            "割喉",
            "割颈",
            "割脉",
            "骨折",
            "断肢",
            "残肢",
            "器官外露",
            "内脏外露",
            "自残",
            "自伤",
            "割腕",
            "自杀",
            "想死",
            "想去死",
            "想要死",
            "希望死掉",
            "希望自己死掉",
            "不想活",
            "不愿活",
            "不愿继续活",
            "不想继续活",
            "活不下去",
            "活够了",
            "活着没意思",
            "活着没有意思",
            "活着没有意义",
            "人生没意义",
            "生命没意义",
            "不如死了",
            "死了算了",
            "去死吧",
            "寻死",
            "求死",
            "一心求死",
            "轻生",
            "自尽",
            "自我了断",
            "结束生命",
            "结束自己的生命",
            "结束我的生命",
            "了结自己",
            "结束一切",
            "一了百了",
            "生无可恋",
            "厌世",
            "死亡愿望",
            "希望永远消失",
            "从世界消失",
            "从这个世界消失",
            "想从世界消失",
            "想消失",
            "不想存在",
            "不想在这个世界",
            "不想醒来",
            "不要醒来",
            "不想再醒来",
            "希望不要醒来",
            "睡着不醒",
            "没有活下去的理由",
            "失去活下去的勇气",
            "撑不下去",
            "寻短见",
            "一死了之",
            "了却生命",
            "想一了百了",
            "跳楼",
            "跳桥",
            "上吊",
            "吞药",
            "吞安眠药",
            "服药过量",
            "服毒",
            "喝农药",
            "卧轨",
            "跳轨",
            "投河",
            "跳河",
            "跳海",
            "烧炭",
            "开煤气",
        ],
        "patient_message_type": "crisis",
    },
    {
        "rule_code": "R-002",
        "category": "武器、刀具、枪支、暴力工具",
        "rule_type": RiskRuleType.CONTEXT,
        "trigger_terms": [
            "刀",
            "匕首",
            "菜刀",
            "砍刀",
            "武士刀",
            "军刀",
            "刺刀",
            "刀刃",
            "刀锋",
            "刀尖",
            "利刃",
            "锐器",
            "凶器",
            "剃刀",
            "美工刀",
            "枪",
            "手枪",
            "步枪",
            "枪械",
            "子弹",
            "弹药",
            "炸弹",
            "爆炸物",
            "手榴弹",
            "地雷",
            "火箭筒",
            "燃烧瓶",
            "棍棒",
            "铁锤",
            "铁链",
            "斧头",
            "电锯",
            "弓弩",
            "毒药",
            "硫酸",
            "绞索",
        ],
        "context_terms": WEAPON_RISK_CONTEXT,
        "exclusion_terms": EXCLUSIONS,
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-003",
        "category": "恐怖化、恶魔化、鬼怪化形象",
        "rule_type": RiskRuleType.CONTEXT,
        "trigger_terms": [
            "恐怖",
            "惊悚",
            "阴森",
            "鬼",
            "恶鬼",
            "僵尸",
            "丧尸",
            "怪物",
            "恶魔",
            "地狱",
            "诅咒",
            "骷髅",
            "幽灵",
            "血眼",
            "裂嘴",
            "无脸",
            "腐烂面孔",
            "腐尸",
            "空洞眼眶",
            "扭曲肢体",
            "畸形怪物",
        ],
        "context_terms": VISUAL_CONTEXT,
        "exclusion_terms": EXCLUSIONS,
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-004",
        "category": "极端威胁表情或攻击动作",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "威胁",
            "恐吓",
            "攻击",
            "袭击",
            "扑向",
            "掐脖子",
            "挥刀",
            "举枪",
            "瞄准",
            "砍杀",
            "刺杀",
            "殴打",
            "勒颈",
            "扼喉",
            "绑架",
            "折磨",
            "虐杀",
            "施暴",
            "威吓",
            "行刑",
            "处决",
            "爆头",
            "肢解",
            "斩首",
            "活埋",
            "追杀",
            "杀掉",
            "弄死",
            "狰狞",
            "凶狠",
            "暴怒",
            "咆哮",
            "攻击姿势",
        ],
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-005",
        "category": "真实患者本人或具体人物肖像",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "真实患者",
            "患者照片",
            "患者肖像",
            "病历照片",
            "诊疗照片",
            "名人脸",
            "明星脸",
            "政治人物脸",
            "换脸成名人",
            "真实人物肖像",
            "本人照片",
            "真人患者形象",
            "身份证照片",
            "护照照片",
            "医生照片",
            "家属照片",
            "指定人物照片",
        ],
        "patient_message_type": "identity",
    },
    {
        "rule_code": "R-006",
        "category": "人种刻板化或歧视性表达",
        "rule_type": RiskRuleType.CONTEXT,
        "trigger_terms": [
            "人种",
            "民族",
            "种族",
            "群体",
            "某族",
            "宗教",
            "国籍",
            "残疾",
            "性取向",
        ],
        "context_terms": [
            "很脏",
            "低等",
            "智商低",
            "像动物",
            "劣等",
            "血统低贱",
            "清洗",
            "歧视",
            "侮辱",
            "丑化",
            "仇恨",
            "灭绝",
            "驱逐",
            "排斥",
            "仇视",
            "污名化",
            "去人化",
        ],
        "exclusion_terms": EXCLUSIONS,
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-007",
        "category": "未成年人敏感或伤害性表达",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "儿童受伤",
            "小孩流血",
            "儿童伤口",
            "儿童自残",
            "儿童自杀",
            "校园暴力",
            "霸凌儿童",
            "虐待儿童",
            "受惊儿童",
            "儿童恐怖形象",
            "儿童尸体",
            "儿童患者肖像",
            "未成年人受伤",
            "婴儿受伤",
            "虐童",
            "儿童性化",
            "未成年人色情",
        ],
        "patient_message_type": "crisis",
    },
    {
        "rule_code": "R-008",
        "category": "强化妄想或被害信念",
        "rule_type": RiskRuleType.CONTEXT,
        "trigger_terms": [
            "被监控",
            "被跟踪",
            "被监听",
            "脑控",
            "思维控制",
            "有人害我",
            "被迫害",
            "秘密组织监视",
            "救世主",
            "天选之人",
            "神谕",
            "被恶魔附身",
            "诅咒",
            "阴谋符号",
            "隐藏信息",
            "宇宙讯号",
            "外星控制",
            "植入芯片",
            "读心",
            "思想被读取",
            "有人操控我",
            "政府监视",
            "政府监视我",
            "监视我",
            "摄像头监控我",
            "电视在对我说话",
            "声音命令我",
        ],
        "context_terms": ["确认", "强化", "真实", "确实", "监视", "控制", "命令"],
        "exclusion_terms": EXCLUSIONS,
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-009",
        "category": "身份信息与研究无关信息",
        "rule_type": RiskRuleType.PII,
        "trigger_terms": [
            "手机号",
            "身份证号",
            "邮箱",
            "住址",
            "姓名",
            "联系方式",
            "病历号",
            "单位",
            "学校",
            "社交账号",
            "微信号",
            "QQ号",
            "护照号",
            "银行卡号",
            "信用卡号",
            "工作单位",
            "家庭地址",
            "车牌号",
            "人脸照片",
        ],
        "patient_message_type": "identity",
    },
    {
        "rule_code": "R-010",
        "category": "色情、裸露或性暴力表达",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "色情",
            "裸露",
            "裸体",
            "全裸",
            "性行为",
            "露骨性内容",
            "性暗示",
            "性骚扰",
            "性侵",
            "强奸",
            "猥亵",
        ],
        "patient_message_type": "risk",
    },
    {
        "rule_code": "R-011",
        "category": "极端主义、仇恨或恐怖组织符号",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "纳粹",
            "卐字",
            "白人至上",
            "种族灭绝",
            "仇恨符号",
            "恐怖组织标志",
            "极端组织标志",
            "恐怖主义宣传",
        ],
        "patient_message_type": "risk",
    },
]

PII_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
)

ENGLISH_RISK_MARKERS: tuple[tuple[str, str], ...] = (
    (
        r"\b(?:blood|bloody|bloodied|bloodstained|blood[- ]?(?:soaked|covered|"
        r"smeared|splattered)|blood (?:splatter|spatter|smear|droplets?)|gore|gory|"
        r"bleeding|hemorrhag(?:e|ing)|wounds?|open wound|laceration|gash|incision|"
        r"lick(?:ing|ed|s)? (?:the )?blood|"
        r"mutilat(?:e|ed|ion)|severed limbs?|exposed organs?|self[- ]?harm|"
        r"self[- ]?injury|cut (?:my|their|his|her) wrists?|"
        r"suicid(?:e|al|ality)|suicidal thoughts?|want to die|wanna die|"
        r"wish (?:i|we) (?:were|was) dead|wish to be dead|hope to die|"
        r"(?:do not|don(?:'|’| )?t) want to (?:live|be alive|be here)|"
        r"no longer want to be here|(?:cannot|can(?:'|’| )?t) go on|"
        r"no (?:reason|point) (?:to|in) (?:live|living)|"
        r"life (?:is not|isn(?:'|’| )?t) worth living|better off dead|"
        r"end (?:my|our|their|his|her) (?:own )?life|"
        r"take (?:my|our|their|his|her) own life|kill myself|"
        r"end it all|want everything to stop|never wake up|not wake up|"
        r"disappear forever|wish (?:i|we) could disappear|"
        r"death wish|(?:lose|lost) the will to live|tired of living|ready to die|"
        r"plan to die|commit suicide|hang myself|slit my wrists?|"
        r"jump off (?:a|the) (?:bridge|building)|(?:take an |)overdose|"
        r"overdose on|poison myself|drown myself)\b",
        "流血自残",
    ),
    (
        r"\b(?:knife|knife edge|blade|dagger|machete|sword|bayonet|razor|"
        r"box cutter|utility knife|sharp object|gun|firearm|handgun|pistol|rifle|"
        r"shotgun|bullet|ammunition|bomb|explosive|grenade|landmine|rocket launcher|"
        r"molotov|baseball bat|axe|chainsaw|crossbow|poison|acid|noose)\b",
        "刀",
    ),
    (
        r"\b(?:attack|harm|hurt|threaten|wield|hold|holding|carry|carrying|point|"
        r"aim|use|using|generate|create|show|depict|draw|add|include|stab|slash|"
        r"shoot|detonate)\b",
        "生成",
    ),
    (
        r"\b(?:no|not|without|avoid|exclude|omit|remove|delete|do not|don't|never|"
        r"free of)\b",
        "不要",
    ),
    (
        r"\b(?:horror|horrific|terrifying|creepy|disturbing|demon|ghost|zombie|"
        r"monster|hell|curse|skull|faceless|rotting face|empty eye sockets|"
        r"twisted limbs)\b",
        "恐怖",
    ),
    (r"\b(?:image|appearance|scene|visual|turn (?:him|her|them|it) into)\b", "形象"),
    (
        r"\b(?:threat|threaten|attack|assault|choke|strangle|stab|shoot|kill|"
        r"murder|torture|execute|execution|kidnap|abduct|behead|decapitate|"
        r"dismember|bury alive|violent rage|aggressive pose)\b",
        "威胁",
    ),
    (
        r"\b(?:real patient|patient photo|patient portrait|medical photo|"
        r"celebrity face|politician face|face swap|real person portrait|"
        r"passport photo|identity card photo|doctor photo|family member photo)\b",
        "真实患者肖像",
    ),
    (
        r"\b(?:race|racial|ethnicity|ethnic group|religion|religious group|"
        r"nationality|disability|sexual orientation)\b",
        "人种",
    ),
    (
        r"\b(?:inferior|dirty race|subhuman|racial cleansing|racial insult|"
        r"racial hatred|exterminate|deport|dehumanize|hate group)\b",
        "歧视",
    ),
    (
        r"\b(?:child|kid|minor)\b.*\b(?:hurt|injur(?:e|ed|y)|bleed|self[- ]?harm|"
        r"suicid(?:e|al)|abuse|corpse|sexualize|sexual content)\b",
        "儿童受伤",
    ),
    (
        r"\b(?:being monitored|being followed|being listened to|mind control|"
        r"secret organization|chosen one|divine message|possessed|hidden message|"
        r"alien control|implanted chip|reading my mind|government surveillance|"
        r"camera is watching me|television is talking to me|voices command me)\b",
        "被监控",
    ),
    (r"\b(?:confirm|prove|real|really|indeed|definitely true)\b", "确认"),
    (
        r"\b(?:phone number|identity card|id number|passport number|bank card|"
        r"credit card|email address|home address|full name|contact details|"
        r"medical record number|social media handle|wechat id|qq number|"
        r"license plate|employer|workplace)\b",
        "姓名",
    ),
    (
        r"\b(?:porn|pornographic|explicit sexual content|nudity|nude|naked|"
        r"sexual act|sexualized|sexual harassment|sexual assault|rape|molest)\b",
        "色情",
    ),
    (
        r"\b(?:nazi|swastika|white supremacy|white supremacist|genocide|"
        r"hate symbol|terrorist propaganda|extremist organization)\b",
        "纳粹",
    ),
)


class RiskServiceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    rule_version: str
    matched_rule_codes: tuple[str, ...] = ()
    patient_message_type: str | None = None

    @property
    def patient_message(self) -> str:
        return {
            "identity": IDENTITY_MESSAGE,
            "crisis": CRISIS_MESSAGE,
        }.get(self.patient_message_type, RISK_MESSAGE)


def normalize_for_risk(text: str) -> str:
    normalized = normalize_multilingual_text(text)
    semantic_text = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    markers = "".join(
        marker
        for pattern, marker in ENGLISH_RISK_MARKERS
        if re.search(pattern, normalized) or re.search(pattern, semantic_text)
    )
    return re.sub(r"[\W_]+", "", f"{normalized}{markers}", flags=re.UNICODE)


async def seed_default_risk_rules(session: AsyncSession) -> None:
    existing = {
        rule.rule_code: rule
        for rule in (await session.scalars(select(RiskRule))).all()
    }
    now = utc_now()
    for definition in DEFAULT_RULES:
        rule = existing.get(definition["rule_code"])
        if rule is not None:
            changed = False
            for field in ("trigger_terms", "context_terms", "exclusion_terms"):
                required = definition.get(field)
                if not required:
                    continue
                current = list(getattr(rule, field) or [])
                merged = list(dict.fromkeys([*current, *required]))
                if merged != current:
                    setattr(rule, field, merged)
                    changed = True
            if rule.version in LEGACY_DEFAULT_RULE_VERSIONS:
                rule.version = RISK_RULE_VERSION
                changed = True
            if changed:
                rule.updated_at = now
            continue
        session.add(
            RiskRule(
                version=RISK_RULE_VERSION,
                is_enabled=True,
                updated_at=now,
                context_terms=definition.get("context_terms"),
                exclusion_terms=definition.get("exclusion_terms"),
                **{
                    key: value
                    for key, value in definition.items()
                    if key not in {"context_terms", "exclusion_terms"}
                },
            )
        )


async def evaluate_adjustment_text(session: AsyncSession, text: str) -> RiskDecision:
    normalized = normalize_for_risk(text)
    if not normalized:
        return RiskDecision(False, RISK_RULE_VERSION, ("INVALID-EMPTY",), "risk")
    try:
        rules = (
            await session.scalars(
                select(RiskRule).where(RiskRule.is_enabled.is_(True)).order_by(RiskRule.rule_code)
            )
        ).all()
    except Exception as exc:
        raise RiskServiceUnavailable("risk rules could not be loaded") from exc
    if not rules:
        raise RiskServiceUnavailable("no enabled risk rules")
    versions = {rule.version for rule in rules}
    policy_version = next(iter(versions)) if len(versions) == 1 else f"{RISK_RULE_VERSION}-MIXED"

    matches: list[RiskRule] = []
    for rule in rules:
        has_trigger = any(normalize_for_risk(term) in normalized for term in rule.trigger_terms)
        if rule.rule_type == RiskRuleType.PII:
            has_trigger = has_trigger or any(pattern.search(text) for pattern in PII_PATTERNS)
        if not has_trigger:
            continue
        if rule.rule_type == RiskRuleType.CONTEXT:
            has_context = any(
                normalize_for_risk(term) in normalized for term in (rule.context_terms or [])
            )
            has_exclusion = any(
                normalize_for_risk(term) in normalized for term in (rule.exclusion_terms or [])
            )
            if not has_context or has_exclusion:
                continue
        matches.append(rule)

    if not matches:
        return RiskDecision(True, policy_version)
    message_priority = {"risk": 1, "identity": 2, "crisis": 3}
    message_type = max(
        (rule.patient_message_type for rule in matches),
        key=lambda item: message_priority.get(item, 1),
    )
    return RiskDecision(
        False,
        policy_version,
        tuple(rule.rule_code for rule in matches),
        message_type,
    )
