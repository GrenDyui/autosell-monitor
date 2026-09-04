"""
AutoSell Monitor - app Android (Kivy).

Nhan du lieu qua webhook HTTP local (mac dinh cong 8788) - thuong tu script
Termux dang chay Discord relay tren CUNG dien thoai (xem "forward_url"
trong autosell_termux.py). Hien thi so lieu AutoSell, tu dong phat hien 3
tinh huong (mat ket noi / dung yen / phat hien nguoi choi gan) va bao qua
thong bao Android, dung logic GIONG HET ban desktop/Termux (autosell_core.py).

App KHONG tu ket noi Discord (khong dung discord.py/aiohttp) de qua trinh
build APK cho Android on dinh hon.
"""

from __future__ import annotations

import json
import os
import queue
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import autosell_core as core

DEFAULT_PORT = 8788

ALERT_COLOR = (1, 0.45, 0.45, 1)
NORMAL_COLOR = (1, 1, 1, 1)
DIM_COLOR = (0.6, 0.65, 0.7, 1)
BG_COLOR = (0.07, 0.09, 0.11, 1)
CARD_COLOR = (0.11, 0.13, 0.16, 1)


def _config_dir() -> str:
    try:
        return App.get_running_app().user_data_dir
    except Exception:
        return os.path.expanduser("~/.autosell_monitor")


def notify(title: str, message: str):
    """Gui 1 thong bao Android qua thu vien android-notify (pure Python,
    khong keo theo goi phu thuoc nao khac - tranh loi build tung gap voi
    plyer). Tren desktop se im lang bo qua thay vi crash, de con test duoc
    main.py ngoai Android."""
    if platform != "android":
        return
    try:
        from android_notify import Notification
        Notification(title=title, message=message).send()
    except Exception:
        pass


def request_android_permissions():
    if platform != "android":
        return
    try:
        from android.permissions import Permission, request_permissions
        request_permissions([Permission.POST_NOTIFICATIONS])
    except Exception:
        pass


class CardWidget(BoxLayout):
    """1 khoi hien thi 1 webhook report - duoc SUA lai tai cho khi co du
    lieu moi (khong tao widget moi) neu bo field khong doi, giong het hanh
    vi cua ban desktop/Termux."""

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical", size_hint_y=None, spacing=2,
            padding=[12, 8, 12, 8], **kwargs,
        )
        self.bind(minimum_height=self.setter("height"))

        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            self._bg_color = Color(*CARD_COLOR)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        self.title_label = Label(
            text="", bold=True, font_size="15sp", size_hint_y=None, height=26,
            halign="left", valign="middle", shorten=True, color=NORMAL_COLOR,
        )
        self.title_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.title_label)

        self.fields_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=1)
        self.fields_box.bind(minimum_height=self.fields_box.setter("height"))
        self.add_widget(self.fields_box)

        self.time_label = Label(
            text="", size_hint_y=None, height=18, font_size="11sp",
            halign="left", valign="middle", color=DIM_COLOR,
        )
        self.time_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.time_label)

        self._field_labels = {}
        self._field_order = []

    def _sync_bg(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def update(self, data: dict):
        kind = data.get("kind", "stats")
        prefix = "⚠ " if kind == "alert" else ""
        self.title_label.text = f"{prefix}{data['title']}"
        self.title_label.color = ALERT_COLOR if kind == "alert" else NORMAL_COLOR

        fields = list(data["fields"])
        if data.get("content"):
            fields = [("Message", data["content"])] + fields
        names = [n for n, _ in fields]

        if names != self._field_order:
            self.fields_box.clear_widgets()
            self._field_labels = {}
            self._field_order = names
            for name, value in fields:
                lbl = Label(
                    text=f"{name}: {value}", size_hint_y=None, height=22,
                    font_size="13sp", halign="left", valign="middle",
                    color=NORMAL_COLOR,
                )
                lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
                self.fields_box.add_widget(lbl)
                self._field_labels[name] = lbl
        else:
            for name, value in fields:
                lbl = self._field_labels[name]
                new_text = f"{name}: {value}"
                if lbl.text != new_text:
                    lbl.text = new_text

        self.time_label.text = f"Cập nhật {datetime.now().strftime('%H:%M:%S')}"


class SettingsPopup(Popup):
    def __init__(self, app: "AutoSellMonitorApp", **kwargs):
        super().__init__(title="Cài đặt", size_hint=(0.9, 0.85), **kwargs)
        self.app_ref = app

        root = BoxLayout(orientation="vertical", spacing=10, padding=14)

        root.add_widget(Label(
            text="URL để dán vào script Termux (forward_url):",
            size_hint_y=None, height=24, halign="left", valign="middle",
        ))
        url_input = TextInput(
            text=app.webhook_url, readonly=True, multiline=False,
            size_hint_y=None, height=42, font_size="13sp",
        )
        root.add_widget(url_input)

        root.add_widget(Label(
            text="Ngưỡng phát hiện đứng yên (giây):",
            size_hint_y=None, height=24, halign="left", valign="middle",
        ))
        self.stall_input = TextInput(
            text=str(app.config_data.get("stall_threshold_seconds", 90)),
            multiline=False, input_filter="float",
            size_hint_y=None, height=42,
        )
        root.add_widget(self.stall_input)

        counts = app.event_log.counts()
        stats_text = (
            f"Mất kết nối: {counts.get('disconnect', 0)}   "
            f"Đứng yên: {counts.get('stall', 0)}   "
            f"Phát hiện người chơi: {counts.get('player_detected', 0)}"
        )
        root.add_widget(Label(text=stats_text, size_hint_y=None, height=24, font_size="12sp"))

        self.status_label = Label(text="", size_hint_y=None, height=22, font_size="12sp")
        root.add_widget(self.status_label)

        btn_row = BoxLayout(size_hint_y=None, height=48, spacing=10)
        save_btn = Button(text="Lưu")
        save_btn.bind(on_release=self._on_save)
        clear_btn = Button(text="Xóa lịch sử sự kiện")
        clear_btn.bind(on_release=self._on_clear)
        close_btn = Button(text="Đóng")
        close_btn.bind(on_release=lambda *_: self.dismiss())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(clear_btn)
        btn_row.add_widget(close_btn)
        root.add_widget(btn_row)

        root.add_widget(Label(text="", size_hint_y=1))  # spacer day cac widget len tren

        self.content = root

    def _on_save(self, *_args):
        try:
            seconds = max(5.0, float(self.stall_input.text.strip() or "90"))
        except ValueError:
            self.status_label.text = "⚠ Giá trị không hợp lệ."
            self.status_label.color = ALERT_COLOR
            return
        self.app_ref.config_data["stall_threshold_seconds"] = seconds
        self.app_ref.event_tracker.stall_threshold_seconds = seconds
        self.app_ref.save_config()
        self.status_label.text = "Đã lưu."
        self.status_label.color = NORMAL_COLOR

    def _on_clear(self, *_args):
        self.app_ref.event_log.clear()
        self.status_label.text = "Đã xóa lịch sử sự kiện."
        self.status_label.color = NORMAL_COLOR
        self.app_ref.update_event_counts()


class AutoSellMonitorApp(App):
    title = "AutoSell Monitor"

    def build(self):
        Window.clearcolor = BG_COLOR

        self.update_queue: "queue.Queue" = queue.Queue()
        self.cards = {}
        self._alert_hide_ev = None

        os.makedirs(_config_dir(), exist_ok=True)
        self.config_path = os.path.join(_config_dir(), "autosell_monitor_config.json")
        self.events_path = os.path.join(_config_dir(), "autosell_monitor_events.json")
        self.config_data = self.load_config()

        self.event_log = core.EventLog(self.events_path)
        self.event_tracker = core.EventTracker(
            self.event_log, on_event=self.on_event,
            stall_threshold_seconds=float(self.config_data.get("stall_threshold_seconds", 90)),
        )

        port = int(self.config_data.get("port", DEFAULT_PORT))
        self.webhook_url = f"http://127.0.0.1:{port}/webhook"
        self.server = core.make_server(
            "127.0.0.1", port, lambda payload: self.update_queue.put(payload),
        )

        request_android_permissions()

        root = BoxLayout(orientation="vertical")

        header = BoxLayout(orientation="vertical", size_hint_y=None, height=86, padding=[14, 10, 14, 6])
        title_row = BoxLayout(size_hint_y=None, height=34)
        title_row.add_widget(Label(
            text="AutoSell Monitor", bold=True, font_size="19sp",
            halign="left", valign="middle",
        ))
        gear_btn = Button(text="⚙", size_hint=(None, None), size=(44, 34))
        gear_btn.bind(on_release=lambda *_: SettingsPopup(self).open())
        title_row.add_widget(gear_btn)
        header.add_widget(title_row)

        self.url_label = Label(
            text=self.webhook_url, font_size="11sp", color=DIM_COLOR,
            size_hint_y=None, height=18, halign="left", valign="middle",
        )
        self.url_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        header.add_widget(self.url_label)

        self.counts_label = Label(
            text="", font_size="12sp", color=DIM_COLOR,
            size_hint_y=None, height=20, halign="left", valign="middle",
        )
        self.counts_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        header.add_widget(self.counts_label)
        root.add_widget(header)

        self.alert_banner = Label(
            text="", size_hint_y=None, height=0, font_size="12sp",
            bold=True, color=(1, 1, 1, 1),
        )
        with self.alert_banner.canvas.before:
            from kivy.graphics import Color, Rectangle
            self._banner_color = Color(0.45, 0.15, 0.18, 1)
            self._banner_rect = Rectangle(pos=self.alert_banner.pos, size=self.alert_banner.size)
        self.alert_banner.bind(
            pos=lambda *_: setattr(self._banner_rect, "pos", self.alert_banner.pos),
            size=lambda *_: setattr(self._banner_rect, "size", self.alert_banner.size),
        )
        root.add_widget(self.alert_banner)

        self.cards_layout = GridLayout(cols=1, size_hint_y=None, spacing=8, padding=[8, 8, 8, 8])
        self.cards_layout.bind(minimum_height=self.cards_layout.setter("height"))

        self.empty_label = Label(text="Chưa có dữ liệu...\nĐang chờ webhook.", color=DIM_COLOR)
        self.cards_layout.add_widget(self.empty_label)

        scroll = ScrollView()
        scroll.add_widget(self.cards_layout)
        root.add_widget(scroll)

        self.update_event_counts()
        Clock.schedule_interval(self.poll_queue, 0.3)
        return root

    # ---------------- config ----------------
    def load_config(self) -> dict:
        default = {"port": DEFAULT_PORT, "stall_threshold_seconds": 90}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            default.update({k: v for k, v in data.items() if k in default})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return default

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---------------- data flow ----------------
    def poll_queue(self, _dt):
        while True:
            try:
                payload = self.update_queue.get_nowait()
            except queue.Empty:
                break
            self.apply_payload(payload)

    def apply_payload(self, payload: dict):
        if self.empty_label.parent is not None:
            self.cards_layout.remove_widget(self.empty_label)

        card_id = payload["id"]
        card = self.cards.get(card_id)
        if card is None:
            card = CardWidget()
            self.cards[card_id] = card
            self.cards_layout.add_widget(card)
        card.update(payload)

        kind = payload.get("kind", "stats")
        if kind == "alert":
            self.event_tracker.process_alert(card_id, payload["title"], payload["fields"])
        else:
            self.event_tracker.process_stats(card_id, payload["fields"])

    def on_event(self, entry: dict):
        # co the duoc goi tu luong khac (khong phai UI thread) trong tuong
        # lai - dua ve UI thread bang Clock.schedule_once cho an toan.
        Clock.schedule_once(lambda _dt: self._apply_event_ui(entry), 0)

    def _apply_event_ui(self, entry: dict):
        self.update_event_counts()

        label = core.EVENT_LABELS.get(entry["kind"], entry["kind"])
        text = f"⚠ {label} lúc {entry['time'][11:19]} — {entry['detail']}"
        self.alert_banner.text = text
        self.alert_banner.height = 40
        self.alert_banner.padding = [12, 8, 12, 8]

        if self._alert_hide_ev is not None:
            self._alert_hide_ev.cancel()
        self._alert_hide_ev = Clock.schedule_once(self._hide_banner, 10)

        notify(f"⚠ {label}", entry["detail"])

    def _hide_banner(self, _dt):
        self.alert_banner.height = 0
        self.alert_banner.text = ""

    def update_event_counts(self):
        counts = self.event_log.counts()
        self.counts_label.text = (
            f"Mất kết nối: {counts.get('disconnect', 0)}   "
            f"Đứng yên: {counts.get('stall', 0)}   "
            f"Người chơi gần: {counts.get('player_detected', 0)}"
        )

    def on_pause(self):
        return True  # cho phep app o nen khi bam Home, khong bi huy ngay

    def on_stop(self):
        try:
            self.server.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    AutoSellMonitorApp().run()
