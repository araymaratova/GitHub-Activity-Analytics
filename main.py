import sqlite3

import analysis
import db
import optimizer
import json_parser
import queries
import visualize
from config import DB_PATH, PARQUET_DIR

MENU = """
GitHub Activity Analytics
1 - Распарсить сырые данные (JSON -> CSV/Parquet)
2 - Замеры памяти и сравнение CSV/Parquet
3 - Построить базу данных SQLite
4 - Статистика по типам событий
5 - Топ-10 репозиториев и пользователей
6 - Языковые тренды (доли, ранги, покрытие)
7 - Сравнение подходов и SQL vs Pandas
8 - Построить графики
9 - Выполнить все 12 SQL-запросов
0 - Выход
"""


def require_db() -> bool:
    if not DB_PATH.exists():
        print("База данных не найдена. Сначала выполните пункт 3.")
        return False
    return True


def show_queries(names: list) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        for name in names:
            df = queries.run_query(conn, queries.QUERIES[name])
            print(f"\n--- {name} ---")
            print(df.head(15).to_string(index=False))
    finally:
        conn.close()


def action_parse() -> None:
    print(json_parser.process_all())


def action_optimize() -> None:
    if not PARQUET_DIR.exists():
        print("Нет Parquet-файлов. Сначала выполните пункт 1.")
        return
    optimizer.run_memory_report()
    optimizer.run_format_comparison()


def action_build_db() -> None:
    if not PARQUET_DIR.exists():
        print("Нет Parquet-файлов. Сначала выполните пункт 1.")
        return
    print(db.build_db())


def action_types() -> None:
    if require_db():
        show_queries(["q01_events_by_type", "q04_events_by_hour"])


def action_top() -> None:
    if require_db():
        show_queries(["q02_top_repos", "q03_top_users"])


def action_languages() -> None:
    if require_db():
        show_queries(["q07_language_rank_pr", "q09_language_share",
                      "q12_language_coverage"])


def action_compare() -> None:
    if require_db():
        analysis.run_comparison()
        analysis.run_sql_vs_pandas()


def action_plots() -> None:
    if require_db():
        print("Созданы графики:", visualize.make_all())


def action_all_queries() -> None:
    if require_db():
        queries.run_all()


ACTIONS = {
    "1": action_parse,
    "2": action_optimize,
    "3": action_build_db,
    "4": action_types,
    "5": action_top,
    "6": action_languages,
    "7": action_compare,
    "8": action_plots,
    "9": action_all_queries,
}


def main() -> None:
    while True:
        print(MENU)
        choice = input("Выберите пункт: ").strip()
        if choice == "0":
            print("До свидания!")
            break
        action = ACTIONS.get(choice)
        if action is None:
            print("Неверный пункт меню, введите число от 0 до 9.")
            continue
        try:
            action()
        except FileNotFoundError as err:
            print("Файл не найден:", err)
        except sqlite3.Error as err:
            print("Ошибка базы данных:", err)
        except (RuntimeError, AssertionError) as err:
            print("Ошибка:", err)
        except KeyboardInterrupt:
            print("\nОперация прервана.")


if __name__ == "__main__":
    main()