import json
import sqlite3
import tiktoken
import typer
from openai import OpenAI
from ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    PROMPT_FILE,
    SECRETS_FILE,
    DIALOG_FILE,
    MAX_TOKENS, AI_MODEL,
)
from ai_context.source.messages import COLORS


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


def load_context_from_db() -> str:
    """
    Загружает актуальный контекст проекта из SQLite-базы (.ai-context/context.db) и формирует его в виде единого текстового документа.

    Каждый файл в базе оборачивается в разделитель:
        ### FILE: <путь_к_файлу> ###
        <содержимое файла>
        ============================================================

    Возвращает объединённую строку, готовую к вставке в системный промт ИИ.
    Если база не существует — завершает выполнение с ошибкой.
    """

    if not CONTEXT_DB.exists():
        typer.secho(" - Контекст не найден. Выполните 'ai-context index'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("SELECT filepath, content FROM files ORDER BY filepath")
    rows = cur.fetchall()
    conn.close()
    parts = []
    for filepath, content in rows:
        parts.append(f"### FILE: {filepath} ###\n{content}\n" + "=" * 60)
    return "\n".join(parts)


def load_system_prompt() -> str:
    """
    Загружает содержимое системного промта из файла .ai-context/system-prompt.txt.

    Используется как основа инструкции для ИИ перед добавлением контекста проекта.
    Если файл отсутствует — завершает выполнение с ошибкой.
    """
    if not PROMPT_FILE.exists():
        typer.secho(" - Промт не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    return PROMPT_FILE.read_text(encoding="utf-8").strip()


def load_secrets():
    """
    Загружает настройки подключения к ИИ из .ai-context/secrets.json.

    Возвращает кортеж:
      - base_url (str): адрес OpenAI-совместимого API (например, Ollama),
      - api_key (str): ключ аутентификации (для Ollama — обычно "ollama").

    Если файл отсутствует — завершает выполнение с ошибкой.
    """
    if not SECRETS_FILE.exists():
        typer.secho(" - secrets.json не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    return data["ollama_base_url"], data.get("openai_api_key", "ollama")


def save_dialog_history(messages: list):
    """
    Сохраняет историю диалога в .ai-context/dialog.json в формате JSON.

    Принимает список сообщений в формате OpenAI Chat API:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    Используется для сохранения состояния между сессиями чата.
    """
    DIALOG_FILE.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")


def chat():
    """Команда: ai-context chat — [ТЕСТ] трёхшаговый чат с ИИ."""

    if not AI_CONTEXT_DIR.exists():
        typer.secho(" - Выполните 'ai-context init' сначала.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    # === ШАГ 0: Подготовка ===
    system_prompt = load_system_prompt()
    context = load_context_from_db()
    base_url, api_key = load_secrets()
    client = OpenAI(base_url=base_url, api_key=api_key)

    typer.secho(" - Запуск трёхшагового чата...", fg=COLORS.INFO)

    # === ШАГ 1: Установка роли ===
    typer.secho("\n[Шаг 1] Установка роли ИИ...", fg=COLORS.INFO)
    role_message = {"role": "user", "content": system_prompt + "\nПодтверди, что все понятно"}

    # noinspection PyTypeChecker
    response1 = client.chat.completions.create(
        model=AI_MODEL,
        messages=[role_message],
        temperature=0.1,
        max_tokens=128
    )
    assistant_reply1 = response1.choices[0].message.content.strip()
    typer.secho(f"ИИ: {assistant_reply1}", fg=COLORS.SUCCESS)

    # === ШАГ 2: Передача контекста ===
    typer.secho("\n[Шаг 2] Передача контекста проекта...", fg=COLORS.INFO)
    context_message = {"role": "user",
                       "content": f"Вот контекст проекта:\n\n{context}\n\nДля подтверждения перечисли все файлы проекта"}
    # noinspection PyTypeChecker
    response2 = client.chat.completions.create(
        # model="deepseek-coder:6.7b-instruct",
        model=AI_MODEL,
        messages=[
            role_message, {"role": "assistant", "content": assistant_reply1},
            context_message
        ],
        temperature=0.1,
        max_tokens=256
    )
    assistant_reply2 = response2.choices[0].message.content.strip()
    typer.secho(f"ИИ: {assistant_reply2}", fg=COLORS.SUCCESS)

    # Сохраняем базовую историю (без полного контекста в каждом сообщении!)
    base_history = [
        role_message,
        {"role": "assistant", "content": assistant_reply1},
        context_message,
        {"role": "assistant", "content": assistant_reply2}
    ]

    typer.secho("\n[Шаг 3] Готов к диалогу! Введите 'quit' или 'Выход' для завершения.", fg=COLORS.INFO)

    # === ШАГ 3: Основной диалог ===
    while True:
        try:
            user_input = typer.prompt("\nВы")
        except typer.Abort:
            break

        if user_input.strip().lower() in ("quit", "выход"):
            typer.secho(" - До свидания!", fg=COLORS.INFO)
            break

        # Формируем полный запрос: базовая история + новый вопрос
        messages = base_history + [{"role": "user", "content": user_input}]

        try:
            # Подсчёт токенов
            prompt_tokens = count_messages_tokens(messages)
            typer.secho(f"\n>>> Подсчёт токенов:", fg=COLORS.INFO)
            typer.secho(f" - Системный промт + контекст + запрос = ~{prompt_tokens} токенов", fg=COLORS.INFO)
            typer.secho(f" - Макс. длина ответа (max_tokens) = {MAX_TOKENS}", fg=COLORS.INFO)
            typer.secho(f" - Итого (примерно): {prompt_tokens + MAX_TOKENS} "
                        f"токенов из 16384 (лимит deepseek-coder:6.7b-instruct)\n", fg=COLORS.INFO)

            if prompt_tokens > 25000:
                typer.secho("Внимание: суммарное количество токенов превысит лимит модели.", fg=COLORS.WARNING)

            elif prompt_tokens + MAX_TOKENS > 30000:
                typer.secho("Внимание: суммарное количество токенов превысит лимит модели.", fg=COLORS.WARNING)

            # noinspection PyTypeChecker
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                stream=True,
                temperature=0.2,
                max_tokens=MAX_TOKENS,
            )

            full_response = ""
            typer.secho("ИИ: ", nl=False, fg=COLORS.SUCCESS)
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                print(content, end="", flush=True)
            print()

            # Добавляем в историю только пользовательский и ассистентский обмен
            base_history.append({"role": "user", "content": user_input})
            base_history.append({"role": "assistant", "content": full_response})
            save_dialog_history(base_history)

        except Exception as e:
            typer.secho(f" - Ошибка: {e}", fg=COLORS.ERROR)

