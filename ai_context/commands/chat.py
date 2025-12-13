import json
import sqlite3
from pathlib import Path
import typer
from openai import OpenAI
from .source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    PROMPT_FILE,
    SECRETS_FILE,
    DIALOG_FILE,
)
from .source.messages import COLORS

def load_context_from_db() -> str:
    """Загружает контекст проекта из SQLite и возвращает как строку."""
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
    """Загружает системный промт."""
    if not PROMPT_FILE.exists():
        typer.secho(" - Промт не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    return PROMPT_FILE.read_text(encoding="utf-8").strip()

def load_secrets():
    """Загружает URL и API-ключ из secrets.json."""
    if not SECRETS_FILE.exists():
        typer.secho(" - secrets.json не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    return data["ollama_base_url"], data.get("openai_api_key", "ollama")

def load_dialog_history() -> list:
    """Загружает историю диалога из dialog.json."""
    if not DIALOG_FILE.exists():
        return []
    try:
        data = json.loads(DIALOG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_dialog_history(messages: list):
    """Сохраняет историю в dialog.json."""
    DIALOG_FILE.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

def clear_context_and_history():
    """Очищает контекст (SQLite) и историю диалога."""
    if CONTEXT_DB.exists():
        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM files")
        conn.commit()
        conn.close()
        typer.secho(" - Контекст очищен (context.db).", fg=COLORS.WARNING)
    DIALOG_FILE.write_text("[]", encoding="utf-8")
    typer.secho(" - История диалога очищена (dialog.json).", fg=COLORS.WARNING)

def chat(
        clear: bool = typer.Option(False, "--clear", "-c", help="Очистить контекст и историю перед запуском"),
):
    """Команда: ai-context chat [--clear]"""
    if not AI_CONTEXT_DIR.exists():
        typer.secho(" - Выполните 'ai-context init' сначала.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    if clear:
        clear_context_and_history()

    # Загрузка данных
    context = load_context_from_db()
    system_prompt = load_system_prompt()
    base_url, api_key = load_secrets()
    history = load_dialog_history()

    client = OpenAI(base_url=base_url, api_key=api_key)

    system_message = {
        "role": "system",
        "content": f"{system_prompt}\n\n=== КОНТЕКСТ ПРОЕКТА ===\n{context}"
    }

    typer.secho(" - Запущен интерактивный чат. Введите 'quit' или 'Выход' для завершения.", fg=COLORS.INFO)

    while True:
        try:
            user_input = typer.prompt("\nВы")
        except typer.Abort:
            typer.secho("\n - До свидания!", fg=COLORS.INFO)
            break

        if user_input.strip().lower() in ("quit", "выход"):
            typer.secho(" - До свидания!", fg=COLORS.INFO)
            break

        history.append({"role": "user", "content": user_input})
        messages = [system_message] + history

        # 🔍 ВРЕМЕННЫЙ ОТЛАДОЧНЫЙ ВЫВОД (можно удалить позже)
        typer.secho("\n[ОТЛАДКА] Первые 200 символов системного промпта:", fg=COLORS.DEBUG)
        typer.secho(system_message["content"][:200] + "...", fg=COLORS.DEBUG)
        typer.secho(f"[ОТЛАДКА] История: {len(history)} сообщений", fg=COLORS.DEBUG)

        try:
            response = client.chat.completions.create(
                model="deepseek-coder:6.7b-instruct",
                messages=messages,
                stream=True,
                temperature=0.2,
                max_tokens=2048,
            )

            full_response = ""
            typer.secho("ИИ: ", nl=False, fg=COLORS.SUCCESS)
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                typer.echo(content, nl=False)

            typer.echo()  # новая строка после ответа
            history.append({"role": "assistant", "content": full_response})
            save_dialog_history(history)

        except Exception as e:
            typer.secho(f"\n - Ошибка при обращении к ИИ: {e}", fg=COLORS.ERROR)