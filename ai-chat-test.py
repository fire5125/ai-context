"""
Простой скрипт для прямого общения с локальной ИИ-моделью через Ollama.
Подсчитывает количество токенов перед отправкой.
"""

import tiktoken
from openai import OpenAI

# === 1. НАСТРОЙКИ ПОДКЛЮЧЕНИЯ ===
BASE_URL = "http://localhost:11434/v1"
API_KEY = "ollama"
# MODEL = "deepseek-coder:6.7b-instruct"
MODEL = "qwen3:14b"

# === 2. СОДЕРЖИМОЕ ЗАПРОСА ===
SYSTEM_PROMPT = """
Ты — эксперт-разработчик, помогающий пользователю понять и улучшить его кодовую базу.
Отвечай на русском языке.
Всегда объясняй кратко, по делу.
Если даёшь пример кода — указывай язык и обрамляй в блоки ```...```.
Не придумывай несуществующие файлы или функции — опирайся ТОЛЬКО на предоставленный контекст.
"""

# PROJECT_CONTEXT = """
# ### FILE: README.md ###
# # ai-context
# Идея: Создать локальный CLI-инструмент для автоматического сбора контекста кодовой базы и взаимодействия с ИИ-моделью в контексте проекта.
# """

# context_filename = "out.txt"
context_filename = "test-resume.txt"
PROJECT_CONTEXT = open(context_filename, "r", encoding="utf-8").read()

USER_MESSAGE = "Привет! Выше, в блоке \"=== КОНТЕКСТ ===\" написан код, который я написал. Помоги мне его улучшить."

# === 3. ПАРАМЕТРЫ ГЕНЕРАЦИИ ===
TEMPERATURE = 0.2
MAX_TOKENS = 4096
TOP_P = 0.95
STREAM = True

# === 4. ФУНКЦИИ ПОДСЧЁТА ТОКЕНОВ ===
def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Подсчитывает приблизительное количество токенов в тексте.
    Для локальных моделей (DeepSeek, Llama и др.) используем токенизатор gpt-3.5-turbo как приближение.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)

    except KeyError:
        # Fallback на cl100k_base (используется в большинстве современных моделей)
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))

def count_messages_tokens(messages: list, model: str = "gpt-3.5-turbo") -> int:
    """
    Подсчитывает общее количество токенов во всех сообщениях.
    Учитывает структуру чата (роли, разделители).
    Простая реализация — без учёта специфичных токенов системы для Ollama.
    """
    total = 0
    for msg in messages:
        # Приблизительный подсчет: роль + содержимое + служебные токены
        total += count_tokens(f"{msg['role']}: {msg['content']}", model)
    # Добавим ~3 токена на служебные метаданные (start of message и т.п.)
    return total + 3

# === 5. ОТПРАВКА ЗАПРОСА ===
def main():
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n=== КОНТЕКСТ ===\n" + PROJECT_CONTEXT},
        {"role": "user", "content": USER_MESSAGE}
    ]

    # Подсчёт токенов
    prompt_tokens = count_messages_tokens(messages)
    print(f"\n>>> Подсчёт токенов:")
    print(f" - Системный промт + контекст + запрос = ~{prompt_tokens} токенов")
    print(f" - Макс. длина ответа (max_tokens) = {MAX_TOKENS}")
    print(f" - Итого (примерно): {prompt_tokens + MAX_TOKENS} токенов из 16384 (лимит deepseek-coder:6.7b-instruct)\n")

    if prompt_tokens > 12000:
        print("Внимание: контекст слишком большой! Модель может обрезать вход.")

    elif prompt_tokens + MAX_TOKENS > 16384:
        print("Внимание: суммарное количество токенов превысит лимит модели.")

    print(">>> Отправляю запрос в модель...\n")
    print(f"[Пользователь]\n{USER_MESSAGE}\n")
    print(">>> Ответ модели:\n")

    # noinspection PyTypeChecker
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        top_p=TOP_P,
        stream=STREAM
    )

    if STREAM:
        full_answer = ""
        for chunk in response:
            content = chunk.choices[0].delta.content or ""
            full_answer += content
            print(content, end="", flush=True)
        print("\n")

    else:
        full_answer = response.choices[0].message.content
        print(full_answer)

    # Подсчёт токенов в ответе
    completion_tokens = count_tokens(full_answer)
    total_tokens = prompt_tokens + completion_tokens
    print(f"\n>>> Статистика токенов:")
    print(f" - Вход (prompt): {prompt_tokens}")
    print(f" - Ответ (completion): {completion_tokens}")
    print(f" - Всего: {total_tokens} токенов")

if __name__ == "__main__":
    main()