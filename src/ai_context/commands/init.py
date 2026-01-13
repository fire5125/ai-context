import json
import typer
from loguru import logger

from src.ai_context.commands.compress import compress
from src.ai_context.commands.read_context import export_context_to_file
from src.ai_context.commands.index import index


def ensure_gitignore_ignores_ai_context():
    """Добавляет .ai-context/ в .gitignore, если ещё не добавлен."""

    try:
        gitignore_text = "\n# Ignore ai-context data\n.ai-context/\n"
        if GITIGNORE.exists():
            content = GITIGNORE.read_text(encoding="utf-8")
            if ".ai-context/" not in content:
                with GITIGNORE.open("a", encoding="utf-8") as f:
                    f.write(gitignore_text)

                logger.success(f" - Добавлено '.ai-context/' в .gitignore")

            else:
                logger.warning(f" - .ai-context/' уже в .gitignore")

        else:
            # Создаём .gitignore, если его нет
            GITIGNORE.write_text(gitignore_text, encoding="utf-8")
            logger.success(f" - Создан .gitignore с '.ai-context/'")

    except Exception as err:
        logger.error(f" - При создании строки '.ai-context/' в .gitignore у нас ошибка: {err}")
        raise


def create_secrets_file():
    """Создает secrets.json, если его нет."""

    try:
        SECRETS_FILE.write_text(
            json.dumps(
                {
                    "openai_api_key": "your-key-here",
                    "ollama_base_url": "http://localhost:11434/v1"
                },
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )
        logger.success(f" - Создан secrets.json (не коммить в Git!)")

    except Exception as err:
        logger.error(f" - При создании secrets.json у нас ошибка: {err}")
        raise


def create_dialog_file():
    """Создает dialog.json, если его нет."""

    try:
        DIALOG_FILE.write_text("[]", encoding="utf-8")
        logger.success(f" - Создан dialog.json")

    except Exception as err:
        logger.error(f" - При создании dialog.json у нас ошибка: {err}")
        raise


def create_prompt_file():
    """Создает system-prompt.txt, если его нет."""

    try:
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        logger.success(f" - Создан prompt.txt")

    except Exception as err:
        logger.error(f" - При создании system-prompt.txt у нас ошибка: {err}")
        raise


def create_ai_context_ignore() -> None:
    """Создает .ai-ignore, если его нет."""

    try:
        ignore_text = INIT_AI_IGNORE_TEXT
        AI_IGNORE.write_text(ignore_text, encoding="utf-8")
        logger.success(f" - Создан .ai-ignore")

    except Exception as err:
        logger.error(f" - При инициализации .ai-ignore у нас ошибка: {err}")
        raise


def init(
        no_context: bool = typer.Option(False, "--no_context", "-nc", help="Не создавать файл контекста"),
        no_resume: bool = typer.Option(False, "--no_resume", "-nr", help="Не создавать файл резюие")
) -> None:
    """Команда: ai-context init - Инициализирует ai-context в текущей директории."""
    try:
        if AI_CONTEXT_DIR.exists():
            logger.info(f" - Папка .ai-context уже существует")
            raise typer.Exit(code=1)

        AI_CONTEXT_DIR.mkdir()
        logger.info(f" - Создана папка .ai-context")

        ensure_gitignore_ignores_ai_context()
        create_secrets_file()
        create_dialog_file()
        create_prompt_file()
        create_ai_context_ignore()

        logger.info(f" - Запуск автоматической индексации проекта...")
        index()  # ← внутри index() уже создаются и контекст, и резюме в БД

        # Экспортируем полный контекст
        if not no_context:
            export_context_to_file(Path('./out_context.txt'))

        # Экспортируем резюме
        if not no_resume:
            compress(Path('./out_resume.txt'))

        logger.info(f" - ai-context успешно инициализирован!")
        for line in INIT_FINISH_ALL_COMMANDS:
            logger.info(line)

    except Exception as err:
        logger.exception(f" - При инициализации ai-context у нас ошибка!\n{err}")
        raise