import pytest

from saans.bot import Bot
from saans.messages import merge, template_messages
from saans.pipeline import fan_out, run_morning
from saans.plan import build_plan
from saans.store import JsonStore

PRINCIPAL, PARENT_HI, PARENT_EN, STRANGER = 100, 200, 300, 999


class FakeChannel:
    def __init__(self):
        self.sent, self.edits, self.voices, self.answers = [], [], [], []

    def send_text(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text, buttons))
        return len(self.sent)

    def edit_text(self, chat_id, message_id, text, buttons=None):
        self.edits.append((chat_id, message_id, text))

    def answer_callback(self, callback_id, text=None):
        self.answers.append(text)

    def send_voice(self, chat_id, audio, caption=None):
        self.voices.append((chat_id, audio))

    def to(self, chat_id):
        return [t for c, t, _ in self.sent if c == chat_id]


def msg(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def tap(chat_id, data):
    return {"update_id": 2, "callback_query": {"id": "cb", "data": data,
                                               "message": {"chat": {"id": chat_id}, "message_id": 7}}}


@pytest.fixture
def world(tmp_path):
    store, channel = JsonStore(tmp_path / "store.json"), FakeChannel()
    synthesized = []

    def synth(text, lang):
        synthesized.append(lang)
        return f"mp3-{lang}".encode()

    def dispatch(action, **kw):
        if action == "run":
            run_morning(kw["school_id"], kw.get("replay"), store=store, channel=channel, offline=True,
                        writer=template_messages)
        elif action == "fanout":
            fan_out(kw["plan_id"], store=store, channel=channel, synth=synth, save=lambda *a: "local")

    bot = Bot(store, channel, dispatch)
    return store, channel, bot, synthesized


def setup_school(bot):
    bot.handle(msg(PRINCIPAL, "/principal DEMO1"))
    bot.handle(msg(PARENT_HI, "/join demo1"))
    bot.handle(tap(PARENT_HI, "lang:demo-1:hi"))
    bot.handle(msg(PARENT_EN, "/join DEMO1"))
    bot.handle(tap(PARENT_EN, "lang:demo-1:en"))


def test_full_morning_flow(world):
    store, channel, bot, synthesized = world
    setup_school(bot)
    assert store.get_principal("demo-1") == PRINCIPAL
    assert sorted(store.subscribers("demo-1")) == [(PARENT_HI, "hi"), (PARENT_EN, "en")]

    bot.handle(msg(PRINCIPAL, "/run DEMO1 2024-11-18"))
    _, text, buttons = channel.sent[-1]
    assert "Approve to notify parents" in text
    plan_id = buttons[0][0][1].split(":", 1)[1]
    assert store.get_plan(plan_id)["status"] == "pending"

    bot.handle(tap(STRANGER, f"approve:{plan_id}"))
    assert store.get_plan(plan_id)["status"] == "pending"

    bot.handle(tap(PRINCIPAL, f"approve:{plan_id}"))
    rec = store.get_plan(plan_id)
    assert rec["status"] == "sent"
    assert rec["parents_reached"] == 2
    assert "साँस साथी" in channel.to(PARENT_HI)[-1]
    assert "SaansSaathi" in channel.to(PARENT_EN)[-1]
    assert sorted(channel.voices) == [(PARENT_HI, b"mp3-hi"), (PARENT_EN, b"mp3-en")]
    assert sorted(synthesized) == ["en", "hi"]
    assert "Sent to 2 parent(s)" in channel.to(PRINCIPAL)[-1]

    impact = store.get_impact("demo-1")
    assert impact["parents_reached"] == 2 and impact["child_hours"] == rec["plan"]["child_hours_protected"]

    bot.handle(tap(PRINCIPAL, f"approve:{plan_id}"))  # double tap
    assert channel.answers[-1] == "Already sent."
    assert store.get_impact("demo-1")["plans_sent"] == 1


def test_skip_notifies_nobody(world):
    store, channel, bot, _ = world
    setup_school(bot)
    rec = run_morning("demo-1", "2024-11-18", store=store, channel=channel, offline=True, writer=template_messages)
    before = len(channel.to(PARENT_HI))
    bot.handle(tap(PRINCIPAL, f"skip:{rec['plan_id']}"))
    assert store.get_plan(rec["plan_id"])["status"] == "skipped"
    assert len(channel.to(PARENT_HI)) == before
    assert channel.voices == []


def test_only_principal_can_run(world):
    store, channel, bot, _ = world
    setup_school(bot)
    bot.handle(msg(PARENT_HI, "/run DEMO1"))
    assert "Only the registered principal" in channel.to(PARENT_HI)[-1]


def test_unknown_code_and_stop(world):
    store, channel, bot, _ = world
    bot.handle(msg(PARENT_HI, "/join NOPE"))
    assert "Unknown school code" in channel.to(PARENT_HI)[-1]
    setup_school(bot)
    bot.handle(msg(PARENT_HI, "/stop"))
    assert store.subscribers("demo-1") == [(PARENT_EN, "en")]


def test_principal_pin(world, monkeypatch):
    store, channel, bot, _ = world
    monkeypatch.setenv("PRINCIPAL_PIN", "4321")
    bot.handle(msg(PRINCIPAL, "/principal DEMO1"))
    assert store.get_principal("demo-1") is None
    bot.handle(msg(PRINCIPAL, "/principal DEMO1 4321"))
    assert store.get_principal("demo-1") == PRINCIPAL


def test_agent_output_that_fails_checks_falls_back_per_field():
    plan = build_plan("demo-1", "2024-11-18", offline=True)
    good_en = "Air is very poor this morning. Sports moved to 12:20. Please send a mask. – SaansSaathi"
    m = merge({"principal_en": "Approve?", "parent_hi": "This is English, not Hindi", "parent_en": good_en}, plan)
    assert m.source == "mixed"
    assert m.parent_en == good_en
    assert m.parent_hi == template_messages(plan).parent_hi
    long_hi = "हवा " * 61
    assert merge({"principal_en": "x", "parent_hi": long_hi, "parent_en": good_en}, plan).parent_hi != long_hi.strip()
    assert merge(None, plan).source == "template"
