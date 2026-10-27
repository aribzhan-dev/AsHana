import sys

from ashana.bootstrap.settings import Settings
from ashana.modules.notifications.infrastructure.delivery import DeliveryFailed, TelegramSender


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    settings = Settings()  
    if not settings.telegram_bot_token:
        raise SystemExit("Токен бота не задан: добавьте ASHANA_TELEGRAM_BOT_TOKEN в .env.")
    bot = TelegramSender(settings.telegram_bot_token.get_secret_value(), settings.telegram_chat_id)
    try:
        me = bot.call("getMe")
        name = me.get("username", "") if isinstance(me, dict) else ""
        print(f"Бот подключён: @{name}")
        if command == "chats":
            updates = bot.call("getUpdates", {"allowed_updates": ["message", "my_chat_member"]})
            seen: dict[str, str] = {}
            for update in updates if isinstance(updates, list) else []:
                for key in ("message", "my_chat_member", "channel_post"):
                    chat = (update.get(key) or {}).get("chat") if isinstance(update, dict) else None
                    if isinstance(chat, dict) and "id" in chat:
                        title = chat.get("title") or chat.get("username") or "личный чат"
                        seen[str(chat["id"])] = f"{title} ({chat.get('type', '')})"
            if not seen:
                print("Чатов нет: добавьте бота в группу и напишите в ней любое сообщение.")
            for chat_id, title in seen.items():
                print(f"{chat_id}\t{title}")
            return
        if not settings.telegram_chat_id:
            raise SystemExit(
                "Чат не задан: выполните команду chats и укажите ASHANA_TELEGRAM_CHAT_ID."
            )
        bot("AsHana подключена: сюда будут приходить новые заказы и их статусы.")
        print("Тестовое сообщение отправлено.")
    except DeliveryFailed:
        raise SystemExit(
            "Telegram не ответил: проверьте токен, интернет и что бот добавлен в чат."
        ) from None


if __name__ == "__main__":
    main()
