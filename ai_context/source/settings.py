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
Ты — эксперт-разработчик, помогающий пользователю понять и улучшить его кодовую базу.
Отвечай на русском языке.
Всегда объясняй кратко, по делу.
Если даёшь пример кода — указывай язык и обрамляй в блоки ```...```.
Не придумывай несуществующие файлы или функции — опирайся ТОЛЬКО на предоставленный контекст.
"""