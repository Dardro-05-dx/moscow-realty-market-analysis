import pandas as pd
from scraper import parse_listings, find_next_page
from analysis import clean_data

HTML = '''<!doctype html><html><body>
<article>
  <a href="/372439915/">79 500 000 ₽1 044 678 ₽/м²</a>
  <h3>Трёхкомнатная квартира</h3>
  <div>3 комнаты • 76.1 м² • 4/15 этаж</div>
  <span>Москва, ул. Серпуховский Вал, 7</span>
  <p>Продажа в районе Даниловский.</p>
</article>
<article>
  <a href="/373643834/">950 000 ₽95 000 ₽/м²</a>
  <div>Студия • 10 м² • 1/12 этаж</div>
  <span>Москва, ул. Маршала Чуйкова</span>
</article>
<a rel="next" href="/Москва/?page=2">Следующая</a>
</body></html>'''


def test_parser_extracts_real_numbers():
    rows = parse_listings(HTML)
    assert len(rows) == 2
    assert rows[0]["price_rub"] == 79_500_000
    assert rows[0]["area_m2"] == 76.1
    assert rows[0]["rooms"] == 3
    assert rows[0]["district"] == "Даниловский"
    assert rows[1]["rooms"] == 0


def test_next_page():
    assert find_next_page(HTML, "https://www.mirkvartir.ru/Москва/") == "https://www.mirkvartir.ru/Москва/?page=2"


def test_clean_data_deduplicates_and_calculates():
    row = {"url": "https://example.com/1", "price_rub": 20_000_000, "area_m2": 50, "rooms": 2}
    df = clean_data(pd.DataFrame([row, row]))
    assert len(df) == 1
    assert df.iloc[0]["price_per_m2_rub"] == 400_000
