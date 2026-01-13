import os
import typer
import subprocess
from loguru import logger

from src.ai_context.source.settings import PROMPT_FILE


def edit_prompt():
    """Команда: ai-context edit_prompt - Открывает system-prompt.txt для редактирования."""

    if not PROMPT_FILE.exists():
        logger.error(f" - system-prompt.txt не найден. "
                    f"Запустите 'ai-context init'")
        raise typer.Exit(code=1)

    default_editor = os.path.join(os.path.expanduser("~"), r"AppData\Local\Programs\Microsoft VS Code\Code.exe")
    editor = os.environ.get("EDITOR", default_editor)

    try:
        subprocess.run([editor, str(PROMPT_FILE)], check=True)
        logger.success(f" - Промпт обновлён")

    except FileNotFoundError:
        logger.error(f" - Редактор '{editor}' не найден. "
                    f"Установите его или задайте переменную EDITOR")
        raise typer.Exit(code=1)

    except subprocess.CalledProcessError:
        logger.warning(f" - Редактирование прервано")

