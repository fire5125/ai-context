import typer
import os
import subprocess
from .source.settings import PROMPT_FILE
from .source.messages import *


def edit_prompt():
    """Открывает system-prompt.txt для редактирования."""

    if not PROMPT_FILE.exists():
        typer.secho(f" - system-prompt.txt не найден. "
                    f"Запустите 'ai-context init'", fg=COLORS.ERROR)
        raise typer.Exit(code=1)

    default_editor = os.path.join(os.path.expanduser("~"), r"AppData\Local\Programs\Microsoft VS Code\Code.exe")
    editor = os.environ.get("EDITOR", default_editor)

    try:
        subprocess.run([editor, str(PROMPT_FILE)], check=True)
        typer.secho(f" - Промпт обновлён", fg=COLORS.SUCCESS)

    except FileNotFoundError:
        typer.secho(f" - Редактор '{editor}' не найден. "
                    f"Установите его или задайте переменную EDITOR", fg=COLORS.WARNING)
        raise typer.Exit(code=1)

    except subprocess.CalledProcessError:
        typer.secho(f" - Редактирование прервано", fg=COLORS.WARNING)

