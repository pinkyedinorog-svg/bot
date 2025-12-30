import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        # Telegram Bot
        self.TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
        
        # Server Configuration
        self.SERVER_IP = os.getenv('SERVER_IP', '0.0.0.0')
        self.SERVER_PORT = int(os.getenv('SERVER_PORT', 8080))
        self.DOMAIN = os.getenv('DOMAIN', f'http://{self.SERVER_IP}:{self.SERVER_PORT}')
        self.REDIRECT_URL = os.getenv('REDIRECT_URL', 'https://example.com')
        
        # Security
        self.SECRET_KEY = os.getenv('SECRET_KEY')
        self.ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
        
        # Logging
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = os.getenv('LOG_FILE', '/var/log/telegram-tracker.log')
        
        # Captcha settings
        self.CAPTCHA_TIMEOUT = 300  # 5 minutes
        self.CAPTCHA_MAX_ATTEMPTS = 3
        
        # Проверяем обязательные настройки
        self.validate()
    
    def validate(self):
        """Проверка обязательных настроек"""
        errors = []
        
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не установлен")
        
        if not self.SECRET_KEY:
            errors.append("SECRET_KEY не установлен")
        elif self.SECRET_KEY == 'default_secret_key_change_me' or len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY слишком слабый (минимум 32 символа)")
        
        if self.REDIRECT_URL == 'https://example.com':
            errors.append("REDIRECT_URL не установлен (используется значение по умолчанию)")
        
        if errors:
            print("⚠️ Ошибки конфигурации:")
            for error in errors:
                print(f"  • {error}")
            print("\nОтредактируйте файл .env")
        
        return len(errors) == 0
    
    def __str__(self):
        return f"Config(TELEGRAM_BOT_TOKEN={'set' if self.TELEGRAM_BOT_TOKEN else 'NOT SET'}, " \
               f"SECRET_KEY={'set' if self.SECRET_KEY else 'NOT SET'}, " \
               f"REDIRECT_URL={self.REDIRECT_URL})"

# Создаем экземпляр конфигурации
config = Config()

# Для обратной совместимости
if __name__ == "__main__":
    print("Конфигурация:")
    print(f"  TELEGRAM_BOT_TOKEN: {'Установлен' if config.TELEGRAM_BOT_TOKEN else 'НЕТ!'}")
    print(f"  SECRET_KEY: {'Установлен' if config.SECRET_KEY else 'НЕТ!'}")
    print(f"  REDIRECT_URL: {config.REDIRECT_URL}")
    print(f"  DOMAIN: {config.DOMAIN}")
    print(f"  LOG_LEVEL: {config.LOG_LEVEL}")
