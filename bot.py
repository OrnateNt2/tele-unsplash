import datetime
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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

# Состояние для диалога поиска
SEARCH = 1

setup_logger()
logger = logging.getLogger(__name__)

def create_main_menu(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    subscribe_text = "Отписаться" if is_subscribed else "Подписаться"
    keyboard = [
        [InlineKeyboardButton("Случайное фото", callback_data="random_photo")],
        [InlineKeyboardButton("Поиск фото", callback_data="prompt_search")],
        [InlineKeyboardButton(subscribe_text, callback_data="toggle_subscription")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\nЭто бот для отправки фото с Unsplash.\nВыберите опцию:",
        reply_markup=create_main_menu(is_subscribed)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Используйте кнопки для навигации:\n"
        "• Случайное фото – получить случайное фото\n"
        "• Поиск фото – найти фото по запросу\n"
        "• Подписаться/Отписаться – получать ежедневные уведомления с фото\n\n"
        "Также доступны команды /start, /help, /subscribe, /unsubscribe, /cancel."
    )

async def random_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    photo = await get_random_photo()
    if photo:
        image_url = photo.get("urls", {}).get("regular")
        description = photo.get("description") or photo.get("alt_description") or "Без описания"
        caption = f"{description}\nАвтор: {photo.get('user', {}).get('name', 'Неизвестно')}"
        keyboard = [
            [InlineKeyboardButton("Ещё", callback_data="random_photo")],
            [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup)
    else:
        await query.message.reply_text("Не удалось получить фото. Попробуйте позже.")

async def prompt_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите поисковый запрос:")
    return SEARCH

async def search_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    results = await search_photos(user_query)
    if results and results.get("results"):
        photo = results["results"][0]
        image_url = photo.get("urls", {}).get("regular")
        description = photo.get("description") or photo.get("alt_description") or "Без описания"
        caption = f"{description}\nАвтор: {photo.get('user', {}).get('name', 'Неизвестно')}"
        keyboard = [
            [InlineKeyboardButton("Ещё", callback_data="prompt_search")],
            [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_photo(photo=image_url, caption=caption, reply_markup=reply_markup)
    else:
        await update.message.reply_text("Ничего не найдено по вашему запросу.")
    return ConversationHandler.END

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
        await query.message.reply_text("Вы отписались от ежедневных уведомлений.")
    else:
        database.add_subscription(user.id, chat_id)
        await query.message.reply_text("Вы подписались на ежедневные уведомления с фото!")
    is_subscribed = database.check_subscription(user.id)
    await query.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.", reply_markup=create_main_menu())
    return ConversationHandler.END

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
                logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not database.check_subscription(user.id):
        database.add_subscription(user.id, chat_id)
        await update.message.reply_text("Вы подписались на ежедневные уведомления с фото!")
    else:
        await update.message.reply_text("Вы уже подписаны.")
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if database.check_subscription(user.id):
        database.remove_subscription(user.id)
        await update.message.reply_text("Вы отписались от ежедневных уведомлений.")
    else:
        await update.message.reply_text("Вы не подписаны.")
    is_subscribed = database.check_subscription(user.id)
    await update.message.reply_text("Главное меню:", reply_markup=create_main_menu(is_subscribed))

def main():
    # Инициализация БД подписок
    database.init_db()

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))

    # ConversationHandler для поиска фото
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_search_handler, pattern="^prompt_search$")],
        states={
            SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)

    # Обработчики inline-кнопок
    application.add_handler(CallbackQueryHandler(random_photo_handler, pattern="^random_photo$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_handler, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(toggle_subscription_handler, pattern="^toggle_subscription$"))

    # Ежедневные уведомления (каждый день в 10:00 по серверному времени)
    job_queue = application.job_queue
    job_queue.run_daily(daily_notification, time=datetime.time(hour=10, minute=0, second=0))

    # Запуск бота (блокирующий вызов)
    application.run_polling()

if __name__ == '__main__':
    main()
