import os
import io
import logging
import time
import requests
from datetime import datetime, timezone, timedelta

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# --- LOGGING ---
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [JARVIS-Bot] %(levelname)s: %(message)s'
)
logger = logging.getLogger('jarvis_bot')

# --- CONFIG ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
BOT_PASSWORD = os.environ.get('TELEGRAM_BOT_PASSWORD', 'jarvis2024')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://backend:5002')
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')

# Session timeout (re-ask password after 1 hour of inactivity)
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', '3600'))

# Conversation states
AUTH, MAIN_MENU = range(2)
ADD_EMP_NAME, ADD_EMP_DEPT, ADD_EMP_PHOTO = range(10, 13)
WHO_CAMERA, SNAPSHOT_CAMERA = range(20, 22)
RENAME_CAMERA_SELECT, RENAME_CAMERA_NAME = range(30, 32)

# --- JARVIS RESPONSES ---

JARVIS_GREETINGS = [
    "Добрый день, сэр. Система S.U.R.V.E.I.L. к вашим услугам.",
    "Здравствуйте, сэр. Все системы наблюдения функционируют в штатном режиме.",
    "Приветствую, сэр. Saphena на связи. Чем могу быть полезен?",
]

JARVIS_AUTH_PROMPT = (
    "🔐 Для доступа к системе наблюдения необходима авторизация.\n\n"
    "Пожалуйста, введите пароль доступа, сэр."
)

JARVIS_AUTH_SUCCESS = (
    "✅ Идентификация подтверждена. Добро пожаловать в систему, сэр.\n\n"
    "Я в вашем распоряжении. Чем могу помочь?"
)

JARVIS_AUTH_FAIL = (
    "⛔ Пароль неверный, сэр. Прошу прощения, но доступ запрещён.\n"
    "Попробуйте ещё раз."
)

JARVIS_HELP = """
 *Система S.U.R.V.E.I.L. — Доступные команды, сэр:*

📋 /menu — Главное меню
👤 /add — Добавить нового сотрудника
📹 /cameras — Список всех камер
👁 /who — Кто сейчас в кабинете (по камере)
📸 /snapshot — Снимок с камеры
✏️ /rename — Переименовать камеру
🔒 /logout — Завершить сессию
❓ /help — Справка по командам

Вы также можете просто написать мне:
• _"Кто в кабинете 3?"_
• _"Покажи камеру 1"_
• _"Добавь сотрудника"_
• _"Переименуй камеру 2"_

Я всегда к вашим услугам, сэр.
"""


def _api_headers():
    """Internal API headers with authentication key"""
    return {'X-Internal-Key': INTERNAL_API_KEY}


def _is_authenticated(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is authenticated and session is still valid"""
    user_data = context.user_data
    if not user_data.get('authenticated'):
        return False
    last_activity = user_data.get('last_activity', 0)
    if time.time() - last_activity > SESSION_TIMEOUT:
        user_data['authenticated'] = False
        return False
    return True


def _touch_session(context: ContextTypes.DEFAULT_TYPE):
    """Update session activity timestamp"""
    context.user_data['last_activity'] = time.time()


def _get_main_keyboard():
    """Main menu keyboard"""
    keyboard = [
        ['👤 Добавить сотрудника', '📹 Камеры'],
        ['👁 Кто в кабинете?', '📸 Снимок'],
        ['✏️ Переименовать камеру', '❓ Помощь'],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if _is_authenticated(context):
        _touch_session(context)
        await update.message.reply_text(
            "Я на связи, сэр. Все системы работают.\n"
            "Чем могу быть полезен?",
            reply_markup=_get_main_keyboard(),
            parse_mode='Markdown'
        )
        return MAIN_MENU

    import random
    greeting = random.choice(JARVIS_GREETINGS)
    await update.message.reply_text(
        f"{greeting}\n\n{JARVIS_AUTH_PROMPT}",
        reply_markup=ReplyKeyboardRemove()
    )
    return AUTH


async def auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle password input"""
    password = update.message.text.strip()

    # Delete the password message for security
    try:
        await update.message.delete()
    except Exception:
        pass

    if password == BOT_PASSWORD:
        context.user_data['authenticated'] = True
        context.user_data['last_activity'] = time.time()
        context.user_data['chat_id'] = update.effective_chat.id
        context.user_data['username'] = update.effective_user.username or update.effective_user.first_name

        logger.info(f"User authenticated: {context.user_data['username']} (chat_id: {update.effective_chat.id})")

        await update.message.reply_text(
            JARVIS_AUTH_SUCCESS,
            reply_markup=_get_main_keyboard(),
            parse_mode='Markdown'
        )
        return MAIN_MENU
    else:
        logger.warning(f"Failed auth attempt from chat_id: {update.effective_chat.id}")
        await update.message.reply_text(JARVIS_AUTH_FAIL)
        return AUTH


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logout command"""
    context.user_data.clear()
    await update.message.reply_text(
        "🔒 Сессия завершена, сэр. Система заблокирована.\n"
        "Для повторного доступа используйте /start.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    await update.message.reply_text(
        JARVIS_HELP,
        reply_markup=_get_main_keyboard(),
        parse_mode='Markdown'
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu command"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    await update.message.reply_text(
        "Главное меню, сэр. Выберите действие:",
        reply_markup=_get_main_keyboard()
    )
    return MAIN_MENU


# --- CAMERAS LIST ---

async def cameras_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all cameras"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)

    try:
        resp = requests.get(f'{API_BASE_URL}/api/internal/cameras', headers=_api_headers(), timeout=10)
        cameras = resp.json()

        if not cameras:
            await update.message.reply_text(
                "📹 Камеры не обнаружены в системе, сэр.",
                reply_markup=_get_main_keyboard()
            )
            return MAIN_MENU

        lines = ["📹 *Камеры в системе, сэр:*\n"]
        for cam in cameras:
            status = "🟢" if cam['is_online'] else "🔴"
            fr = " 🧠" if cam.get('face_recognition_enabled') else ""
            location = f" ({cam['location']})" if cam.get('location') else ""
            lines.append(f"{status} *#{cam['id']}* — {cam['name']}{location}{fr}")

        lines.append(f"\n_Всего камер: {len(cameras)}_")
        await update.message.reply_text(
            '\n'.join(lines),
            reply_markup=_get_main_keyboard(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Cameras list error: {e}")
        await update.message.reply_text(
            "⚠️ Прошу прощения, сэр. Не удалось получить список камер. Проверьте соединение с сервером.",
            reply_markup=_get_main_keyboard()
        )

    return MAIN_MENU


# --- WHO IS IN THE ROOM ---

async def who_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start 'who is in the room' flow"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    await update.message.reply_text(
        "👁 Укажите номер камеры или её название, сэр.\n"
        "Например: `1` или `Кабинет директора`",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return WHO_CAMERA


async def who_camera_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process camera ID/name and return who's there"""
    _touch_session(context)
    query = update.message.text.strip()

    camera_id = None

    # Try parsing as integer (camera ID)
    try:
        camera_id = int(query)
    except ValueError:
        # Search by name
        try:
            resp = requests.get(
                f'{API_BASE_URL}/api/internal/cameras/search',
                params={'q': query},
                headers=_api_headers(),
                timeout=10
            )
            results = resp.json()
            if results:
                camera_id = results[0]['id']
            else:
                await update.message.reply_text(
                    f"🔍 Камера с названием «{query}» не найдена, сэр.\n"
                    "Используйте /cameras для просмотра списка камер.",
                    reply_markup=_get_main_keyboard()
                )
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Camera search error: {e}")
            await update.message.reply_text(
                "⚠️ Ошибка поиска камеры, сэр.",
                reply_markup=_get_main_keyboard()
            )
            return MAIN_MENU

    try:
        resp = requests.get(
            f'{API_BASE_URL}/api/internal/cameras/{camera_id}/detections',
            headers=_api_headers(),
            timeout=10
        )

        if resp.status_code == 404:
            await update.message.reply_text(
                f"⚠️ Камера #{camera_id} не найдена, сэр.",
                reply_markup=_get_main_keyboard()
            )
            return MAIN_MENU

        data = resp.json()
        camera_name = data.get('camera_name', f'#{camera_id}')
        people = data.get('people', [])

        if not people:
            await update.message.reply_text(
                f"📹 *{camera_name}*\n\n"
                f"В данный момент никого не обнаружено, сэр.\n"
                f"_(анализ за последние 10 минут)_",
                reply_markup=_get_main_keyboard(),
                parse_mode='Markdown'
            )
        else:
            lines = [f"📹 *{camera_name}* — обнаружено {len(people)} чел.:\n"]
            for p in people:
                conf = f" ({p['confidence']:.0%})" if p.get('confidence') else ""
                dept = f" | {p['department']}" if p.get('department') else ""
                lines.append(f"👤 *{p['employee_name']}*{dept}{conf}")
                if p.get('last_seen'):
                    try:
                        dt = datetime.fromisoformat(p['last_seen'])
                        lines.append(f"   _Замечен: {dt.strftime('%H:%M:%S')}_")
                    except Exception:
                        pass

            lines.append(f"\n_Данные за последние 10 минут_")
            await update.message.reply_text(
                '\n'.join(lines),
                reply_markup=_get_main_keyboard(),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Who detection error: {e}")
        await update.message.reply_text(
            "⚠️ Не удалось получить данные, сэр. Проверьте соединение.",
            reply_markup=_get_main_keyboard()
        )

    return MAIN_MENU


# --- SNAPSHOT ---

async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start snapshot flow"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    await update.message.reply_text(
        "📸 Укажите номер камеры или её название, сэр.\n"
        "Я сделаю снимок для вас.",
        reply_markup=ReplyKeyboardRemove()
    )
    return SNAPSHOT_CAMERA


async def snapshot_camera_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture and send snapshot from camera"""
    _touch_session(context)
    query = update.message.text.strip()

    camera_id = None
    camera_name = query

    # Try parsing as integer
    try:
        camera_id = int(query)
    except ValueError:
        try:
            resp = requests.get(
                f'{API_BASE_URL}/api/internal/cameras/search',
                params={'q': query},
                headers=_api_headers(),
                timeout=10
            )
            results = resp.json()
            if results:
                camera_id = results[0]['id']
                camera_name = results[0]['name']
            else:
                await update.message.reply_text(
                    f"🔍 Камера «{query}» не найдена, сэр.",
                    reply_markup=_get_main_keyboard()
                )
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Camera search error: {e}")
            await update.message.reply_text(
                "⚠️ Ошибка поиска камеры, сэр.",
                reply_markup=_get_main_keyboard()
            )
            return MAIN_MENU

    await update.message.reply_text(f"📸 Делаю снимок с камеры *{camera_name}*, секунду, сэр...", parse_mode='Markdown')

    try:
        resp = requests.get(
            f'{API_BASE_URL}/api/internal/cameras/{camera_id}/snapshot',
            headers=_api_headers(),
            timeout=30
        )

        if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('image'):
            photo_bytes = io.BytesIO(resp.content)
            photo_bytes.name = f'camera_{camera_id}_snapshot.jpg'

            now = datetime.now(timezone(timedelta(hours=5)))
            caption = (
                f"📸 *{camera_name}* (камера #{camera_id})\n"
                f"🕐 {now.strftime('%d.%m.%Y %H:%M:%S')}"
            )

            await update.message.reply_photo(
                photo=photo_bytes,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=_get_main_keyboard()
            )
        else:
            error_msg = "Камера недоступна"
            try:
                error_data = resp.json()
                error_msg = error_data.get('error', error_msg)
            except Exception:
                pass
            await update.message.reply_text(
                f"⚠️ Не удалось получить снимок, сэр: {error_msg}",
                reply_markup=_get_main_keyboard()
            )
    except requests.Timeout:
        await update.message.reply_text(
            "⏳ Камера не отвечает, сэр. Время ожидания истекло.",
            reply_markup=_get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        await update.message.reply_text(
            "⚠️ Прошу прощения, сэр. Произошла ошибка при получении снимка.",
            reply_markup=_get_main_keyboard()
        )

    return MAIN_MENU


# --- ADD EMPLOYEE ---

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add employee flow"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    context.user_data['new_employee'] = {}
    await update.message.reply_text(
        "👤 Регистрация нового сотрудника, сэр.\n\n"
        "Шаг 1 из 3: Введите *ФИО* сотрудника.",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_EMP_NAME


async def add_emp_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive employee name"""
    _touch_session(context)
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("⚠️ Имя слишком короткое, сэр. Попробуйте ещё раз.")
        return ADD_EMP_NAME

    context.user_data['new_employee']['name'] = name
    await update.message.reply_text(
        f"✅ Имя: *{name}*\n\n"
        f"Шаг 2 из 3: Укажите *отдел* сотрудника.",
        parse_mode='Markdown'
    )
    return ADD_EMP_DEPT


async def add_emp_dept_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive employee department"""
    _touch_session(context)
    dept = update.message.text.strip()
    if len(dept) < 2:
        await update.message.reply_text("⚠️ Название отдела слишком короткое, сэр.")
        return ADD_EMP_DEPT

    context.user_data['new_employee']['department'] = dept
    name = context.user_data['new_employee']['name']
    await update.message.reply_text(
        f"✅ Сотрудник: *{name}*\n"
        f"📂 Отдел: *{dept}*\n\n"
        f"Шаг 3 из 3: Отправьте *фотографию* сотрудника.\n"
        f"_Убедитесь, что лицо чётко видно на фото._",
        parse_mode='Markdown'
    )
    return ADD_EMP_PHOTO


async def add_emp_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive employee photo and register"""
    _touch_session(context)
    emp_data = context.user_data.get('new_employee', {})

    if not update.message.photo:
        await update.message.reply_text(
            "⚠️ Я ожидаю фотографию, сэр. Пожалуйста, отправьте фото с лицом сотрудника."
        )
        return ADD_EMP_PHOTO

    await update.message.reply_text("⏳ Обрабатываю фотографию, сэр. Один момент...")

    try:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()

        # Send to API
        files = {'photo': ('employee.jpg', bytes(photo_bytes), 'image/jpeg')}
        data = {
            'name': emp_data['name'],
            'department': emp_data['department'],
            'position': '',
        }

        resp = requests.post(
            f'{API_BASE_URL}/api/internal/employees',
            headers=_api_headers(),
            files=files,
            data=data,
            timeout=30
        )

        if resp.status_code == 201:
            result = resp.json()
            await update.message.reply_text(
                f"✅ Сотрудник успешно зарегистрирован, сэр!\n\n"
                f"👤 *{emp_data['name']}*\n"
                f"📂 Отдел: *{emp_data['department']}*\n"
                f"🆔 ID: `{result.get('employee_id', 'N/A')}`\n\n"
                f"Лицо распознано и внесено в базу данных системы.",
                parse_mode='Markdown',
                reply_markup=_get_main_keyboard()
            )
        else:
            error_data = resp.json()
            error_msg = error_data.get('error', 'Unknown error')
            await update.message.reply_text(
                f"⚠️ Не удалось добавить сотрудника, сэр.\n"
                f"Причина: _{error_msg}_",
                parse_mode='Markdown',
                reply_markup=_get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Add employee error: {e}")
        await update.message.reply_text(
            "⚠️ Прошу прощения, сэр. Произошла ошибка при регистрации сотрудника.",
            reply_markup=_get_main_keyboard()
        )

    context.user_data.pop('new_employee', None)
    return MAIN_MENU


# --- RENAME CAMERA ---

async def rename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start rename camera flow"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    await update.message.reply_text(
        "✏️ Переименование камеры, сэр.\n\n"
        "Укажите *номер камеры* или текущее *название*.",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return RENAME_CAMERA_SELECT


async def rename_camera_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select camera to rename"""
    _touch_session(context)
    query = update.message.text.strip()

    camera_id = None
    camera_name = None

    try:
        camera_id = int(query)
    except ValueError:
        try:
            resp = requests.get(
                f'{API_BASE_URL}/api/internal/cameras/search',
                params={'q': query},
                headers=_api_headers(),
                timeout=10
            )
            results = resp.json()
            if results:
                camera_id = results[0]['id']
                camera_name = results[0]['name']
            else:
                await update.message.reply_text(
                    f"🔍 Камера «{query}» не найдена, сэр.",
                    reply_markup=_get_main_keyboard()
                )
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Camera search error: {e}")
            await update.message.reply_text(
                "⚠️ Ошибка поиска, сэр.",
                reply_markup=_get_main_keyboard()
            )
            return MAIN_MENU

    context.user_data['rename_camera_id'] = camera_id
    display_name = camera_name or f"#{camera_id}"
    await update.message.reply_text(
        f"📹 Выбрана камера: *{display_name}*\n\n"
        f"Введите новое название для этой камеры, сэр.",
        parse_mode='Markdown'
    )
    return RENAME_CAMERA_NAME


async def rename_camera_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply new camera name"""
    _touch_session(context)
    new_name = update.message.text.strip()
    camera_id = context.user_data.get('rename_camera_id')

    if not camera_id:
        await update.message.reply_text(
            "⚠️ Камера не выбрана, сэр. Начните заново: /rename",
            reply_markup=_get_main_keyboard()
        )
        return MAIN_MENU

    if len(new_name) < 2:
        await update.message.reply_text("⚠️ Название слишком короткое, сэр. Попробуйте ещё раз.")
        return RENAME_CAMERA_NAME

    try:
        resp = requests.put(
            f'{API_BASE_URL}/api/internal/cameras/{camera_id}/rename',
            headers={**_api_headers(), 'Content-Type': 'application/json'},
            json={'name': new_name},
            timeout=10
        )

        if resp.status_code == 200:
            data = resp.json()
            old_name = data.get('old_name', '?')
            await update.message.reply_text(
                f"✅ Камера переименована, сэр.\n\n"
                f"Было: *{old_name}*\n"
                f"Стало: *{new_name}*",
                parse_mode='Markdown',
                reply_markup=_get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "⚠️ Не удалось переименовать камеру, сэр.",
                reply_markup=_get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Rename camera error: {e}")
        await update.message.reply_text(
            "⚠️ Ошибка соединения, сэр.",
            reply_markup=_get_main_keyboard()
        )

    context.user_data.pop('rename_camera_id', None)
    return MAIN_MENU


# --- NATURAL LANGUAGE HANDLER ---

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages in main menu (natural language + button presses)"""
    if not _is_authenticated(context):
        await update.message.reply_text(JARVIS_AUTH_PROMPT)
        return AUTH

    _touch_session(context)
    text = update.message.text.strip().lower()

    # Button handlers
    if '👤 добавить сотрудника' in text or 'добавь сотрудника' in text or 'добавить' in text:
        return await add_command(update, context)
    elif '📹 камеры' in text or 'камеры' == text or 'список камер' in text:
        return await cameras_command(update, context)
    elif '👁 кто в кабинете' in text or 'кто в кабинете' in text or 'кто в' in text or 'кто там' in text:
        return await who_command(update, context)
    elif '📸 снимок' in text or 'покажи камеру' in text or 'снимок' in text or 'скриншот' in text:
        return await snapshot_command(update, context)
    elif '✏️ переименовать' in text or 'переименуй' in text or 'переименовать' in text:
        return await rename_command(update, context)
    elif '❓ помощь' in text or 'помощь' == text or 'помоги' in text:
        return await help_command(update, context)

    # Natural language: "кто в кабинете 3" / "кто на камере Приёмная"
    import re
    who_match = re.search(r'кто\s+(?:в|на|у)\s+(?:кабинет[еу]?\s*|камер[еуа]?\s*)?(.+)', text)
    if who_match:
        query = who_match.group(1).strip().rstrip('?')
        # Simulate typing the camera query
        update.message.text = query
        return await who_camera_handler(update, context)

    # Natural language: "покажи камеру 1" / "покажи кабинет директора"
    show_match = re.search(r'покажи\s+(?:камеру?\s*|кабинет\s*)?(.+)', text)
    if show_match:
        query = show_match.group(1).strip()
        update.message.text = query
        return await snapshot_camera_handler(update, context)

    # Default response
    await update.message.reply_text(
        "Прошу прощения, сэр, но я не совсем понял ваш запрос.\n"
        "Используйте /help для списка доступных команд "
        "или выберите действие из меню.",
        reply_markup=_get_main_keyboard()
    )
    return MAIN_MENU


# --- CANCEL ---

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    context.user_data.pop('new_employee', None)
    context.user_data.pop('rename_camera_id', None)
    await update.message.reply_text(
        "Операция отменена, сэр.",
        reply_markup=_get_main_keyboard()
    )
    return MAIN_MENU


# --- MAIN ---

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set! Bot cannot start.")
        logger.error("Set the TELEGRAM_BOT_TOKEN environment variable and restart.")
        return

    logger.info("Starting JARVIS Surveillance Bot...")

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
        ],
        states={
            AUTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, auth_handler),
            ],
            MAIN_MENU: [
                CommandHandler('help', help_command),
                CommandHandler('menu', menu_command),
                CommandHandler('cameras', cameras_command),
                CommandHandler('who', who_command),
                CommandHandler('snapshot', snapshot_command),
                CommandHandler('add', add_command),
                CommandHandler('rename', rename_command),
                CommandHandler('logout', logout_command),
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler),
            ],
            ADD_EMP_NAME: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_emp_name_handler),
            ],
            ADD_EMP_DEPT: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_emp_dept_handler),
            ],
            ADD_EMP_PHOTO: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.PHOTO, add_emp_photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text(
                    "⚠️ Ожидаю фотографию, сэр. Отправьте фото или /cancel для отмены."
                )),
            ],
            WHO_CAMERA: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, who_camera_handler),
            ],
            SNAPSHOT_CAMERA: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, snapshot_camera_handler),
            ],
            RENAME_CAMERA_SELECT: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rename_camera_select_handler),
            ],
            RENAME_CAMERA_NAME: [
                CommandHandler('cancel', cancel_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rename_camera_name_handler),
            ],
        },
        fallbacks=[
            CommandHandler('start', start_command),
            CommandHandler('logout', logout_command),
            CommandHandler('cancel', cancel_command),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    logger.info("JARVIS Bot is online and ready, sir.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
