# Проверка карты NordSec

GATE: OPEN 35 (rounds used up)

## Концепт и вид

Карта бесплатных вещей с двумя сценариями: у владельца и на улице. Реальная карта Leaflet/OpenStreetMap, без придуманных отметок в локальной базе. Сетка, кольца и геометрические формы на фоне добавлены по прямой просьбе пользователя. Цвета бренда сохранены, шрифт Onest локальный. Hero — split с действующим продуктом; word-highlight в заголовке двух сценариев. Форма размещения имеет компактную сетку и карту под адресом.

## Что проверено

Дополнение после правок формы: заголовок редактора больше не закрепляется при прокрутке (`position: static`). Обновлённая форма просмотрена на 1440 и 390 пикселях. Убраны кнопки подтверждения наличия и соответствующий серверный путь для present/missing; жалобы сохранены. Проверены необязательные описание и состояние, автоподстановка четырёх районов при смене точки, отсутствие автоподстановки района за пределами локальной области. Проверка района приблизительная, ручной выбор остаётся доступным. Текущие снимки: `.taste-skill/fixes-shots/`. Это проверка конкретных исправлений; прежний общий статус GATE OPEN ниже не заменён на PASS.

Итоговые снимки главной просмотрены на ширинах 1440, 1024, 820, 768 и 390 пикселей; редактор — на 1440 и 390. Перекрытий текста и горизонтального выхода страницы при просмотре не обнаружено. Финальная проверка производительности: 0 FAIL, 5 WARN (включая вес шрифтов и размеры логотипа), без неудачных сетевых запросов; CLS 0. После последних правок дополнительно прошли 29 тестов аккаунтов, карты и нормализации и проверка JavaScript-сценариев карты.

93 теста Django на PostgreSQL проходят; node scripts/check_map_ui.cjs проверяет высокую точность, приоритет ручного выбора над поздним GPS, повторный запрос, ошибку геолокации и скрытие контактов для улицы. Схема и миграции согласованы. SQL-демобаза пересобрана из публичной фикстуры и восстановлена в отдельную базу. Поиск реальной публичной улицы через API вернул три результата. Подложка и подпись OpenStreetMap реально загружаются.

Редактор проверяется на серверно отрисованном снимке без отправки формы. В браузерной проверке геолокация недоступна, и виден ручной запасной путь. Физическая точность GPS ноутбука не проверялась и не обещается. Для улицы погрешность более 100 м требует ручного выбора.

Ни одна ошибка не исключалась через waivers. Часть замечаний относится к полноэкранным маркетинговым секциям, структуре шаблона навыка и подписи под визуалом. Здесь подпись карты показывает наличие точек и доступность API, а атрибуция необходима поставщику. Замечания остаются открытыми, PASS не заявляется.

## Открытые FAIL consistency

### 1440 пикселей
- `hero-fill` — `main#main > section.container.platform-recent`: the next section shows on the first screen: it starts at 852px on a 900px screen (the hero ends at 852px)
- `nav` — `div.topbar > div.container.topbar-inner > a`: "Основной сайт фонда" sits outside the nav bar div.topbar (0-1440px)
- `no-visual` — `main#main > section.container.platform-recent`: pictures, effects and mocks cover 9% of this section; a feature section needs a visual (about 25% or more)
- `cta` — `main#main > section.platform-steps.mo-wh`: the last section before the footer ends with no button
- `copy-fact` — `section.hero.map-hero > div.container.map-hero-grid > div.map-hero-copy > h1`: the first screen holds no number, price, date, place, platform or genre
- `copy-actions` — `div.hero-live-map > div.public-map-block > div.map-toolbar > button.button.btn`: 5 actions in the hero ("Открыть карту ↗", "Разместить вещь", "Рядом со мной", "+", "−"); at most 2
- `tilt` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(2)`: rotated 32.0°
- `tilt` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(3)`: rotated -15.0°
- `map-link` — `div.leaflet-control-container:nth-of-type(2) > div.leaflet-bottom.leaflet-right:nth-of-type(4) > div.leaflet-control-attribution.leaflet-control > a:nth-of-type(2)`: "OpenStreetMap" searches for nothing: a map of a district or a town shows nobody the door
- `hero-screen` — `main#main > section.hero.map-hero`: the hero ends at 852px on a 900px screen, 48px above the fold: it ends at the fold, 1px either way (SR-1)
- `hero-screen` — `main#main > section.container.platform-recent`: 48px of the next section shows on the first screen (from 852px on a 900px screen): nothing below the hero shows at load (SR-1)
- `section-height` — `footer.footer`: the section is 440px tall (0.5 screens), 460px short of one screen (900px): every section after the hero is one screen or two, 2px either way (SR-2)
- `section-height` — `main#main > section.platform-steps.mo-wh`: the scene's section is 570px tall (0.6 screens), 330px short of one screen (900px): every section after the hero is one screen or two, 2px either way; a pinned scene is (hold + 1) screens tall, so write data-big-scene-opts='{"hold": 1}' (two screens) and keep --h on the section (SR-2)
- `section-height` — `main#main > section.container.platform-recent`: the section is 694px tall (0.8 screens), 206px short of one screen (900px): every section after the hero is one screen or two, 2px either way (SR-2)
- `section-height` — `footer.footer`: the section starts at 2116px, 316px below the screen grid (2 x 900px): sections start on whole screens (SR-2)
- `section-height` — `main#main > section.platform-steps.mo-wh`: the section starts at 1546px, 254px above the screen grid (2 x 900px): sections start on whole screens (SR-2)
- `section-height` — `main#main > section.hero.map-hero`: the section starts at 132px, 132px below the screen grid (0 x 900px): sections start on whole screens (and 1 more like it: "Рядом с вамиСвежие объяв") (SR-2)
- `section-height` — `footer.footer`: the section's content does not fit it: its lowest content ends 421px below its top, past 368px (the section less 72px of bottom padding) (SR-2)
- `one-section` — `footer.footer`: the screen at scroll 1546px (the top of section 3) shows 330px of section 4 and the content of 2 sections, over 24px each beside section 3: a screen shows one section (another may peek 8px, 24px WARN) (SR-4)
- `one-section` — `section.container.platform-recent > div.section-heading > div > h2`: the screen at scroll 132px (the top of section 1) shows 180px of section 2 and the heading of section 2 whole and the content of 2 sections, over 24px each beside section 1: a screen shows one section (another may peek 8px, 24px WARN) (SR-4)
- `one-section` — `main#main > section.container.platform-recent`: the screen at scroll 0px (stride 0) shows 48px of section 2 beside section 1: a screen shows one section (another may peek 8px, 24px WARN) (and 2 more like it: scroll 900px, scroll 852px) (SR-4)
- `container-edges` — `a.skip-link`: a <a> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (SR-6)
- `container-edges` — `div.topbar`: a <div> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (SR-6)
- `container-edges` — `header.header`: a <header> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (and 6 more like it: "NordSec Бесплатные вещи ", "NordSec · НорильскВещи б", main#main > section.hero.map-hero > div.hero-shapes) (SR-6)
- `container-edges` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(1)`: a box runs 1090-1440px, outside the container lines of section 1 at 80-1360px: full width is for background layers and grounds only (SR-6)
- `container-edges` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(2)`: a box runs 0-138px, outside the container lines of section 1 at 80-1360px: full width is for background layers and grounds only (SR-6)
- `split-pair` — `main#main > section.hero.map-hero > div.container.map-hero-grid`: the two columns of the split start 68px apart at the top: a split's columns are top-aligned, 8px either way (SR-8)
- `split-pair` — `main#main > section.hero.map-hero > div.container.map-hero-grid`: the split's columns are off the page's one pair of lines: its right column starts at x 704, on none of the split lines 623 (k=5), 732 (k=6), 841 (k=7) (SR-8)

### 390 пикселей
- `spill` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(3)`: runs 104px past the right edge of the panel it sits on (main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(2))
- `no-visual` — `main#main > section.container.platform-recent`: pictures, effects and mocks cover 10% of this section; a feature section needs a visual (about 25% or more)
- `cta` — `main#main > section.platform-steps.mo-wh`: the last section before the footer ends with no button
- `copy-actions` — `div.hero-live-map > div.public-map-block > div.map-toolbar > button.button.btn`: 5 actions in the hero ("Открыть карту ↗", "Разместить вещь", "Рядом со мной", "+", "−"); at most 2
- `tilt` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(2)`: rotated 32.0°
- `tilt` — `main#main > section.hero.map-hero > div.hero-shapes > i:nth-of-type(3)`: rotated -15.0°

## Предупреждения

- `scroll-reveal`: starts "color" (0.2 s) the moment it is scrolled into view (an IntersectionObserver) on span.mo-w:nth-of-type(1) (inside a dealt moment's section, [data-moment]: an enter moment is expected on every kind; its still is judged under reduced motion)
- `copy-headline`: "Вещи бесплатно. На карте города.": no category known to check it against (pass --category, or write the <title> as "Name: what it is for whom")
- `copy-actions`: the main action "Открыть карту" does not read word for word the same in the closing section
- `photo-set`: 3 photographs in more than one look: lightness from 0.25 to 0.86; saturation from 0.20 to 0.72; the odd one out is
- `grounds`: 4 flat grounds across the page (#e9eee4 section, #f7f7f1 section, #dfe8d6 section, #15362a footer): three at most (the base, a surface, an inverse)
- `action-count`: the main action "Открыть карту" is on 6 buttons and links: the nav, the hero and the closing call carry it; elsewhere a section has its own action
- `one-screen`: 2 sections are shorter than the screen, so the next one's heading or picture shows with them: "Свежие объявления" is 694px of the 900px under the nav, and "Два способа разместить вещь" shows below it ("Два способа размести")
- `skip-link`: the first Tab stop is "Перейти к содержимому", not a skip link: a keyboard user tabs through the whole nav on every visit
- `share-meta`: the head lacks og:title, og:description, og:image, twitter:card: a shared link shows no picture or title of its own
- `action-repeat`: "разместить вещь" shows 2 times on the first screen at 1440px (nav, hero): the nav's button and the hero's; nothing else on the screen may repeat it
- `one-heading`: headings of two sections show whole on one screen at 3 of 34 scroll positions (8.8%; at scroll 850, 900, 950px), here with "Свежие объявления": at most 3% on a desktop (it is in a scroll scene: told as a WARN) (SR-5)
- `tap-size`: a 40x40px tap target: under the 44px a phone needs
- `button-styles`: on the phone 2 buttons run the full width of their column, but  "Рядом со мной" is 102px of 324px: one action in two sizes
- `nav-family`: the nav's links come in 2 sizes (16, 11px)

Названия и цифры объявлений берутся из базы; отзывы, факты о пользователях и обещания наличия не добавлялись. Стоковые фотографии не используются. Фото предметов должны добавлять авторы. Четыре координаты в приложенной демобазе вымышлены и обозначены как тестовые в инструкции к ней; локальным существующим объявлениям они не присваиваются.
