import os
from datetime import datetime
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-dev-temporaria")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///local.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================
# MODELO DO BANCO
# =========================

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    yampi_id = db.Column(db.String(100), unique=True, nullable=False)

    customer_name = db.Column(db.String(255))
    customer_phone = db.Column(db.String(100))
    customer_email = db.Column(db.String(255))
    customer_document = db.Column(db.String(100))

    customer_address = db.Column(db.Text)

    items_json = db.Column(db.JSON)

    total = db.Column(db.Float, default=0)
    delivery_fee = db.Column(db.Float, default=0)

    payment_status = db.Column(db.String(100))
    payment_method = db.Column(db.String(100))

    order_status = db.Column(db.String(100), default="novo")

    local_payment_method = db.Column(db.String(100))

    notes = db.Column(db.Text)

    raw_json = db.Column(db.JSON)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========================
# LOGIN
# =========================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username")
        password = request.form.get("password")

        admin_user = os.getenv("ADMIN_USER", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "123456")

        if user == admin_user and password == admin_password:
            session["logged_in"] = True
            session["user"] = user
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Usuário ou senha incorretos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================
# PAINEL
# =========================

@app.route("/")
@login_required
def dashboard():
    orders = Order.query.order_by(Order.created_at.desc()).limit(100).all()
    return render_template("dashboard.html", orders=orders)


# =========================
# YAMPI
# =========================

def yampi_headers():
    return {
        "User-Token": os.getenv("YAMPI_USER_TOKEN", ""),
        "User-Secret-Key": os.getenv("YAMPI_SECRET_KEY", ""),
        "Content-Type": "application/json",
    }


def get_yampi_base_url():
    alias = os.getenv("YAMPI_ALIAS", "").strip()
    return f"https://api.dooki.com.br/v2/{alias}"

def extract_text(value):

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, dict):

        return (
            value.get("formated_number")
            or value.get("formatted_number")
            or value.get("full_number")
            or value.get("number")
            or value.get("alias")
            or value.get("name")
            or value.get("status")
            or ""
        )

    return str(value)

def extract_order_items(order_data):

    possible_keys = [
        "products",
        "items",
        "order_products",
        "cart_items"
    ]

    products_data = []

    for key in possible_keys:

        value = order_data.get(key)

        if isinstance(value, dict):
            products_data = value.get("data", []) or []

        elif isinstance(value, list):
            products_data = value

        if products_data:
            break

    items = []

    for product in products_data:

        quantity = (
            product.get("quantity")
            or product.get("amount")
            or product.get("qty")
            or 1
        )

        sku_data = {}

        if isinstance(product.get("sku"), dict):
            sku_data = product.get("sku", {}).get("data", {}) or {}

        product_name = (
            sku_data.get("title")
            or sku_data.get("name")
            or product.get("title")
            or product.get("name")
            or product.get("product_name")
            or "Produto"
        )

        price = (
            product.get("price_sale")
            or product.get("price")
            or product.get("value")
            or product.get("total")
            or 0
        )

        try:
            price = float(price)
        except:
            price = 0

        customizations = []

        customizations_raw = product.get("customizations")

        if isinstance(customizations_raw, dict):
            customizations_data = customizations_raw.get("data", []) or []
        elif isinstance(customizations_raw, list):
            customizations_data = customizations_raw
        else:
            customizations_data = []

        for customization in customizations_data:

            value = (
                customization.get("value")
                or customization.get("name")
                or customization.get("title")
                or customization.get("description")
            )

            if value:
                customizations.append(str(value))

        items.append({
            "name": product_name,
            "quantity": quantity,
            "price": price,
            "customizations": customizations
        })

    return items

@app.route("/api/yampi/test")
@login_required
def test_yampi():
    try:
        url = f"{get_yampi_base_url()}/orders"
        response = requests.get(url, headers=yampi_headers(), timeout=20)

        return jsonify({
            "status_code": response.status_code,
            "ok": response.ok,
            "preview": response.text[:1000]
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/yampi/sync")
@login_required
def sync_yampi_orders():
    try:

        url = f"{get_yampi_base_url()}/orders"

        response = requests.get(
            url,
            headers=yampi_headers(),
            timeout=20
        )

        if not response.ok:
            return jsonify({
                "ok": False,
                "status_code": response.status_code,
                "error": response.text
            }), response.status_code

        data = response.json()

        orders = data.get("data", [])

        saved = 0
        saved_ids = []

        for item in orders:

            yampi_id = str(item.get("id") or "")

            if not yampi_id:
                continue
            detail_item = item

            try:
                detail_url = f"{get_yampi_base_url()}/orders/{yampi_id}"
                detail_response = requests.get(
                    detail_url,
                    headers=yampi_headers(),
                    timeout=20
                )

                if detail_response.ok:
                    detail_json = detail_response.json()
                    detail_item = detail_json.get("data") or item

            except:
                detail_item = item
            existing = Order.query.filter_by(
                yampi_id=yampi_id
            ).first()

            if existing:
                continue

            customer = {}

            if isinstance(item.get("customer"), dict):
                customer = item.get(
                    "customer",
                    {}
                ).get("data", {}) or {}

            payment = {}

            if isinstance(item.get("payment"), dict):
                payment = item.get(
                    "payment",
                    {}
                ).get("data", {}) or {}

            shipping = {}

            if isinstance(item.get("shipping_address"), dict):
                shipping = item.get(
                    "shipping_address",
                    {}
                ).get("data", {}) or {}

            customer_name = (
                customer.get("name")
                or item.get("customer_name")
                or "Cliente não identificado"
            )

            customer_phone = extract_text(
                customer.get("phone")
                or customer.get("whatsapp")
                or item.get("phone")
                or ""
            )

            payment_status = extract_text(
                payment.get("status")
                or item.get("payment_status")
                or item.get("status")
                or ""
            )

            payment_method = extract_text(
                item.get("payment_method")
                or payment.get("method")
                or ""
            )

            total = (
                item.get("total")
                or item.get("value_total")
                or item.get("value_total_paid")
                or item.get("value_products")
                or 0
            )

            try:
                total = float(total)
            except:
                total = 0

            delivery_fee = (
                detail_item.get("value_shipment")
                or detail_item.get("shipment_cost")
                or detail_item.get("value_shipping")
                or detail_item.get("shipping_price")
                or 0
            )

            try:
                delivery_fee = float(delivery_fee)
            except:
                delivery_fee = 0

            street = shipping.get("street", "")
            number = shipping.get("number", "")
            neighborhood = shipping.get("neighborhood", "")
            city = shipping.get("city", "")
            state = shipping.get("state", "")
            zipcode = shipping.get("zipcode", "")

            customer_address = (
                f"{street}, {number}\n"
                f"{neighborhood}\n"
                f"{city} - {state}\n"
                f"CEP: {zipcode}"
            )
                        
            items = []

            try:

                items_url = f"{get_yampi_base_url()}/orders/{yampi_id}/items"

                items_response = requests.get(
                    items_url,
                    headers=yampi_headers(),
                    timeout=20
                )

                if items_response.ok:

                    items_json = items_response.json()

                    products_data = items_json.get("data", [])

                    for product in products_data:

                        quantity = product.get("quantity", 1)

                        sku_data = product.get("sku", {}).get("data", {})

                        product_name = (
                            sku_data.get("title")
                            or product.get("name")
                            or "Produto"
                        )

                        price = (
                            product.get("price")
                            or sku_data.get("price_sale")
                            or 0
                        )

                        customizations = []

                        customizations_data = product.get(
                            "customizations",
                            []
                        )

                        for customization in customizations_data:

                            value = (
                                customization.get("value")
                                or customization.get("name")
                                or customization.get("title")
                            )

                            if value:
                                customizations.append(str(value))

                        items.append({
                            "name": product_name,
                            "quantity": quantity,
                            "price": price,
                            "customizations": customizations
                        })

            except Exception as e:

                print("ERRO AO BUSCAR ITENS:", e)

            order = Order(
                yampi_id=yampi_id,

                customer_name=customer_name,
                customer_phone=customer_phone,

                customer_email=customer.get("email") or "",
                customer_document=extract_text(
                    customer.get("document")
                    or customer.get("cpf")
                    or item.get("document")
                    or item.get("customer_document")
                    or item.get("cpf")
                    or ""
                ),
                customer_address=customer_address,

                items_json=items,

                total=total,
                delivery_fee=delivery_fee,

                payment_status=payment_status,
                payment_method=payment_method,

                order_status="novo",

                raw_json=detail_item,
            )

            db.session.add(order)
            db.session.flush()

            saved += 1
            saved_ids.append(order.id)

        db.session.commit()

        return jsonify({
            "ok": True,
            "saved": saved,
            "saved_ids": saved_ids,
            "total_received": len(orders)
        })

    except Exception as e:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
# =========================
# PEDIDOS
# =========================

@app.route("/api/orders")
@login_required
def api_orders():
    orders = Order.query.order_by(Order.created_at.desc()).limit(100).all()

    return jsonify([
        {
            "id": order.id,
            "yampi_id": order.yampi_id,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "total": order.total,
            "payment_status": order.payment_status,
            "order_status": order.order_status,
            "local_payment_method": order.local_payment_method,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        for order in orders
    ])


@app.route("/api/orders/<int:order_id>/status", methods=["POST"])
@login_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json() or {}

    order.order_status = data.get("order_status", order.order_status)
    order.local_payment_method = data.get("local_payment_method", order.local_payment_method)
    order.notes = data.get("notes", order.notes)
    order.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({"ok": True})


@app.route("/print/<int:order_id>")
@login_required
def print_order(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("print.html", order=order)


# =========================
# INICIAR BANCO
# =========================

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Banco criado com sucesso.")


with app.app_context():
    db.create_all()


# =========================
# RODAR LOCAL / RENDER
# =========================
@app.route("/debug/yampi/<yampi_id>")
@login_required
def debug_yampi(yampi_id):

    endpoints = [
        f"/orders/{yampi_id}",
        f"/orders/{yampi_id}/items",
        f"/orders/{yampi_id}/products",
        f"/orders/{yampi_id}/order-products",
        f"/orders/{yampi_id}/details",
    ]

    results = {}

    for endpoint in endpoints:

        try:

            url = f"{get_yampi_base_url()}{endpoint}"

            response = requests.get(
                url,
                headers=yampi_headers(),
                timeout=20
            )

            try:
                body = response.json()
            except:
                body = response.text

            results[endpoint] = {
                "status": response.status_code,
                "body": body
            }

        except Exception as e:

            results[endpoint] = {
                "error": str(e)
            }

    return jsonify(results)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 6060))
    app.run(host="0.0.0.0", port=port, debug=True)