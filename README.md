# Personal Academic Website · Static-first Research Portfolio

[English](#english) · [Русский](#русский)

[![Website](https://img.shields.io/badge/website-sitkovskiy.ru-informational)](https://sitkovskiy.ru/)
[![GitHub Pages](https://img.shields.io/badge/demo-GitHub%20Pages-blue)](https://arseniy24rus.github.io/personal-website/)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Content: CC BY 4.0](https://img.shields.io/badge/content-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

---

## English

### Overview

`personal-website` is a static-first academic website and research portfolio for Arseniy Sitkovskiy. It combines a public biography, publication lists, project pages, teaching and media materials, GitHub portfolio links, metrics pages and automated data-refresh workflows. The site is designed as the central entry point connecting academic identity, research software, digital dashboards and open methodological materials.

The repository is intentionally built around a static deployment model. The public website can be served by GitHub Pages or any simple static hosting provider, while automated update scripts refresh selected metadata and publication-related files without exposing private API keys in client-side JavaScript.

### Public website

Main domain: <https://sitkovskiy.ru/>  
GitHub Pages version: <https://arseniy24rus.github.io/personal-website/>

### What this project does

The website performs three functions. First, it acts as an academic portfolio: it presents research fields, institutional affiliations, publications, grants, media activities, projects and teaching materials. Second, it works as a gateway to research software and dashboards published in other repositories. Third, it provides a maintainable infrastructure for regular updates of publication and profile metadata.

### Repository structure

```text
.github/              GitHub Actions workflows
assets/               Static assets: images, styles, icons, scripts
config/               Configuration files for automated update scripts
content/              Structured website content
data/                 Publication, metric and project data used by pages
docs/                 Documentation and auxiliary materials
scripts/              Data refresh and maintenance scripts
tests/e2e/            Playwright end-to-end tests
CNAME                 Custom domain for GitHub Pages
*.html                Static website pages
package.json          Node.js dependencies and quality scripts
playwright.config.ts  Playwright configuration
```

### Data and automation model

The site separates public presentation from data maintenance. Publication and profile metadata can be updated through scripts and GitHub Actions. The repository may use public data sources and researcher identifiers such as ORCID, OpenAlex, Crossref and GitHub metadata. Sensitive credentials, where needed, should be passed through GitHub Actions secrets and must not be embedded into browser-side JavaScript.

### Local development

```bash
# Install dependencies
npm ci

# Run Playwright tests
npx playwright test

# Serve locally with any static server
python -m http.server 8000
```

Then open <http://localhost:8000/> in a browser.

### Quality assurance

The repository is suitable for automated quality control through Playwright end-to-end tests, broken-link checks, HTML validation and periodic review of external data sources. The recommended baseline is to verify that the main pages load, navigation works, project links are reachable, publication tables render correctly, and no private credentials appear in generated client-side files.

### Reproducibility and maintenance

This project is not a data-analysis pipeline in the narrow sense; it is a reproducible academic web platform. Reproducibility means that the website can be rebuilt from versioned static files and structured data, and that automated scripts can update selected metadata in a transparent and auditable way.

### License and attribution

Unless otherwise stated, the code is released under the MIT License. Website text, documentation and non-code materials are released under Creative Commons Attribution 4.0 International (CC BY 4.0). When reusing the website structure, texts, figures or portfolio materials, please cite the author and this repository.

---

## Русский

### Обзор

`personal-website` — статический академический сайт и исследовательское портфолио Арсения Ситковского. Репозиторий объединяет публичную биографию, списки публикаций, страницы проектов, учебные и медийные материалы, ссылки на GitHub-портфолио, страницы метрик и автоматизированные процедуры обновления данных. Сайт выступает центральной точкой входа, связывающей академическую идентичность, исследовательское программное обеспечение, цифровые дашборды и открытые методические материалы.

Проект сознательно построен по модели static-first. Публичная версия сайта может обслуживаться GitHub Pages или любым статическим хостингом, а автоматические скрипты обновляют отдельные метаданные и публикационные файлы без размещения приватных API-ключей в клиентском JavaScript.

### Публичный сайт

Основной домен: <https://sitkovskiy.ru/>  
Версия GitHub Pages: <https://arseniy24rus.github.io/personal-website/>

### Что делает проект

Сайт выполняет три функции. Во-первых, это академическое портфолио: он представляет исследовательские направления, институциональные аффилиации, публикации, гранты, медийную активность, проекты и учебные материалы. Во-вторых, это входная точка к исследовательскому программному обеспечению и дашбордам, опубликованным в других репозиториях. В-третьих, это поддерживаемая инфраструктура для регулярного обновления публикационных и профильных метаданных.

### Структура репозитория

```text
.github/              Workflow GitHub Actions
assets/               Статические ресурсы: изображения, стили, иконки, скрипты
config/               Конфигурации для автоматизированных скриптов
content/              Структурированное содержимое сайта
data/                 Данные публикаций, метрик и проектов
docs/                 Документация и вспомогательные материалы
scripts/              Скрипты обновления и обслуживания
tests/e2e/            Сквозные тесты Playwright
CNAME                 Пользовательский домен GitHub Pages
*.html                Статические страницы сайта
package.json          Node.js-зависимости и команды контроля качества
playwright.config.ts  Конфигурация Playwright
```

### Модель данных и автоматизации

Сайт разделяет публичное представление и обслуживание данных. Публикационные и профильные метаданные могут обновляться с помощью скриптов и GitHub Actions. Репозиторий может использовать публичные источники и исследовательские идентификаторы, включая ORCID, OpenAlex, Crossref и GitHub metadata. Конфиденциальные ключи, если они необходимы, должны передаваться через GitHub Actions secrets и не должны попадать в клиентский JavaScript.

### Локальный запуск

```bash
# Установка зависимостей
npm ci

# Запуск Playwright-тестов
npx playwright test

# Локальный статический сервер
python -m http.server 8000
```

После запуска откройте <http://localhost:8000/> в браузере.

### Контроль качества

Репозиторий подходит для автоматического контроля качества через Playwright-тесты, проверку битых ссылок, HTML-валидацию и периодическую ревизию внешних источников данных. Минимальная проверка должна подтверждать, что основные страницы загружаются, навигация работает, ссылки на проекты доступны, таблицы публикаций корректно отображаются, а приватные ключи не попадают в клиентские файлы.

### Воспроизводимость и сопровождение

Проект не является аналитическим пайплайном в узком смысле; это воспроизводимая академическая веб-платформа. Воспроизводимость здесь означает, что сайт может быть пересобран из версионированных статических файлов и структурированных данных, а автоматические скрипты обновляют выбранные метаданные прозрачным и проверяемым способом.

### Лицензия и атрибуция

Если явно не указано иное, программный код распространяется по лицензии MIT. Тексты сайта, документация и не-кодовые материалы распространяются по лицензии Creative Commons Attribution 4.0 International (CC BY 4.0). При повторном использовании структуры сайта, текстов, графики или материалов портфолио, пожалуйста, указывайте автора и данный репозиторий.
