# Архитектура AI Design

Скилл ставится в папку навыков агента; весь код — стандартная библиотека Python 3.9+ и статический HTML/CSS/JS.

## Поток данных

1. Агент по `skills/aidesign/phases/0-start.md` копирует `tools/ad.py` и `tools/check.py` в `.aidesign-work/` проекта пользователя.
2. `ad.py init --skill-dir ABS` создаёт папку прогона `.aidesign-work/<YYYY-MM-DD>-<slug>/`, копирует шаблон панели в `.aidesign-work/dashboard.html` (и `index.html`) и `examples/` скилла в `.aidesign-work/examples/`.
3. Агент пишет состояние только командами `ad.py` (`stage`, `ask`, `ref`, `theme`, `round`, `direction`, `check`, `finish`…). `ad.py` держит единственный источник состояния — `.aidesign-work/state.js` (`window.STATE`, `version: 1`).
4. Панель читает `state.js`, `examples/INDEX.json` и превью `<dir>/<option.src>` через локальный сервер на `127.0.0.1`; ничего не пишет.
5. Рабочие файлы прогона: `brief.md`, `refs.md`, `vkus.md`, `interview.md`, `rounds/NN/{a,b,c}.html`, `rounds/NN/feedback.md`, `direction.md`, `report.md`. Итог передачи — `DESIGN.md` и блок `aidesign` в `AGENTS.md`/`CLAUDE.md` проекта пользователя.

Этапы (в этом порядке, id для `ad.py stage`): `preflight, refs, interview, previews, build, check, handoff`; пользователю называются Подготовка · Референсы · Интервью · Превью · Сборка · Проверка · Передача.

## Границы модулей

| Модуль | Владеет | Не делает |
|---|---|---|
| `skills/aidesign/tools/ad.py` | `state.js`, `dashboard.html`, реестр прогонов `README.md`, сервер | не содержит правил дизайна |
| `skills/aidesign/phases/dashboard-template.html` | отрисовка панели по полям `state.js` | не читает ничего кроме `state.js` и `examples/INDEX.json` |
| `skills/aidesign/SKILL.md`, `phases/*.md`, `prompts/*.md` | процесс: кто что и когда читает | субагенты скиллов не вызывают |
| `skills/aidesign/knowledge/` | правила и приёмы; вход — `INDEX.md` | не исполняется |
| `skills/aidesign/tools/check.py` | `scan(paths) -> list[Finding]`, `RULES`, CLI | не правит файлы |
| `skills/aidesign/examples/` | самодостаточные демо-страницы; каждая проходит `check.py` без находок | без внешних картинок, без кода GSAP |
| `tools/public-export.py` | чистая выгрузка из `git ls-files` и её проверка | не публикует |

Подробности контрактов — в самих файлах: команды `ad.py` — в начале самого файла и в `skills/aidesign/phases/*.md` (`--help` до `init` не работает), правила — `check.py --rules`.

## Договорённости проекта

- Пользовательский текст — по-русски; `README.md` английский, `README.ru.md` русский, зеркально.
- Нет путей домашней папки, имён людей, ключей. Слова об основе семейства — только в `LICENSE` и последней строке обоих README.
- Файл, перенесённый или близко пересказанный из источника, начинается с `<!-- Источник: <репо/путь>, <SPDX>, © <копирайт>. Изменено: <что>. -->` (для Apache-2.0 «Изменено» обязательно); идеи своими словами — `<!-- По мотивам: <репо> (<SPDX>) -->`. Копирайт-строки с именами авторов разрешены.
- Не копировать: код GSAP, пресеты и графы shaders.com, фото из примеров taste-skill, `DESIGN.md` брендов, текст hoodini (только идеи), платные части UI UX Pro Max и Pro HyperFrames.
- Источники для работы — `.sources/<подпапка>/`, не коммитятся.
- Только стандартная библиотека, без npm-зависимостей в скилле.
- `state.js`: `option.src` хранится от папки прогона; референсы-картинки копируются в `<dir>/refs/`; круг доработки (`round refine`) закрывается выбором при одном варианте, обычный круг — при трёх.
- Умолчания `init`: `mode=interview`, `questions=one`, `entry=new`; проверку версии выключает `AIDESIGN_NO_UPDATE_CHECK`.
- `check.py`: коды выхода 0 — чисто, 1 — находки, 2 — ошибка ввода; исключение в коде — комментарий `aidesign-ignore: <id> — причина` (действует на свою и следующую строку); каждое правило ссылается на якорь `{#id}` в `knowledge/язык/антипаттерны.md`.
- Метка «DESIGN.md от AI Design» — во фронтматтере ключи `aidesign: "<версия>"` и `direction`; по ней передача правил и подсказка в AISpa узнают файл.
- Блок памяти `<!-- aidesign:start -->…<!-- aidesign:end -->` — в конце `AGENTS.md`/`CLAUDE.md` проекта пользователя; в пустой папке создаётся `AGENTS.md` только с ним.
- Первый `DESIGN.md` пишется сразу после выбора направления, до сборки; доводится на Передаче.
- Громкие приёмы движения — только по запросу «навороченно» и по одному на экран; колесо прокрутки не перехватываем; готовый сайт переделывается внутри его идентичности.
- Связка с AISpa — только подсказка, не зависимость (`docs/adr/0003-связка-с-aispa-только-подсказкой.md`).
