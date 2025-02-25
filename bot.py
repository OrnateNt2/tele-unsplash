import datetime
import logging
import io
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from config import TELEGRAM_BOT_TOKEN
from unsplash_client import get_random_photo, search_photos
import database
from utils.logger import setup_logger
import httpx
import asyncio
from redis_client import get_cached_search_results, cache_search_results, cache_gallery_state
from buffer_manager import get_buffered_image, cleanup_buffer

# Состояния для диалога и галереи
SEARCH = 1
GALLERY_SEARCH = 2
GALLERY_NAV = 3
SETTINGS_MAIN, SET_ORIENTATION, SET_COLOR, SET_ORDER = range(10, 14)

# Глобальные переменные
LAST_PHOTO = {}         # для скачивания одиночных фото
RANDOM_CACHE = []       # буфер предзагруженных случайных фото
BUFFER_SIZE = 5

# Дефолтные настройки
DEFAULT_SETTINGS = {
    "orientation": "any",  # any, landscape, portrait, squarish
    "color": "any",        # any, black_and_white, black, white, yellow, orange, red, purple, magenta, green, teal, blue
    "order_by": "relevant" # relevant, latest
}

setup_logger()
logger = logging.getLogger(__name__)

# ----- Хелперы для настроек -----
def orientation_keyboard(current_settings: dict) -> InlineKeyboardMarkup:
    options = ["any", "landscape", "portrait", "squarish"]
    buttons = []
    for option in options:
        text = option + (" ✅" if current_settings.get("orientation", "any") == option else "")
        buttons.append([InlineKeyboardButton(text, callback_data=f"set_orientation:{option}")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def color_keyboard(current_settings: dict) -> InlineKeyboardMarkup:
    options = ["any", "black_and_white", "black", "white", "yellow", "orange", "red", "purple", "magenta", "green", "teal", "blue"]
    buttons = []
    for option in options:
        text = option + (" ✅" if current_settings.get("color", "any") == option else "")
        buttons.append([InlineKeyboardButton(text, callback_data=f"set_color:{option}")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def order_keyboard(current_settings: dict) -> InlineKeyboardMarkup:
    options = ["relevant", "latest"]
    buttons = []
    for option in options:
        text = option + (" ✅" if current_settings.get("order_by", "relevant") == option else "")
        buttons.append([InlineKeyboardButton(text, callback_data=f"set_order:{option}")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(buttons)

def settings_menu_keyboard(current_settings: dict) -> InlineKeyboardMarkup:
    text = f"Ваши настройки:\n" \
           f"Ориентация: {current_settings.get('orientation', 'any')}\n" \
           f"Цвет: {current_settings.get('color', 'any')}\n" \
           f"Сортировка: {current_settings.get('order_by', 'relevant')}"
    keyboard = [
        [InlineKeyboardButton("Изменить ориентацию", callback_data="settings_orientation")],
        [InlineKeyboardButton("Изменить цвет", callback_data="settings_color")],
        [InlineKeyboardButton("Изменить сортировку", callback_data="settings_order")],
        [InlineKeyboardButton("Сбросить настройки", callback_data="reset_settings")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----- Главное меню -----
def create_main_menu(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    subscribe_text = "Отписаться" if is_subscribed else "Подписаться"
    keyboard = [
        [InlineKeyboardButton("Случайное фото", callback_data="random_photo")],
        [InlineKeyboardButton("Галерея", callback_data="gallery")],
        [InlineKeyboardButton("Настройки", callback_data="settings_main")],
        [InlineKeyboardButton(subscribe_text, callback_data="toggle_subscription")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ----- Буфер предзагрузки для случайных фото -----
async def preload_random_photo(extra_params: dict):
    photo = await get_random_photo(**extra_params)
    if photo:
        RANDOM_CACHE.append(photo)

# ----- Команды и обработчики -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\nЭто бот для фото с Unsplash.\nВыберите опцию:",
        reply_markup=create_main_menu(is_subscribed)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n/start, /help, /subscribe, /unsubscribe, /settings, /gallery"
    )

# ----- Случайное фото -----
async def random_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    settings = database.get_user_settings(user_id) or DEFAULT_SETTINGS
    extra_params = {}
    if settings.get("orientation", "any") != "any":
        extra_params["orientation"] = settings["orientation"]
    if settings.get("color", "any") != "any":
        extra_params["color"] = settings["color"]
    if RANDOM_CACHE:
        photo = RANDOM_CACHE.pop(0)
    else:
        photo = await get_random_photo(**extra_params)
    if len(RANDOM_CACHE) < BUFFER_SIZE:
        context.application.create_task(preload_random_photo(extra_params))
    if photo:
        LAST_PHOTO[user_id] = photo
        image_url = photo.get("urls", {}).get("regular")
        description = photo.get("description") or photo.get("alt_description") or "Без описания"
        caption = f"{description}\nАвтор: {photo.get('user', {}).get('name', 'Неизвестно')}"
        keyboard = [
            [InlineKeyboardButton("Ещё", callback_data="random_photo")],
            [InlineKeyboardButton("Скачать", callback_data="download_photo")],
            [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
        ]
        await query.message.reply_photo(photo=image_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.message.reply_text("Не удалось получить фото.")

async def download_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    photo = LAST_PHOTO.get(user_id)
    if not photo:
        await query.message.reply_text("Фото для скачивания не найдено.")
        return
    full_url = photo.get("urls", {}).get("full")
    if not full_url:
        await query.message.reply_text("Нет ссылки для скачивания.")
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(full_url)
        if response.status_code == 200:
            file_bytes = io.BytesIO(response.content)
            file_bytes.name = "photo.jpg"
            await query.message.reply_document(document=InputFile(file_bytes))
        else:
            await query.message.reply_text("Не удалось скачать фото.")
    except Exception as e:
        logger.error(f"Ошибка при скачивании фото: {e}")
        await query.message.reply_text("Ошибка при скачивании фото.")

async def back_to_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    is_subscribed = database.check_subscription(user.id)
    await query.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

async def toggle_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    chat_id = query.message.chat_id
    if database.check_subscription(user.id):
        database.remove_subscription(user.id)
        await query.message.reply_text("Вы отписались от уведомлений.")
    else:
        database.add_subscription(user.id, chat_id)
        await query.message.reply_text("Вы подписались на уведомления!")
    is_subscribed = database.check_subscription(user.id)
    await query.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

# ----- Галерея с кэшированием и буфером -----
async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите поисковый запрос для галереи:")
    return GALLERY_SEARCH

async def gallery_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    user_id = update.effective_user.id
    settings = database.get_user_settings(user_id) or DEFAULT_SETTINGS
    extra_params = {}
    if settings.get("orientation", "any") != "any":
        extra_params["orientation"] = settings["orientation"]
    if settings.get("color", "any") != "any":
        extra_params["color"] = settings["color"]
    if settings.get("order_by", "relevant"):
        extra_params["order_by"] = settings["order_by"]
    page = 1
    cached = await get_cached_search_results(query_text, settings, page)
    if cached:
        results = cached
    else:
        results = await search_photos(query_text, page=page, per_page=10, **extra_params)
        if results and results.get("results"):
            await cache_search_results(query_text, settings, page, results)
    if results and results.get("results"):
        state = {"query": query_text, "page": page, "total_pages": results.get("total_pages", 1)}
        await cache_gallery_state(user_id, state)
        context.user_data["gallery_query"] = query_text
        context.user_data["gallery_page"] = page
        context.user_data["gallery_total_pages"] = results.get("total_pages", 1)
        context.user_data["gallery_results"] = results
        await send_gallery(update.effective_chat.id, context)
    else:
        await update.message.reply_text("Ничего не найдено.")
        return ConversationHandler.END
    return GALLERY_NAV

async def send_gallery(chat_id, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get("gallery_results")
    if not results:
        return
    media = []
    # Для каждой фотографии скачиваем миниатюру в буфер
    for photo in results.get("results", []):
        thumb_url = photo.get("urls", {}).get("small")
        if thumb_url:
            local_path = await get_buffered_image(thumb_url)
            if local_path:
                media.append(InputMediaPhoto(media=local_path))
    if media:
        await context.bot.send_media_group(chat_id=chat_id, media=media)
    # Формируем клавиатуру для выбора и навигации
    buttons = []
    for i in range(len(results.get("results", []))):
        buttons.append(InlineKeyboardButton(f"{i+1}", callback_data=f"gallery_select:{i}"))
    nav_buttons = []
    page = context.user_data.get("gallery_page", 1)
    total = context.user_data.get("gallery_total_pages", 1)
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀ Предыдущая", callback_data="gallery_prev"))
    if page < total:
        nav_buttons.append(InlineKeyboardButton("Следующая ▶", callback_data="gallery_next"))
    buttons.append(InlineKeyboardButton("Главное меню", callback_data="back_to_menu"))
    keyboard = InlineKeyboardMarkup([buttons, nav_buttons] if nav_buttons else [buttons])
    await context.bot.send_message(chat_id=chat_id, text="Выберите номер фото для скачивания в хорошем качестве:", reply_markup=keyboard)

async def gallery_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    settings = database.get_user_settings(user_id) or DEFAULT_SETTINGS
    if data.startswith("gallery_select:"):
        index = int(data.split(":")[1])
        results = context.user_data.get("gallery_results")
        if results and index < len(results.get("results", [])):
            photo = results["results"][index]
            LAST_PHOTO[user_id] = photo
            image_url = photo.get("urls", {}).get("full")
            description = photo.get("description") or photo.get("alt_description") or "Без описания"
            caption = f"{description}\nАвтор: {photo.get('user', {}).get('name', 'Неизвестно')}"
            await query.message.reply_photo(photo=image_url, caption=caption)
    elif data in ("gallery_next", "gallery_prev"):
        current_page = context.user_data.get("gallery_page", 1)
        total = context.user_data.get("gallery_total_pages", 1)
        new_page = current_page + 1 if data == "gallery_next" else current_page - 1
        if new_page < 1 or new_page > total:
            return
        query_text = context.user_data.get("gallery_query")
        extra_params = {}
        if settings.get("orientation", "any") != "any":
            extra_params["orientation"] = settings["orientation"]
        if settings.get("color", "any") != "any":
            extra_params["color"] = settings["color"]
        if settings.get("order_by", "relevant"):
            extra_params["order_by"] = settings["order_by"]
        cached = await get_cached_search_results(query_text, settings, new_page)
        if cached:
            results = cached
        else:
            results = await search_photos(query_text, page=new_page, per_page=10, **extra_params)
            if results and results.get("results"):
                await cache_search_results(query_text, settings, new_page, results)
        if results and results.get("results"):
            context.user_data["gallery_page"] = new_page
            context.user_data["gallery_results"] = results
            await send_gallery(query.message.chat_id, context)
    elif data == "back_to_menu":
        await query.message.reply_text("Главное меню:", reply_markup=create_main_menu(database.check_subscription(user_id)))
    return GALLERY_NAV

# ----- Настройки -----
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = database.get_user_settings(user_id)
    if not settings:
        settings = DEFAULT_SETTINGS.copy()
        database.set_user_settings(user_id, settings)
    await update.message.reply_text("Настройки поиска:", reply_markup=settings_menu_keyboard(settings))

async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current_settings = database.get_user_settings(user_id) or DEFAULT_SETTINGS.copy()
    data = query.data
    if data == "settings_main":
        await query.message.edit_text("Настройки поиска:", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN
    elif data == "settings_orientation":
        await query.message.edit_text("Выберите ориентацию:", reply_markup=orientation_keyboard(current_settings))
        return SET_ORIENTATION
    elif data == "settings_color":
        await query.message.edit_text("Выберите цвет:", reply_markup=color_keyboard(current_settings))
        return SET_COLOR
    elif data == "settings_order":
        await query.message.edit_text("Выберите порядок сортировки:", reply_markup=order_keyboard(current_settings))
        return SET_ORDER
    elif data == "reset_settings":
        database.set_user_settings(user_id, DEFAULT_SETTINGS.copy())
        current_settings = DEFAULT_SETTINGS.copy()
        await query.message.edit_text("Настройки сброшены.", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN
    elif data == "settings_back":
        await query.message.edit_text("Настройки поиска:", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN
    elif data.startswith("set_orientation:"):
        value = data.split(":")[1]
        current_settings["orientation"] = value
        database.set_user_settings(user_id, current_settings)
        await query.message.edit_text("Настройки обновлены.", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN
    elif data.startswith("set_color:"):
        value = data.split(":")[1]
        current_settings["color"] = value
        database.set_user_settings(user_id, current_settings)
        await query.message.edit_text("Настройки обновлены.", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN
    elif data.startswith("set_order:"):
        value = data.split(":")[1]
        current_settings["order_by"] = value
        database.set_user_settings(user_id, current_settings)
        await query.message.edit_text("Настройки обновлены.", reply_markup=settings_menu_keyboard(current_settings))
        return SETTINGS_MAIN

def settings_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return SETTINGS_MAIN

# ----- Ежедневные уведомления -----
async def daily_notification(context: ContextTypes.DEFAULT_TYPE):
    subscriptions = database.get_all_subscriptions()
    for user_id, chat_id in subscriptions:
        photo = await get_random_photo()
        if photo:
            image_url = photo.get("urls", {}).get("regular")
            description = photo.get("description") or photo.get("alt_description") or "Без описания"
            caption = f"{description}\nАвтор: {photo.get('user', {}).get('name', 'Неизвестно')}"
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

# ----- Подписка/отписка -----
async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not database.check_subscription(user.id):
        database.add_subscription(user.id, chat_id)
        await update.message.reply_text("Вы подписались на уведомления!")
    else:
        await update.message.reply_text("Вы уже подписаны.")
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if database.check_subscription(user.id):
        database.remove_subscription(user.id)
        await update.message.reply_text("Вы отписались от уведомлений.")
    else:
        await update.message.reply_text("Вы не подписаны.")
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

# ----- Основной запуск -----
def main():
    database.init_db()
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Командные обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("gallery", gallery_command))

    # Conversation для галереи
    gallery_conv = ConversationHandler(
        entry_points=[CommandHandler("gallery", gallery_command)],
        states={
            GALLERY_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, gallery_search_handler)],
            GALLERY_NAV: [CallbackQueryHandler(gallery_callback_handler, pattern="^(gallery_select:.*|gallery_next|gallery_prev|back_to_menu)$")]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Операция отменена.", reply_markup=create_main_menu()))]
    )
    application.add_handler(gallery_conv)

    # Conversation для настроек
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_callback_handler, pattern="^(settings_.*|set_.*|reset_settings)$")],
        states={
            SET_ORIENTATION: [CallbackQueryHandler(settings_callback_handler, pattern="^(set_orientation:.*|settings_back)$")],
            SET_COLOR: [CallbackQueryHandler(settings_callback_handler, pattern="^(set_color:.*|settings_back)$")],
            SET_ORDER: [CallbackQueryHandler(settings_callback_handler, pattern="^(set_order:.*|settings_back)$")],
            SETTINGS_MAIN: [CallbackQueryHandler(settings_callback_handler, pattern="^(settings_.*|reset_settings)$")]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Операция отменена.", reply_markup=create_main_menu()))]
    )
    application.add_handler(settings_conv)

    # Inline-обработчики для одиночных фото
    application.add_handler(CallbackQueryHandler(random_photo_handler, pattern="^random_photo$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(toggle_subscription_handler, pattern="^toggle_subscription$"))
    application.add_handler(CallbackQueryHandler(download_photo_handler, pattern="^download_photo$"))

    # Ежедневные уведомления (10:00)
    job_queue = application.job_queue
    job_queue.run_daily(daily_notification, time=datetime.time(hour=10, minute=0, second=0))

    application.run_polling()

if __name__ == '__main__':
    main()
