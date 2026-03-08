# K-Connect Badge Monitor Bot

Telegram-бот для отслеживания появления новых бейджиков в магазине K-Connect и автоматической отправки уведомлений в Telegram-канал.

Возможности:

· Периодическая проверка новых бейджиков через API K-Connect

· Автоматическая отправка уведомлений в указанный Telegram-канал

· Ограничение доступа к командам по ID пользователя

· Гибкая настройка интервала проверки

· Сохранение состояния между перезапусками (известные ID бейджиков хранятся в JSON-файле)

## Требования

· Python 3.7 или выше

· Аккаунт на K-Connect с API-доступом (email/пароль и API-ключ)

· Telegram Bot Token

· Telegram канал (или чат), куда бот будет отправлять сообщения

## Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/zer1tex/k-connect-badge-monitor-bot.git
   cd k-connect-badge-monitor-bot
   ```
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

## Настройка

Создайте файл .env в корневой папке проекта и заполните его:

```env
# Telegram Bot Token
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Имя канала или chat_id
CHANNEL_NAME=@your_channel

# API ключ K-Connect (X-Key)
TOKEN=your_api_key_here

# Email и пароль от аккаунта K-Connect
API_EMAIL=your@email.com
API_PASSWORD=your_password

# Интервал проверки в минутах (по умолчанию 60)
CHECK_INTERVAL=60
```

## Запуск

```bash
python main.py
```

Бот запустится и начнёт опрашивать API K-Connect с заданным интервалом. При обнаружении новых бейджиков отправит сообщение в канал.

Лицензия

Проект распространяется под лицензией Apache 2.0. Подробнее см. в файле LICENSE.
