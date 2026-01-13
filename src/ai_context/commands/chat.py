import re
import json
import typer
import sqlite3
import tiktoken
from loguru import logger
from openai import APIConnectionError
from typing import List, Optional
from openai import OpenAI
from pydantic import BaseModel

from src.ai_context.commands.compress import load_summary_from_db
from src.ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    PROMPT_FILE,
    SECRETS_FILE,
    DIALOG_FILE,
    AI_MODEL,
    MAX_TOKENS,
)


def load_secrets():
    """
    Загружает секретные данные из файла secrets.json.
    """
    if not SECRETS_FILE.exists():
        logger.error(" - secrets.json не найден. Выполните 'ai-context init'.")
        raise typer.Exit(1)
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    return data["ollama_base_url"], data.get("openai_api_key", "ollama")


class Message(BaseModel):
    index: int
    role: str
    tokens: Optional[int] = None
    response: Optional[str] = None
    reasoning: Optional[str] = None


class Chat:
    def __init__(self, base_url: str, api_key: str, token_size: int = MAX_TOKENS):
        """Инициализирует клиент для взаимодействия с AI-сервисом.
        base_url: Базовый URL API-сервиса.
        api_key: API-ключ для аутентификации.
        token_size: Максимальное количество токенов в истории сообщений.
        """
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
            logger.error(" - Контекст не найден. Выполните 'ai-context index'.")
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
            logger.error(" - Промт не найден. Выполните 'ai-context init'.")
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

    def _send_and_expect_confirmation(self, system_content: str, step_name: str) -> bool:
        """
        Отправляет два сообщения:
          1. system: контекст (промпт, резюме или полный контекст)
          2. user: вопрос "Ты всё понял?"
        Ждёт ответ от assistant и проверяет его.
        """
        # 1. System message
        system_msg = Message(
            index=self._next_index,
            role="system",
            response=system_content
        )
        system_msg.tokens = self.count_tokens(f"system: {system_msg.response}", AI_MODEL)
        self.history.append(system_msg)
        self._next_index += 1

        # 2. User message
        user_question = "Ты всё понял? Ответь строго «Да» или «Нет»."
        user_msg = Message(
            index=self._next_index,
            role="user",
            response=user_question
        )
        user_msg.tokens = self.count_tokens(f"user: {user_msg.response}", AI_MODEL)
        self.history.append(user_msg)
        self._next_index += 1

        # Подготавливаем историю для отправки
        messages_to_send = self.prepare_history()
        max_tokens_for_response = self.token_size - sum(
            self.count_tokens(f"{m['role']}: {m['content']}", AI_MODEL) for m in messages_to_send
        ) - 100

        try:
            # noinspection PyTypeChecker
            response = self.client.chat.completions.create(
                model=AI_MODEL,
                messages=messages_to_send,
                temperature=0.1,
                max_tokens=max_tokens_for_response,
                stream=False,
            )
            assistant_response = (response.choices[0].message.content or "").strip()
            assistant_reasoning = getattr(response.choices[0].message, 'reasoning', None)

            logger.debug(f"[{step_name}] Размышление модели: {repr(assistant_reasoning)}")
            logger.success(f"[{step_name}] Ответ модели: {repr(assistant_response)}")

            clean_response = assistant_response.lower().strip(" .,!?")
            is_affirmative = clean_response in ("да", "yes", "ok", "okay", "понял", "got it")

            # 3. Assistant message
            assistant_msg = Message(
                index=self._next_index,
                role="assistant",
                response=assistant_response,
                reasoning=assistant_reasoning
            )
            assistant_msg.tokens = self.count_tokens(f"assistant: {assistant_msg.response}", AI_MODEL)
            self.history.append(assistant_msg)
            self._next_index += 1

            return is_affirmative

        except APIConnectionError:
            logger.error("[ОШИБКА] : Не удаётся подключиться к нейросети.")
            logger.error("Проверьте, запущена ли локальная модель или доступен ли удалённый API.")
            raise  # или вернуть заглушку, например: return "[Ошибка подключения к ИИ]"

        except Exception as e:
            logger.error(f"[{step_name}] Ошибка при вызове ИИ: {e}")
            raise

    @staticmethod
    def _extract_filenames_from_text(text: str) -> set[str]:
        """
        Извлекает потенциальные имена файлов из текста.
        Ищет слова, содержащие точку и допустимое расширение.
        """
        # Простой паттерн: любая последовательность символов с точкой и буквами/цифрами после
        candidates = re.findall(r'\b\w+\.\w{1,6}\b', text)
        return set(candidates)

    @staticmethod
    def _fetch_file_contexts_by_names(filenames: set[str]) -> str:
        """
        По множеству имён файлов ищет все соответствующие записи в БД и возвращает их контекст.
        """
        if not CONTEXT_DB.exists():
            return ""

        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()
        placeholders = ','.join('?' * len(filenames))
        query = f"SELECT filepath, content FROM files WHERE {' OR '.join([f'filepath LIKE ?' for _ in filenames])}"

        # Строим шаблоны: %/filename.ext
        patterns = [f"%/{name}" for name in filenames]
        cur.execute(query, patterns)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return ""

        parts = []
        for filepath, content in rows:
            parts.append(f"### FILE: {filepath} ###\n{content}\n{'-' * 60}")
        return "\n".join(parts)

    def step_1_send_prompt(self) -> bool:
        prompt = self.load_system_prompt()
        return self._send_and_expect_confirmation(
            system_content=f"Системный промпт:\n{prompt}",
            step_name="STEP 1"
        )

    def step_2_send_summary(self) -> bool:
        summary = self.load_resume_from_db()
        return self._send_and_expect_confirmation(
            system_content=f"Резюме проекта:\n{summary}",
            step_name="STEP 2"
        )

    def step_3_send_context(self) -> bool:
        context = self.load_context_from_db()
        return self._send_and_expect_confirmation(
            system_content=f"Полный контекст проекта:\n{context}",
            step_name="STEP 3"
        )

    def send_message(self, message_from_user: str) -> str:
        # Шаг 0: поиск упомянутых файлов
        mentioned_files = self._extract_filenames_from_text(message_from_user)
        if mentioned_files:
            file_context = self._fetch_file_contexts_by_names(mentioned_files)
            if file_context:
                # Вставляем system-сообщение с контекстом файлов
                file_msg = Message(
                    index=self._next_index,
                    role="system",
                    response=f"Контекст упомянутых файлов:\n{file_context}"
                )
                file_msg.tokens = self.count_tokens(f"system: {file_msg.response}", AI_MODEL)
                self.history.append(file_msg)
                self._next_index += 1

        # Теперь само сообщение пользователя
        user_message = Message(
            index=self._next_index,
            role="user",
            response=message_from_user
        )
        user_message.tokens = self.count_tokens(f"user: {user_message.response}", AI_MODEL)
        self.history.append(user_message)
        self._next_index += 1

        # Отправка
        messages_to_send = self.prepare_history()
        max_tokens_for_response = self.token_size - sum(
            self.count_tokens(f"{m['role']}: {m['content']}", AI_MODEL) for m in messages_to_send
        ) - 100

        if max_tokens_for_response <= 50:
            logger.warning("[SYSTEM] : Контекст почти заполнен — ответ может быть усечён.")

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
                logger.debug(f"[DEBUG] : {assistant_reasoning}")
        except Exception as e:
            logger.error(f"[ОШИБКА] : Ошибка при вызове ИИ: {e}")
            raise

        assistant_message = Message(
            index=self._next_index,
            role="assistant",
            response=assistant_response,
            reasoning=assistant_reasoning
        )
        assistant_message.tokens = self.count_tokens(f"assistant: {assistant_message.response}", AI_MODEL)
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


def chat():
    """Команда: ai-context chat — простой интерактивный чат с ИИ."""
    if not AI_CONTEXT_DIR.exists():
        logger.error("[SYSTEM] : Выполните 'ai-context init' сначала.")
        raise typer.Exit(1)

    base_url, api_key = load_secrets()
    chat_instance = Chat(base_url=base_url, api_key=api_key, token_size=MAX_TOKENS)

    logger.info("[SYSTEM] : Начинаю подготовку модели (3 шага)...")

    # Шаг 1: системный промпт
    logger.info("[SYSTEM] : Шаг 1 — отправка системного промпта...")
    if not chat_instance.step_1_send_prompt():
        logger.warning("[SYSTEM] : Модель не подтвердила понимание промпта.")

    # Шаг 2: резюме
    logger.info("[SYSTEM] : Шаг 2 — отправка резюме проекта...")
    if not chat_instance.step_2_send_summary():
        logger.warning("[SYSTEM] : Модель не подтвердила понимание резюме.")

    # Шаг 3: полный контекст
    logger.info("[SYSTEM] : Шаг 3 — отправка полного контекста...")
    if not chat_instance.step_3_send_context():
        logger.warning("[SYSTEM] : Модель не подтвердила понимание контекста.")

    chat_instance.save_dialog_history()
    logger.warning("[SYSTEM] : Подготовка завершена. Готов к диалогу! Введите 'quit' или 'Выход' для завершения.")

    while True:
        try:
            user_input = typer.prompt("[User] ")
        except typer.Abort:
            break

        if user_input.strip().lower() in ("quit", "выход"):
            logger.info("[SYSTEM] : До свидания!")
            chat_instance.save_dialog_history()
            break

        try:
            response = chat_instance.send_message(user_input)
            logger.success(f"[AI agent] : {response}")
            chat_instance.save_dialog_history()

        except Exception as e:
            logger.error(f"[SYSTEM] : Ошибка в диалоге: {e}")
            continue
