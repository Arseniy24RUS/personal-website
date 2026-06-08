from __future__ import annotations

BASE_URL = "https://sitkovskiy.ru"
SITE_IMAGE = f"{BASE_URL}/assets/craftum/portrait-library.jpeg"
ROBOTS_META = "index,follow,max-image-preview:large"

PAGE_FILES = [
    "index.html",
    "projects.html",
    "publications.html",
    "teaching.html",
    "media.html",
    "diplomas.html",
    "it.html",
    "materials.html",
    "metrics.html",
]

PAGES = [
    {
        "file": "index.html",
        "ru_title": "Ситковский Арсений Михайлович — персональный сайт | Ситковский А. М.",
        "ru_description": "Официальный персональный сайт: Ситковский Арсений Михайлович, Ситковский А. М.; демограф, экономгеограф, исследователь пространственного развития, научный сотрудник ФНИСЦ РАН, преподаватель РУДН. Публикации, проекты, СМИ, преподавание, наукометрия и научные идентификаторы.",
        "en_title": "Sitkovskiy Arseniy — personal website | Arseniy M. Sitkovskiy",
        "en_description": "Official personal website of Arseniy M. Sitkovskiy, also indexed as Sitkovskiy Arseniy: demographer, economic geographer, spatial development researcher, FCTAS RAS researcher and RUDN University lecturer. Publications, projects, media, teaching, research metrics and scholarly identifiers.",
        "ru_og_title": "Ситковский Арсений Михайлович — персональный сайт",
        "ru_og_description": "Демограф, экономгеограф, исследователь пространственного развития. Публикации, проекты, СМИ, преподавание, наукометрия и научные идентификаторы.",
        "en_og_title": "Sitkovskiy Arseniy — personal website",
        "en_og_description": "Demographer, economic geographer and spatial development researcher. Publications, projects, media, teaching, research metrics and scholarly identifiers.",
        "og_type": "profile",
    },
    {
        "file": "projects.html",
        "ru_title": "Проекты — Ситковский Арсений Михайлович",
        "ru_description": "Научные и прикладные проекты Арсения Михайловича Ситковского.",
        "en_title": "Projects — Arseniy M. Sitkovskiy",
        "en_description": "Research and applied projects by Arseniy M. Sitkovskiy.",
    },
    {
        "file": "publications.html",
        "ru_title": "Научные статьи — Ситковский Арсений Михайлович",
        "ru_description": "Список научных публикаций Арсения Михайловича Ситковского по данным eLibrary/РИНЦ, Scopus, Web of Science, ORCID, OpenAlex и Crossref.",
        "en_title": "Research articles — Arseniy M. Sitkovskiy",
        "en_description": "Research publications by Arseniy M. Sitkovskiy based on eLibrary/RSCI, Scopus, WoS and journal quality references.",
    },
    {
        "file": "teaching.html",
        "ru_title": "Преподавание — Ситковский Арсений Михайлович",
        "ru_description": "Преподавательская деятельность Арсения Михайловича Ситковского: курсы высшего образования, онлайн-курсы и лекции ДПО по демографии, ГИС и государственному управлению.",
        "en_title": "Teaching — Arseniy M. Sitkovskiy",
        "en_description": "Teaching by Arseniy M. Sitkovskiy: higher education courses, online courses and continuing professional education lectures in demography, GIS and public administration.",
    },
    {
        "file": "media.html",
        "ru_title": "СМИ — Ситковский Арсений Михайлович",
        "ru_description": "Материалы СМИ, публичные упоминания, интервью и аналитические публикации Арсения Михайловича Ситковского.",
        "en_title": "Media — Arseniy M. Sitkovskiy",
        "en_description": "Media articles, public mentions, interviews and analytical publications related to Arseniy M. Sitkovskiy.",
    },
    {
        "file": "diplomas.html",
        "ru_title": "Дипломы и сертификаты — Ситковский Арсений Михайлович",
        "ru_description": "Коллаж дипломов, благодарностей и сертификатов Арсения Михайловича Ситковского.",
        "en_title": "Diplomas and certificates — Arseniy M. Sitkovskiy",
        "en_description": "Diplomas, certificates, letters of appreciation and verified professional achievements of Arseniy M. Sitkovskiy.",
    },
    {
        "file": "it.html",
        "ru_title": "ИТ-ресурсы — Ситковский Арсений Михайлович",
        "ru_description": "Интерактивные дашборды, карты, симуляторы и учебные веб-приложения Арсения Михайловича Ситковского.",
        "en_title": "IT Resources — Arseniy M. Sitkovskiy",
        "en_description": "Interactive dashboards, maps, simulators and educational web applications by Arseniy M. Sitkovskiy.",
    },
    {
        "file": "materials.html",
        "ru_title": "Материалы — Ситковский Арсений Михайлович",
        "ru_description": "Дополнительные материалы профессионального портфолио Арсения Михайловича Ситковского.",
        "en_title": "Materials — Arseniy M. Sitkovskiy",
        "en_description": "Additional materials from the professional portfolio of Arseniy M. Sitkovskiy.",
    },
    {
        "file": "metrics.html",
        "ru_title": "Наукометрия — Ситковский Арсений Михайлович",
        "ru_description": "Автоматически обновляемые наукометрические показатели Арсения Михайловича Ситковского.",
        "en_title": "Research metrics — Arseniy M. Sitkovskiy",
        "en_description": "Research metrics and scholarly identifiers of Arseniy M. Sitkovskiy.",
    },
]

PAGES_BY_FILE = {page["file"]: page for page in PAGES}

ALTERNATE_NAMES = [
    "Ситковский Арсений",
    "Ситковский Арсений Михайлович",
    "Ситковский А. М.",
    "Ситковский А.М.",
    "Арсений Ситковский",
    "Sitkovskiy Arseniy",
    "Arseniy Sitkovskiy",
    "Arseniy M. Sitkovskiy",
    "Arseniy Mikhailovich Sitkovskiy",
    "Arseniy Sitkovskii",
    "Arseniy Sitkovsky",
]

SAME_AS = [
    "https://www.elibrary.ru/author_profile.asp?id=1012909",
    "https://orcid.org/0000-0002-8725-6580",
    "https://www.webofscience.com/wos/author/record/AAG-1530-2021",
    "http://www.scopus.com/inward/authorDetails.url?authorID=57220956828&partnerID=MN8TOARS",
    "https://cyberleninka.ru/search?q=Ситковский%20Арсений%20Михайлович&page=1",
    "https://www.researchgate.net/profile/Arseniy-Sitkovskiy",
    "https://scholar.google.com/citations?user=jEben4MAAAAJ&hl=ru",
    "https://independent.academia.edu/АрсенийСитковский",
    "https://github.com/Arseniy24RUS",
]


def page_path(page: dict[str, str], lang: str) -> str:
    file_name = page["file"]
    if lang == "en":
        return "/en/" if file_name == "index.html" else f"/en/{file_name}"
    return "/" if file_name == "index.html" else f"/{file_name}"


def page_url(page: dict[str, str], lang: str) -> str:
    return f"{BASE_URL}{page_path(page, lang)}"


def title_for(page: dict[str, str], lang: str) -> str:
    return page[f"{lang}_title"]


def description_for(page: dict[str, str], lang: str) -> str:
    return page[f"{lang}_description"]

