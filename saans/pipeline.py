"""The morning pipeline: plan -> messages -> principal approval -> parents.

    python -m saans.pipeline --school demo-1 --replay 2024-11-18
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from .agent import write_messages
from .channel import Channel, ChannelError
from .plan import build_plan
from .store import Store
from .voice import save_audio, synthesize

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def approval_buttons(plan_id: str):
    return [[("✅ Approve", f"approve:{plan_id}"), ("Skip", f"skip:{plan_id}")]]


def run_morning(school_key: str, replay: str | None = None, *, store: Store, channel: Channel | None,
                offline: bool = False, writer=write_messages) -> dict:
    """Build today's plan, write the messages and ask the principal to approve."""
    plan = build_plan(school_key, replay, offline=offline)
    messages = writer(plan)
    plan_id = f"{plan.school_id}-{plan.date.replace('-', '')}-{plan.mode[0]}-{uuid.uuid4().hex[:6]}"
    rec = {
        "plan_id": plan_id,
        "school_id": plan.school_id,
        "date": plan.date,
        "mode": plan.mode,
        "status": "pending",
        "created_at": _now(),
        "plan": plan.to_dict(),
        "messages": messages.to_dict(),
        "principal_chat": None,
        "principal_message_id": None,
        "parents_reached": 0,
    }
    store.save_plan(rec)

    principal = store.get_principal(plan.school_id)
    if principal and channel:
        try:
            msg_id = channel.send_text(principal, messages.principal_en, approval_buttons(plan_id))
            store.update_plan(plan_id, principal_chat=principal, principal_message_id=msg_id)
            rec.update(principal_chat=principal, principal_message_id=msg_id)
        except ChannelError:
            log.exception("could not reach principal for %s", plan.school_id)
    else:
        log.warning("no principal registered for %s; plan %s waits for approval", plan.school_id, plan_id)
    return rec


def fan_out(plan_id: str, *, store: Store, channel: Channel, synth=synthesize, save=save_audio) -> dict:
    """Send the approved plan to every parent: text plus voice note in their language."""
    if not store.transition(plan_id, "approved", "sending"):
        log.info("plan %s is not awaiting fan-out", plan_id)
        return store.get_plan(plan_id) or {}
    rec = store.get_plan(plan_id)
    msgs = rec["messages"]
    texts = {"hi": msgs["parent_hi"], "en": msgs["parent_en"]}
    subs = store.subscribers(rec["school_id"])

    audio: dict[str, bytes] = {}
    audio_uris: dict[str, str] = {}
    for lang in sorted({lang for _, lang in subs}):
        try:
            audio[lang] = synth(texts[lang], lang)
            audio_uris[lang] = save(plan_id, lang, audio[lang])
        except Exception:
            log.exception("voice synthesis failed for %s/%s; sending text only", plan_id, lang)

    reached = 0
    for chat_id, lang in subs:
        try:
            channel.send_text(chat_id, texts[lang])
            if lang in audio:
                channel.send_voice(chat_id, audio[lang])
            reached += 1
        except ChannelError:
            log.exception("could not reach parent chat %s", chat_id)

    child_hours = rec["plan"]["child_hours_protected"]
    store.update_plan(plan_id, status="sent", parents_reached=reached, audio=audio_uris, sent_at=_now())
    store.add_impact(rec["school_id"], child_hours, reached)
    if rec.get("principal_chat"):
        try:
            channel.send_text(rec["principal_chat"], f"Sent to {reached} parent(s). {child_hours:g} child-hours protected today.")
        except ChannelError:
            log.exception("could not confirm to principal")
    return store.get_plan(plan_id)


if __name__ == "__main__":
    import argparse

    from .channel import TelegramChannel
    from .config import load_env
    from .store import default_store

    load_env()
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="python -m saans.pipeline")
    p.add_argument("--school", required=True)
    p.add_argument("--replay", metavar="YYYY-MM-DD")
    args = p.parse_args()
    try:
        ch = TelegramChannel()
    except ChannelError:
        ch = None
        log.warning("TELEGRAM_BOT_TOKEN not set: plan is stored but nothing is sent")
    rec = run_morning(args.school, args.replay, store=default_store(), channel=ch)
    print(f"plan {rec['plan_id']} status={rec['status']} messages={rec['messages']['source']}")
    print(rec["messages"]["principal_en"])
