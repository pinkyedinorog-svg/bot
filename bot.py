import logging
import json
import os
import random
import hashlib
import hmac
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=os.getenv('LOG_LEVEL', 'INFO'),
    handlers=[
        logging.FileHandler('data/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SECRET_KEY = os.getenv('SECRET_KEY')
DOMAIN = os.getenv('DOMAIN', 'http://localhost:8080')
REDIRECT_URL = os.getenv('REDIRECT_URL', 'https://example.com')

class TrackingBot:
    def __init__(self):
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
        if not SECRET_KEY:
            raise ValueError("SECRET_KEY не установлен")
        
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
        logger.info("Бот инициализирован")
    
    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(CommandHandler("mylog", self.mylog_command))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        try:
            user = update.effective_user
            logger.info(f"Пользователь {user.id} (@{user.username}) запустил бота")
            
            # Создаем tracking_id
            timestamp = int(datetime.now().timestamp())
            tracking_id = f"{user.id}_{timestamp}"
            
            # Сохраняем в контексте
            context.user_data.update({
                'tracking_id': tracking_id,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'language_code': user.language_code
                }
            })
            
            # Создаем капчу
            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            correct_answer = num1 + num2
            
            context.user_data['captcha_answer'] = str(correct_answer)
            
            # Сохраняем данные капчи
            self.save_captcha_data(context.user_data, num1, num2, correct_answer)
            
            # Создаем варианты ответов
            answers = self.generate_answers(correct_answer)
            
            # Создаем клавиатуру с кнопками ответов
            keyboard = []
            row = []
            
            for i, answer in enumerate(answers):
                callback_data = f"captcha_{answer}_{tracking_id}"
                button = InlineKeyboardButton(str(answer), callback_data=callback_data)
                row.append(button)
                
                if len(row) == 2 or i == len(answers) - 1:
                    keyboard.append(row)
                    row = []
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Салам алейкум ва рахматуллахи ва баракатух, {user.first_name}!\n\n"
                f"Решите капчу для получения доступа к сайту:\n\n"
                f"**{num1} + {num2} = ?**",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка в start_command: {e}", exc_info=True)
            await update.message.reply_text("⚠️ Ошибка. Попробуйте позже.")
    
    async def mylog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mylog - показывает историю действий пользователя"""
        try:
            user = update.effective_user
            
            # Получаем историю действий пользователя
            user_log = self.get_user_log(user.id)
            
            if not user_log:
                message = "📝 У вас пока нет записей в логе."
            else:
                message = f"📊 **Ваша история действий**, {user.first_name}:\n\n"
                
                for i, log_entry in enumerate(user_log[-5:], 1):  # Последние 5 записей
                    time_str = datetime.fromisoformat(log_entry['timestamp']).strftime('%H:%M')
                    message += f"{i}. {time_str} - {log_entry['action']}\n"
                
                message += f"\nВсего действий: {len(user_log)}"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Ошибка в mylog_command: {e}")
            await update.message.reply_text("⚠️ Ошибка получения лога")
    
    def generate_answers(self, correct_answer):
        """Генерация вариантов ответов"""
        answers = [str(correct_answer)]
        
        while len(answers) < 4:
            offset = random.choice([-1, 1]) * random.randint(1, 5)
            wrong = str(correct_answer + offset)
            if wrong != str(correct_answer) and wrong not in answers and int(wrong) > 0:
                answers.append(wrong)
        
        random.shuffle(answers)
        return answers
    
    def save_captcha_data(self, user_data, num1, num2, answer):
        """Сохраняем данные капчи"""
        try:
            data = {
                'tracking_id': user_data['tracking_id'],
                'telegram_user': user_data['user'],
                'captcha': {
                    'num1': num1,
                    'num2': num2,
                    'answer': answer
                },
                'created_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            os.makedirs('data/captchas', exist_ok=True)
            with open(f'data/captchas/{user_data["tracking_id"]}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Сохранена капча для user_id={user_data['user']['id']}")
                
        except Exception as e:
            logger.error(f"Ошибка сохранения капчи: {e}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            user = query.from_user
            
            logger.info(f"Нажата кнопка: user_id={user.id}, data={data}")
            
            if data.startswith('captcha_'):
                await self.handle_captcha_button(query, data, user, context)
            else:
                await query.edit_message_text("❌ Неизвестная команда")
                
        except Exception as e:
            logger.error(f"Ошибка в button_callback: {e}", exc_info=True)
            try:
                await query.edit_message_text("⚠️ Ошибка обработки")
            except:
                pass
    
    async def handle_captcha_button(self, query, data, user, context):
        """Обработка кнопки с ответом на капчу"""
        # Парсим данные
        parts = data.split('_', 2)
        if len(parts) != 3:
            await query.edit_message_text("❌ Ошибка данных")
            return
        
        _, answer, tracking_id = parts
        correct_answer = context.user_data.get('captcha_answer')
        
        if answer == correct_answer:
            # Капча решена правильно - сразу показываем кнопку перехода
            await self.handle_correct_captcha(query, user, tracking_id, context)
        else:
            # Неправильный ответ
            await self.handle_wrong_captcha(query, user, tracking_id)
    
    async def handle_correct_captcha(self, query, user, tracking_id, context):
        """Капча решена правильно - показываем кнопку перехода"""
        try:
            # Обновляем статус капчи
            self.update_captcha_status(tracking_id, 'solved')
            
            # Генерируем ссылку с Telegram ID
            final_url = self.generate_final_url_with_user_data(
                tracking_id, 
                context.user_data['user']
            )
            
            # Создаем ОДНУ кнопку для перехода
            keyboard = [[
                InlineKeyboardButton(
                    "🌐 Перейти на сайт", 
                    url=final_url
                )
            ]]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "✅ **Капча пройдена успешно!**\n\n"
                "Нажмите кнопку ниже, чтобы перейти на сайт:\n\n"
                "• Ссылка действительна 10 минут",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Логируем создание ссылки
            self.log_user_action(
                user.id,
                'captcha_solved_and_link_generated',
                {
                    'tracking_id': tracking_id,
                    'url': final_url,
                    'expires_in': '10 minutes'
                }
            )
            
            logger.info(f"Создана ссылка для user_id={user.id}, tracking_id={tracking_id}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки правильной капчи: {e}")
            await query.edit_message_text("⚠️ Ошибка создания ссылки")
    
    async def handle_wrong_captcha(self, query, user, tracking_id):
        """Неправильная капча"""
        self.update_captcha_status(tracking_id, 'failed')
        
        # Логируем неудачную попытку
        self.log_user_action(user.id, 'captcha_failed', {'tracking_id': tracking_id})
        
        await query.edit_message_text(
            "❌ **Неправильный ответ!**\n\n"
            "Используйте команду /start для новой попытки.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    def generate_final_url_with_user_data(self, tracking_id, user_data):
        """Генерирует URL с данными пользователя"""
        # Генерируем основной токен
        secret = SECRET_KEY.encode('utf-8')
        message = tracking_id.encode('utf-8')
        hmac_obj = hmac.new(secret, message, hashlib.sha256)
        token = hmac_obj.hexdigest()[:16]
        
        # Дополнительный токен для Telegram ID
        user_token = hashlib.sha256(
            f"{user_data['id']}{user_data.get('username', '')}{SECRET_KEY}".encode()
        ).hexdigest()[:12]
        
        # Формируем URL с параметрами пользователя
        params = {
            'tgid': user_data['id'],
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'token': user_token,
            'ts': int(datetime.now().timestamp())
        }
        
        # Кодируем параметры
        query_string = '&'.join([f"{k}={v}" for k, v in params.items() if v])
        
        return f"{DOMAIN}/verify/{tracking_id}/{token}?{query_string}"
    
    def update_captcha_status(self, tracking_id, status):
        """Обновляет статус капчи"""
        try:
            captcha_file = f'data/captchas/{tracking_id}.json'
            if os.path.exists(captcha_file):
                with open(captcha_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                data['status'] = status
                data['updated_at'] = datetime.now().isoformat()
                
                with open(captcha_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                logger.debug(f"Обновлен статус капчи: {tracking_id} -> {status}")
                
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")
    
    def log_user_action(self, user_id, action, data=None):
        """Логирует действие пользователя"""
        try:
            log_entry = {
                'user_id': user_id,
                'action': action,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            
            os.makedirs('data/user_logs', exist_ok=True)
            
            # Сохраняем в общий лог пользователя
            user_log_file = f'data/user_logs/{user_id}.json'
            user_logs = []
            
            if os.path.exists(user_log_file):
                with open(user_log_file, 'r', encoding='utf-8') as f:
                    user_logs = json.load(f)
            
            user_logs.append(log_entry)
            
            # Ограничиваем количество записей (последние 100)
            if len(user_logs) > 100:
                user_logs = user_logs[-100:]
            
            with open(user_log_file, 'w', encoding='utf-8') as f:
                json.dump(user_logs, f, indent=2, ensure_ascii=False)
            
            # Также сохраняем в общий лог
            os.makedirs('data/logs', exist_ok=True)
            general_log_file = 'data/logs/actions.log'
            
            with open(general_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.error(f"Ошибка логирования действия: {e}")
    
    def get_user_log(self, user_id):
        """Получает лог действий пользователя"""
        try:
            user_log_file = f'data/user_logs/{user_id}.json'
            if os.path.exists(user_log_file):
                with open(user_log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения лога пользователя: {e}")
        
        return []
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        self.application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == '__main__':
    try:
        # Проверяем настройки
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
            exit(1)
        
        if not SECRET_KEY:
            logger.error("❌ SECRET_KEY не установлен!")
            exit(1)
        
        logger.info(f"DOMAIN: {DOMAIN}")
        logger.info(f"REDIRECT_URL: {REDIRECT_URL}")
        
        # Создаем необходимые директории
        for dir_name in ['data', 'data/captchas', 'data/user_logs', 'data/logs']:
            os.makedirs(dir_name, exist_ok=True)
        
        bot = TrackingBot()
        bot.run()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        exit(1)
