from typer import colors


class COLORS:
    SUCCESS = colors.GREEN
    INFO = colors.WHITE
    DEBUG = colors.BRIGHT_BLUE
    WARNING = colors.YELLOW
    ERROR = colors.BRIGHT_RED


INIT_FINISH_ALL_COMMANDS = [
    "\nДля дальнейшей работы используй следующие команды:",
    " >>> ai-context edit-prompt - Открывает system-prompt.txt для редактирования (откроется в стандартном тесктовом редакторе)",
    " >>> ai-context index - Метод индексации файлов проекта. Вызывайте его для повтороной ручной индексации (не создает файл ./out_context.txt)",
    " >>> ai-context read ./output.txt — воссоздаёт в output.txt контекст из SQLite БД",
    " >>> ai-context ai-context watchdog [--stop|-s] - Запуск службы (демона) для отслеживания файлов и обновления контекста",
    " >>> ai-context ai-context chat — простой интерактивный чат с ИИ",
    " >>> ai-context ai-context compress [--output ./out_resume.txt] Экспортирует уже сгенерированное резюме проекта из БД в файл",
]

INIT_AI_IGNORE_TEXT = """
.gitignore
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
build/
sdist/
dist/
MANIFEST
pyproject.toml
out.md
*.log
*.txt
*.py~
*.egg
*.egg-info/
*.py~
.env
.envrc
.venv
"""

