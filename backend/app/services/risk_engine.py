from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RiskRuleType
from app.models.entities import RiskRule
from app.services.core import utc_now

RISK_RULE_VERSION = "RISK-V1.0"

RISK_MESSAGE = "内容存在风险，请修改后重试。"
IDENTITY_MESSAGE = "请勿输入姓名、手机号、身份证号、邮箱或其他身份信息。"
CRISIS_MESSAGE = "请先暂停操作，并联系现场医生获得支持。"
SERVICE_UNAVAILABLE_MESSAGE = "风险校验暂时不可用，请稍后重试。"

EXCLUSIONS = ["没有", "不要", "不包含", "禁止", "避免"]
ACTION_CONTEXT = ["攻击", "伤害", "威胁", "挥舞", "瞄准", "使用", "生成"]
VISUAL_CONTEXT = ["生成", "形象", "表情", "场景", "视觉化"]

DEFAULT_RULES = [
    {
        "rule_code": "R-001",
        "category": "血腥、伤口、自残、身体伤害",
        "rule_type": RiskRuleType.DIRECT,
        "trigger_terms": [
            "血腥",
            "鲜血",
            "流血",
            "血肉模糊",
            "伤口",
            "开放性伤口",
            "割伤",
            "骨折",
            "断肢",
            "自残",
            "自伤",
            "割腕",
            "自杀",
            "跳楼",
            "上吊",
            "吞药",
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
            "枪",
            "手枪",
            "步枪",
            "子弹",
            "炸弹",
            "爆炸物",
            "燃烧瓶",
            "棍棒",
            "斧头",
            "电锯",
            "弓弩",
            "毒药",
            "硫酸",
            "绞索",
        ],
        "context_terms": ACTION_CONTEXT,
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
        ],
        "patient_message_type": "identity",
    },
    {
        "rule_code": "R-006",
        "category": "人种刻板化或歧视性表达",
        "rule_type": RiskRuleType.CONTEXT,
        "trigger_terms": ["人种", "民族", "种族", "群体", "某族"],
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
        ],
        "patient_message_type": "identity",
    },
]

PII_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
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
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", "", normalized)


async def seed_default_risk_rules(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(RiskRule.rule_code))).all())
    now = utc_now()
    for definition in DEFAULT_RULES:
        if definition["rule_code"] in existing:
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
