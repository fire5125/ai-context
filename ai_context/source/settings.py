from pathlib import Path

# Внутренний флаг для демона
DAEMON_INTERNAL_FLAG = "--no-daemon"

GITIGNORE = Path(".gitignore")
AI_CONTEXT_DIR = Path(".ai-context")
AI_IGNORE = AI_CONTEXT_DIR / ".ai-ignore"
CONTEXT_FILE = AI_CONTEXT_DIR / "context.txt"
CONTEXT_DB = AI_CONTEXT_DIR / "context.db"
SECRETS_FILE = AI_CONTEXT_DIR / "secrets.json"
PROMPT_FILE = AI_CONTEXT_DIR / "system-prompt.txt"
DIALOG_FILE = AI_CONTEXT_DIR / "dialog.json"
STOP_FLAG_FILE = AI_CONTEXT_DIR / ".watchdog.pid"

# AI_MODEL = "deepseek-coder:6.7b-instruct"
AI_MODEL = "qwen3:14b"
MAX_TOKENS = 32768

DEFAULT_PROMPT = """
Ты — эксперт по разработке и анализу кода. 
Пользователь предоставил тебе полный контекст текущего проекта через систему ai-context. 
Отвечай кратко, точно и без «воды». 
Не используй вводные фразы вроде «Как разработчик...» или «Вы можете...».

— Если запрошенная информация отсутствует в контексте — скажи: «Информация об этом не найдена в текущем контексте проекта».
— Не выдумывай файлы, функции или настройки, которых нет в предоставленных данных.
— Форматируй код с помощью markdown (например, ```python).
— Отвечай на том же языке, что и вопрос пользователя.
— Предполагай, что пользователь технически компетентен — не объясняй базовые вещи.
— Не предлагай решения, требующие доступа к интернету, внешним API или установки пакетов, если явно не попрошено.
— Не генерируй вредоносный, опасный или этически сомнительный код.
"""