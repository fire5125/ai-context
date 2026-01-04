import json
import typer

from .read_context import export_context_to_file
from ai_context.source.settings import *
from ai_context.source.messages import *
from .index import index_to_text_and_db


def ensure_gitignore_ignores_ai_context():
    """Добавляет .ai-context/ в .gitignore, если ещё не добавлен."""

    try:
        gitignore_text = "\n# Ignore ai-context data\n.ai-context/\n"
        if GITIGNORE.exists():
            content = GITIGNORE.read_text(encoding="utf-8")
            if ".ai-context/" not in content:
                with GITIGNORE.open("a", encoding="utf-8") as f:
                    f.write(gitignore_text)

                typer.secho(f" - Добавлено '.ai-context/' в .gitignore", fg=COLORS.SUCCESS)

            else:
                typer.secho(f" - .ai-context/' уже в .gitignore", fg=COLORS.WARNING)

        else:
            # Создаём .gitignore, если его нет
            GITIGNORE.write_text(gitignore_text, encoding="utf-8")
            typer.secho(f" - Создан .gitignore с '.ai-context/'", fg=COLORS.SUCCESS)

    except Exception as err:
        typer.secho(f" - При создании строки '.ai-context/' в .gitignore у нас ошибка!\n"
                    f"{err.__str__()}", fg=COLORS.ERROR)
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
        typer.secho(f" - Создан secrets.json (не коммить в Git!)", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - При создании secrets.json у нас ошибка!\n"
                    f"{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_dialog_file():
    """Создает dialog.json, если его нет."""

    try:
        DIALOG_FILE.write_text("[]", encoding="utf-8")
        typer.secho(f" - Создан dialog.json", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - При создании dialog.json у нас ошибка!\n"
                    f"{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_prompt_file():
    """Создает system-prompt.txt, если его нет."""

    try:
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        typer.secho(f" - Создан prompt.txt", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - При создании system-prompt.txt у нас ошибка!\n"
                    f"{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_ai_context_ignore() -> None:
    """Создает .ai-ignore, если его нет."""

    try:
        ignore_text = """.gitignore
.env
.envrc
.venv
__pycache__/
env/
venv/
ENV/
env.bak/
venv.bak/
/.idea/
/.gigaide/
.git/*
.ai-context/
*.log
build/
sdist/
dist/
*.egg
MANIFEST
pyproject.toml
*.txt
*.py~
        """
        AI_IGNORE.write_text(ignore_text, encoding="utf-8")
        typer.secho(f" - Создан .ai-ignore", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - При инициализации .ai-ignore у нас ошибка!\n"
                    f"{err.__str__()}", fg=COLORS.ERROR)
        raise


def init() -> None:
    """Инициализирует ai-context в текущей директории."""

    try:
        if AI_CONTEXT_DIR.exists():
            typer.secho(f" - Папка .ai-context уже существует", fg=COLORS.WARNING)
            raise typer.Exit(code=1)

        # Создаём папку
        AI_CONTEXT_DIR.mkdir()
        typer.secho(f" - Создана папка .ai-context", fg=COLORS.SUCCESS)

        # Добавляем в .gitignore
        ensure_gitignore_ignores_ai_context()

        # Создаём файлы
        create_secrets_file()
        create_dialog_file()
        create_prompt_file()
        create_ai_context_ignore()

        # Автоматическая индексация после init
        typer.secho(f" - Запуск автоматической индексации проекта...", fg=COLORS.INFO)
        index_to_text_and_db()

        # Экспортируем контекст в файл
        export_context_to_file(Path('./out.txt'))

        typer.secho(f" - ai-context успешно инициализирован!", fg=COLORS.SUCCESS)
        typer.secho(f" - Созданы файлы", fg=COLORS.SUCCESS)
        for line in INIT_FINISH_ALL_COMMANDS:
            typer.echo(line)

    except Exception as err:
        typer.secho(f" - При инициализации ai-context у нас ошибка!\n{err.__str__()}", fg=COLORS.ERROR)