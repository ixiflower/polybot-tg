import os
import sys
import re
import base64
import asyncio
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs

import httpx
from dotenv import load_dotenv

load_dotenv("main.env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = "@" + CHANNEL_ID_RAW.rsplit("/", 1)[-1].lstrip("@")
DB_PATH = os.getenv("DB_PATH", "data/polybot.db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lstrip("@").lower()

CHECK_INTERVAL = 5
PROXY_URL = "https://raw.githubusercontent.com/Grim1313/mtproto-for-telegram/master/all_proxies.txt"
VMESS_URL = ""
VLESS_URL = ""
V2RAY_URL = ""
CONFIG_NAME = "ixi-conf"
PING_TIMEOUT = 5.0
MAX_PING = 250
MAX_PROXY_PER_INTERVAL = 6
PROXY_PER_MESSAGE = 3
GOLDEN_PING = 50
MAX_CONFIG_CHECK = 200
MAX_CONFIG_PER_INTERVAL = 6
CONFIG_SCORES: dict[str, int] = {}


def get_setting(key: str, default: str = "") -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default


def delete_setting(key: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))


def set_setting(key: str, value: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_all_settings() -> dict[str, str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return dict(rows)


ENABLE_PANEL = True
ENABLE_PROXIES = True
ENABLE_CONFIGS = True


def apply_db_overrides() -> None:
    global CHECK_INTERVAL, PROXY_URL, VMESS_URL, VLESS_URL, V2RAY_URL
    global CONFIG_NAME, PING_TIMEOUT, MAX_PING, MAX_PROXY_PER_INTERVAL
    global PROXY_PER_MESSAGE, GOLDEN_PING, MAX_CONFIG_CHECK, MAX_CONFIG_PER_INTERVAL, CONFIG_SCORES
    global CHANNEL_ID, CHANNEL_ID_RAW, ADMIN_USERNAME, ENABLE_PANEL, ENABLE_PROXIES, ENABLE_CONFIGS

    overrides = get_all_settings()
    if overrides.get("ENABLE_PANEL"):
        ENABLE_PANEL = overrides["ENABLE_PANEL"].lower() == "true"
    if overrides.get("ENABLE_PROXIES"):
        ENABLE_PROXIES = overrides["ENABLE_PROXIES"].lower() == "true"
    if overrides.get("ENABLE_CONFIGS"):
        ENABLE_CONFIGS = overrides["ENABLE_CONFIGS"].lower() == "true"
    if overrides.get("CHECK_INTERVAL"):
        CHECK_INTERVAL = int(overrides["CHECK_INTERVAL"])
    if overrides.get("PROXY_URL"):
        PROXY_URL = overrides["PROXY_URL"]
    if overrides.get("VMESS_URL"):
        VMESS_URL = overrides["VMESS_URL"]
    if overrides.get("VLESS_URL"):
        VLESS_URL = overrides["VLESS_URL"]
    if overrides.get("V2RAY_URL"):
        V2RAY_URL = overrides["V2RAY_URL"]
    if overrides.get("VMESS_URL_2"):
        VMESS_URL_2 = overrides["VMESS_URL_2"]
    if overrides.get("VLESS_URL_2"):
        VLESS_URL_2 = overrides["VLESS_URL_2"]
    if overrides.get("CONFIG_NAME"):
        CONFIG_NAME = overrides["CONFIG_NAME"]
    if overrides.get("PING_TIMEOUT"):
        PING_TIMEOUT = float(overrides["PING_TIMEOUT"])
    if overrides.get("MAX_PING"):
        MAX_PING = int(overrides["MAX_PING"])
    if overrides.get("MAX_PROXY_PER_INTERVAL"):
        MAX_PROXY_PER_INTERVAL = int(overrides["MAX_PROXY_PER_INTERVAL"])
    if overrides.get("PROXY_PER_MESSAGE"):
        PROXY_PER_MESSAGE = int(overrides["PROXY_PER_MESSAGE"])
    if overrides.get("GOLDEN_PING"):
        GOLDEN_PING = int(overrides["GOLDEN_PING"])
    if overrides.get("MAX_CONFIG_CHECK"):
        MAX_CONFIG_CHECK = int(overrides["MAX_CONFIG_CHECK"])
    if overrides.get("MAX_CONFIG_PER_INTERVAL"):
        MAX_CONFIG_PER_INTERVAL = int(overrides["MAX_CONFIG_PER_INTERVAL"])
    if overrides.get("CONFIG_SCORES"):
        CONFIG_SCORES = json.loads(overrides["CONFIG_SCORES"])
    if overrides.get("CHANNEL_ID_RAW"):
        CHANNEL_ID_RAW = overrides["CHANNEL_ID_RAW"]
        CHANNEL_ID = "@" + CHANNEL_ID_RAW.rsplit("/", 1)[-1].lstrip("@")
    if overrides.get("ADMIN_USERNAME"):
        ADMIN_USERNAME = overrides["ADMIN_USERNAME"].lstrip("@").lower()


VMESS_URL_2 = ""
VLESS_URL_2 = ""


def build_main_menu(user_is_admin: bool = False) -> tuple[str, dict]:
    text = (
        "🤖 <b>PolyBot</b>\n"
        "MTProto & V2Ray Auto Poster\n\n"
        "📡 <b>Status</b> — view bot statistics\n"
        "⚙️ <b>Admin Panel</b> — manage settings\n"
        "ℹ️ <b>About</b> — about the bot"
    )
    rows = [
        [{"text": "📡 Status", "callback_data": "menu:status"}],
        [{"text": "ℹ️ About", "callback_data": "menu:about"}],
    ]
    if user_is_admin:
        rows.insert(0, [{"text": "⚙️ Admin Panel", "callback_data": "menu:admin"}])
    return text, {"inline_keyboard": rows}


def build_status_page() -> tuple[str, dict]:
    with sqlite3.connect(DB_PATH) as conn:
        proxies = conn.execute("SELECT COUNT(*) FROM proxies").fetchone()[0]
        configs = conn.execute("SELECT COUNT(*) FROM configs").fetchone()[0]
    text = (
        f"📡 <b>Bot Status</b>\n\n"
        f"MTProto proxies sent: <b>{proxies}</b>\n"
        f"V2Ray configs sent: <b>{configs}</b>\n\n"
        f"🔄 Check interval: {CHECK_INTERVAL} min\n"
        f"⚡ Max ping: {MAX_PING}ms\n"
        f"📊 Max proxies/cycle: {MAX_PROXY_PER_INTERVAL}\n"
        f"📊 Max configs/cycle: {MAX_CONFIG_PER_INTERVAL}\n"
        f"📦 Configs per message: {PROXY_PER_MESSAGE}"
    )
    kb = {"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "menu:main"}]]}
    return text, kb


def build_about_page() -> tuple[str, dict]:
    text = (
        "ℹ️ <b>PolyBot</b>\n\n"
        "📌 Automatically fetches MTProto proxies and V2Ray configs,\n"
        "pings them, and posts the best ones to your channel.\n\n"
        "⚡ Golden proxies (ping &lt; 50ms) get special treatment.\n"
        "🚫 Duplicate prevention via SQLite database.\n"
        "🔧 Configurable via inline admin panel.\n\n"
        f"📢 Channel: {CHANNEL_ID}"
    )
    kb = {"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "menu:main"}]]}
    return text, kb


pending_inputs: dict[int, str] = {}


def cur_val(key: str) -> str:
    db = get_setting(key)
    if db:
        return db
    return str({
        "CHECK_INTERVAL": CHECK_INTERVAL,
        "PROXY_URL": PROXY_URL,
        "VMESS_URL": VMESS_URL,
        "VLESS_URL": VLESS_URL,
        "V2RAY_URL": V2RAY_URL,
        "VMESS_URL_2": VMESS_URL_2,
        "VLESS_URL_2": VLESS_URL_2,
        "CONFIG_NAME": CONFIG_NAME,
        "PING_TIMEOUT": PING_TIMEOUT,
        "MAX_PING": MAX_PING,
        "MAX_PROXY_PER_INTERVAL": MAX_PROXY_PER_INTERVAL,
        "PROXY_PER_MESSAGE": PROXY_PER_MESSAGE,
        "GOLDEN_PING": GOLDEN_PING,
        "MAX_CONFIG_CHECK": MAX_CONFIG_CHECK,
        "MAX_CONFIG_PER_INTERVAL": MAX_CONFIG_PER_INTERVAL,
        "CONFIG_SCORES": json.dumps(CONFIG_SCORES),
        "CHANNEL_ID_RAW": CHANNEL_ID_RAW,
        "ADMIN_USERNAME": ADMIN_USERNAME,
        "BOT_TOKEN": BOT_TOKEN,
        "DB_PATH": DB_PATH,
        "ENABLE_PANEL": str(ENABLE_PANEL),
        "ENABLE_PROXIES": str(ENABLE_PROXIES),
        "ENABLE_CONFIGS": str(ENABLE_CONFIGS),
    }.get(key, ""))


NUMERIC_KEYS = {
    "CHECK_INTERVAL": [1, 2, 5, 10, 15, 30, 60],
    "PING_TIMEOUT": [1, 2, 3, 5, 10],
    "MAX_PING": [50, 100, 150, 200, 250, 300, 500],
    "GOLDEN_PING": [20, 30, 50, 75, 100],
    "PROXY_PER_MESSAGE": list(range(1, 11)),
    "MAX_PROXY_PER_INTERVAL": list(range(1, 21)),
}


def build_admin_home() -> tuple[str, dict]:
    text = (
        "╔═══ ⚙️ Admin Panel ═══╗\n\n"
        "Choose a category:\n\n"
        f"⏱ <b>Limits & Timers</b>\n"
        f"🔗 <b>Source URLs</b>\n"
        f"⚙️ <b>General Config</b>\n"
        f"🎯 <b>Actions</b>\n\n"
        f"<i>C: {CHECK_INTERVAL}m | P: {PROXY_PER_MESSAGE}ppp | "
        f"MP: {MAX_PROXY_PER_INTERVAL} | MC: {MAX_CONFIG_PER_INTERVAL} | "
        f"⚡{MAX_PING}ms</i>"
    )
    kb = {
        "inline_keyboard": [
            [{"text": "⏱ Limits & Timers", "callback_data": "admin:section:limits"},
             {"text": "📦 Config Sources", "callback_data": "admin:section:configs"}],
            [{"text": "🔗 Proxy Source", "callback_data": "admin:section:urls"},
             {"text": "⚙️ General Config", "callback_data": "admin:section:general"}],
            [{"text": "🎯 Actions", "callback_data": "admin:section:actions"}],
            [{"text": "🔙 Back to Menu", "callback_data": "menu:main"}],
        ]
    }
    return text, kb


def build_limits_section() -> tuple[str, dict]:
    text = "╔═══ ⏱ Limits & Timers ═══╗\n\n"
    rows: list[list[dict]] = []
    for key, vals in NUMERIC_KEYS.items():
        v = cur_val(key)
        text += f"<b>{key}</b>: <code>{v}</code>\n"
        btn_row = [{"text": str(x), "callback_data": f"admin:set:{key}:{x}"} for x in vals]
        rows.append(btn_row)
        rows.append([{"text": f"✏️ Custom {key}", "callback_data": f"admin:edit:{key}"}])
    rows.append([{"text": "🔙 Back to Admin", "callback_data": "admin:section:home"}])
    return text, {"inline_keyboard": rows}


def build_urls_section() -> tuple[str, dict]:
    text = "╔═══ 🔗 Proxy Source ═══╗\n\n"
    v = cur_val("PROXY_URL")
    short = v[:60] + "..." if len(v) > 60 else v
    text += f"<b>PROXY_URL</b>\n<code>{short}</code>\n\n"
    text += "Click ✏️ to edit."
    rows = [
        [{"text": "✏️ Edit PROXY_URL", "callback_data": "admin:edit:PROXY_URL"}],
        [{"text": "🔙 Back to Admin", "callback_data": "admin:section:home"}],
    ]
    return text, {"inline_keyboard": rows}


def build_configs_section() -> tuple[str, dict]:
    text = "╔═══ 📦 Config Sources ═══╗\n\n"
    url_keys = ["VMESS_URL", "VMESS_URL_2", "VLESS_URL", "VLESS_URL_2", "V2RAY_URL"]
    for k in url_keys:
        v = cur_val(k)
        short = v[:40] + "..." if len(v) > 40 else v
        text += f"🔗 <b>{k}</b>: <code>{short}</code>\n"
    text += f"\n📛 <b>CONFIG_NAME</b>: <code>{cur_val('CONFIG_NAME')}</code>\n"
    text += f"📊 <b>CONFIG_SCORES</b>: <code>{cur_val('CONFIG_SCORES')}</code>\n"
    text += f"🔍 <b>MAX_CONFIG_CHECK</b>: <code>{cur_val('MAX_CONFIG_CHECK')}</code>\n"
    text += f"📬 <b>MAX_CONFIG_PER_INTERVAL</b>: <code>{cur_val('MAX_CONFIG_PER_INTERVAL')}</code>\n\n"
    text += "Click values to change or ✏️ for custom."

    rows = [
        [{"text": "✏️ VMESS_URL", "callback_data": "admin:edit:VMESS_URL"},
         {"text": "✏️ VMESS_URL_2", "callback_data": "admin:edit:VMESS_URL_2"}],
        [{"text": "✏️ VLESS_URL", "callback_data": "admin:edit:VLESS_URL"},
         {"text": "✏️ VLESS_URL_2", "callback_data": "admin:edit:VLESS_URL_2"}],
        [{"text": "✏️ V2RAY_URL", "callback_data": "admin:edit:V2RAY_URL"},
         {"text": "✏️ CONFIG_NAME", "callback_data": "admin:edit:CONFIG_NAME"}],
        [{"text": "✏️ CONFIG_SCORES", "callback_data": "admin:edit:CONFIG_SCORES"}],
        [
            {"text": "50", "callback_data": "admin:set:MAX_CONFIG_CHECK:50"},
            {"text": "100", "callback_data": "admin:set:MAX_CONFIG_CHECK:100"},
            {"text": "200", "callback_data": "admin:set:MAX_CONFIG_CHECK:200"},
            {"text": "300", "callback_data": "admin:set:MAX_CONFIG_CHECK:300"},
            {"text": "500", "callback_data": "admin:set:MAX_CONFIG_CHECK:500"},
        ],
        [{"text": "✏️ Custom MAX_CONFIG_CHECK", "callback_data": "admin:edit:MAX_CONFIG_CHECK"}],
        [
            {"text": "1", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:1"},
            {"text": "2", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:2"},
            {"text": "3", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:3"},
            {"text": "4", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:4"},
            {"text": "5", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:5"},
            {"text": "6", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:6"},
            {"text": "8", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:8"},
            {"text": "10", "callback_data": "admin:set:MAX_CONFIG_PER_INTERVAL:10"},
        ],
        [{"text": "✏️ Custom MAX_CONFIG_PER_INTERVAL", "callback_data": "admin:edit:MAX_CONFIG_PER_INTERVAL"}],
        [{"text": "🔙 Back to Admin", "callback_data": "admin:section:home"}],
    ]
    return text, {"inline_keyboard": rows}


def build_general_section() -> tuple[str, dict]:
    text = "╔═══ ⚙️ General Config ═══╗\n\n"
    keys = ["CHANNEL_ID_RAW", "ADMIN_USERNAME", "BOT_TOKEN", "DB_PATH"]
    for k in keys:
        v = cur_val(k)
        short = v[:40] + "..." if len(v) > 40 else v
        text += f"<b>{k}</b>\n<code>{short}</code>\n\n"
    text += "Click ✏️ to edit."
    rows = [
        [{"text": "✏️ CHANNEL_ID", "callback_data": "admin:edit:CHANNEL_ID_RAW"},
         {"text": "✏️ ADMIN_USERNAME", "callback_data": "admin:edit:ADMIN_USERNAME"}],
        [{"text": "✏️ BOT_TOKEN", "callback_data": "admin:edit:BOT_TOKEN"}],
        [{"text": "🔙 Back to Admin", "callback_data": "admin:section:home"}],
    ]
    return text, {"inline_keyboard": rows}


def build_actions_section() -> tuple[str, dict]:
    pan = "🟢 ON" if ENABLE_PANEL else "🔴 OFF"
    prx = "🟢 ON" if ENABLE_PROXIES else "🔴 OFF"
    cfg = "🟢 ON" if ENABLE_CONFIGS else "🔴 OFF"
    text = "╔═══ 🎯 Actions ═══╗\n\n"
    text += f"🖥 <b>Panel</b>: {pan}\n"
    text += f"📡 <b>Proxies</b>: {prx}\n"
    text += f"📦 <b>Configs</b>: {cfg}\n"
    text += "🔄 <b>Force Check</b> — run now\n"
    rows = [
        [{"text": f"Panel: {pan}", "callback_data": "admin:action:TOGGLE_PANEL"},
         {"text": f"Proxies: {prx}", "callback_data": "admin:action:TOGGLE_PROXIES"}],
        [{"text": f"Configs: {cfg}", "callback_data": "admin:action:TOGGLE_CONFIGS"},
         {"text": "🔄 Force Check", "callback_data": "admin:action:FORCE_CHECK"}],
        [{"text": "🔙 Back to Admin", "callback_data": "admin:section:home"}],
    ]
    return text, {"inline_keyboard": rows}


async def answer_callback(client: httpx.AsyncClient, cb_id: str, text: str = "") -> None:
    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                      json={"callback_query_id": cb_id, "text": text, "show_alert": False})


async def edit_message(client: httpx.AsyncClient, chat_id: int, msg_id: int, text: str, reply_markup: dict) -> None:
    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                      json={"chat_id": chat_id, "message_id": msg_id, "text": text,
                            "parse_mode": "HTML", "reply_markup": reply_markup})


async def send_private(client: httpx.AsyncClient, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)


async def handle_update(client: httpx.AsyncClient, update: dict) -> None:
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        user = cq.get("from", {})
        username = user.get("username", "").lower()
        chat_id = cq["message"]["chat"]["id"]
        msg_id = cq["message"]["message_id"]
        is_admin = username == ADMIN_USERNAME

        if data.startswith("menu:"):
            action = data.split(":", 1)[1]
            if action == "main":
                text, kb = build_main_menu(is_admin)
            elif action == "status":
                text, kb = build_status_page()
            elif action == "admin":
                if not is_admin:
                    await answer_callback(client, cq["id"], "⛔ Unauthorized")
                    return
                reload_config()
                apply_db_overrides()
                text, kb = build_admin_home()
            elif action == "about":
                text, kb = build_about_page()
            else:
                text, kb = build_main_menu(is_admin)
            await edit_message(client, chat_id, msg_id, text, kb)
            await answer_callback(client, cq["id"])
            return

        if data.startswith("admin:"):
            if not is_admin:
                await answer_callback(client, cq["id"], "⛔ Unauthorized")
                return
            if not ENABLE_PANEL:
                await answer_callback(client, cq["id"], "🚫 Panel is disabled")
                return
            parts = data.split(":", 2)
            if len(parts) == 3 and parts[0] == "admin" and parts[1] == "section":
                section = parts[2]
                if section == "home":
                    text, kb = build_admin_home()
                elif section == "limits":
                    text, kb = build_limits_section()
                elif section == "configs":
                    text, kb = build_configs_section()
                elif section == "urls":
                    text, kb = build_urls_section()
                elif section == "general":
                    text, kb = build_general_section()
                elif section == "actions":
                    text, kb = build_actions_section()
                else:
                    text, kb = build_admin_home()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"])
                return
            if parts[1] == "set":
                key, val = parts[2].split(":", 1) if ":" in parts[2] else (parts[2], "")
                set_setting(key, val)
                reload_config()
                apply_db_overrides()
                text, kb = build_limits_section()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"], f"✅ {key} = {val}")
                return
            if parts[1] == "edit":
                key = parts[2]
                pending_inputs[chat_id] = key
                await edit_message(client, chat_id, msg_id,
                                   f"✏️ Send me the new value for <b>{key}</b>:\n"
                                   f"(current: <code>{cur_val(key)}</code>)\n"
                                   f"Send /cancel to abort.", {})
                await answer_callback(client, cq["id"], f"Type the new {key}")
                return
            if parts[1] == "action" and parts[2] == "FORCE_CHECK":
                await edit_message(client, chat_id, msg_id, "🔄 Checking now...", {})
                await answer_callback(client, cq["id"])
                await check_and_post()
                reload_config()
                apply_db_overrides()
                text, kb = build_actions_section()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"], "✅ Check complete!")
                return
            if parts[1] == "action" and parts[2] == "TOGGLE_PANEL":
                set_setting("ENABLE_PANEL", "false" if ENABLE_PANEL else "true")
                reload_config()
                apply_db_overrides()
                text, kb = build_actions_section()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"], f"Panel {'🟢 ON' if ENABLE_PANEL else '🔴 OFF'}")
                return
            if parts[1] == "action" and parts[2] == "TOGGLE_PROXIES":
                set_setting("ENABLE_PROXIES", "false" if ENABLE_PROXIES else "true")
                reload_config()
                apply_db_overrides()
                text, kb = build_actions_section()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"], f"Proxies {'🟢 ON' if ENABLE_PROXIES else '🔴 OFF'}")
                return
            if parts[1] == "action" and parts[2] == "TOGGLE_CONFIGS":
                set_setting("ENABLE_CONFIGS", "false" if ENABLE_CONFIGS else "true")
                reload_config()
                apply_db_overrides()
                text, kb = build_actions_section()
                await edit_message(client, chat_id, msg_id, text, kb)
                await answer_callback(client, cq["id"], f"Configs {'🟢 ON' if ENABLE_CONFIGS else '🔴 OFF'}")
                return
            await answer_callback(client, cq["id"])
            return

        await answer_callback(client, cq["id"])

    elif "message" in update:
        msg = update["message"]
        user = msg.get("from", {})
        username = user.get("username", "").lower()
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        is_admin = username == ADMIN_USERNAME

        if text == "/start":
            menu_text, menu_kb = build_main_menu(is_admin)
            await send_private(client, chat_id, menu_text, menu_kb)
            return
        if is_admin and text == "/panel":
            reload_config()
            apply_db_overrides()
            if not ENABLE_PANEL:
                await send_private(client, chat_id, "🚫 Panel is disabled. Set ENABLE_PANEL=true in main.env to enable.")
                return
            panel_text, panel_kb = build_admin_home()
            await send_private(client, chat_id, panel_text, panel_kb)
            return
        if is_admin and text == "/force":
            await send_private(client, chat_id, "🔄 Force checking...")
            await check_and_post()
            await send_private(client, chat_id, "✅ Check complete!")
            return
        if is_admin and text == "/cancel" and chat_id in pending_inputs:
            key = pending_inputs.pop(chat_id)
            await send_private(client, chat_id, f"❌ Edit of <b>{key}</b> cancelled.")
            return
        if is_admin and chat_id in pending_inputs:
            key = pending_inputs.pop(chat_id)
            set_setting(key, text)
            reload_config()
            apply_db_overrides()
            await send_private(client, chat_id, f"✅ <b>{key}</b> updated!\nNew value: <code>{cur_val(key)}</code>",
                               {"inline_keyboard": [[{"text": "⚙️ Admin Panel", "callback_data": "menu:admin"}]]})
            return


async def admin_poller() -> None:
    offset = 0
    logger.info("Admin poller started for @%s", ADMIN_USERNAME)
    while True:
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await handle_update(client, update)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error("Admin poller error: %s", e)
            await asyncio.sleep(5)


def reload_config() -> None:
    global CHECK_INTERVAL, PROXY_URL, VMESS_URL, VLESS_URL, V2RAY_URL
    global CONFIG_NAME, PING_TIMEOUT, MAX_PING, MAX_PROXY_PER_INTERVAL
    global PROXY_PER_MESSAGE, GOLDEN_PING, MAX_CONFIG_CHECK, MAX_CONFIG_PER_INTERVAL, CONFIG_SCORES
    global CHANNEL_ID, CHANNEL_ID_RAW, ADMIN_USERNAME, BOT_TOKEN, DB_PATH, ENABLE_PANEL

    load_dotenv("main.env", override=True)
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "5"))
    PROXY_URL = os.getenv("PROXY_URL", "https://raw.githubusercontent.com/Grim1313/mtproto-for-telegram/master/all_proxies.txt")
    VMESS_URL = os.getenv("VMESS_URL", "")
    VLESS_URL = os.getenv("VLESS_URL", "")
    V2RAY_URL = os.getenv("V2RAY_URL", "")
    CONFIG_NAME = os.getenv("CONFIG_NAME", "ixi-conf")
    PING_TIMEOUT = float(os.getenv("PING_TIMEOUT", "5"))
    MAX_PING = int(os.getenv("MAX_PING", "250"))
    MAX_PROXY_PER_INTERVAL = int(os.getenv("MAX_PROXY_PER_INTERVAL", "5"))
    PROXY_PER_MESSAGE = int(os.getenv("PROXY_PER_MESSAGE", "3"))
    GOLDEN_PING = int(os.getenv("GOLDEN_PING", "50"))
    MAX_CONFIG_CHECK = int(os.getenv("MAX_CONFIG_CHECK", "200"))
    MAX_CONFIG_PER_INTERVAL = int(os.getenv("MAX_CONFIG_PER_INTERVAL", "6"))
    CONFIG_SCORES = json.loads(os.getenv("CONFIG_SCORES", "{}"))
    CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "")
    CHANNEL_ID = "@" + CHANNEL_ID_RAW.rsplit("/", 1)[-1].lstrip("@")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lstrip("@").lower()
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    DB_PATH = os.getenv("DB_PATH", "polybot.db")
    ENABLE_PANEL = os.getenv("ENABLE_PANEL", "true").lower() == "true"
    ENABLE_PROXIES = os.getenv("ENABLE_PROXIES", "true").lower() == "true"
    ENABLE_CONFIGS = os.getenv("ENABLE_CONFIGS", "true").lower() == "true"
    logger.info("Config reloaded")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("polybot")

reload_config()


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_url TEXT UNIQUE NOT NULL,
                server TEXT NOT NULL,
                port INTEGER NOT NULL,
                secret TEXT NOT NULL,
                ping REAL,
                sent_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_url ON proxies(raw_url)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_config TEXT UNIQUE NOT NULL,
                config_type TEXT NOT NULL,
                server TEXT,
                port INTEGER,
                ping REAL,
                sent_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_config ON configs(raw_config)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)"
        )


def load_seen(table: str, col: str) -> set[str]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
            return {row[0] for row in rows}
    except sqlite3.OperationalError:
        return set()


def save_sent(table: str, cols: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    placeholders = ", ".join(cols)
    markers = ", ".join(f":{c}" for c in cols)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            f"INSERT OR IGNORE INTO {table} ({placeholders}, sent_at) "
            f"VALUES ({markers}, :sent_at)",
            [{**r, "sent_at": now} for r in rows],
        )


async def fetch_lines(client: httpx.AsyncClient, url: str) -> list[str]:
    if not url:
        return []
    resp = await client.get(url)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip()]


def parse_proxy_url(url: str) -> dict | None:
    try:
        if url.startswith("tg://proxy?"):
            url = url.replace("tg://", "https://", 1)
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return None
        qs = parse_qs(parsed.query)
        server = qs.get("server", [None])[0]
        port_str = qs.get("port", [None])[0]
        secret = qs.get("secret", [None])[0]
        if not server or not port_str or not secret:
            return None
        return {"raw_url": url, "server": server, "port": int(port_str), "secret": secret}
    except Exception:
        return None


def parse_v2ray_config(raw: str) -> dict | None:
    try:
        if raw.startswith("vmess://"):
            b64 = raw.removeprefix("vmess://")
            b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
            pad = 4 - len(b64) % 4
            if pad != 4:
                b64 += "=" * pad
            decoded = base64.b64decode(b64).decode()
            try:
                data = json.loads(decoded)
                server = data.get("add") or data.get("host", "")
                port = int(data.get("port", 443))
            except json.JSONDecodeError:
                if "@" in decoded:
                    parts = decoded.split("@", 1)
                    addr_port = parts[1].split("?")[0] if "?" in parts[1] else parts[1]
                    if ":" in addr_port:
                        server, port_str = addr_port.rsplit(":", 1)
                        port = int(port_str.split("/")[0].split("?")[0])
                    else:
                        server, port = addr_port, 443
                else:
                    return None
            return {"raw_config": raw, "config_type": "vmess", "server": server, "port": port}

        if raw.startswith("ss://"):
            parts = raw.removeprefix("ss://").split("@")
            if len(parts) == 2:
                server_part = parts[1].split("#")[0].split("/")[0]
                if ":" in server_part:
                    host, pstr = server_part.rsplit(":", 1)
                    return {"raw_config": raw, "config_type": "ss", "server": host, "port": int(pstr)}
            return None

        if "://" in raw:
            parsed = urlparse(raw)
            if parsed.hostname:
                return {
                    "raw_config": raw,
                    "config_type": parsed.scheme,
                    "server": parsed.hostname,
                    "port": parsed.port or 443,
                }
            return None
    except Exception:
        return None
    return None


def truncate(s: str, max_len: int = 16) -> str:
    return s if len(s) <= max_len else s[:max_len] + "..."

def format_proxy_message(proxy: dict) -> str:
    return (
        f"Server: {proxy['server']}\n"
        f"Port: {proxy['port']}\n"
        f"Secret: <code>{proxy['secret']}</code>"
    )

def format_golden_message(proxy: dict) -> str:
    return (
        f"▶▶▶ G O L D E N ◀◀◀\n\n"
        f"Server: {proxy['server']}\n"
        f"Port: {proxy['port']}\n"
        f"Secret: <code>{proxy['secret']}</code>"
    )

def format_config_block(configs: list[dict]) -> str:
    lines = []
    for cfg in configs:
        raw = cfg["raw_config"]
        if "#" in raw:
            raw = raw.rsplit("#", 1)[0] + "#" + CHANNEL_ID.lstrip("@")
        lines.append(raw)
    return "<pre>" + "\n\n".join(lines) + "</pre>"

def build_connect_url(proxy: dict) -> str:
    return f"tg://proxy?server={proxy['server']}&port={proxy['port']}&secret={proxy['secret']}"


async def tcp_ping(host: str, port: int, timeout: float = 5.0) -> float | None:
    try:
        loop = asyncio.get_event_loop()
        start = loop.time()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        elapsed = (loop.time() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return elapsed
    except Exception:
        return None


async def send_message(
    client: httpx.AsyncClient,
    text: str,
    connect_urls: list[str] | None = None,
    button_labels: list[str] | None = None,
) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload: dict = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if connect_urls:
        labels = button_labels or [f"connect{i + 1}" for i in range(len(connect_urls))]
        buttons = [
            {"text": labels[i], "url": cu}
            for i, cu in enumerate(connect_urls)
        ]
        rows = [
            buttons[i:i + 3]
            for i in range(0, len(buttons), 3)
        ]
        payload["reply_markup"] = json.dumps({"inline_keyboard": rows})
    resp = await client.post(url, json=payload)
    resp.raise_for_status()


async def process_mtproto(seen: set[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        raw = await fetch_lines(client, PROXY_URL)
    new_raw = [p for p in raw if p not in seen]
    if not new_raw:
        return []

    parsed: list[dict] = []
    for p in new_raw:
        info = parse_proxy_url(p)
        if info:
            parsed.append(info)

    if not parsed:
        return []

    logger.info("Pinging %d MTProto proxy(ies)...", len(parsed))
    tasks = [tcp_ping(p["server"], p["port"], PING_TIMEOUT) for p in parsed]
    pings = await asyncio.gather(*tasks)
    for p, pi in zip(parsed, pings):
        p["ping"] = pi

    good = [p for p in parsed if p.get("ping") is not None and p["ping"] <= MAX_PING]
    if not good:
        return []

    golden = [p for p in good if p["ping"] < GOLDEN_PING]
    regular = good[:MAX_PROXY_PER_INTERVAL] if not golden else good[len(golden):MAX_PROXY_PER_INTERVAL + len(golden)]

    async with httpx.AsyncClient(timeout=30) as client:
        for p in golden:
            try:
                text = format_golden_message(p) + f"\n\n{CHANNEL_ID}"
                await send_message(client, text, connect_urls=[build_connect_url(p)], button_labels=["🔱 connect 🔱"])
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Failed golden proxy: %s", e)

        to_send = regular[:MAX_PROXY_PER_INTERVAL]
        if to_send:
            batches = [to_send[i:i + PROXY_PER_MESSAGE] for i in range(0, len(to_send), PROXY_PER_MESSAGE)]
            for batch in batches:
                try:
                    lines = [format_proxy_message(p) for p in batch]
                    text = "\n\n".join(lines) + f"\n\n{CHANNEL_ID}"
                    urls = [build_connect_url(p) for p in batch]
                    await send_message(client, text, connect_urls=urls)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error("Failed batch: %s", e)

    sent = golden + to_send
    if sent:
        save_sent("proxies", ["raw_url", "server", "port", "secret", "ping"],
                  [{"raw_url": p["raw_url"], "server": p["server"], "port": p["port"],
                    "secret": p["secret"], "ping": p.get("ping")} for p in sent])
    logger.info("MTProto — %d golden, %d regular", len(golden), len(to_send))
    return sent


async def process_v2ray(seen: set[str]) -> list[dict]:
    sources = []
    for u in (V2RAY_URL, VMESS_URL, VMESS_URL_2, VLESS_URL, VLESS_URL_2):
        if u:
            sources.append(u)

    if not sources:
        return []

    raw_configs: list[str] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for u in sources:
            try:
                raw_configs.extend(await fetch_lines(client, u))
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", u, e)

    if not raw_configs:
        return []

    parsed: list[dict] = []
    for c in raw_configs:
        if c in seen:
            continue
        info = parse_v2ray_config(c)
        if info and CONFIG_SCORES.get(info["config_type"], 1) > 0:
            parsed.append(info)
            if len(parsed) >= MAX_CONFIG_CHECK:
                break

    if not parsed:
        return []

    logger.info("Pinging %d V2Ray config(s)...", len(parsed))
    tasks = [tcp_ping(p["server"], p["port"], PING_TIMEOUT) for p in parsed]
    pings = await asyncio.gather(*tasks)
    for p, pi in zip(parsed, pings):
        p["ping"] = pi

    good = [
        p for p in parsed
        if p.get("ping") is not None and p["ping"] <= MAX_PING
        and CONFIG_SCORES.get(p["config_type"], 1) > 0
    ]
    if not good:
        return []

    good.sort(key=lambda x: (-CONFIG_SCORES.get(x["config_type"], 1), x["ping"]))
    to_send = good[:MAX_CONFIG_PER_INTERVAL]
    to_send.sort(key=lambda x: x["config_type"])

    async with httpx.AsyncClient(timeout=30) as client:
        batches = [to_send[i:i + PROXY_PER_MESSAGE] for i in range(0, len(to_send), PROXY_PER_MESSAGE)]
        for batch in batches:
            try:
                text = format_config_block(batch) + f"\n\n💎 <span class=\"tg-spoiler\">{CHANNEL_ID}</span> 💎"
                await send_message(client, text)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Failed to send config batch: %s", e)

    if to_send:
        save_sent("configs", ["raw_config", "config_type", "server", "port", "ping"],
                  [{"raw_config": p["raw_config"], "config_type": p["config_type"],
                    "server": p["server"], "port": p["port"], "ping": p.get("ping")}
                   for p in to_send])
    logger.info("V2Ray — sent %d config(s)", len(to_send))
    return to_send


async def check_and_post() -> None:
    reload_config()
    if ENABLE_PROXIES:
        proxy_seen = load_seen("proxies", "raw_url")
        await process_mtproto(proxy_seen)
    if ENABLE_CONFIGS:
        config_seen = load_seen("configs", "raw_config")
        await process_v2ray(config_seen)


async def loop_check() -> None:
    while True:
        try:
            await check_and_post()
        except Exception as e:
            logger.error("Check cycle failed: %s", e)
        now = datetime.now(timezone.utc)
        next_min = ((now.minute // CHECK_INTERVAL) + 1) * CHECK_INTERVAL
        target = now.replace(minute=next_min % 60, second=0, microsecond=0)
        if next_min >= 60:
            target += timedelta(hours=1)
        delay = (target - now).total_seconds()
        logger.info("Next check at %s  (in %d s / %.1f min)", target.strftime("%H:%M"), delay, delay / 60)
        await asyncio.sleep(delay)


async def main() -> None:
    logger.info("PolyBot started — interval %d min, admin @%s", CHECK_INTERVAL, ADMIN_USERNAME)
    tasks = [asyncio.create_task(loop_check())]
    if ADMIN_USERNAME:
        tasks.append(asyncio.create_task(admin_poller()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    init_db()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown.")
        sys.exit(0)
