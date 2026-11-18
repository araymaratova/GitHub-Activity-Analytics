import sqlite3

import matplotlib
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import pandas as pd

from config import DB_PATH, REPORTS_DIR
from queries import QUERIES, run_query

PLOTS_DIR = REPORTS_DIR / "plots"


def load(name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return run_query(conn, QUERIES[name])
    finally:
        conn.close()


def plot_event_types() -> None:
    df = load("q01_events_by_type").sort_values("events")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(df["type_name"], df["events"])
    ax.set_xscale("log")
    ax.set_xlabel("Число событий (логарифмическая шкала)")
    ax.set_title("События GitHub по типам (30 часов)")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "event_types.png", dpi=150)
    plt.close(fig)


def plot_language_trend() -> None:
    df = load("q11_language_trend")
    df["hour"] = pd.to_datetime(df["hour"], format="%Y-%m-%dT%H")
    pivot = df.pivot(index="hour", columns="language_name", values="events")
    fig, ax = plt.subplots(figsize=(10, 5))
    for lang in pivot.columns:
        ax.plot(pivot.index, pivot[lang], marker="o", markersize=3, label=lang)
    ax.set_xlabel("Время (UTC)")
    ax.set_ylabel("Число событий")
    ax.set_title("Тренд активности по языкам (топ-5, репозитории с известным языком)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "language_trend.png", dpi=150)
    plt.close(fig)


def plot_language_pr() -> None:
    df = load("q07_language_rank_pr").head(10).sort_values("pr_events")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(df["language_name"], df["pr_events"])
    ax.set_xlabel("Число PullRequestEvent")
    ax.set_title("Топ-10 языков по числу событий Pull Request")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "language_pr.png", dpi=150)
    plt.close(fig)


def make_all() -> list:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_event_types()
    plot_language_trend()
    plot_language_pr()
    return sorted(p.name for p in PLOTS_DIR.glob("*.png"))


if __name__ == "__main__":
    try:
        print("Созданы графики:", make_all())
    except (sqlite3.Error, FileNotFoundError, KeyError) as err:
        print("Ошибка:", err)