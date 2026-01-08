import json
from pathlib import Path
from typing import List, Optional

import sqlite3
import tiktoken
import typer
from openai import OpenAI
from pydantic import BaseModel

from ai_context.commands.compress import load_summary_from_db
from ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    PROMPT_FILE,
    SECRETS_FILE,
    DIALOG_FILE,
    AI_MODEL,
    MAX_TOKENS,
)
from ai_context.source.messages import COLORS


class Message(BaseModel):
    index: int
    role: str
    tokens: Optional[int] = None
    response: Optional[str] = None
    reasoning: Optional[str] = None


class Chat:
    def __init__(self, base_url: str, api_key: str, token_size: int = MAX_TOKENS):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.token_size = token_size
        self.history: List[Message] = []
        self._next_index = 0

    @staticmethod
    def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
        """
        Подсчитывает приблизительное количество токенов в тексте.
        Для локальных моделей (DeepSeek, Llama и др.) используем токенизатор gpt-3.5-turbo как приближение.
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))

    @staticmethod
    def load_context_from_db() -> str:
        """Загружает полный контекст проекта из SQLite-базы."""
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

    @staticmethod
    def load_resume_from_db() -> str:
        """Загружает кэшированное резюме проекта из БД."""
        return load_summary_from_db()

    @staticmethod
    def load_system_prompt() -> str:
        """Загружает системный промпт из файла."""
        if not PROMPT_FILE.exists():
            typer.secho(" - Промт не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
            raise typer.Exit(1)
        return PROMPT_FILE.read_text(encoding="utf-8").strip()

    def prepare_history(self) -> List[dict]:
        """
        Возвращает срез истории, укладывающийся в лимит self.token_size.
        История формируется в формате OpenAI: [{"role": "...", "content": "..."}]
        """
        total_tokens = 0
        selected_messages: List[dict] = []

        # Инвертируем историю, чтобы начать с самых свежих сообщений
        for msg in reversed(self.history):
            msg_tokens = msg.tokens or self.count_tokens(f"{msg.role}: {msg.response}", AI_MODEL)
            if total_tokens + msg_tokens > self.token_size:
                break
            selected_messages.insert(0, {"role": msg.role, "content": msg.response})
            total_tokens += msg_tokens

        return selected_messages

    def send_message(self, message_from_user: str) -> str:
        """
        Отправляет сообщение от пользователя в ИИ, получает ответ и сохраняет в историю.
        Возвращает ответ ИИ как строку.
        """
        user_message = Message(
            index=self._next_index,
            role="user",
            response=message_from_user
        )
        user_message.tokens = self.count_tokens(
            f"{user_message.role}: {user_message.response}", AI_MODEL
        )
        self.history.append(user_message)
        self._next_index += 1

        messages_to_send = self.prepare_history()
        max_tokens_for_response = self.token_size - sum(
            self.count_tokens(f"{m['role']}: {m['content']}", AI_MODEL) for m in messages_to_send
        ) - 100  # запас

        if max_tokens_for_response <= 50:
            typer.secho("[SYSTEM] : Контекст почти заполнен — ответ может быть усечён.", fg=COLORS.WARNING)

        try:
            # noinspection PyTypeChecker
            response = self.client.chat.completions.create(
                model=AI_MODEL,
                messages=messages_to_send,
                temperature=0.2,
                max_tokens=max_tokens_for_response,
                stream=False,  # пока без streaming — можно добавить позже
            )
            assistant_response = response.choices[0].message.content or ""
            assistant_reasoning = response.choices[0].message.reasoning or ""
            typer.secho(f"[DEBUG] : {response.choices[0].message.reasoning}", fg=COLORS.DEBUG)

        except Exception as e:
            typer.secho(f"[ОШИБКА] : Ошибка при вызове ИИ: {e}", fg=COLORS.ERROR)
            raise

        assistant_message = Message(
            index=self._next_index,
            role="assistant",
            response=assistant_response,
            reasoning=assistant_reasoning
        )
        assistant_message.tokens = self.count_tokens(
            f"{assistant_message.role}: {assistant_message.response}", AI_MODEL
        )
        self.history.append(assistant_message)
        self._next_index += 1

        return assistant_response

    def save_dialog_history(self):
        """
        Сохраняет историю в формате:
        """
        exportable = [
            {
                "role": e.role,
                "tokens": e.tokens,
                "response": e.response,
                "reasoning": e.reasoning,
            } for e in self.history
        ]
        DIALOG_FILE.write_text(json.dumps(exportable, ensure_ascii=False, indent=2), encoding="utf-8")

        # h = f"{}"
        # h = '[' + ','.join([msg.model_dump_json() for msg in self.history]) + ']'
        # print(h)
        #
        # test_file = AI_CONTEXT_DIR / "test_dialog.json"
        #
        # test_file.write_text(
        #     data=json.loads(h),
        #     encoding="utf-8"
        # )


def load_secrets():
    if not SECRETS_FILE.exists():
        typer.secho(" - secrets.json не найден. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    return data["ollama_base_url"], data.get("openai_api_key", "ollama")


def chat():
    """Команда: ai-context chat — простой интерактивный чат с ИИ."""
    if not AI_CONTEXT_DIR.exists():
        typer.secho("[SYSTEM] : Выполните 'ai-context init' сначала.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    base_url, api_key = load_secrets()
    chat_instance = Chat(base_url=base_url, api_key=api_key, token_size=MAX_TOKENS)

    typer.secho("[SYSTEM] : Готов к диалогу! Введите 'quit' или 'Выход' для завершения.", fg=COLORS.WARNING)

    while True:
        try:
            user_input = typer.prompt("[User] ")
        except typer.Abort:
            break

        if user_input.strip().lower() in ("quit", "выход"):
            typer.secho("[SYSTEM] : До свидания!", fg=COLORS.INFO)
            break

        try:
            response = chat_instance.send_message(user_input)
            typer.secho(f"[AI agent] : {response}", fg=COLORS.SUCCESS)
            chat_instance.save_dialog_history()

        except Exception as e:
            typer.secho(f"Нет[SYSTEM] : Ошибка в диалоге: {e}", fg=COLORS.ERROR)
            continue


if __name__ == '__main__':
    # base_url, api_key = load_secrets()
    chat_instance = Chat(base_url='base_url', api_key='ollama', token_size=MAX_TOKENS)

    chat_instance.history = [
        Message(
            index=1,
            role="user",
            response="test 1",
        ),
        Message(
            index=2,
            role="assistant",
            response="test 2",
        ),
        Message(
            index=3,
            role="user",
            response="test 3",
        ),
        Message(
            index=4,
            role="assistant",
            response="test 4",
        ),
    ]

    try:
        chat_instance.save_dialog_history()

    except Exception as e:
        print(e)

