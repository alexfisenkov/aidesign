# Сторонние материалы (Third-Party Notices)

AI Design собран на знаниях из открытых дизайн-скиллов и инструментов. Здесь — по каждому источнику: что это, лицензия (SPDX), строка копирайта дословно, адрес, что именно взято и в каком виде. Полные тексты лицензий MIT и Apache-2.0 — в конце файла.

Как помечены файлы скилла:

- `<!-- Источник: <репо/путь>, <SPDX>, © <копирайт>. Изменено: <что>. -->` — текст перенесён или пересказан близко к оригиналу (перевод на русский, сокращение, объединение). Для материалов под Apache-2.0 это и есть обязательная пометка об изменениях (раздел 4(b) лицензии).
- `<!-- По мотивам: <репо> (<SPDX>) -->` — взяты идеи, текст написан своими словами.

Сверено по клонам репозиториев от 18.11.2026; в скобках — коммит, с которого брались материалы.

Тот же список для программ — реестр `skills/aidesign/knowledge/sources.json` (по записи на каждый раздел ниже, с файлами скилла, где источник назван в шапке); тесты сверяют его с этим файлом, обоими README и шапками атрибуции. Как добавить новый источник — `docs/пополнение.md`.

## Взятые материалы

### Impeccable — `pbakaus/impeccable` (d41d986)

- **Лицензия:** Apache-2.0
- **Копирайт:** `Copyright 2025 Paul Bakaus`
- **Адрес:** https://github.com/pbakaus/impeccable
- **Что взято:** каталог примет шаблонного дизайна (62 правила детектора, `crates/live/assets/antipatterns.json`), «пол качества» (`skill/reference/craft-floor.md`), правила типографики, цвета, раскладки, движения (`typeset.md`, `colorize.md`, `layout.md`, `animate.md`), режимы посетителя (`mode-*.md`), формат DESIGN.md (`document.md`), извлечение токенов (`extract.md`); для раздела движения и медиа — `skill/reference/animate.md` (движение, режимы посетителя), `overdrive.md` (громкие приёмы, морфинг, WebGL), `live.md` (фиксация идентичности готового сайта, план трёх вариантов превью). Перевод на русский, пересказ, объединение с другими источниками; изменённые файлы помечены шапкой «Источник … Изменено …». Код детектора не копировался: `tools/check.py` написан заново на Python.
- **Не взято:** `skill/reference/ios.md` и `android.md` (производные от ehmo/platform-design-skills, MIT) — не переносились.
- **NOTICE:** содержимое `NOTICE.md` Impeccable перенесено дословно в файл `NOTICE` этого репозитория.

### frontend-design (Anthropic) — `anthropics/skills`, папка `skills/frontend-design` (e4bb5d9)

- **Лицензия:** Apache-2.0 (файл `skills/frontend-design/LICENSE.txt`)
- **Копирайт:** строки копирайта в `LICENSE.txt` нет; правообладатель — Anthropic.
- **Адрес:** https://github.com/anthropics/skills/tree/main/skills/frontend-design
- **Что взято:** список клише ИИ-дизайна (кремовый с терракотой, чёрный с кислотным акцентом, газетные линейки, набор SaaS-карточек, шаблонная обвязка), принцип «смелость в одном месте», план «4–6 цветов, 1–2 гарнитуры», правила текста интерфейса. Перевод и пересказ, файлы помечены.

### Taste Skill — `Leonxlnx/taste-skill` (f6b7657)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 Leonxlnx`
- **Адрес:** https://github.com/Leonxlnx/taste-skill
- **Что взято:** правила по типу дела (эффекты и сцены только для технических предметов, фото для мест и услуг), приметы ИИ-текста (`references/copy-tells.md`), запреты («никогда»), чек-лист проверки, одиннадцать раскладок героя и их правила (`references/layout-v4.md`, своими словами); идеи палитр и раздачи стиля (`library/palettes.json`, `library/type.json`) — пересказом; для раздела движения и медиа — `references/motion.md` (движение, прокрутка, курсор, видео в сайте), `perf.md` (производительность анимации и видео), `effects-usage.md` (когда уместны эффекты и 3D), `photos.md` (фото). Перевод и пересказ.
- **Не взято:** фотографии из `examples/v2` (часть под CC BY и CC BY-SA, см. `examples/v2/CREDITS.md`) — не копировались. Код и ассеты кита (`assets/`, `scripts/`) не копировались.
- **Связанные репозитории** `Leonxlnx/taste-skill-classics` и `Leonxlnx/imagegen-skills` (MIT, `Copyright (c) 2026 Leonxlnx` по данным GitHub API) — не использовались.

### UI UX Pro Max — `nextlevelbuilder/ui-ux-pro-max-skill` (f984fcd)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2024 Next Level Builder`
- **Адрес:** https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- **Что взято:** признаки стилей (`src/ui-ux-pro-max/data/styles.csv`) — отбор 17 семейств, перевод и пересказ с поправками по каталогу антипаттернов; UX-правила и правила WCAG 2.2 (`ux-guidelines.csv`); характеры шрифтовых пар (`typography.csv`); схемы лендингов (`landing.csv`, десять из 34); типы графиков по данным (`charts.csv`, семь из 25); сверка кириллицы шрифтов по `google-fonts.csv`.
- **Не взято:** премиум-версия (uupm.cc) — не использовалась; CSV-базы целиком не копировались.

### web-design-guidelines (Vercel) — `vercel-labs/agent-skills`, папка `skills/web-design-guidelines` (1a2c79d)

- **Лицензия:** MIT заявлена в README репозитория; файла LICENSE в корне нет, строки копирайта нет.
- **Копирайт:** не указан; автор в метаданных скилла — `vercel`.
- **Адрес:** https://github.com/vercel-labs/agent-skills
- **Что взято:** только идея — аудит по свежему своду правил с выводом находок в форме `файл:строка`. Текст не переносился.

### Web Interface Guidelines — `vercel-labs/web-interface-guidelines` (434b7f9)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2025 Vercel Labs`
- **Адрес:** https://github.com/vercel-labs/web-interface-guidelines
- **Что взято:** свод правил интерфейса (`command.md`): доступность, фокус, формы, анимация, типографика, изображения, производительность, навигация, касание, безопасные зоны, тёмная тема, локаль, тексты, антипаттерны. Перевод, нумерация, адаптация под русский набор — `knowledge/язык/доступность-и-качество.md`.

### GSAP skills — `greensock/gsap-skills` (aed9cfd)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 GreenSock`
- **Адрес:** https://github.com/greensock/gsap-skills
- **Что взято:** для раздела движения и медиа — правила анимации (`skills/gsap-core`), ScrollTrigger (`skills/gsap-scrolltrigger`), плагинов SplitText, Flip, MorphSVG (`skills/gsap-plugins/SKILL.md`), производительности и `quickTo` (`skills/gsap-performance`); в визуальном языке — упоминание SplitText. Пересказ, код библиотеки не переносился.

### Библиотека GSAP (не входит в репозиторий)

- **Лицензия:** проприетарная «Standard No Charge License» (Webflow), не OSI; бесплатна для коммерческих сайтов, все плагины тоже.
- **Адрес:** https://gsap.com/licensing/
- **Что взято:** ничего. Код GSAP в репозитории нет; страницы, которым он нужен, подключают его с CDN или ставят из npm в проекте человека.

### MengTo Skills — `MengTo/Skills` (3cc9345)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 Meng To`
- **Адрес:** https://github.com/MengTo/Skills
- **Что взято:** из `scroll-world-storytelling` — три режима отрисовки и запрет смешивать их, «колесо не перехватывать никогда», раскладка истории на сцены, стилевые этюды, меняющие материал и свет; из `add-shader-cursor-trail` — правила включения эффекта курсора (касание, reduced-motion, forced-colors) для раздела движения. Перевод и пересказ.

### Пакет `shaders` и shaders.com (не входит в репозиторий)

- **Лицензия:** код пакета — MIT; пресеты, коллекции и секции shaders.com — проприетарные, Pro по подписке.
- **Адрес:** https://shaders.com/license
- **Что взято:** ничего из пресетов и графов. Идея эффекта следа курсора описана своими словами.

### premium-frontend-ui — `github/awesome-copilot`, папка `skills/premium-frontend-ui` (a255a19)

- **Лицензия:** MIT
- **Копирайт:** `Copyright GitHub, Inc.`
- **Автор скилла:** Utkarsh Patrikar (по метаданным скилла)
- **Адрес:** https://github.com/github/awesome-copilot/tree/main/skills/premium-frontend-ui
- **Что взято:** направления (Editorial Brutalism, Cyber/Technical, Cinematic Pacing), прелоадер, прячущееся меню, магнитные кнопки, свой курсор, параллакс — как позиции в спорах и идеи для движения; правила отключения эффектов курсора на касании и при reduced-motion. Пересказ.

### HyperFrames — `heygen-com/hyperframes` (a82ee10)

- **Лицензия:** Apache-2.0
- **Копирайт:** `Copyright 2026 HeyGen, Inc.`
- **Адрес:** https://github.com/heygen-com/hyperframes
- **Что взято:** для раздела движения и медиа — идея «один образ по намерению, сдержанно, проверить глазами» из `skills/media-use/SKILL.md` и `references/grading.md` (фото); идеи HTML-презентации — слайд как сцена, фрагменты, размер текста, скрытые слайды — из `skills/slideshow/SKILL.md` (поверхности); указание на инструмент «HTML → видео» — по мотивам (видео). Пересказ, код и компоненты не переносились.
- **Не взято:** каталог блоков (содержит GSAP, материалы под MPL-2.0, CC-BY-4.0 и ассеты с неясным происхождением), Pro-скиллы.

### video-to-landing-page и parallax-landing-page — `hoodini/ai-agents-skills` (a52f5f4)

- **Лицензия:** в README написано «MIT License — Feel free to use, modify, and distribute»; файла LICENSE нет, правообладатель не назван.
- **Адрес:** https://github.com/hoodini/ai-agents-skills
- **Что взято:** только идеи, своими словами, из `video-to-landing-page`, `parallax-landing-page` и `cinematic-scrub-landing` (число кадров по длине ролика, бюджет веса, видео за курсором, сцены текста; перехват колеса и капс-надзаголовки — как позиция в спорах, которую мы не принимаем). Текст не переносился.

### awesome-design-md — `VoltAgent/awesome-design-md` (fcc7028)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 VoltAgent`
- **Адрес:** https://github.com/VoltAgent/awesome-design-md
- **Что взято:** структура DESIGN.md из девяти разделов (таблица из README) — для `knowledge/язык/design-md.md`.
- **Не взято:** файлы `design-md/<бренд>/DESIGN.md` — не копировались. Они описывают айдентику сторонних компаний; названия брендов упоминаются только номинативно, AI Design с ними не связан.

### getdesign.md (сайт, не входит в репозиторий)

- **Условия:** пользовательское соглашение https://getdesign.md/terms; платные стили («Catalog Pass») распространять нельзя.
- **Что взято:** ничего из файлов. Упоминается команда `npx getdesign@latest add <slug>` как путь, которым человек сам берёт разбор бренда.

### Dembrandt — `dembrandt/dembrandt` (90e2691)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2025 thevangelist`
- **Адрес:** https://github.com/dembrandt/dembrandt
- **Что взято:** описание команд и флагов извлечения токенов с сайта (`README.md`). Код не копировался; инструмент запускается через `npx` только с согласия человека.

### Dembrandt skills — `dembrandt/dembrandt-skills` (66d0331)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 Dembrandt`
- **Адрес:** https://github.com/dembrandt/dembrandt-skills
- **Что взято:** модульная шкала (`modular-scale-typography`), алгоритмическая палитра (`algorithmic-color-palette`), извлечение и воспроизведение сайта (`extract-design`, `clone-website`); идеи гештальта, плотности, поверхностей. Перевод и пересказ.

### scroll-world — `oso95/scroll-world` (71cc36d)

- **Лицензия:** MIT
- **Копирайт:** `Copyright (c) 2026 cyw`
- **Адрес:** https://github.com/oso95/scroll-world
- **Что взято:** для раздела движения и медиа — из `skills/scroll-world/SKILL.md` (шаги 6–8, «Gotchas») пересказаны правила перемотки через Blob, объединения перемоток, телефонной версии 9:16, стыков и проверки, а также интервью об арт-направлении и смета до генерации (видео в сайте); по мотивам — бесшовные стыки сцен (морфинг). Код движка и шаблоны промптов не переносились.

### AIMaster, авторские инструкции — `alexfisenkov/aimaster` (пакет 2026.11.19)

- **Лицензия:** пересказ в AI Design распространяется под MIT по разрешению автора от 19.11.2026. Сам aimaster — под авторскими условиями использования (файл `LICENSE` в его репозитории), это разрешение их не меняет.
- **Копирайт:** `Copyright (c) 2026 Alexander Fisenkov`
- **Адрес:** https://github.com/alexfisenkov/aimaster
- **Что взято:** для раздела медиа (`knowledge/медиа/`) своими словами и сжато под медиа сайта пересказаны авторские инструкции из `guides/` — Gemini Images (Nano Banana), Midjourney, GPT Image, Seedream, Higgsfield, Magnific, Seedance, Kling, Veo, CineMaster (камера и свет), качество изображений, визуальные референсы — и процесс из `references/` (выбор модели, привязка референсов, видео как вход). Факты о моделях оставлены с датой сверки и ссылкой на официальную страницу.
- **Не взято:** дословный текст инструкций, сценарные и карточные руководства, движок и студия aimaster.

## Товарные знаки

Названия компаний, продуктов и сайтов (Apple, Stripe, Linear, Vercel, Anthropic, GitHub и другие) упоминаются только номинативно — чтобы назвать источник или стиль. AI Design не связан с их владельцами и не выдаёт разборы чужих брендов за официальные.

---

## Текст лицензии MIT

Применяется к каждому источнику с лицензией MIT выше, вместе с его строкой копирайта.

```text
MIT License

Copyright (c) <год> <правообладатель — см. строку источника выше>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Текст лицензии Apache License 2.0

Применяется к Impeccable, frontend-design (Anthropic) и HyperFrames, вместе с их строками копирайта.

```text
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS
```
