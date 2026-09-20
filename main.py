import os
import time
from threading import Thread
from flask import Flask, jsonify
import telebot
from openai import OpenAI

# --- HTTP Keep-Alive сервер для Render / UptimeRobot ---
app = Flask('')

@app.route('/')
@app.route('/health')
def health_check():
    return jsonify({"status": "online", "model": "Nemotron-3-Ultra"}), 200

def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

def keep_alive():
    Thread(target=run_flask, daemon=True).start()

# --- Конфигурация ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("OPENROUTER_API_KEY")  # или ключ от вашего провайдера
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_ID = os.getenv("MODEL_ID", "nvidia/nemotron-3-ultra-550b-a55b")

if not TELEGRAM_TOKEN or not API_KEY:
    raise ValueError("Не заданы TELEGRAM_TOKEN или API-ключ провайдера!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# Память диалогов: chat_id -> list of messages
user_histories = {}
MAX_HISTORY_LEN = 20

SYSTEM_PROMPT = (
    "Ты — NVIDIA Nemotron 3 Ultra, флагманский ИИ-ассистент с максимальной мощностью. "
    "Давай глубокие, технически безупречные, исчерпывающие и структурные ответы. "
    "Пиши код целиком, без заглушек. Продумывай архитектуру, производительность и краевые случаи."
)

def get_user_messages(chat_id, user_text):
    if chat_id not in user_histories:
        user_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    history = user_histories[chat_id]
    if not history or history[0]["role"] != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        
    history.append({"role": "user", "content": user_text})
    
    # Обрезка истории, оставляем system + последние N сообщений
    if len(history) > MAX_HISTORY_LEN + 1:
        user_histories[chat_id] = [history[0]] + history[-(MAX_HISTORY_LEN):]
        
    return user_histories[chat_id]

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    text = (
        "🤖 **Бот на базе NVIDIA Nemotron 3 Ultra**\n\n"
        "• Контекст памяти диалога активен.\n"
        "• Режим максимальной мощности.\n\n"
        "Команды:\n"
        "• /clear — сбросить память диалога"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['clear'])
def cmd_clear(message):
    chat_id = message.chat.id
    if chat_id in user_histories:
        del user_histories[chat_id]
    bot.reply_to(message, "🧹 Память диалога очищена.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        messages_payload = get_user_messages(chat_id, message.text)
        
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages_payload,
            temperature=0.6,
            max_tokens=8192
        )
        
        answer = response.choices[0].message.content
        
        # Сохраняем ответ ассистента в историю
        user_histories[chat_id].append({"role": "assistant", "content": answer})
        
        # Разбиение при превышении лимита Telegram (4096 символов)
        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                bot.reply_to(message, answer[i:i+4000])
        else:
            bot.reply_to(message, answer)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка генерации API: {str(e)}")

if __name__ == "__main__":
    keep_alive()
    print("HTTP Keep-Alive сервер запущен. Запуск Telegram Polling...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Сбой polling: {e}. Переподключение через 5 секунд...")
            time.sleep(5)
