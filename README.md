# ПіцаДім

Навчальний вебзастосунок доставки піци на Flask, SQLAlchemy та SQLite.

## Запуск у PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
# Пароль вводиться приховано й не записується у файл.
$env:ADMIN_PASSWORD = (python -c "import getpass; print(getpass.getpass('Admin password: '))")
python app.py
```

Відкрити http://127.0.0.1:5000. Логін адміністратора — `admin`.
`ADMIN_PASSWORD` створює адміністратора лише якщо такого облікового запису ще немає.
Наявні облікові записи та робоча база під час оновлення коду не змінюються.
Якщо наявний адміністратор має демонстраційний пароль, його потрібно окремо змінити.
Для постійної роботи задайте власний сталий `SECRET_KEY` у середовищі сервера.
Без нього генерується випадковий ключ на кожен запуск; попередні сесії завершаться.
Не додавайте паролі, `.env`, `venv/` та `instance/` у репозиторій.

## Перевірки

```powershell
python tests.py
node price_tests.js
```

`tests.py` запускає `unit_tests.py` (прямі тести `cart_items`, `cart_total`,
`unit_price`, `validate_checkout` та окремі HTTP-тести безпеки), після них —
24 попередні HTTP-сценарії з `integration_tests.py`.
Тестова SQLite працює у пам’яті, `instance/pizza.db` не змінюється.
`price_tests.js` виконує справжній `main.js` для 240 комбінацій меню.

Фактичний вивід перевірок: [Python](docs/test-results.txt),
[JavaScript](docs/price-results.txt). Приклад інтерфейсу за ширини 390 px:
[мобільне меню](docs/mobile-menu.png).

Ціна одиниці округлюється до гривні (0,5 вгору), потім множиться на кількість.
Усі POST-форми містять CSRF-токен, який сервер порівнює з токеном сесії.
Замовлення доступне сесії, що його створила (останні 50 замовлень), та адміністратору.
