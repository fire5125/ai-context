import json
import typer
from .source.settings import *
from .source.messages import *


def ensure_gitignore_ignores_ai_context():
    """Добавляет .ai-context/ в .gitignore, если ещё не добавлен."""

    try:
        gitignore_text = "\n# Ignore ai-context data\n.ai-context/\n"
        if GITIGNORE.exists():
            content = GITIGNORE.read_text(encoding="utf-8")
            if ".ai-context/" not in content:
                with GITIGNORE.open("a", encoding="utf-8") as f:
                    f.write(gitignore_text)

                typer.secho(f" - {ICONS.success} {GITIGNORE_SUCCESS}", fg=COLORS.SUCCESS)

            else:
                typer.secho(f" - {ICONS.info} {GITIGNORE_WARNING}", fg=COLORS.WARNING)

        else:
            # Создаём .gitignore, если его нет
            GITIGNORE.write_text(gitignore_text, encoding="utf-8")
            typer.secho(f" - {ICONS.success} {GITIGNORE_CREATE}", fg=COLORS.SUCCESS)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {GITIGNORE_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)
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
        typer.secho(f" - {ICONS.key} {SECRET_SUCCESS}", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {SECRET_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_dialog_file():
    """Создает dialog.json, если его нет."""

    try:
        DIALOG_FILE.write_text("[]", encoding="utf-8")
        typer.secho(f" - {ICONS.chat} {DIALOG_SUCCESS}", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {DIALOG_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_prompt_file():
    """Создает system-prompt.txt, если его нет."""
    try:
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        typer.secho(f" - {ICONS.file} {PROMPT_SUCCESS}", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {PROMPT_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)
        raise


def create_ai_context_ignore():
    """Создает system-prompt.txt, если его нет."""
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
        """
        AI_IGNORE.write_text(ignore_text, encoding="utf-8")
        typer.secho(f" - {ICONS.file} {AI_IGNORE_SUCCESS}", fg=COLORS.INFO)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {AI_IGNORE_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)
        raise



def init():
    """Инициализирует ai-context в текущей директории."""

    try:
        if AI_CONTEXT_DIR.exists():
            typer.secho(f" - {ICONS.warning} {INIT_CREATE_WARNING}", fg=COLORS.WARNING)
            raise typer.Exit(code=1)

        # Создаём папку
        AI_CONTEXT_DIR.mkdir()
        typer.secho(f" - {ICONS.folder} {INIT_CREATE_DIR}", fg=COLORS.SUCCESS)

        # Добавляем в .gitignore
        ensure_gitignore_ignores_ai_context()

        # Создаём файлы
        create_secrets_file()
        create_dialog_file()
        create_prompt_file()
        create_ai_context_ignore()

        typer.secho(f" - {ICONS.ai} {INIT_SUCCESS}", fg=COLORS.SUCCESS)
        typer.secho(f" - {ICONS.success} {INIT_INFO}", fg=COLORS.SUCCESS)
        for line in INIT_FINISH_ALL_COMMANDS:
            typer.echo(line)

    except Exception as err:
        typer.secho(f" - {ICONS.error} {INIT_ERROR}\n{err.__str__()}", fg=COLORS.ERROR)