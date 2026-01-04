import json
import sqlite3
import tiktoken
import typer
from openai import OpenAI

from ai_context.commands.compress import extract_summaries_from_db
from ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    PROMPT_FILE,
    SECRETS_FILE,
    DIALOG_FILE,
    MAX_TOKENS,
    AI_MODEL,
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


def send_message(client: OpenAI, messages: list) -> str:
    """
    Отправляет список сообщений в ИИ и возвращает полный ответ.
    Поддерживает streaming и отладочный вывод.
    """

    prompt_tokens = count_messages_tokens(messages, model=AI_MODEL)

    # Ограничиваем, чтобы не превысить лимит
    max_tokens_for_response = MAX_TOKENS - prompt_tokens - 100  # запас на погрешность
    typer.secho(f"\n[DEBUG] Токенов в запросе: {prompt_tokens}", fg=COLORS.DEBUG)
    typer.secho(f"[DEBUG] Макс. токенов на ответ: {max_tokens_for_response}", fg=COLORS.DEBUG)

    typer.secho("\n[DEBUG] → Отправка в ИИ:", fg=COLORS.DEBUG)
    for msg in messages:
        typer.secho(f"  {msg['role'].upper()}: {msg['content'][:400]}...", fg=COLORS.DEBUG)

    typer.secho("-" * 50, fg=COLORS.DEBUG)

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens_for_response,
            stream=True,
        )

        full_response = ""
        full_reasoning = ""
        typer.secho("ИИ: ", nl=False, fg=COLORS.SUCCESS)
        for chunk in response:
            content = chunk.choices[0].delta.content or ""
            full_response += content

            if hasattr(chunk.choices[0].delta, 'reasoning') and chunk.choices[0].delta.reasoning:
                full_reasoning += chunk.choices[0].delta.reasoning or ""

            print(content, end="", flush=True)

        print()  # новая строка после ответа
        typer.secho(f"[DEBUG] Content: {full_response}", fg=COLORS.DEBUG)
        typer.secho(f"[DEBUG] Reasoning: {full_reasoning}", fg=COLORS.DEBUG)

        print()  # новая строка после ответа


        return full_response.strip()

    except Exception as e:
        typer.secho(f"\n[ОШИБКА] При вызове ИИ: {e}", fg=COLORS.ERROR)
        raise


def chat():
    """Команда: ai-context chat — трёхшаговый чат с ИИ."""

    if not AI_CONTEXT_DIR.exists():
        typer.secho(" - Выполните 'ai-context init' сначала.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    # === Подготовка ===
    base_history = []
    system_prompt = load_system_prompt()
    resume = "\n".join(extract_summaries_from_db())  # resume как строка
    base_url, api_key = load_secrets()
    client = OpenAI(base_url=base_url, api_key=api_key)

    # === ШАГ 1: Установка роли ===
    typer.secho("\n[Шаг 1] Установка роли ИИ...", fg=COLORS.WARNING)
    messages_step1 = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Подтверди, что все понятно в виде ответа \"Да\" или \"Нет\""}
    ]
    reply_1 = send_message(client, messages_step1)

    if "Да" not in reply_1:
        typer.secho("[Шаг 1] Модель не подтвердила понимание инструкции.", fg=COLORS.ERROR)
        return

    # === ШАГ 2: Передача контекста (резюме) ===
    base_history.extend(messages_step1)
    typer.secho("\n[Шаг 2] Передача контекста проекта (резюме)", fg=COLORS.WARNING)
    messages_step2 = [
        {"role": "assistant", "content": reply_1},
        {"role": "user", "content": f"Вот резюме проекта:\n\n{resume}\n\nТвоя задача — помочь с разработкой. Подтверди понимание: \"Да\" или \"Нет\""}
    ]
    reply_2 = send_message(client, messages_step2)

    if "Да" not in reply_2:
        typer.secho("[Шаг 2] Модель не подтвердила понимание контекста.", fg=COLORS.ERROR)
        return

    # === ШАГ 3: Проверочный вопрос ===
    base_history.extend(messages_step2)
    typer.secho("\n[Шаг 3] Проверочный вопрос", fg=COLORS.WARNING)
    messages_step3 = [
        {"role": "assistant", "content": reply_2},
        {"role": "user", "content": f"Кратко опиши о чем проект и выведи его структуру ниде в виде дерева элементов"}
    ]
    reply_3 = send_message(client, messages_step3)

    if "Да" not in reply_2:
        typer.secho("[Шаг 3] Модель не подтвердила понимание контекста.", fg=COLORS.ERROR)
        return

    # === Формируем базовую историю для последующих вопросов ===
    base_history.extend(messages_step3)
    base_history.extend({"role": "assistant", "content": reply_3})

    save_dialog_history(base_history)
    typer.secho("\n[Шаг 3] Готов к диалогу! Введите 'quit' или 'Выход' для завершения.", fg=COLORS.WARNING)

    # === Основной цикл ===
    while True:
        try:
            user_input = typer.prompt("\nВы")
        except typer.Abort:
            break

        if user_input.strip().lower() in ("quit", "выход"):
            typer.secho(" - До свидания!", fg=COLORS.INFO)
            break

        # Формируем полный контекст запроса
        current_messages = base_history + [{"role": "user", "content": user_input}]

        # Подсчёт токенов (для отладки)
        try:
            prompt_tokens = count_messages_tokens(current_messages, model=AI_MODEL)
            typer.secho(f"\n[DEBUG] Токены запроса: ~{prompt_tokens}", fg=COLORS.DEBUG)

        except Exception as e:
            typer.secho(f"[DEBUG] Не удалось подсчитать токены: {e}", fg=COLORS.WARNING)

        # Отправка
        try:
            assistant_reply = send_message(client, [{"role": "user", "content": user_input}])

            # Обновляем историю
            base_history.append({"role": "user", "content": user_input})
            base_history.append({"role": "assistant", "content": assistant_reply})
            save_dialog_history(base_history)

        except Exception as e:
            typer.secho(f"Ошибка в диалоге: {e}", fg=COLORS.ERROR)
            continue