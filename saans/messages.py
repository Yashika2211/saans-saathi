"""The three messages per plan: principal summary (EN), parent note (HI), parent note (EN).

Templates here are the fallback when Bedrock fails, and check() decides whether an
agent-written message is safe to send.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .planner import DayPlan

PARENT_MAX_WORDS = 60
PRINCIPAL_MAX_WORDS = 160

CATEGORY_HI = {
    "Good": "अच्छी",
    "Satisfactory": "संतोषजनक",
    "Moderate": "मध्यम",
    "Poor": "खराब",
    "Very Poor": "बहुत खराब",
    "Severe": "गंभीर",
}


@dataclass
class Messages:
    principal_en: str
    parent_hi: str
    parent_en: str
    source: str = "template"  # agent | template | mixed

    def to_dict(self) -> dict:
        return asdict(self)


def word_count(text: str) -> int:
    return len(text.split())


def devanagari_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)


def check(field: str, text: str | None) -> bool:
    if not text or not text.strip():
        return False
    if field == "parent_hi":
        return word_count(text) <= PARENT_MAX_WORDS and devanagari_share(text) >= 0.6
    if field == "parent_en":
        return word_count(text) <= PARENT_MAX_WORDS and devanagari_share(text) < 0.1
    if field == "principal_en":
        return word_count(text) <= PRINCIPAL_MAX_WORDS
    raise ValueError(field)


def _moves(plan: DayPlan):
    return [b for b in plan.blocks if b.action == "reschedule"], [b for b in plan.blocks if b.action == "indoors"]


def principal_template(plan: DayPlan) -> str:
    w = plan.worst
    lines = [f"Good morning. Air plan for {plan.school_name}, {plan.date}."]
    if w:
        lines.append(f"Worst school hour: {w.time}, {plan.aqi_label} {w.aqi} ({w.category}).")
    if plan.cleanest:
        lines.append(f"Cleanest school hour: {plan.cleanest.time}, {plan.aqi_label} {plan.cleanest.aqi}.")
    changed = [b for b in plan.blocks if b.action != "keep"]
    if changed:
        lines.append("Proposed changes:")
        lines += [f"- {b.reason}" for b in changed]
    else:
        lines.append("No changes needed. Outdoor activities can go ahead.")
    lines += [f"- {a}" for a in plan.advisories]
    if plan.child_hours_protected:
        lines.append(f"This moves {plan.child_hours_protected:g} child-hours of outdoor activity out of bad air.")
    lines.append("Approve to notify parents.")
    return "\n".join(lines)


def parent_en_template(plan: DayPlan) -> str:
    moved, indoors = _moves(plan)
    w = plan.worst
    if not w or (not moved and not indoors):
        return "Good morning. The air near school is fine for today's outdoor activities. No changes today. – SaansSaathi"
    parts = [f"Good morning. Air near school is {w.category.lower()} this morning ({plan.aqi_label} {w.aqi})."]
    if moved:
        parts.append(f"Sports moved to {moved[0].new_start}, when the air is cleaner.")
    if indoors:
        parts.append("Assembly and other outdoor activities will be indoors." if len(indoors) > 1 else f"{indoors[0].name} will be indoors.")
    if any(a.startswith("Masks") for a in plan.advisories):
        parts.append("Please send your child with a mask.")
    parts.append("– SaansSaathi")
    return " ".join(parts)


def parent_hi_template(plan: DayPlan) -> str:
    moved, indoors = _moves(plan)
    w = plan.worst
    if not w or (not moved and not indoors):
        return "नमस्ते। आज स्कूल के पास हवा ठीक है। बाहर की सभी गतिविधियाँ सामान्य रहेंगी। – साँस साथी"
    cat = CATEGORY_HI.get(w.category, w.category)
    parts = [f"नमस्ते। आज सुबह स्कूल के पास हवा {cat} है (AQI अनुमान {w.aqi})।"]
    if moved:
        parts.append(f"खेल का पीरियड {moved[0].new_start} बजे होगा, जब हवा साफ़ होगी।")
    if indoors:
        parts.append("प्रार्थना सभा और बाकी बाहरी गतिविधियाँ अंदर होंगी।")
    if any(a.startswith("Masks") for a in plan.advisories):
        parts.append("कृपया बच्चे को मास्क पहनाकर भेजें।")
    parts.append("– साँस साथी")
    return " ".join(parts)


def template_messages(plan: DayPlan) -> Messages:
    return Messages(
        principal_en=principal_template(plan),
        parent_hi=parent_hi_template(plan),
        parent_en=parent_en_template(plan),
        source="template",
    )


def merge(agent: dict | None, plan: DayPlan) -> Messages:
    """Use each agent-written field that passes check(), else the template for that field."""
    fallback = template_messages(plan)
    if not agent:
        return fallback
    out, used = {}, 0
    for field in ("principal_en", "parent_hi", "parent_en"):
        text = agent.get(field)
        if check(field, text):
            out[field] = re.sub(r"\n{3,}", "\n\n", text.strip())
            used += 1
        else:
            out[field] = getattr(fallback, field)
    source = "agent" if used == 3 else "mixed" if used else "template"
    return Messages(**out, source=source)
