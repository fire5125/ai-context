import typer
import sqlite3
from loguru import logger
from pathlib import Path
from pathspec import PathSpec

from src.ai_context.source.settings import CONTEXT_DB, AI_IGNORE, AI_CONTEXT_DIR


def load_ai_ignore() -> PathSpec:
    """Загружает правила игнорирования из .ai-context/.ai-ignore."""

    if AI_IGNORE.exists():
        with AI_IGNORE.open(encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return PathSpec.from_lines('gitwildmatch', lines)
    else:
        AI_IGNORE.write_text("# Add file/folder patterns to ignore (like .gitignore)\n", encoding="utf-8")
        logger.debug(f" - Создан .ai-context/.ai-ignore")
        return PathSpec.from_lines('gitwildmatch', [])


def is_binary(path: Path) -> bool:
    """Проверка файла (он бинарный?)"""

    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
            return b'\0' in chunk
    except Exception:
        return True


def should_index(path: Path, ai_ignore: PathSpec) -> bool:
    """Определяет, должен ли файл быть включён в контекст по правилам .ai-ignore, размеру и бинарности."""
    if not path.is_file():
        return False
    try:
        rel_path = path.relative_to(Path.cwd())
    except ValueError:
        return False
    if ai_ignore.match_file(str(rel_path)):
        return False
    if is_binary(path):
        return False
    if path.stat().st_size > 1_000_000:
        return False
    return True


def write_to_sqlite(indexed_files):
    """Сохраняет список файлов (rel_path, content) в SQLite БД."""

    CONTEXT_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            filepath TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    data = [(str(rel_path), content) for rel_path, content in indexed_files]
    cur.executemany("""
        INSERT OR REPLACE INTO files (filepath, content)
        VALUES (?, ?)
    """, data)
    conn.commit()
    conn.close()
    logger.success(f" - Контекст сохранён в {CONTEXT_DB}")


def update_summary_cache():
    """Обновляет кэш резюме в project_summary на основе текущих данных в files."""

    from .compress import extract_summaries_from_db
    import sqlite3
    from src.ai_context.source.settings import CONTEXT_DB

    logger.info(" - Обновление кэша резюме...")
    summaries = extract_summaries_from_db()
    header = (
        "РЕЗЮМЕ КОНТЕКСТА ПРОЕКТА (только сигнатуры и докстринги)\n"
        + "=" * 80 + "\n"
    )
    full_summary = header + "\n".join(summaries) + "\n"

    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_summary (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            summary_text TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO project_summary (id, summary_text)
        VALUES (1, ?)
    """, (full_summary,))
    conn.commit()
    conn.close()
    logger.success(" - Резюме сохранено в БД")


def index():
    """Команда: ai-context index - Метод индексации файлов проекта"""

    if not AI_CONTEXT_DIR.exists():
        logger.error(f" - При инициализации ai-context у нас ошибка!")
        raise typer.Exit(1)

    ai_ignore = load_ai_ignore()
    indexed_files = []

    logger.info(f" - Сканирование проекта...")
    for path in Path.cwd().rglob("*"):
        if should_index(path, ai_ignore):
            rel_path = path.relative_to(Path.cwd())
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                indexed_files.append((rel_path, content))
            except Exception as e:
                logger.warning(f"- Не удалось прочитать {rel_path}: {e}")

    write_to_sqlite(indexed_files)
    update_summary_cache()