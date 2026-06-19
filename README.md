# PolyBot TG

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A Telegram bot that automatically fetches **MTProto proxies** and **V2Ray configs** (vmess, vless, trojan, ss, hysteria2, etc.) from multiple sources, pings them for latency, and posts the best ones to your Telegram channel — all with a real-time inline admin panel.

## Features

- **MTProto Proxy Poster** — fetches from configurable source URLs, pings via TCP, posts formatted messages to the channel
- **V2Ray Config Poster** — supports vmess://, vless://, trojan://, ss://, hysteria2://, tuic://, wireguard://
- **Smart Ping Filter** — TCP connect ping with configurable max latency; golden proxies (<50ms) get special formatting + inline connect button
- **Config Scoring** — prioritize config types with custom scores; skip low-value types entirely
- **Duplicate Detection** — SQLite database tracks seen proxies and configs across restarts
- **Inline Admin Panel** — `/start` opens a full menu; admins can edit all settings live without touching the env file
- **Toggle System** — enable/disable proxies, configs, or the whole panel from the admin panel or env file
- **Batched Posting** — control proxies per message, max per interval, and configs per interval independently
- **Environment + DB Overrides** — settings stored in DB override main.env; changes take effect immediately without restart

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/AmirabbasRouintan/polybot-tg.git
cd polybot-tg
pip install -r requirements.txt
```

### 2. Configure

```bash
cp main.env.example main.env
# Edit main.env with your bot token and channel
```

### 3. Run

```bash
python main.py
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token | — |
| `CHANNEL_ID` | Your channel URL (e.g. `https://t.me/ixiconfig`) | — |
| `ADMIN_USERNAME` | Admin Telegram username (without `@`) | — |
| `PROXY_URL` | MTProto proxy source URL | Grim1313's list |
| `VMESS_URL` / `VLESS_URL` / `V2RAY_URL` | V2Ray config source URLs | ebraSha lists |
| `VMESS_URL_2` / `VLESS_URL_2` | Secondary V2Ray source URLs | barry-far lists |
| `CONFIG_NAME` | Alias appended to configs | `ixi-conf` |
| `CONFIG_SCORES` | JSON dict of type → priority score | vless:5, vmess:4, trojan:3 |
| `CHECK_INTERVAL` | Minutes between check cycles | 5 |
| `MAX_PING` | Max acceptable ping (ms) | 250 |
| `GOLDEN_PING` | Threshold for golden badge (ms) | 50 |
| `MAX_PROXY_PER_INTERVAL` | Max proxies sent per cycle | 6 |
| `MAX_CONFIG_PER_INTERVAL` | Max configs sent per cycle | 6 |
| `PROXY_PER_MESSAGE` | Proxies grouped per message | 3 |
| `PING_TIMEOUT` | TCP connect timeout (s) | 5 |
| `ENABLE_PANEL` | Enable admin panel | true |
| `ENABLE_PROXIES` | Enable MTProto posting | true |
| `ENABLE_CONFIGS` | Enable V2Ray posting | true |
| `DB_PATH` | SQLite database path | `polybot.db` |

## Admin Panel

Send `/start` to the bot in a private chat. The main menu gives you:

- **Config Sources** — edit all V2Ray source URLs, scores, name, and limits
- **Limits & Timers** — change check interval, pings, batch sizes with inline buttons or custom values
- **Proxy Source** — change the MTProto source URL
- **General Config** — edit channel ID, admin username, bot token
- **Actions** — toggle panel/proxies/configs on/off, trigger a force check

> All changes are saved to the database and take effect immediately. No restart needed.

## How It Works

1. Every `CHECK_INTERVAL` minutes, the bot fetches fresh proxy/config lists from source URLs
2. Parses and validates each entry (supports tg://, vmess://, vless://, ss://, trojan://, hysteria2://)
3. Pings each server via TCP connect and filters by `MAX_PING`
4. Sorts by config score and ping, deduplicates against the SQLite database
5. Posts formatted messages to the channel — golden proxies get an inline connect button

## Requirements

- Python 3.10+
- httpx
- python-dotenv

## Tags

`telegram-bot` `mtproto` `v2ray` `proxy` `vmess` `vless` `trojan` `shadowsocks` `hysteria` `python` `asyncio` `telegram-api` `admin-panel` `inline-keyboard`

## License

MIT
