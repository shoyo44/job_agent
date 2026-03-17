from __future__ import annotations

import sys

from api.app import _RUNS, _RUNS_LOCK, _STARTUP_STATUS
from tools.telegram_bot import TelegramBotClient, TelegramCommandService


def _runs_snapshot() -> dict:
    with _RUNS_LOCK:
        return {run_id: dict(data) for run_id, data in _RUNS.items()}


def _startup_snapshot() -> dict:
    return dict(_STARTUP_STATUS)


if __name__ == "__main__":
    bot = TelegramBotClient()
    check = bot.test_connection()
    if not check.get("ok"):
        print("Telegram connectivity check failed.")
        print(f"Reason: {check.get('message', 'Unknown error')}")
        print("Tip: verify the bot token, then try another network or VPN if Telegram is blocked.")
        sys.exit(1)

    print(
        f"Telegram connectivity OK | bot=@{check.get('bot_username', '')} | chat_configured={bool(bot.default_chat_id)}"
    )
    service = TelegramCommandService(
        bot=bot,
        run_state_provider=_runs_snapshot,
        startup_status_provider=_startup_snapshot,
    )
    service.run_forever()
