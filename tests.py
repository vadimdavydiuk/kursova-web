"""Автоматичні функціональні тести застосунку «ПіцаДім».

Запуск (з папки проєкту, де лежать app.py, templates/ і static/):
    python tests.py

Скрипт копіює проєкт у тимчасову папку, тому робоча база даних
instance/pizza.db НЕ змінюється. Використовується тестовий клієнт Flask.
"""
import os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="pizza_test_")
shutil.copy(os.path.join(HERE, "app.py"), TMP)
for folder in ("templates", "static"):
    shutil.copytree(os.path.join(HERE, folder), os.path.join(TMP, folder))
sys.path.insert(0, TMP)

from app import app, db, Order, OrderItem, ContactMessage, Pizza  # noqa: E402

app.config["TESTING"] = True
R = []

def rec(n, scen, expected, actual, ok): R.append(dict(n=n,scenario=scen,expected=expected,actual=actual,ok=bool(ok)))
def cards(html): return len(re.findall(r'<article class="card">', html))
def flashes(html): return re.findall(r'<p class="flash flash-\w+">(.*?)</p>', html)

with app.test_client() as c:
    r=c.get("/"); h=r.get_data(as_text=True)
    rec(1,"Відкриття головної сторінки (GET /)","Код 200, показано 4 піци",f"Код {r.status_code}, карток: {cards(h)}", r.status_code==200 and cards(h)==4)
    r=c.get("/menu"); h=r.get_data(as_text=True)
    rec(2,"Відкриття меню (GET /menu)","Код 200, показано 8 піц",f"Код {r.status_code}, карток: {cards(h)}", r.status_code==200 and cards(h)==8)
    r=c.get("/menu?category=spicy"); h=r.get_data(as_text=True)
    rec(3,"Фільтр категорії «Гострі»","Показано 1 піцу (Діабло)",f"Карток: {cards(h)}, Діабло: {'Діабло' in h}", cards(h)==1 and 'Діабло' in h)
    r=c.post("/cart/add",data={"pizza_id":2,"size":"large","quantity":2},follow_redirects=True); h=r.get_data(as_text=True)
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(4,"Додавання піци до кошика (Пепероні, велика, 2 шт.)","У сесії ключ 2:large зі значенням 2",f"Кошик: {cart}", cart=={"2:large":2})
    r=c.get("/cart"); h=r.get_data(as_text=True)
    rec(5,"Розрахунок суми: 239 грн × 1,3 × 2","До сплати 622 грн",f"Є «622 грн»: {'622 грн' in h}", '622 грн' in h)
    before=dict(cart)
    r=c.post("/cart/add",data={"pizza_id":2,"size":"huge","quantity":1},follow_redirects=True); h=r.get_data(as_text=True)
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(6,"Додавання з неіснуючим розміром («huge»)","Відмова, кошик не змінюється",f"Повідомлення: {flashes(h)[:1]}; кошик без змін: {cart==before}", cart==before and len(flashes(h))>0)
    r=c.post("/cart/add",data={"pizza_id":2,"size":"large","quantity":11},follow_redirects=True)
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(7,"Кількість більша за ліміт (11 шт.)","Відмова, кошик не змінюється",f"Кошик: {cart}", cart==before)
    c.post("/cart/add",data={"pizza_id":2,"size":"large","quantity":9})
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(8,"Накопичення кількості понад 10 (2 + 9)","Кількість обмежується до 10",f"Кошик: {cart}", cart.get("2:large")==10)
    c.post("/cart/remove",data={"key":"2:large"})
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(9,"Видалення позиції з кошика","Кошик порожній",f"Кошик: {cart}", cart=={})
    r=c.post("/checkout",data={"name":"Тест","phone":"+380671234567","address":"вул. Тестова, 1"},follow_redirects=False)
    rec(10,"Оформлення замовлення з порожнім кошиком","Перенаправлення на меню, замовлення не створюється",f"Код {r.status_code}, перенаправлення на {r.headers.get('Location')}, замовлень: {Order.query.count()}", r.status_code==302 and r.headers['Location'].endswith("/menu") and Order.query.count()==0)
    c.post("/cart/add",data={"pizza_id":1,"size":"medium","quantity":1})
    r=c.post("/checkout",data={"name":"Т","phone":"123","address":"вул"},follow_redirects=False)
    rec(11,"Оформлення з некоректними даними (ім’я, телефон, адреса)","Відмова, замовлення не створюється",f"Код {r.status_code}, перенаправлення на {r.headers.get('Location')}, замовлень: {Order.query.count()}", Order.query.count()==0 and r.headers['Location'].endswith("/cart"))
    r=c.post("/checkout",data={"name":"Олена Коваль","phone":"+380671234567","address":"вул. Соборна, 25","comment":"Домофон 14"},follow_redirects=False)
    o=Order.query.first()
    with c.session_transaction() as s: cart=dict(s.get("cart",{}))
    rec(12,"Оформлення коректного замовлення (Маргарита, середня, 1 шт.)","Створено замовлення зі статусом «new», сумою 189 грн, кошик очищено",f"Замовлень: {Order.query.count()}, статус: {o.status}, сума: {o.total}, позицій: {len(o.items)}, кошик: {cart}", o and o.status=="new" and o.total==189 and len(o.items)==1 and cart=={})
    oid=o.id
    r=c.get(f"/order/{oid}")
    rec(13,"Сторінка підтвердження замовлення","Код 200, відображається номер і сума",f"Код {r.status_code}, є «189 грн»: {'189 грн' in r.get_data(as_text=True)}", r.status_code==200 and '189 грн' in r.get_data(as_text=True))
    r=c.get("/admin",follow_redirects=False)
    rec(14,"Доступ до /admin без авторизації","Перенаправлення на /login",f"Код {r.status_code}, перенаправлення на {r.headers.get('Location')}", r.status_code==302 and r.headers['Location'].endswith("/login"))
    r=c.post("/admin/orders/%d/status"%oid,data={"status":"done"},follow_redirects=False)
    rec(15,"Зміна статусу без авторизації","Відмова, статус не змінюється",f"Код {r.status_code}, статус: {db.session.get(Order,oid).status}", db.session.get(Order,oid).status=="new")
    r=c.post("/login",data={"login":"admin","password":"wrong"},follow_redirects=True)
    rec(16,"Вхід з хибним паролем","Повідомлення про помилку, доступу немає",f"Повідомлення: {flashes(r.get_data(as_text=True))[:1]}", "Невірний" in r.get_data(as_text=True))
    r=c.post("/login",data={"login":"admin","password":"admin123"},follow_redirects=True)
    rec(17,"Вхід з правильними обліковими даними","Відкривається адмінпанель",f"Код {r.status_code}, є заголовок «Замовлення»: {'Замовлення' in r.get_data(as_text=True)}", r.status_code==200 and "Замовлення" in r.get_data(as_text=True))
    c.post("/admin/orders/%d/status"%oid,data={"status":"cooking"})
    db.session.expire_all(); st=db.session.get(Order,oid).status
    rec(18,"Зміна статусу замовлення на «Готується»","Статус у БД: cooking",f"Статус у БД: {st}", st=="cooking")
    c.post("/admin/orders/%d/status"%oid,data={"status":"hacked"})
    db.session.expire_all(); st=db.session.get(Order,oid).status
    rec(19,"Зміна статусу на неіснуюче значення","Статус не змінюється",f"Статус у БД: {st}", st=="cooking")
    r=c.post("/contact",data={"name":"А","phone":"1","message":"ок"},follow_redirects=False)
    rec(20,"Форма зворотного зв’язку з некоректними даними","Повідомлення не зберігається",f"Повідомлень у БД: {ContactMessage.query.count()}", ContactMessage.query.count()==0)
    r=c.post("/contact",data={"name":"Максим","phone":"+380977776655","message":"Чи є алергени у піці?"},follow_redirects=False)
    rec(21,"Форма зворотного зв’язку з коректними даними","Повідомлення збережено в БД",f"Повідомлень у БД: {ContactMessage.query.count()}", ContactMessage.query.count()==1)
    c.post("/admin/orders/%d/delete"%oid)
    rec(22,"Видалення замовлення адміністратором","Замовлення та його позиції видалено (каскадно)",f"Замовлень: {Order.query.count()}, позицій: {OrderItem.query.count()}", Order.query.count()==0 and OrderItem.query.count()==0)
    mid=ContactMessage.query.first().id
    c.post("/admin/messages/%d/delete"%mid)
    rec(23,"Видалення повідомлення адміністратором","Повідомлення видалено з БД",f"Повідомлень: {ContactMessage.query.count()}", ContactMessage.query.count()==0)
    r=c.post("/logout",follow_redirects=False); r2=c.get("/admin",follow_redirects=False)
    rec(24,"Вихід із панелі адміністратора","Доступ до /admin знову закритий",f"Код {r2.status_code}, перенаправлення на {r2.headers.get('Location')}", r2.status_code==302)

print()
print("Результат: пройдено %d з %d" % (sum(x["ok"] for x in R), len(R)))
for x in R:
    print(("OK   " if x["ok"] else "FAIL ") + "%2d. %s" % (x["n"], x["scenario"]))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if all(x["ok"] for x in R) else 1)
