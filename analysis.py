"""Анализ цен предложений и построение графиков (не цен завершённых сделок)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.grid": True, "grid.alpha": 0.15})


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for field in ("price_rub", "area_m2", "rooms"):
        df[field] = pd.to_numeric(df[field], errors="coerce")
    df = df.dropna(subset=["price_rub", "area_m2", "rooms"])
    df = df.drop_duplicates(subset=["url"])
    # Отсекаем очевидно некорректные записи, не скрывая дорогие квартиры.
    df = df[df["price_rub"].between(500_000, 3_000_000_000)]
    df = df[df["area_m2"].between(8, 500)]
    df = df[df["rooms"].between(0, 9)]
    df["rooms"] = df["rooms"].astype(int)
    df["price_per_m2_rub"] = (df["price_rub"] / df["area_m2"]).round().astype(int)
    df = df[df["price_per_m2_rub"].between(30_000, 5_000_000)]
    return df


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def make_charts(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    price_m = df["price_rub"] / 1_000_000
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(price_m, bins=min(15, max(4, len(df) // 2)), edgecolor="white")
    ax.set(title="Распределение цен предложений в Москве", xlabel="Цена, млн ₽", ylabel="Количество объявлений")
    target = out_dir / "01_price_distribution.png"; _save(fig, target); outputs.append(target)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(df["area_m2"], price_m, alpha=0.75)
    ax.set(title="Площадь квартиры и цена", xlabel="Общая площадь, м²", ylabel="Цена, млн ₽")
    target = out_dir / "02_area_vs_price.png"; _save(fig, target); outputs.append(target)

    room_labels = {0: "Студия", 1: "1 комн.", 2: "2 комн.", 3: "3 комн.", 4: "4 комн.", 5: "5 комн."}
    med = df.groupby("rooms")["price_per_m2_rub"].median().sort_index() / 1000
    labels = [room_labels.get(int(r), f"{r} комн.") for r in med.index]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, med.values)
    for bar, value in zip(bars, med.values):
        ax.annotate(f"{value:,.0f}", (bar.get_x() + bar.get_width()/2, bar.get_height()),
                    ha="center", va="bottom", fontsize=9)
    ax.set(title="Медианная стоимость м² по комнатности", xlabel="Тип квартиры", ylabel="Тысяч ₽ за м²")
    ax.set_ylim(0, max(med.values) * 1.22)
    target = out_dir / "03_median_m2_by_rooms.png"; _save(fig, target); outputs.append(target)

    groups = [(room_labels.get(int(r), f"{r} комн."), (g["price_per_m2_rub"] / 1000).to_numpy())
              for r, g in df.groupby("rooms")]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.boxplot([g for _, g in groups], tick_labels=[n for n, _ in groups], showfliers=True)
    ax.set(title="Разброс стоимости квадратного метра", xlabel="Тип квартиры", ylabel="Тысяч ₽ за м²")
    target = out_dir / "04_price_m2_boxplot.png"; _save(fig, target); outputs.append(target)
    return outputs


def make_report(df: pd.DataFrame, out_dir: Path, mode: str) -> Path:
    area = df["area_m2"].median()
    price = df["price_rub"].median()
    ppm = df["price_per_m2_rub"].median()
    count = len(df)
    room_table = df.groupby("rooms").agg(
        listings=("url", "count"),
        median_price_rub=("price_rub", "median"),
        median_price_per_m2=("price_per_m2_rub", "median"),
    )
    lines = [
        "# Анализ объявлений о продаже квартир в Москве", "",
        f"**Режим:** {'сбор с сайта' if mode == 'live' else 'офлайн-снимок реальных объявлений'}", "",
        f"**Объявлений в выборке:** {count}", "",
        f"**Медианная цена предложения:** {price:,.0f} ₽", "",
        f"**Медианная площадь:** {area:.1f} м²", "",
        f"**Медианная цена м²:** {ppm:,.0f} ₽/м²", "",
        "## По количеству комнат", "",
        "| Комнат | Объявлений | Медианная цена, ₽ | Медианная цена м², ₽ |",
        "|---:|---:|---:|---:|",
    ]
    for rooms, row in room_table.iterrows():
        label = "Студия" if rooms == 0 else str(rooms)
        lines.append(f"| {label} | {int(row['listings'])} | {row['median_price_rub']:,.0f} | {row['median_price_per_m2']:,.0f} |")
    lines.extend([
        "", "## Ограничения", "",
        "- Это цены **предложений**, а не заключённых сделок.",
        "- Выборка неполная и не репрезентирует весь рынок Москвы.",
        "- Площадь и описание указаны рекламодателями и могут содержать ошибки.",
        "- Повторные объявления, особенности сортировки и доли в квартире могут искажать оценку.",
        "- Медиана вычисляется по собранным объявлениям, а не по всем объектам Москвы.",
        "", "**Источник:** https://www.mirkvartir.ru/Москва/", "",
    ])
    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
