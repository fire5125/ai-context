from typer import colors


class ICONS:
    error = " ❌ "
    warning = " ⚠️ "
    debug = " ⚠️ "
    info = " ℹ️ "
    success = " ✅ "
    folder = " 📁 "
    file = " 📝 "
    key = " 🔑 "
    chat = " 💬 "
    ai = " ✨ "


class COLORS:
    SUCCESS = colors.GREEN
    INFO = colors.WHITE
    DEBUG = colors.BRIGHT_BLUE
    WARNING = colors.YELLOW
    ERROR = colors.BRIGHT_RED

INDEX_FINISH = "Контекст сохранён в {context_file}"
INDEX_SUMMARY = "Найдено {context_lines} файлов (примерно)"
INDEX_FILE_ERROR = "Не удалось прочитать {rel_path}"
INDEX_SCAN = "Сканирование проекта..."
INDEX_INIT_ERROR = "Папка .ai-context не найдена. Запустите 'ai-context init' сначала."

GITIGNORE_SUCCESS = "Добавлено '.ai-context/' в .gitignore"
GITIGNORE_WARNING = ".ai-context/' уже в .gitignore"
GITIGNORE_CREATE = "Создан .gitignore с '.ai-context/'"
GITIGNORE_ERROR = "При создании строки '.ai-context/' в .gitignore у нас ошибка!"

SECRET_SUCCESS = "Создан secrets.json (не коммить в Git!)"
SECRET_ERROR = "При создании secrets.json у нас ошибка!"

DIALOG_SUCCESS = "Создан dialog.json"
DIALOG_ERROR = "При создании dialog.json у нас ошибка!"

PROMPT_SUCCESS = "Создан prompt.txt"
PROMPT_ERROR = "При создании system-prompt.txt у нас ошибка!"

AI_IGNORE_SUCCESS = "Создан .ai-ignore"
AI_IGNORE_ERROR = "При инициализации .ai-ignore у нас ошибка!"

INIT_SUCCESS = "ai-context успешно инициализирован!"
INIT_CREATE_DIR = "Создана папка .ai-context"
INIT_CREATE_WARNING = "Папка .ai-context уже существует"
INIT_INFO = "Созданы файлы: secrets.json, dialog.json, prompt.txt"
INIT_ERROR = "При инициализации ai-context у нас ошибка!"

INIT_FINISH_ALL_COMMANDS = [
    " > Используй следующие команды:",
    " >>> 'ai-context edit-prompt' для редактирования промпта",
    " >>> 'ai-context chat' для общения с AI (в процессе разработки)",
    " >>> 'ai-context index' для сканирования проекта и добавления его в контекст",
    " >>> 'ai-context read-context ./output.txt' для записи контекста в файл",
    " >>> 'ai-context watchdog' для отслеживания изменений в проекте",
]

EDIT_PROMPT_SUCCESS = "Промпт обновлён"
EDIT_PROMPT_ERR_EDITOR = "Редактор '{editor}' не найден. Установите его или задайте переменную EDITOR"
EDIT_PROMPT_ERR_FILE = "system-prompt.txt не найден. Запустите 'ai-context init'"
EDIT_PROMPT_WARNING = "Редактирование прервано"
