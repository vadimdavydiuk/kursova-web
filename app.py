import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "pizza.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "pizza-coursework-key")

db = SQLAlchemy(app)

SIZES = {
    "small": ("Мала, 25 см", 0.85),
    "medium": ("Середня, 30 см", 1.0),
    "large": ("Велика, 35 см", 1.3),
}

STATUSES = {
    "new": "Нове",
    "cooking": "Готується",
    "delivering": "В дорозі",
    "done": "Доставлено",
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class Pizza(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    badge = db.Column(db.String(40))
    items = db.relationship("OrderItem", backref="pizza", lazy=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    comment = db.Column(db.Text)
    total = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="new", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    pizza_id = db.Column(db.Integer, db.ForeignKey("pizza.id"), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Увійдіть як адміністратор.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def cart_items():
    raw = session.get("cart", {})
    result = []
    for key, qty in raw.items():
        pizza_id, size = key.split(":")
        pizza = db.session.get(Pizza, int(pizza_id))
        if not pizza or size not in SIZES or qty < 1:
            continue
        unit = round(pizza.price * SIZES[size][1])
        result.append({
            "key": key,
            "pizza": pizza,
            "size": size,
            "size_label": SIZES[size][0],
            "quantity": qty,
            "unit": unit,
            "line": unit * qty,
        })
    return result


def cart_total(items=None):
    items = cart_items() if items is None else items
    return sum(item["line"] for item in items)


def cart_count():
    return sum(session.get("cart", {}).values())


@app.context_processor
def inject_cart():
    return {"cart_count": cart_count(), "statuses": STATUSES}


@app.route("/")
def home():
    pizzas = Pizza.query.limit(4).all()
    return render_template("index.html", pizzas=pizzas)


@app.route("/menu")
def menu():
    category = request.args.get("category", "all")
    query = Pizza.query
    if category != "all":
        query = query.filter_by(category=category)
    return render_template("menu.html", pizzas=query.all(), category=category, sizes=SIZES)


@app.route("/cart/add", methods=["POST"])
def add_to_cart():
    pizza_id = request.form.get("pizza_id", type=int)
    size = request.form.get("size", "medium")
    quantity = request.form.get("quantity", type=int) or 1
    pizza = db.session.get(Pizza, pizza_id) if pizza_id else None
    if not pizza or size not in SIZES or quantity < 1 or quantity > 10:
        flash("Не вдалося додати піцу до кошика.", "error")
        return redirect(url_for("menu"))

    cart = session.setdefault("cart", {})
    key = f"{pizza.id}:{size}"
    cart[key] = min(10, cart.get(key, 0) + quantity)
    session["cart"] = cart
    session.modified = True
    flash(f"«{pizza.name}» додано до кошика.", "success")
    return redirect(request.referrer or url_for("menu"))


@app.route("/cart/remove", methods=["POST"])
def remove_from_cart():
    key = request.form.get("key", "")
    cart = session.get("cart", {})
    cart.pop(key, None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/cart")
def cart():
    items = cart_items()
    return render_template("cart.html", items=items, total=cart_total(items))


@app.route("/checkout", methods=["POST"])
def checkout():
    items = cart_items()
    if not items:
        flash("Кошик порожній.", "error")
        return redirect(url_for("menu"))

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    comment = request.form.get("comment", "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())

    if len(name) < 2 or len(address) < 5 or len(digits) < 10:
        flash("Перевірте ім’я, телефон і адресу доставки.", "error")
        return redirect(url_for("cart"))

    order = Order(
        name=name,
        phone=phone,
        address=address,
        comment=comment,
        total=cart_total(items),
    )
    db.session.add(order)
    db.session.flush()
    for item in items:
        db.session.add(OrderItem(
            order_id=order.id,
            pizza_id=item["pizza"].id,
            size=item["size"],
            quantity=item["quantity"],
            price=item["unit"],
        ))
    db.session.commit()
    session["cart"] = {}
    session.modified = True
    return redirect(url_for("order_done", order_id=order.id))


@app.route("/order/<int:order_id>")
def order_done(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return redirect(url_for("home"))
    return render_template("order.html", order=order, sizes=SIZES)


@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    message = request.form.get("message", "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(name) < 2 or len(digits) < 10 or len(message) < 5:
        flash("Заповніть усі поля форми зворотного зв’язку.", "error")
        return redirect(url_for("home") + "#contact")

    db.session.add(ContactMessage(name=name, phone=phone, message=message))
    db.session.commit()
    flash("Дякуємо, повідомлення надіслано.", "success")
    return redirect(url_for("home") + "#contact")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_name = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(login=login_name).first()
        if not user or not user.is_admin or not check_password_hash(user.password, password):
            flash("Невірний логін або пароль.", "error")
            return redirect(url_for("login"))
        session["is_admin"] = True
        session["admin_name"] = user.name
        return redirect(url_for("admin"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("is_admin", None)
    session.pop("admin_name", None)
    flash("Ви вийшли з панелі адміністратора.", "success")
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template("admin.html", orders=orders, messages=messages, sizes=SIZES)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_status(order_id):
    order = db.get_or_404(Order, order_id)
    status = request.form.get("status", "")
    if status in STATUSES:
        order.status = status
        db.session.commit()
        flash(f"Статус замовлення №{order.id} оновлено.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
@admin_required
def delete_order(order_id):
    order = db.get_or_404(Order, order_id)
    db.session.delete(order)
    db.session.commit()
    flash(f"Замовлення №{order_id} видалено.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
@admin_required
def delete_message(message_id):
    message = db.get_or_404(ContactMessage, message_id)
    db.session.delete(message)
    db.session.commit()
    flash("Повідомлення видалено.", "success")
    return redirect(url_for("admin"))


def seed():
    if User.query.filter_by(login="admin").first() is None:
        db.session.add(User(
            name="Адміністратор",
            login="admin",
            password=generate_password_hash("admin123"),
            is_admin=True,
        ))
    if Pizza.query.first() is None:
        menu_seed = [
            ("Маргарита", "Томатний соус, моцарела, базилік.", "classic", 189, "Класика"),
            ("Пепероні", "Томатний соус, моцарела, пікантна пепероні.", "meat", 239, "Хіт"),
            ("Чотири сири", "Моцарела, дорблю, пармезан, чедер.", "cheese", 259, None),
            ("Гавайська", "Моцарела, курка, ананас, томатний соус.", "classic", 229, None),
            ("Барбекю", "Соус барбекю, яловичина, бекон, червона цибуля.", "meat", 269, "Ситно"),
            ("Діабло", "Гострий соус, пепероні, халапеньйо, моцарела.", "spicy", 249, "Гостра"),
            ("Вегетаріанська", "Цукіні, перець, томати, оливки, моцарела.", "veggie", 219, None),
            ("Карбонара", "Вершковий соус, бекон, яйце, пармезан.", "cheese", 259, None),
        ]
        for name, description, category, price, badge in menu_seed:
            db.session.add(Pizza(
                name=name,
                description=description,
                category=category,
                price=price,
                badge=badge,
            ))
    db.session.commit()


with app.app_context():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db.create_all()
    seed()


if __name__ == "__main__":
    app.run(debug=True)
