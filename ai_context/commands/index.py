import typer
import sqlite3
from pathlib import Path
from pathspec import PathSpec
from .source.messages import COLORS
from .source.settings import CONTEXT_DB, AI_IGNORE, AI_CONTEXT_DIR

def load_ai_ignore() -> PathSpec:
    """Загружает правила игнорирования из .ai-context/.ai-ignore."""
    if AI_IGNORE.exists():
        with AI_IGNORE.open(encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return PathSpec.from_lines('gitwildmatch', lines)
    else:
        AI_IGNORE.write_text("# Add file/folder patterns to ignore (like .gitignore)\n", encoding="utf-8")
        typer.secho(f" - Создан .ai-context/.ai-ignore", fg=typer.colors.BLUE)
        return PathSpec.from_lines('gitwildmatch', [])

def is_binary(path: Path) -> bool:
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
        return b'\0' in chunk
    except Exception:
        return True

def should_index(path: Path, ai_ignore: PathSpec) -> bool:
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

# def write_to_text_file(context_lines):
#     CONTEXT_FILE.write_text("".join(context_lines), encoding="utf-8")
#     typer.secho(f" - Контекст сохранён в {CONTEXT_FILE}", fg=COLORS.SUCCESS)
#     typer.secho(f" - Найдено ~{len(context_lines) // 4} файлов", fg=COLORS.INFO)

def write_to_sqlite(indexed_files):
    """Сохраняет список файлов (rel_path, content) в SQLite БД."""
    CONTEXT_DB.parent.mkdir(exist_ok=True)  # убедимся, что .ai-context существует
    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            filepath TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Подготовка данных
    data = [(str(rel_path), content) for rel_path, content in indexed_files]
    cur.executemany("""
        INSERT OR REPLACE INTO files (filepath, content)
        VALUES (?, ?)
    """, data)
    conn.commit()
    conn.close()
    typer.secho(f" - Контекст сохранён в {CONTEXT_DB}", fg=COLORS.SUCCESS)

def index_to_text_and_db():
    if not AI_CONTEXT_DIR.exists():
        typer.secho(f" - При инициализации ai-context у нас ошибка!", fg=COLORS.ERROR)
        raise typer.Exit(1)

    ai_ignore = load_ai_ignore()
    context_lines = []
    indexed_files = []  # для SQLite: [(rel_path, content), ...]

    typer.secho(f" - Сканирование проекта...", fg=COLORS.INFO)

    for path in Path.cwd().rglob("*"):
        if should_index(path, ai_ignore):
            rel_path = path.relative_to(Path.cwd())
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                # Для текстового файла
                context_lines.append(f"### FILE: {rel_path} ###\n")
                context_lines.append(content)
                context_lines.append("\n" + "="*60 + "\n")
                # Для SQLite
                indexed_files.append((rel_path, content))
            except Exception as e:
                typer.secho(f"- Не удалось прочитать {rel_path}: {e}", fg=COLORS.WARNING)

    # Сохраняем в оба формата
    # write_to_text_file(context_lines)
    write_to_sqlite(indexed_files)

def index():
    """Команда: ai-context index"""
    index_to_text_and_db()