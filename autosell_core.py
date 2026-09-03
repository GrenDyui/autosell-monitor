"""
Phan loi (backend) dung chung cho app Android AutoSell Monitor.

CO TINH CHU Y: file nay KHONG import discord.py/aiohttp - chi dung thu vien
chuan cua Python (http.server, json, threading...) de python-for-android
build APK it rui ro loi nhat co the. App Android nhan du lieu qua webhook
HTTP local (tu script Termux dang chay Discord relay tren cung may, hoac tu
bat ky nguon nao khac gui toi), khong tu ket noi Discord.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


EVENT_LABELS = {
    "disconnect": "Mat ket noi / Rot server",
    "stall": "Dung yen (khong earn du Running)",
    "player_detected": "Phat hien nguoi choi gan",
}

PLAYER_ALERT_KEYWORDS = (
    "player detection",
    "detection alert",
    "player alert",
    "phat hien nguoi choi",
)


def classify_title(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in PLAYER_ALERT_KEYWORDS):
        return "alert"
    return "stats"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "card"


def normalize_payload(data) -> dict:
    """Giong het ban desktop/termux - chap nhan JSON tu do hoac kieu Discord
    webhook (co 'embeds')."""
    if not isinstance(data, dict):
        data = {"content": str(data)}

    title = None
    fields = []
    content = data.get("content")

    embeds = data.get("embeds")
    if isinstance(embeds, list) and embeds:
        embed = embeds[0] or {}
        title = embed.get("title")
        if embed.get("description"):
            fields.append(("Description", str(embed["description"])))
        for f in embed.get("fields", []) or []:
            name = str(f.get("name", "")).strip() or "-"
            value = str(f.get("value", ""))
            fields.append((name, value))
    else:
        raw_fields = data.get("fields")
        if isinstance(raw_fields, dict):
            fields = [(str(k), str(v)) for k, v in raw_fields.items()]
        elif isinstance(raw_fields, list):
            for f in raw_fields:
                if isinstance(f, dict):
                    name = str(f.get("name", "")).strip() or "-"
                    value = str(f.get("value", ""))
                    fields.append((name, value))
                elif isinstance(f, (list, tuple)) and len(f) == 2:
                    fields.append((str(f[0]), str(f[1])))
        title = data.get("title")

    card_id = str(data.get("id") or title or "default")
    if not title:
        title = card_id

    kind = data.get("kind") or classify_title(title)

    return {"id": card_id, "title": title, "fields": fields, "content": content, "kind": kind}


# ---------- HTTP server: nhan webhook tu Termux (hoac bat ky nguon nao) ----------
def make_server(host: str, port: int, on_payload):
    """Tao 1 ThreadingHTTPServer; moi khi nhan duoc POST/PUT/PATCH hop le se
    goi on_payload(normalized_dict) - chay tren thread rieng cua request do."""

    class Handler(BaseHTTPRequestHandler):
        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                length = 0
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {"content": raw.decode("utf-8", errors="replace")}

        def _handle(self):
            data = self._read_json()
            try:
                normalized = normalize_payload(data)
                on_payload(normalized)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as e:  # noqa: BLE001
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())

        def do_POST(self):
            self._handle()

        def do_PATCH(self):
            self._handle()

        def do_PUT(self):
            self._handle()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"AutoSell Monitor dang chay. POST JSON toi URL nay.")

        def log_message(self, fmt, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------- Theo doi su kien (giong het ban desktop/termux) ----------
class EventLog:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.events = self._load()

    def _load(self) -> list:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.events, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add(self, kind: str, card_id: str, detail: str, ongoing: bool = False) -> dict:
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "card_id": card_id,
            "detail": detail,
            "ongoing": ongoing,
        }
        with self._lock:
            self.events.append(entry)
            self._save()
        return entry

    def end_ongoing(self, kind: str, card_id: str, new_detail: str):
        with self._lock:
            for entry in reversed(self.events):
                if entry["kind"] == kind and entry["card_id"] == card_id and entry.get("ongoing"):
                    entry["ongoing"] = False
                    entry["detail"] = new_detail
                    self._save()
                    return entry
        return None

    def counts(self) -> dict:
        with self._lock:
            c = {}
            for e in self.events:
                c[e["kind"]] = c.get(e["kind"], 0) + 1
            return c

    def recent(self, limit: int = 300) -> list:
        with self._lock:
            return list(reversed(self.events[-limit:]))

    def clear(self):
        with self._lock:
            self.events = []
            self._save()


class EventTracker:
    def __init__(self, event_log: EventLog, on_event=None, stall_threshold_seconds: float = 90):
        self.log = event_log
        self.on_event = on_event
        self.stall_threshold_seconds = stall_threshold_seconds
        self._last_status = {}
        self._last_earned = {}
        self._stall_started = {}

    def _fire(self, entry):
        if entry is not None and self.on_event:
            self.on_event(entry)

    def process_stats(self, card_id: str, fields: list):
        field_map = {str(n): v for n, v in fields}
        status_raw = field_map.get("Status")
        status = str(status_raw).strip().lower() if status_raw is not None else ""
        earned = field_map.get("Earned")

        prev_status = self._last_status.get(card_id)
        self._last_status[card_id] = status or prev_status
        if status:
            if prev_status == "running" and status != "running":
                self._fire(self.log.add(
                    "disconnect", card_id,
                    f"Status: Running -> {status.capitalize()}",
                ))

        if status == "running" and earned is not None:
            now = datetime.now()
            prev = self._last_earned.get(card_id)
            if prev is None or prev[0] != earned:
                if self._stall_started.get(card_id):
                    started = self._stall_started[card_id]
                    duration = (now - started).total_seconds()
                    self._fire(self.log.end_ongoing(
                        "stall", card_id,
                        f"Dung yen khoang {int(duration)}s roi earn tro lai",
                    ))
                    self._stall_started[card_id] = None
                self._last_earned[card_id] = (earned, now)
            else:
                since = (now - prev[1]).total_seconds()
                if since >= self.stall_threshold_seconds and not self._stall_started.get(card_id):
                    self._stall_started[card_id] = prev[1]
                    self._fire(self.log.add(
                        "stall", card_id,
                        f"Earned khong doi ({earned}) du Status van Running "
                        f"(>= {int(self.stall_threshold_seconds)}s) - dang tiep dien...",
                        ongoing=True,
                    ))
        elif status and status != "running":
            self._last_earned.pop(card_id, None)
            self._stall_started[card_id] = None

    def process_alert(self, card_id: str, title: str, fields: list):
        parts = [f"{n}: {v}" for n, v in fields]
        detail = "; ".join(parts) if parts else (title or "")
        self._fire(self.log.add("player_detected", card_id, detail))
