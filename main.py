"""Точка входа: python main.py --mode sample или --mode live."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

import pandas as pd
from scraper import scrape_live
from analysis import clean_data, make_charts, make_report

ROOT = Path(__file__).resolve().parent


def run() -> int:
    parser = argparse.ArgumentParser(description="Анализ объявлений о продаже квартир в Москве")
    parser.add_argument("--mode", choices=["sample", "live"], default="sample",
                        help="sample — сохранённые реальные объявления; live — скрейпинг сайта")
    parser.add_argument("--max-pages", type=int, default=1, help="До 10 страниц каталога")
    parser.add_argument("--delay", type=float, default=4, help="Пауза не менее 3 с между страницами")
    parser.add_argument("--input", type=Path, help="Анализ другого CSV с аналогичными колонками")
    parser.add_argument("--out", type=Path, default=ROOT / "output", help="Папка с результатами")
    args = parser.parse_args()
    try:
        if args.input:
            df = pd.read_csv(args.input)
            mode = "sample"
        elif args.mode == "live":
            df = pd.DataFrame(scrape_live(max_pages=args.max_pages, delay_seconds=args.delay))
            mode = "live"
        else:
            df = pd.read_csv(ROOT / "data" / "real_listings_snapshot.csv")
            mode = "sample"
        clean = clean_data(df)
        if clean.empty:
            raise ValueError("После очистки не осталось корректных объявлений")
        args.out.mkdir(parents=True, exist_ok=True)
        csv_path = args.out / "moscow_listings.csv"
        clean.to_csv(csv_path, index=False, encoding="utf-8-sig")
        chart_paths = make_charts(clean, args.out)
        report_path = make_report(clean, args.out, mode)
        print(f"\nОбработано объявлений: {len(clean)}")
        print(f"Медианная цена: {clean['price_rub'].median():,.0f} ₽")
        print(f"Медианная цена за м²: {clean['price_per_m2_rub'].median():,.0f} ₽")
        print(f"Таблица: {csv_path}\nОтчёт: {report_path}")
        for path in chart_paths:
            print(f"График: {path}")
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
