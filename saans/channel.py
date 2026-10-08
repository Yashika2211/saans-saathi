"""Messaging channels. Telegram today; anything with the same methods can replace it."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Protocol

Buttons = list[list[tuple[str, str]]]  # rows of (label, callback data)


class ChannelError(RuntimeError):
    pass


class Channel(Protocol):
    def send_text(self, chat_id: int, text: str, buttons: Buttons | None = None) -> int: ...
    def edit_text(self, chat_id: int, message_id: int, text: str, buttons: Buttons | None = None) -> None: ...
    def answer_callback(self, callback_id: str, text: str | None = None) -> None: ...
    def send_voice(self, chat_id: int, audio: bytes, caption: str | None = None) -> None: ...


def _keyboard(buttons: Buttons | None) -> dict | None:
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}


def _multipart(fields: dict, file_field: str, filename: str, data: bytes, mime: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class TelegramChannel:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
        if not self.token:
            raise ChannelError("TELEGRAM_BOT_TOKEN is not set")
        self.base = f"https://api.telegram.org/bot{self.token}"

    def _call(self, method: str, payload: dict | None = None, *, body: bytes | None = None,
              content_type: str = "application/json", timeout: float = 30) -> dict:
        if body is None:
            body = json.dumps({k: v for k, v in (payload or {}).items() if v is not None}).encode()
        req = urllib.request.Request(f"{self.base}/{method}", data=body, headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            out = json.loads(exc.read() or b"{}")
        except Exception as exc:
            raise ChannelError(f"Telegram {method} failed: {exc}") from exc
        if not out.get("ok"):
            raise ChannelError(f"Telegram {method}: {out.get('description', out)}")
        return out["result"]

    def send_text(self, chat_id, text, buttons=None):
        res = self._call("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": _keyboard(buttons)})
        return res["message_id"]

    def edit_text(self, chat_id, message_id, text, buttons=None):
        self._call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text,
                                       "reply_markup": _keyboard(buttons)})

    def answer_callback(self, callback_id, text=None):
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def send_voice(self, chat_id, audio, caption=None):
        fields = {"chat_id": chat_id, **({"caption": caption} if caption else {})}
        try:
            body, ctype = _multipart(fields, "voice", "saans-saathi.mp3", audio, "audio/mpeg")
            self._call("sendVoice", body=body, content_type=ctype, timeout=60)
        except ChannelError:
            # Some clients/privacy settings refuse voice messages; a regular audio file still plays.
            body, ctype = _multipart(fields, "audio", "saans-saathi.mp3", audio, "audio/mpeg")
            self._call("sendAudio", body=body, content_type=ctype, timeout=60)

    # Transport helpers (not part of the Channel interface)
    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict]:
        return self._call("getUpdates", {"offset": offset, "timeout": timeout,
                                         "allowed_updates": ["message", "callback_query"]}, timeout=timeout + 10)

    def delete_webhook(self) -> None:
        self._call("deleteWebhook", {})

    def set_webhook(self, url: str, secret: str) -> None:
        self._call("setWebhook", {"url": url, "secret_token": secret,
                                  "allowed_updates": ["message", "callback_query"]})
