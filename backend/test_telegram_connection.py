from __future__ import annotations

from tools.telegram_bot import TelegramBotClient


if __name__ == "__main__":
    bot = TelegramBotClient()
    status = bot.get_status()
    check = bot.test_connection()
    print("Telegram config:")
    print(status)
    print("Telegram connectivity:")
    print(check)
