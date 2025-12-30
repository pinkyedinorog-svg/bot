#!/usr/bin/env python3
"""
Captcha Server
"""

from flask import Flask, request, redirect, jsonify
import json
import os
import hmac
import hashlib
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv
import urllib.parse

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
SECRET_KEY = os.getenv('SECRET_KEY')
REDIRECT_URL = os.getenv('REDIRECT_URL', 'https://example.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def verify_token(tracking_id, token):
    """Проверка основного токена"""
    try:
        secret = SECRET_KEY.encode('utf-8')
        message = tracking_id.encode('utf-8')
        hmac_obj = hmac.new(secret, message, hashlib.sha256)
        expected = hmac_obj.hexdigest()[:16]
        return hmac.compare_digest(expected, token)
    except Exception as e:
        logger.error(f"Ошибка проверки токена: {e}")
        return False

def verify_user_token(telegram_id, username, token, timestamp):
    """Проверка токена пользовательских данных"""
    try:
        # Проверяем срок действия ссылки (10 минут)
        link_time = datetime.fromtimestamp(int(timestamp))
        if datetime.now() - link_time > timedelta(minutes=10):
            logger.warning(f"Ссылка устарела: создана {link_time}, сейчас {datetime.now()}")
            return False
        
        # Проверяем токен
        data_string = f"{telegram_id}{username}{SECRET_KEY}"
        expected = hashlib.sha256(data_string.encode()).hexdigest()[:12]
        return hmac.compare_digest(expected, token)
    except Exception as e:
        logger.error(f"Ошибка проверки user token: {e}")
        return False

def get_browser_info(user_agent):
    """Определение браузера из User-Agent"""
    if not user_agent:
        return "Неизвестно"
    
    ua = user_agent.lower()
    
    if 'chrome' in ua and 'edg' not in ua:
        return "Google Chrome"
    elif 'firefox' in ua:
        return "Mozilla Firefox"
    elif 'safari' in ua and 'chrome' not in ua:
        return "Apple Safari"
    elif 'edg' in ua:
        return "Microsoft Edge"
    elif 'opera' in ua:
        return "Opera"
    elif 'yandex' in ua:
        return "Yandex Browser"
    elif 'mobile' in ua:
        return "Мобильный браузер"
    else:
        return "Другой браузер"

def get_real_ip(request):
    """Получение реального IP-адреса с учетом прокси"""
    ip = request.remote_addr
    
    # Проверяем различные заголовки прокси
    if request.headers.get('CF-Connecting-IP'):  # Cloudflare
        ip = request.headers.get('CF-Connecting-IP')
    elif request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    
    return ip

def save_visit_data(tracking_id, request_data, telegram_data):
    """Сохранение данных о посещении"""
    try:
        # Создаем структуру данных
        visit_data = {
            'tracking_id': tracking_id,
            'timestamp': datetime.now().isoformat(),
            'telegram_user': {
                'id': telegram_data.get('id'),
                'username': telegram_data.get('username'),
                'first_name': telegram_data.get('first_name'),
                'validated': telegram_data.get('validated', False)
            },
            'ip_info': {
                'address': request_data['ip_address'],
                'is_proxied': request_data['ip_address'] != request.remote_addr,
                'original_ip': request.remote_addr
            },
            'user_agent': {
                'raw': request_data['user_agent'],
                'browser': request_data['browser']
            },
            'request_info': {
                'referrer': request.referrer,
                'method': request.method,
                'url': request.url,
                'endpoint': request.endpoint
            },
            'headers': {k: v for k, v in request.headers.items() if k not in ['Authorization', 'Cookie']}
        }
        
        # Создаем директорию если нет
        os.makedirs('data/visits', exist_ok=True)
        
        # Генерируем уникальное имя файла
        filename = f"data/visits/{tracking_id}_{int(datetime.now().timestamp())}.json"
        
        # Сохраняем в файл
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(visit_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Посещение сохранено в {filename}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")
        return False

@app.route('/verify/<tracking_id>/<token>')
def verify_captcha(tracking_id, token):
    """Основной endpoint для верификации - мгновенный редирект"""
    try:
        logger.info(f"🔗 Начало обработки запроса: tracking_id={tracking_id}")
        
        # Получаем параметры пользователя из URL
        telegram_id = request.args.get('tgid', type=int)
        username = request.args.get('username', '')
        first_name = request.args.get('first_name', '')
        user_token = request.args.get('token', '')
        timestamp = request.args.get('ts', type=int, default=0)
        
        # Проверяем основной токен
        if not verify_token(tracking_id, token):
            logger.error(f"❌ Неверный основной токен для {tracking_id}")
            return jsonify({
                'error': 'Неверная или просроченная ссылка',
                'timestamp': datetime.now().isoformat()
            }), 403
        
        logger.info("✅ Основной токен прошел проверку")
        
        # Проверяем пользовательские данные если они переданы
        telegram_data = {
            'id': telegram_id,
            'username': username,
            'first_name': first_name,
            'validated': False
        }
        
        if telegram_id and user_token and timestamp:
            if verify_user_token(telegram_id, username, user_token, timestamp):
                telegram_data['validated'] = True
                logger.info(f"✅ Telegram данные проверены: id={telegram_id}, user=@{username}")
            else:
                logger.warning(f"⚠️ Telegram данные не прошли проверку: id={telegram_id}")
        
        # Получаем информацию о клиенте
        ip_address = get_real_ip(request)
        user_agent = request.headers.get('User-Agent', 'Неизвестно')
        browser = get_browser_info(user_agent)
        
        # Логируем информацию о запросе
        logger.info(f"📊 Информация о запросе:")
        logger.info(f"   Telegram ID: {telegram_id or 'Не указан'}")
        logger.info(f"   Username: @{username or 'Не указан'}")
        logger.info(f"   IP-адрес: {ip_address}")
        logger.info(f"   Браузер: {browser}")
        logger.info(f"   User-Agent: {user_agent[:100]}...")
        
        # Подготавливаем данные для сохранения
        request_data = {
            'ip_address': ip_address,
            'user_agent': user_agent,
            'browser': browser
        }
        
        # Сохраняем данные о посещении
        save_visit_data(tracking_id, request_data, telegram_data)
        
        # МГНОВЕННЫЙ РЕДИРЕКТ на целевой URL
        logger.info(f"🚀 Мгновенный редирект на: {REDIRECT_URL}")
        return redirect(REDIRECT_URL, code=302)
        
    except Exception as e:
        logger.error(f"🔥 Критическая ошибка в verify_captcha: {e}", exc_info=True)
        
        # Даже при ошибке перенаправляем пользователя на сайт
        logger.info(f"⚠️ Ошибка, но перенаправляем на: {REDIRECT_URL}")
        return redirect(REDIRECT_URL, code=302)

@app.route('/health')
def health_check():
    """Endpoint для проверки работоспособности сервера"""
    visits_count = 0
    if os.path.exists('data/visits'):
        visits_count = len([f for f in os.listdir('data/visits') if f.endswith('.json')])
    
    return jsonify({
        'status': 'ok',
        'service': 'captcha_tracker',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_visits': visits_count,
            'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': 'N/A'  # Можно добавить логику расчета uptime
        },
        'config': {
            'redirect_url': REDIRECT_URL,
            'has_secret_key': bool(SECRET_KEY),
            'admin_enabled': bool(ADMIN_PASSWORD)
        }
    })

@app.route('/')
def index():
    """Главная страница сервера"""
    return jsonify({
        'service': 'Captcha Verification Server',
        'description': 'Сервер для верификации капчи и логирования переходов',
        'version': '2.0.0',
        'endpoints': {
            'verify': '/verify/<tracking_id>/<token>?tgid=ID&username=USER&first_name=NAME&token=TOKEN&ts=TIMESTAMP',
            'health': '/health',
            'admin_visits': '/admin/visits (требует аутентификации)',
            'admin_user': '/admin/user/<telegram_id> (требует аутентификации)'
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/admin/visits')
def admin_visits():
    """Административный endpoint для просмотра посещений"""
    # Базовая HTTP аутентификация
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != ADMIN_PASSWORD:
        return jsonify({'error': 'Требуется аутентификация'}), 401
    
    visits = []
    if os.path.exists('data/visits'):
        # Получаем последние 100 посещений
        files = sorted(os.listdir('data/visits'), reverse=True)[:100]
        for filename in files:
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join('data/visits', filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        visit_data = json.load(f)
                    
                    # Добавляем имя файла для удобства
                    visit_data['_filename'] = filename
                    visits.append(visit_data)
                    
                except Exception as e:
                    logger.error(f"Ошибка чтения файла {filename}: {e}")
    
    # Статистика
    stats = {
        'total': len(visits),
        'with_telegram_id': len([v for v in visits if v.get('telegram_user', {}).get('id')]),
        'validated_telegram': len([v for v in visits if v.get('telegram_user', {}).get('validated')]),
        'unique_ips': len(set(v.get('ip_info', {}).get('address', '') for v in visits))
    }
    
    return jsonify({
        'stats': stats,
        'visits': visits
    })

@app.route('/admin/user/<int:telegram_id>')
def admin_user_visits(telegram_id):
    """Посещения конкретного пользователя"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != ADMIN_PASSWORD:
        return jsonify({'error': 'Требуется аутентификация'}), 401
    
    user_visits = []
    if os.path.exists('data/visits'):
        for filename in os.listdir('data/visits'):
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join('data/visits', filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        visit_data = json.load(f)
                    
                    if visit_data.get('telegram_user', {}).get('id') == telegram_id:
                        visit_data['_filename'] = filename
                        user_visits.append(visit_data)
                        
                except Exception as e:
                    logger.error(f"Ошибка чтения файла {filename}: {e}")
    
    # Сортируем по времени
    user_visits.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Статистика пользователя
    if user_visits:
        timestamps = [datetime.fromisoformat(v['timestamp']) for v in user_visits if v.get('timestamp')]
        first_visit = min(timestamps) if timestamps else None
        last_visit = max(timestamps) if timestamps else None
        
        user_info = user_visits[0].get('telegram_user', {})
        
        stats = {
            'total_visits': len(user_visits),
            'first_visit': first_visit.isoformat() if first_visit else None,
            'last_visit': last_visit.isoformat() if last_visit else None,
            'username': user_info.get('username'),
            'first_name': user_info.get('first_name'),
            'data_validated': user_info.get('validated', False)
        }
    else:
        stats = {'total_visits': 0}
    
    return jsonify({
        'telegram_id': telegram_id,
        'stats': stats,
        'visits': user_visits[:50]  # Ограничиваем 50 последними посещениями
    })

@app.route('/admin/stats')
def admin_stats():
    """Общая статистика"""
    auth = request.authorization
    if not auth or auth.username != 'admin' or auth.password != ADMIN_PASSWORD:
        return jsonify({'error': 'Требуется аутентификация'}), 401
    
    if not os.path.exists('data/visits'):
        return jsonify({'total_visits': 0})
    
    files = os.listdir('data/visits')
    total_visits = len(files)
    
    # Анализ последних 1000 посещений
    recent_files = files[:min(1000, total_visits)]
    
    visits_by_hour = {}
    unique_users = set()
    browsers = {}
    
    for filename in recent_files:
        if filename.endswith('.json'):
            try:
                filepath = os.path.join('data/visits', filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    visit = json.load(f)
                
                # Группировка по часам
                timestamp = visit.get('timestamp', '')
                if timestamp:
                    hour = datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:00')
                    visits_by_hour[hour] = visits_by_hour.get(hour, 0) + 1
                
                # Уникальные пользователи
                user_id = visit.get('telegram_user', {}).get('id')
                if user_id:
                    unique_users.add(user_id)
                
                # Браузеры
                browser = visit.get('user_agent', {}).get('browser', 'Неизвестно')
                browsers[browser] = browsers.get(browser, 0) + 1
                
            except:
                continue
    
    return jsonify({
        'total_visits': total_visits,
        'unique_users': len(unique_users),
        'recent_visits_analyzed': len(recent_files),
        'visits_by_hour': dict(sorted(visits_by_hour.items())[-24:]),  # Последние 24 часа
        'browsers': browsers,
        'server_time': datetime.now().isoformat()
    })

def check_configuration():
    """Проверка конфигурации при запуске"""
    errors = []
    
    if not SECRET_KEY:
        errors.append("❌ SECRET_KEY не установлен в .env файле")
    
    if REDIRECT_URL == 'https://example.com':
        errors.append("⚠️ REDIRECT_URL использует значение по умолчанию")
    
    if not ADMIN_PASSWORD or ADMIN_PASSWORD == 'admin123':
        errors.append("⚠️ ADMIN_PASSWORD использует слабый или стандартный пароль")
    
    return errors

if __name__ == '__main__':
    # Проверяем конфигурацию
    config_errors = check_configuration()
    
    if config_errors:
        for error in config_errors:
            logger.error(error)
        
        if any('❌' in error for error in config_errors):
            logger.error("Критические ошибки конфигурации! Завершение работы.")
            exit(1)
    
    # Создаем необходимые директории
    os.makedirs('data', exist_ok=True)
    os.makedirs('data/visits', exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("🚀 Запуск Captcha Server v2.0.0")
    logger.info("=" * 60)
    logger.info(f"📡 Редирект на: {REDIRECT_URL}")
    logger.info(f"🔐 SECRET_KEY: {'Установлен' if SECRET_KEY else 'НЕ УСТАНОВЛЕН!'}")
    logger.info(f"👑 Админ панель: {'Доступна' if ADMIN_PASSWORD else 'Отключена'}")
    logger.info("=" * 60)
    
    app.run(
        host='127.0.0.1',
        port=8080,
        debug=False
    )
