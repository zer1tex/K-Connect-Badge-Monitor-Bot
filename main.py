import os
import json
import logging
import requests
import telegram
import asyncio
from datetime import UTC
from telegram.helpers import escape_markdown
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from functools import wraps

load_dotenv() 

logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)  # Также можно отключить логи httpx, если они мешают

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

headers = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'X-Key': os.getenv('TOKEN')
    }
        
config = {
    'TOKEN': os.getenv('BOT_TOKEN'),
    'API_BASE_URL': 'https://k-connect.ru/api',
    'CHANNEL': os.getenv('CHANNEL_NAME'),
    'AUTH_DATA': {
        'email': os.getenv('API_EMAIL'),
        'password': os.getenv('API_PASSWORD')
    },
    'CHECK_INTERVAL': int(os.getenv('CHECK_INTERVAL', 60)),
    'DATA_DIR': 'data',
    'BADGE_IDS_FILE': 'known_badges.json',
    'ALLOWED_USER_IDS': [6413866359]
}
class BadgeBot:
    def __init__(self):
        """Инициализация бота с настройками."""
        os.makedirs(config['DATA_DIR'], exist_ok=True)
        self.badge_ids_file = os.path.join(config['DATA_DIR'], config['BADGE_IDS_FILE'])
        self.application = Application.builder().token(config['TOKEN']).build()
        self.session = requests.Session()
        self.scheduler = AsyncIOScheduler(timezone=UTC)
        self.known_badge_ids = self._load_data()
        self.jwt_token = None
        logger.info(f"Загружено известных бейджиков: {len(self.known_badge_ids)}")

    def _load_data(self) -> set:
        """Загрузка известных ID бейджиков из файла."""
        try:
            if os.path.exists(self.badge_ids_file):
                with open(self.badge_ids_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        logger.error("Некорректный формат данных в файле, создаю новый")
                        return set()
                    return set(data)
            return set()
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла: {e}")
            return set()

    def _save_data(self):
        """Сохранение известных ID бейджиков в файл."""
        try:
            with open(self.badge_ids_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.known_badge_ids), f, indent=2, ensure_ascii=False)
            logger.info(f"Сохранено {len(self.known_badge_ids)} бейджиков в файл")
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла: {e}")

    async def _auth(self) -> bool:
        """Аутентификация в API."""
        try:
            response = self.session.post(
                f"{config['API_BASE_URL']}/auth/login",
                json=config['AUTH_DATA'],
                headers=headers
            )
            response.raise_for_status()
            self.jwt_token = response.json().get('access_token')
            logger.info("Успешная аутентификация в API")
            return True
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
            return False

    async def _fetch_badges(self) -> list:
        """Получение списка бейджиков с API."""
        if not self.jwt_token and not await self._auth():
            logger.error("Не удалось аутентифицироваться")
            return []

        try:
            
            response = self.session.get(
                f"{config['API_BASE_URL']}/badges/shop",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                logger.info("Токен устарел, повторная аутентификация...")
                if await self._auth():
                    return await self._fetch_badges()
                return []

            response.raise_for_status()
            data = response.json()
            
            # Обрабатываем новую структуру ответа
            if isinstance(data, dict) and 'badges' in data:
                badges = data['badges']
            elif isinstance(data, list):
                badges = data
            else:
                logger.error(f"Неожиданный формат ответа API: {data}")
                return []
                
            logger.info(f"Получено {len(badges)} бейджиков с API")
            return badges
        except Exception as e:
            logger.error(f"Ошибка при получении бейджиков: {e}")
            return []
            
    async def start_scheduler(self, application: Application):
        """Запуск планировщика после старта бота."""
        self.scheduler.add_job(
            self._check_new_badges,
            'interval',
            minutes=config['CHECK_INTERVAL'],
        )
        self.scheduler.start()
        logger.info(f"Планировщик запущен, проверка каждые {config['CHECK_INTERVAL']} минут")
        
    async def _check_new_badges(self):
        """Проверка новых бейджиков и отправка уведомлений."""
        logger.info("Начало проверки новых бейджиков...")
        badges = await self._fetch_badges()
        
        if not badges:
            logger.warning("Не получено ни одного бейджика")
            return
    
        # Получаем текущие ID бейджиков из API
        current_badge_ids = {badge.get('id') for badge in badges if isinstance(badge, dict) and badge.get('id')}
        
        # Удаляем из known_badge_ids те, которых нет в current_badge_ids
        removed_badges = self.known_badge_ids - current_badge_ids
        if removed_badges:
            logger.info(f"Найдены удалённые бейджики: {removed_badges}")
            self.known_badge_ids -= removed_badges
        
        # Добавляем новые бейджики
        new_badges = []
        for badge in badges:
            if not isinstance(badge, dict):
                continue
                
            badge_id = badge.get('id')
            if not badge_id:
                continue
                
            if badge_id not in self.known_badge_ids:
                new_badges.append(badge)
                self.known_badge_ids.add(badge_id)
    
        if new_badges or removed_badges:
            self._save_data()  # Сохраняем изменения (новые + удалённые)
            
        if new_badges:
            logger.info(f"Найдено {len(new_badges)} новых бейджиков")
            for badge in new_badges:
                await self._send_notification(badge)
        else:
            logger.info("Новых бейджиков не обнаружено")
    async def _send_notification(self, badge: dict):
        """Отправка уведомления о новом бейджике."""
        try:
            message = self._format_message(badge)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✨ Купить",
                    url="https://k-connect.ru/badge-shop"
                )
            ]])
            
            await asyncio.sleep(30)
            

            await self.application.bot.send_message(
                chat_id=config['CHANNEL'],
                text=message,
                parse_mode='MarkdownV2',
                reply_markup=keyboard
            )
            logger.info(f"Отправлено уведомление о бейджике ID {badge.get('id')}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

    def restricted_access(func):
        """Декоратор для ограничения доступа к командам."""
        @wraps(func)
        async def wrapped(self, update: Update, context, *args, **kwargs):
            user_id = update.effective_user.id
            if user_id not in config['ALLOWED_USER_IDS']:
                await update.message.reply_text("Эта команда не доступна для вас")
                return
            return await func(self, update, context, *args, **kwargs)
        return wrapped
    
    @staticmethod
    def _format_message(badge: dict) -> str:
        """Форматирование сообщения о бейджике с экранированием MarkdownV2."""
        # Экранируем все текстовые поля
        name = escape_markdown(badge.get('name', 'Без названия'), version=2)
        description = escape_markdown(badge.get('description', 'Нет описания'), version=2)
        price = badge.get('price') or 0
        max_copies = badge.get('max_copies')
        copies_sold = badge.get('copies_sold') or 0
        
        copies_info = f"{copies_sold} / {max_copies if max_copies is not None else '∞'}"
        
        return (
            "🆕 *Новый бейджик\\!*\n\n"
            f"✨ *Название:* {name}\n"
            f"📝 *Описание:* {description}\n"
            f"💰 *Цена:* {price} ₽\n"
            f"🛒 *Купили уже:* {copies_info}\n"
        )

    async def start(self, update: Update, context):
        """Обработчик команды /start."""
        await update.message.reply_text("Привет! Этот бот монитроит бейджик на сайте k-connect.ru")
        # УБИРАЕМ scheduler.start() отсюда
        
    async def force_check(self, update: Update, context):
        """Принудительная проверка новых бейджиков."""
        await update.message.reply_text("Запускаю принудительную проверку...")
        await self._check_new_badges()
        await update.message.reply_text("Проверка завершена!")
    
    @restricted_access
    async def test(self, update: Update, context):
        """Обработчик команды /test."""
        test_badge = {
            "id": 9999,
            "name": "Тестовый бейджик",
            "description": "Это тестовое уведомление",
            "price": 100,
            "copies_sold": 0,
            "max_copies": 5,
            "is_sold_out": False,
            "creator": {
                "name": "Тестовый Создатель"
            },
            "purchases": []
        }
        await self._send_notification(test_badge)
        await update.message.reply_text("Тестовое уведомление отправлено!")
    @restricted_access

    async def status(self, update: Update, context):
        """Обработчик команды /status без Markdown."""
        # Статусы
        auth_status = "✅ Активен" if self.jwt_token else "❌ Не активен"
        scheduler_status = "✅ Работает" if self.scheduler.running else "❌ Остановлен"
        
        # Проверка API
        api_status = "❓ Не проверялось"
        try:
            response = self.session.get(f"{config['API_BASE_URL']}/auth/check",
            timeout=5, headers=headers)
            api_status = f"{response.status_code} ✅" if response.ok else f"{response.status_code} ❌"
        except Exception as e:
            api_status = f"❌ {str(e)}"
        
        # Получаем версии
        import platform
        import telegram
        import requests
        python_version = platform.python_version()
        telegram_version = telegram.__version__
        requests_version = requests.__version__
    
        # Формируем простое текстовое сообщение
        status_msg = f"""
    🔍 Статус бота
    
    🔄 Основное
    • Состояние: ✅ Активен
    • Бейджиков в памяти: {len(self.known_badge_ids)}
    • Интервал проверки: {config['CHECK_INTERVAL']} мин
    • Файл данных: {os.path.abspath(self.badge_ids_file)}
    
    🔐 Аутентификация
    • JWT-токен: {auth_status}
    • API статус: {api_status}
    
    ⏱ Планировщик
    • Состояние: {scheduler_status}
    
    📦 Зависимости
    • Python: {python_version}
    • python-telegram-bot: {telegram_version}
    • requests: {requests_version}
        """
        
        await update.message.reply_text(
            status_msg,
            parse_mode=None  # Явно отключаем Markdown
        )
    @restricted_access
    async def dump_ids(self, update: Update, context):
        """Обработчик команды /dump_ids для отладки."""
        await update.message.reply_text(f"Известные ID бейджей: {sorted(self.known_badge_ids)}")

def main():
    """Запуск бота."""
    bot = BadgeBot()
    
    # Регистрируем обработчики команд
    bot.application.add_handler(CommandHandler("start", bot.start))
    bot.application.add_handler(CommandHandler("test", bot.test))
    bot.application.add_handler(CommandHandler("status", bot.status))
    bot.application.add_handler(CommandHandler("upd", bot.force_check))
    
    # Запускаем планировщик ПОСЛЕ старта бота
    bot.application.post_init = bot.start_scheduler
    
    logger.info("Бот запускается...")
    bot.application.run_polling()

if __name__ == '__main__':
    main()