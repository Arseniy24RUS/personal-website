# Персональный сайт учёного: static-first платформа

Репозиторий предназначен для персонального сайта-портфолио учёного на GitHub Pages с автоматизированным сбором данных через GitHub Actions.

Текущая архитектура:

- публичный сайт публикуется как статический GitHub Pages;
- автоматический сбор данных выполняется GitHub Actions;
- eLibrary/РИНЦ загружается из публичного HTML-снимка или live-страницы автора;
- Scopus загружается через серверный GitHub Actions secret `SCOPUS_API_KEY`;
- ORCID/OpenAlex/Crossref/GitHub добавляются как открытые API-коннекторы;
- неоднозначные записи должны попадать в `data/admin_queue/`, а уверенные записи — в нормализованные JSON/CSV.

Важно: API-ключи не должны попадать в клиентский JavaScript или публичные JSON. Для GitHub Pages правильная схема — `GitHub Actions secrets -> harvested JSON snapshots -> static site`.

## Быстрый запуск

```bash
python -m pip install beautifulsoup4 requests pyyaml rapidfuzz
python scripts/parse_elibrary_author_items.py "data/snapshots/elibrary/author_items.html" --out data/processed/elibrary_publications.json
```

Для Scopus локально:

```bash
export SCOPUS_API_KEY="..."
export SCOPUS_AUTHOR_ID="57220956828"
python scripts/harvest_scopus.py
```

В GitHub: `Settings -> Secrets and variables -> Actions -> New repository secret -> SCOPUS_API_KEY`, затем запустить workflow `Refresh scientist portfolio data`.
