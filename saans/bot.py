"""Telegram bot logic, shared by local long polling and the Lambda webhook.

Parents:    /join DEMO1, then pick हिन्दी or English. /stop to leave.
Principal:  /principal DEMO1 [pin] once, then Approve / Skip on each morning's plan.
            /run DEMO1 [YYYY-MM-DD] triggers the 5:30 AM check now (replay a past day with a date).

    python -m saans.bot      # local long polling, no tunnel needed
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from .channel import Channel, ChannelError
from .schools import UnknownSchool, get_school
from .store import Store

log = logging.getLogger(__name__)

Dispatch = Callable[..., None]  # dispatch("run", school_id=..., replay=...) / dispatch("fanout", plan_id=...)

HELP = (
    "SaansSaathi sends a short air-quality note before school.\n"
    "साँस साथी स्कूल से पहले हवा की जानकारी भेजता है।\n\n"
    "Parents / अभिभावक: /join <school code>, e.g. /join DEMO1\n"
    "Principals: /principal <school code>\n"
    "/stop to unsubscribe"
)

JOINED = {
    "hi": "आप {school} से जुड़ गए हैं। हर सुबह हवा की जानकारी और आवाज़ संदेश मिलेगा। बंद करने के लिए /stop भेजें।",
    "en": "You have joined {school}. You'll get a short air note and voice message on school mornings. Send /stop to leave.",
}


class Bot:
    def __init__(self, store: Store, channel: Channel, dispatch: Dispatch):
        self.store = store
        self.channel = channel
        self.dispatch = dispatch

    def handle(self, update: dict) -> None:
        try:
            if "callback_query" in update:
                self._callback(update["callback_query"])
            elif "message" in update and update["message"].get("text"):
                self._message(update["message"])
        except ChannelError:
            log.exception("telegram error while handling update %s", update.get("update_id"))

    # Commands

    def _message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        cmd, *args = msg["text"].strip().split()
        cmd = cmd.split("@")[0].lower()
        handler = {
            "/start": self._start,
            "/help": self._start,
            "/join": self._join,
            "/stop": self._stop,
            "/principal": self._principal,
            "/run": self._run,
        }.get(cmd)
        if handler:
            handler(chat_id, args)
        else:
            self.channel.send_text(chat_id, HELP)

    def _start(self, chat_id, args):
        if args:  # deep link: t.me/<bot>?start=DEMO1
            return self._join(chat_id, args)
        self.channel.send_text(chat_id, HELP)

    def _school(self, chat_id, args):
        if not args:
            self.channel.send_text(chat_id, "Please add the school code, e.g. /join DEMO1")
            return None
        try:
            return get_school(args[0])
        except UnknownSchool:
            self.channel.send_text(chat_id, f"Unknown school code {args[0]}. / स्कूल कोड नहीं मिला।")
            return None

    def _join(self, chat_id, args):
        school = self._school(chat_id, args)
        if school:
            self.channel.send_text(
                chat_id,
                f"{school.name}\nभाषा चुनें / Choose language:",
                [[("हिन्दी", f"lang:{school.id}:hi"), ("English", f"lang:{school.id}:en")]],
            )

    def _stop(self, chat_id, args):
        left = self.store.remove_subscriber(chat_id)
        self.channel.send_text(chat_id, "Unsubscribed. / आपकी सदस्यता बंद कर दी गई है।" if left else "You were not subscribed.")

    def _principal(self, chat_id, args):
        school = self._school(chat_id, args)
        if not school:
            return
        pin = os.environ.get("PRINCIPAL_PIN")
        if pin and (len(args) < 2 or args[1] != pin):
            self.channel.send_text(chat_id, "Wrong or missing PIN. Use /principal <code> <pin>.")
            return
        self.store.set_principal(school.id, chat_id)
        self.channel.send_text(
            chat_id,
            f"You are now the approver for {school.name}. Each school morning at 5:30 you'll get the day's plan "
            f"to approve. Send /run {school.join_code} to run the check now.",
        )

    def _run(self, chat_id, args):
        school = self._school(chat_id, args)
        if not school:
            return
        if self.store.get_principal(school.id) != chat_id:
            self.channel.send_text(chat_id, "Only the registered principal can run the check.")
            return
        replay = args[1] if len(args) > 1 else None
        self.channel.send_text(chat_id, f"Running the 5:30 AM check for {school.name}" + (f" (replay of {replay})" if replay else "") + "…")
        self.dispatch("run", school_id=school.id, replay=replay)

    # Buttons

    def _callback(self, cb: dict) -> None:
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]
        kind, _, rest = (cb.get("data") or "").partition(":")

        if kind == "lang":
            school_id, _, lang = rest.partition(":")
            school = get_school(school_id)
            self.store.add_subscriber(school.id, chat_id, lang)
            self.channel.answer_callback(cb["id"])
            self.channel.edit_text(chat_id, message_id, JOINED[lang].format(school=school.name))
            return

        if kind in ("approve", "skip"):
            plan_id = rest
            rec = self.store.get_plan(plan_id)
            if not rec or self.store.get_principal(rec["school_id"]) != chat_id:
                self.channel.answer_callback(cb["id"], "Only the principal can do this.")
                return
            original = rec["messages"]["principal_en"]
            if kind == "approve" and self.store.transition(plan_id, "pending", "approved"):
                n = len(self.store.subscribers(rec["school_id"]))
                self.channel.answer_callback(cb["id"], "Approved")
                self.channel.edit_text(chat_id, message_id, f"{original}\n\n✅ Approved. Sending to {n} parent(s)…")
                self.dispatch("fanout", plan_id=plan_id)
            elif kind == "skip" and self.store.transition(plan_id, "pending", "skipped"):
                self.channel.answer_callback(cb["id"], "Skipped")
                self.channel.edit_text(chat_id, message_id, f"{original}\n\n⏭ Skipped. Parents were not notified.")
            else:
                self.channel.answer_callback(cb["id"], f"Already {self.store.get_plan(plan_id)['status']}.")
            return

        self.channel.answer_callback(cb["id"])


def poll() -> None:
    """Local long polling: no public URL needed."""
    from .channel import TelegramChannel
    from .config import load_env
    from .pipeline import fan_out, run_morning
    from .store import default_store

    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store, channel = default_store(), TelegramChannel()

    def dispatch(action, **kw):
        if action == "run":
            run_morning(kw["school_id"], kw.get("replay"), store=store, channel=channel)
        elif action == "fanout":
            fan_out(kw["plan_id"], store=store, channel=channel)

    bot = Bot(store, channel, dispatch)
    channel.delete_webhook()
    log.info("polling Telegram; Ctrl+C to stop")
    offset = None
    while True:
        try:
            for update in channel.get_updates(offset):
                offset = update["update_id"] + 1
                bot.handle(update)
        except ChannelError:
            log.exception("polling error; retrying")
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    poll()
