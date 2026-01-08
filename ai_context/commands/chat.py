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

        for msg in reversed(self.history):
            msg_tokens = msg.tokens or self.count_tokens(f"{msg.role}: {msg.response}", AI_MODEL)
            if total_tokens + msg_tokens > self.token_size:
                break
            selected_messages.insert(0, {"role": msg.role, "content": msg.response})
            total_tokens += msg_tokens

        return selected_messages

    def _send_and_expect_confirmation(self, role: str, content: str, step_name: str) -> bool:
        """
        Внутренний вспомогательный метод для отправки сообщения и ожидания ответа 'Да' или 'Yes'.
        """
        user_message = Message(
            index=self._next_index,
            role=role,
            response=content
        )
        user_message.tokens = self.count_tokens(
            f"{user_message.role}: {user_message.response}", AI_MODEL
        )
        self.history.append(user_message)
        self._next_index += 1

        messages_to_send = self.prepare_history()
        max_tokens_for_response = self.token_size - sum(
            self.count_tokens(f"{m['role']}: {m['content']}", AI_MODEL) for m in messages_to_send
        ) - 100

        try:
            # noinspection PyTypeChecker
            response = self.client.chat.completions.create(
                model=AI_MODEL,
                messages=messages_to_send,
                temperature=0.1,  # детерминированный ответ
                max_tokens=max_tokens_for_response,
                stream=False,
            )
            assistant_reasoning = getattr(response.choices[0].message, 'reasoning', None)
            assistant_response = (response.choices[0].message.content or "").strip()
            if not assistant_reasoning:
                assistant_reasoning = '...'
            typer.secho(f"[{step_name}] Размышление модели: {repr(assistant_reasoning)}", fg=COLORS.DEBUG)
            typer.secho(f"[{step_name}] Ответ модели: {repr(assistant_response)}", fg=COLORS.SUCCESS)

            # Приводим к нижнему регистру и убираем пунктуацию
            clean_response = assistant_response.lower().strip(" .,!?")
            is_affirmative = clean_response in ("да", "yes", "ok", "okay", "понял", "got it")

            assistant_message = Message(
                index=self._next_index,
                role="assistant",
                response=assistant_response,
                reasoning=getattr(response.choices[0].message, 'reasoning', None)
            )
            assistant_message.tokens = self.count_tokens(
                f"{assistant_message.role}: {assistant_message.response}", AI_MODEL
            )
            self.history.append(assistant_message)
            self._next_index += 1

            return is_affirmative

        except Exception as e:
            typer.secho(f"[{step_name}] Ошибка при вызове ИИ: {e}", fg=COLORS.ERROR)
            raise

    def step_1_send_prompt(self) -> bool:
        """Шаг 1: отправка системного промпта. Ожидается подтверждение «Да»."""
        prompt = self.load_system_prompt()
        return self._send_and_expect_confirmation(
            role="system",
            content=f"Системный промпт:\n\n{prompt}\n\n"
                    f"Ты все точно понял?"
                    f"Дай ответ только \"Да\" или \"Нет\"",
            step_name="STEP 1"
        )

    def step_2_send_summary(self) -> bool:
        """Шаг 2: отправка резюме проекта. Ожидается подтверждение «Да»."""
        summary = self.load_resume_from_db()
        return self._send_and_expect_confirmation(
            role="system",
            content=f"Резюме проекта:\n\n{summary}\n\n"
                    f"Ты понял структуру?"
                    f"Дай ответ только \"Да\" или \"Нет\"",
            step_name="STEP 2"
        )

    def step_3_send_context(self) -> bool:
        """Шаг 3: отправка полного контекста. Ожидается подтверждение «Да»."""
        context = self.load_context_from_db()
        return self._send_and_expect_confirmation(
            role="system",
            content=f"Полный контекст проекта:\n\n{context}\n\n"
                    f"Ты понял о чем проект?"
                    f"Дай ответ \"Да\" или \"Нет\" и краткое описание проекта, как ты его понял",
            step_name="STEP 3"
        )

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
                stream=False,
            )
            assistant_response = response.choices[0].message.content or ""
            assistant_reasoning = getattr(response.choices[0].message, 'reasoning', None)
            if assistant_reasoning:
                typer.secho(f"[DEBUG] : {assistant_reasoning}", fg=COLORS.DEBUG)

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
        Сохраняет историю в формате JSON в DIALOG_FILE.
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

    typer.secho("[SYSTEM] : Начинаю подготовку модели (3 шага)...", fg=COLORS.INFO)

    # Шаг 1: системный промпт
    typer.secho("[SYSTEM] : Шаг 1 — отправка системного промпта...", fg=COLORS.INFO)
    if not chat_instance.step_1_send_prompt():
        typer.secho("[SYSTEM] : Модель не подтвердила понимание промпта.", fg=COLORS.WARNING)

    # Шаг 2: резюме
    typer.secho("[SYSTEM] : Шаг 2 — отправка резюме проекта...", fg=COLORS.INFO)
    if not chat_instance.step_2_send_summary():
        typer.secho("[SYSTEM] : Модель не подтвердила понимание резюме.", fg=COLORS.WARNING)

    # Шаг 3: полный контекст
    # typer.secho("[SYSTEM] : Шаг 3 — отправка полного контекста...", fg=COLORS.INFO)
    # if not chat_instance.step_3_send_context():
    #     typer.secho("[SYSTEM] : Модель не подтвердила понимание контекста.", fg=COLORS.WARNING)

    chat_instance.save_dialog_history()
    typer.secho("[SYSTEM] : Подготовка завершена. Готов к диалогу! Введите 'quit' или 'Выход' для завершения.",
                fg=COLORS.WARNING)

    while True:
        try:
            user_input = typer.prompt("[User] ")
        except typer.Abort:
            break

        if user_input.strip().lower() in ("quit", "выход"):
            typer.secho("[SYSTEM] : До свидания!", fg=COLORS.INFO)
            chat_instance.save_dialog_history()
            break

        try:
            response = chat_instance.send_message(user_input)
            typer.secho(f"[AI agent] : {response}", fg=COLORS.SUCCESS)
            chat_instance.save_dialog_history()

        except Exception as e:
            typer.secho(f"[SYSTEM] : Ошибка в диалоге: {e}", fg=COLORS.ERROR)
            continue
