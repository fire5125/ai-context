import sys
import os
import time
import sqlite3
import typer
import subprocess
from pathlib import Path
from loguru import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.ai_context.commands.index import load_ai_ignore, should_index
from src.ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    CONTEXT_FILE,
    STOP_FLAG_FILE,
)

# Внутренний флаг — чтобы отличать внутренний запуск
_INTERNAL_FLAG = "--run"


class ContextUpdater(FileSystemEventHandler):
    """
    Обработчик изменений файловой системы для автоматического обновления контекста проекта.

    Следит за событиями создания, изменения и удаления файлов в рабочей директории.
    При изменении файла:
      - проверяет, должен ли он входить в контекст (по правилам .ai-ignore, размеру, бинарности),
      - обновляет или удаляет запись в SQLite-базе context.db,
      - повторно генерирует текстовый файл context.txt для совместимости с отладочными инструментами.

    Игнорирует все изменения внутри папки .ai-context/, чтобы избежать рекурсивных событий.
    """

    def __init__(self):
        self.ai_ignore = load_ai_ignore()
        logger.info(" - Наблюдение за изменениями запущено...")

    def on_any_event(self, event) -> None:
        """
        Обрабатывает все файловые события (создание, изменение, удаление) в рабочей директории.

        Метод:
          - игнорирует события внутри папки `.ai-context/`,
          - определяет относительный путь файла относительно корня проекта,
          - при удалении — удаляет запись из SQLite-базы,
          - при создании/изменении — проверяет, должен ли файл входить в контекст
            (по `.ai-ignore`, размеру, бинарности),
            → если да — обновляет запись в БД,
            → если нет — удаляет его из контекста (на случай, если он был ранее добавлен),
          - после любого изменения перезаписывает `context.txt` для совместимости с отладочными инструментами.

        Поддерживаемые типы событий: 'created', 'modified', 'deleted'.
        """
        if event.is_directory:
            return

        if event.event_type not in ("created", "modified", "deleted"):
            return

        src_path = Path(event.src_path).resolve()
        try:
            rel_path = src_path.relative_to(Path.cwd())
            rel_path_str = str(rel_path)
        except ValueError:
            return

        # Игнорируем всё внутри .ai-context/
        if rel_path_str.startswith(".ai-context" + os.sep) or rel_path_str == ".ai-context":
            return

        # Выводим файл, который изменился
        logger.debug(f" - Событие: {event.event_type} → {rel_path}")

        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()

        if event.event_type == "deleted":
            cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
            logger.warning(f" - Удалён из контекста: {rel_path}")
        else:
            if should_index(src_path, self.ai_ignore):
                try:
                    content = src_path.read_text(encoding="utf-8", errors="replace")
                    cur.execute(
                        "INSERT OR REPLACE INTO files (filepath, content) VALUES (?, ?)",
                        (rel_path_str, content),
                    )
                    logger.success(f" - Обновлён в контексте: {rel_path}")
                except Exception as e:
                    logger.warning(f" - Ошибка чтения {rel_path}: {e}")
            else:
                cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
                logger.info(f" - Исключён из контекста: {rel_path}")

        conn.commit()
        conn.close()
        self.export_context_to_file()

    @staticmethod
    def export_context_to_file():
        """
        Экспортирует текущий контекст из SQLite-базы в текстовый файл context.txt.

        Собирает содержимое всех проиндексированных файлов из таблицы `files`,
        объединяет их в единый документ с разделителями вида:
            === file: <путь> ===
            <содержимое>
        и записывает результат в `.ai-context/context.txt`.

        Используется для отладки, внешних инструментов или резервного просмотра контекста.
        """

        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()
        cur.execute("SELECT filepath, content FROM files ORDER BY filepath")
        rows = cur.fetchall()
        conn.close()

        lines = []
        for filepath, content in rows:
            lines.append(f"### FILE: {filepath} ###\n")
            lines.append(content)
            lines.append("\n" + "=" * 60 + "\n")

        CONTEXT_FILE.write_text("".join(lines), encoding="utf-8")


def start_observer():
    """Запускает наблюдатель в отдельном терминале."""

    if not AI_CONTEXT_DIR.exists():
        logger.error(" - Папка .ai-context не найдена. Выполните 'ai-context init'.")
        raise typer.Exit(1)

    if not CONTEXT_DB.exists():
        logger.error(" - База данных не найдена. Выполните 'ai-context index'.")
        raise typer.Exit(1)

    # Сохраняем PID
    pid = str(os.getpid())
    STOP_FLAG_FILE.write_text(pid, encoding="utf-8")
    logger.info(f" - PID процесса сохранён: {pid}")

    event_handler = ContextUpdater()
    observer = Observer()
    observer.schedule(event_handler, Path.cwd(), recursive=True)
    observer.start()

    logger.success(" - Режим наблюдения активен. Закройте окно для остановки.")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n - Получен сигнал завершения...")

    finally:
        observer.stop()
        observer.join()
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def stop_daemon():
    """Останавливает демон."""
    if not STOP_FLAG_FILE.exists():
        logger.info(" - Демон не запущен.")
        return

    try:
        pid = int(STOP_FLAG_FILE.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            os.system(f"taskkill /F /PID {pid} >nul 2>&1")
        else:
            os.kill(pid, 9)
        STOP_FLAG_FILE.unlink()
        logger.success(" - Демон остановлен.")

    except Exception as e:
        logger.error(f" - Не удалось остановить демон: {e}")
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def watchdog(
        stop: bool = typer.Option(False, "--stop", "-s", help="Остановить демон"),
        run_watchdog: bool = typer.Option(False, "--run", "-r", help="Запустить в терминале"),
):
    """Команда: ai-context watchdog [--stop|-s] - Запуск службы (демона) для отслеживания файлов и обновления контекста"""
    if stop:
        stop_daemon()
        return

    # Уже внутри наблюдателя — запускаем логику
    if run_watchdog:
        start_observer()
        return

    # Запускаем в новом окне терминала
    cmd = [sys.executable, "-m", "ai_context.cli", "watchdog", _INTERNAL_FLAG]

    try:
        if os.name == "nt":
            # Windows: открываем новое окно cmd, которое НЕ закрывается (/k)
            subprocess.Popen(
                ["cmd", "/k"] + cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=False
            )
        else:
            # Unix: можно использовать xterm, gnome-terminal, или просто фон
            # Для простоты — запускаем в фоне, но оставляем вывод
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=None,  # чтобы видеть вывод
                stderr=None,
            )
        logger.success(" - Watchdog запущен в новом окне терминала.")

    except Exception as e:
        logger.error(f" - Не удалось запустить watchdog: {e}")
        raise typer.Exit(1)
