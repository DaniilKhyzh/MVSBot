# MVSUA Ticket Monitor

Python-бот для read-only моніторингу появи вільних талонів на практичний іспит у системі Е-запису сервісних центрів МВС України.

Проєкт створюється тільки для сповіщень. Він не бронює талони, не створює записи, не натискає кнопки замість користувача, не проходить Дія.Підпис або BankID автоматично і не обходить захист системи. Після сповіщення користувач сам заходить в офіційний кабінет і записується вручну.

## Поточний Стан

У браузері після ручного входу були знайдені read-only запити календаря для потрібної послуги та сервісного центру.

Параметри з дослідженого сценарію:

```text
serviceId=43
departmentId=93
```

Знайдені корисні read-only endpoints:

```text
GET https://eqn.hsc.gov.ua/api/v2/equeue/days?serviceId=43&departmentId=93
GET https://eqn.hsc.gov.ua/api/v2/equeue/slots?serviceId=43&departmentId=93&date=2026-06-30T00:00:00
```

Приклад відповіді `days`:

```json
{
  "data": [
    {
      "date": "2026-06-30T00:00:00"
    }
  ]
}
```

Приклад відповіді `slots`:

```json
{
  "data": [
    {
      "startTime": "09:20:00",
      "stopTime": "09:40:00"
    },
    {
      "startTime": "14:00:00",
      "stopTime": "14:20:00"
    }
  ]
}
```

Також був знайдений endpoint бронювання:

```text
POST https://eqn.hsc.gov.ua/api/v2/booking
```

Його не використовувати в цьому проєкті. Це дія бронювання, вона змінює стан у системі, містить `x-csrf-token`, короткоживучий `token` та конфігурацію вибраного слота. Бот має працювати тільки з `GET /equeue/days` і `GET /equeue/slots`.

## Архітектура

1. Користувач вручну входить у кабінет через Дія.Підпис або BankID.
2. Після повернення з BankID бот сам відкриває `/cabinet/queue`.
3. Бот пробує пройти read-only кроки вибору послуги, категорії та сервісного центру до календаря.
4. Паралельно бот зберігає знайдені JSON-відповіді `GET /api/v2/...` у `data/discovered-api`.
5. Бот періодично виконує `GET /equeue/days`.
6. Якщо `days` повернув доступні дати, бот для кожної дати виконує `GET /equeue/slots`.
7. Якщо `slots` повернув хоча б один `startTime`/`stopTime`, бот надсилає сповіщення.
8. Користувач вручну відкриває офіційний сайт і сам бронює потрібний слот.

Схема:

```text
manual login -> bot opens queue wizard -> GET days -> GET slots -> notification -> manual booking
```

## Файли Проєкту

```text
.env.example
README.md
docs/http-analysis-uk.md
docs/provided-requests-analysis-uk.md
pyproject.toml
src/mvsuabot/availability.py
src/mvsuabot/config.py
src/mvsuabot/equeue.py
src/mvsuabot/http_probe.py
src/mvsuabot/monitor.py
src/mvsuabot/notifier.py
tests/test_availability.py
```

Основні ролі файлів:

```text
src/mvsuabot/config.py        читає .env
src/mvsuabot/equeue.py        будує і виконує read-only запити days/slots
src/mvsuabot/availability.py  парсить дати та часові слоти
src/mvsuabot/session_manager.py відкриває Chrome, чекає BankID і веде до календаря
src/mvsuabot/monitor.py       запускає цикл перевірки
src/mvsuabot/notifier.py      надсилає Telegram або console notification
```

## Налаштування

Створити віртуальне середовище:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Приклад `.env`:

```env
CHECK_INTERVAL_SECONDS=60
MVS_API_BASE_URL=https://eqn.hsc.gov.ua/api/v2
MVS_SERVICE_ID=43
MVS_DEPARTMENT_ID=93
MVS_DEPARTMENT_LABEL=ТСЦ МВС № 5342
MVS_REQUEST_HEADERS_JSON={"accept":"application/json, text/plain, */*"}
MVS_COOKIE_HEADER=
MVS_BROWSER_CHANNEL=chrome

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`MVS_COOKIE_HEADER` для основного режиму не потрібен. Через Akamai copied cookies часто не працюють поза браузером, тому вхід виконується у Chrome-вікні, яке відкриває бот.

Запуск:

```bash
mvsua-monitor
```

Якщо Telegram не налаштований, повідомлення будуть виводитися в консоль.

## Як Відбувається Вхід

1. Запустити `mvsua-monitor`.
2. Бот відкриє окреме Chrome-вікно з профілем у `data/browser-profile`.
3. У цьому вікні вручну пройти BankID або Дія.Підпис.
4. Після повернення в кабінет бот сам відкриє сторінку запису в чергу.
5. Бот спробує дійти до календаря потрібної послуги та центру.
6. Усі знайдені JSON-відповіді `GET /api/v2/...` буде збережено у `data/discovered-api`.

Не копіювати `x-csrf-token`, booking `token`, BankID-дані, Дія.Підпис або будь-які одноразові коди.

## Як Працює Монітор

Поточна логіка вже реалізована:

1. `monitor.py` завантажує налаштування.
2. `session_manager.py` відкриває Chrome і чекає завершення BankID.
3. `session_manager.py` відкриває `/cabinet/queue` і проходить read-only wizard до календаря.
4. `equeue.py` викликає `GET /equeue/days`.
5. `availability.py` дістає дати з `data[].date`.
6. Для кожної дати `equeue.py` викликає `GET /equeue/slots`.
7. `availability.py` дістає слоти з `data[].startTime` і `data[].stopTime`.
8. `monitor.py` формує повідомлення.
9. `notifier.py` відправляє його в Telegram або друкує в консоль.

Приклад повідомлення:

```text
Знайдено доступні слоти: 2026-06-30: 09:20:00-09:40:00, 14:00:00-14:20:00. Перевірте кабінет і запишіться вручну.
```

## Детальний План Далі

### Етап 1. Перевірити Локальний Запуск

Статус: треба зробити.

Дії:

1. Створити `.env` з `.env.example`.
2. Заповнити `MVS_SERVICE_ID`, `MVS_DEPARTMENT_ID`, `MVS_DEPARTMENT_LABEL`.
3. Запустити `mvsua-monitor`.
4. У Chrome-вікні бота пройти BankID.
5. Переконатися, що бот сам відкрив `/cabinet/queue`.
6. Переконатися, що у `data/discovered-api` зʼявилися JSON-відповіді.
7. Переконатися, що бот отримує `days` і `slots`.

Очікуваний результат:

```text
Якщо слоти є -> бот показує доступні дати й час.
Якщо слотів немає -> бот пише, що доступних слотів не знайдено.
Якщо cookie протух -> бот повідомляє про 401 або 403.
```

### Етап 2. Перевірити Реальний Формат Помилок

Статус: треба зробити.

Дії:

1. Запустити бота з валідною cookie.
2. Запустити бота з порожньою або старою cookie.
3. Подивитися, що саме повертає сервер при протухлій сесії.
4. За потреби додати точніші повідомлення для `401`, `403`, redirect або HTML замість JSON.

Очікуваний результат:

```text
Користувач чітко бачить: треба заново увійти в кабінет і оновити cookie.
```

### Етап 3. Додати Захист Від Повторних Сповіщень

Статус: треба зробити.

Поточна поведінка: якщо слоти є, бот може повідомляти на кожній перевірці.

Потрібна поведінка:

1. Запамʼятовувати останній набір слотів.
2. Надсилати сповіщення тільки коли:
   - зʼявився новий слот;
   - змінився список слотів;
   - слоти зникли після того, як були доступні.
3. Зберігати стан у `data/last_seen_slots.json`.

Очікуваний результат:

```text
Бот не спамить однаковим повідомленням кожні 60 секунд.
```

### Етап 4. Налаштувати Telegram

Статус: треба зробити.

Дії:

1. Створити Telegram bot через BotFather.
2. Отримати `TELEGRAM_BOT_TOKEN`.
3. Дізнатися `TELEGRAM_CHAT_ID`.
4. Записати обидва значення в `.env`.
5. Перевірити тестове повідомлення.

Очікуваний результат:

```text
Коли зʼявляється слот, повідомлення миттєво приходить у Telegram.
```

### Етап 5. Зробити Одноразову Команду Перевірки

Статус: бажано зробити.

Зараз основна команда запускає нескінченний цикл. Варто додати режим:

```bash
mvsua-monitor-once
```

Він має:

1. Один раз виконати `days`.
2. Один раз виконати `slots`.
3. Вивести результат.
4. Завершитися.

Це зручно для тестів і діагностики.

### Етап 6. Додати Підтримку Кількох Сервісних Центрів

Статус: опціонально.

Поточна конфігурація працює для одного `departmentId`.

Майбутній формат може бути таким:

```env
MVS_TARGETS_JSON=[
  {"serviceId":43,"departmentId":93,"label":"ТСЦ МВС № 5342"},
  {"serviceId":43,"departmentId":94,"label":"Інший ТСЦ"}
]
```

Очікуваний результат:

```text
Бот перевіряє кілька центрів і в повідомленні пише, де саме є слот.
```

### Етап 7. Підготувати Довготривалий Запуск

Статус: опціонально.

Можливі варіанти:

1. Запуск у звичайному терміналі.
2. Запуск через `launchd` на macOS.
3. Запуск через `systemd` на Linux/VPS.
4. Запуск у Docker.

Важливо:

```text
Cookie все одно доведеться оновлювати вручну після протухання сесії.
```

### Етап 8. Документувати Обмеження

Статус: треба підтримувати постійно.

Обмеження проєкту:

1. Бот залежить від поточної авторизованої cookie.
2. Якщо МВС змінить API або формат JSON, парсер треба оновити.
3. Бот не вирішує CAPTCHA, не генерує booking token, не повторює `POST /booking`.
4. Бот не гарантує, що слот залишиться доступним до моменту ручного запису.
5. Частота перевірки має бути помірною, наприклад 60 секунд або більше.

## Правила Для Людей Та Інших ШІ

Не робити:

```text
Не додавати POST /api/v2/booking.
Не автоматизувати бронювання.
Не обходити Дія.Підпис, BankID, CAPTCHA або інші захисні механізми.
Не зберігати cookie, CSRF або token у README, тестах чи git.
Не робити агресивний polling.
```

Дозволено робити:

```text
Виконувати GET /equeue/days після ручної авторизації.
Виконувати GET /equeue/slots для знайдених дат.
Парсити JSON-відповіді.
Надсилати сповіщення користувачу.
Просити користувача записатися вручну.
```

## Перевірка Коду

Синтаксична перевірка:

```bash
python3 -m compileall src tests
```

Швидка ручна перевірка парсера:

```bash
PYTHONPATH=src python3 - <<'PY'
from mvsuabot.availability import parse_days, parse_slots, summarize_slots

days_payload = {"data": [{"date": "2026-06-30T00:00:00"}]}
slots_payload = {
    "data": [
        {"startTime": "09:20:00", "stopTime": "09:40:00"},
        {"startTime": "14:00:00", "stopTime": "14:20:00"},
    ]
}

days = parse_days(days_payload)
slots = []
for day in days:
    slots.extend(parse_slots(slots_payload, date=day))

print(summarize_slots(slots).summary)
PY
```

Очікуваний результат:

```text
Знайдено доступні слоти: 2026-06-30: 09:20:00-09:40:00, 14:00:00-14:20:00.
```

## Додаткові Документи

Документи з аналізу браузерного трафіку:

```text
docs/http-analysis-uk.md
docs/provided-requests-analysis-uk.md
```

Вони пояснюють, як знаходилися запити через DevTools і чому booking endpoint не використовується.
