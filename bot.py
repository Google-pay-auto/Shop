"""
bot.py — سيرفر الموقع + بوت التلجرام بملف واحد كامل (نسخة v2)

المتطلبات (ثبّتها مرة واحدة):
    pip install flask requests

كيفية التشغيل:
    1. عدّل القيم بأعلى الملف (قسم الإعدادات).
    2. حط صورة باركود شام كاش بمجلد assets باسم sham_barcode.png (اختياري).
    3. شغّل: python bot.py
    4. افتح المتصفح على: http://localhost:5000
"""

import json
import os
import threading
import time
import uuid

import requests
from flask import Flask, jsonify, request, send_from_directory

# ============================== الإعدادات ==============================

BRAND_NAME = "متجر التوكنز"

TELEGRAM_BOT_TOKEN = "8868682615:AAEdr1RY9bToUKz2KuWIstIJH-MK8_YYhpk"
ADMIN_CHAT_ID = "5437487652"
ADMIN_USER_ID = ""  # اختياري

# بيانات شام كاش
SHAM_CASH_NUMBER = "6bf82cecf71637705f0cf2f728da48e4"
SHAM_CASH_NAME = "ريه الديوان"
SHAM_BARCODE_IMAGE = "assets/sham_barcode.png"  # حط الصورة الحقيقية بهاد المسار

# بيانات سيريتل كاش
SYRIATEL_CASH_NUMBER = "49188726"
SYRIATEL_CASH_NAME = ""  

# سعر صرف الدولار مقابل الليرة السورية — عدّله وقت ما بدك
EXCHANGE_RATE_USD_TO_SYP = 13000

PORT = 5000

# باقات التوكنز — usd_price هو السعر الأساسي بالدولار
PACKAGES = [
    {"id": "p1", "name": "الفئة الأولى", "tokens": 130000, "usd_price": 10},
    {"id": "p2", "name": "الفئة الثانية", "tokens": 270000, "usd_price": 20},
    {"id": "p3", "name": "الفئة الثالثة", "tokens": 420000, "usd_price": 30},
    {"id": "p4", "name": "الفئة الرابعة", "tokens": 850000, "usd_price": 60},
]

# =========================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "orders.json")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__, static_folder=BASE_DIR)
db_lock = threading.Lock()

METHOD_LABEL = {
    "sham_usd": "Sham Cash (USD)",
    "sham_syp": "Sham Cash (SYP)",
    "syriatel": "Syriatel Cash",
    "binance": "Binance",
}


# ------------------------------ تخزين بسيط ------------------------------

def read_orders():
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def write_orders(orders):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)


def create_order(order):
    with db_lock:
        orders = read_orders()
        orders.append(order)
        write_orders(orders)
    return order


def get_order(order_id):
    return next((o for o in read_orders() if o["id"] == order_id), None)


def update_order(order_id, patch):
    with db_lock:
        orders = read_orders()
        for o in orders:
            if o["id"] == order_id:
                o.update(patch)
                write_orders(orders)
                return o
    return None


# ------------------------------ بوت تلجرام ------------------------------

def tg_call(method, payload):
    if not TELEGRAM_BOT_TOKEN or "ضع_" in TELEGRAM_BOT_TOKEN:
        print("⚠️  لم تضع توكن بوت التلجرام بعد — تجاهل إرسال الرسالة.")
        return None
    try:
        r = requests.post(f"{TELEGRAM_API}/{method}", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print("خطأ بالاتصال مع تلجرام:", e)
        return None


def send_approval_request(order):
    text = (
        "🧾 *طلب شحن توكنز جديد*\n\n"
        f"رقم الطلب: `{order['id']}`\n"
        f"الباقة: {order['packageName']} ({order['tokens']} توكن)\n"
        f"طريقة الدفع: {METHOD_LABEL.get(order['method'], order['method'])}\n"
        f"المبلغ المطلوب: {order['amountText']}\n"
        f"رمز العملية: `{order['txCode']}`\n"
        "\nالرجاء التحقق من العملية، ثم الموافقة أو الرفض:"
    )

    result = tg_call(
        "sendMessage",
        {
            "chat_id": ADMIN_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ موافقة", "callback_data": f"approve_{order['id']}"},
                        {"text": "❌ رفض", "callback_data": f"reject_{order['id']}"},
                    ]
                ]
            },
        },
    )
    if result and result.get("ok"):
        msg = result["result"]
        update_order(order["id"], {
            "adminMessageId": msg["message_id"],
            "adminChatId": msg["chat"]["id"],
        })


def notify_player_id(order):
    text = (
        "🎮 *تم إدخال رقم اللاعب*\n\n"
        f"رقم الطلب: `{order['id']}`\n"
        f"رقم اللاعب: `{order['playerId']}`\n\n"
        f"الرجاء شحن {order['tokens']} توكن لهذا الحساب."
    )
    tg_call("sendMessage", {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    })


def handle_callback_query(query):
    data = query.get("data", "")
    if "_" not in data:
        return
    action, order_id = data.split("_", 1)
    if action not in ("approve", "reject"):
        return

    from_user_id = str(query.get("from", {}).get("id", ""))
    if ADMIN_USER_ID and from_user_id != str(ADMIN_USER_ID):
        tg_call("answerCallbackQuery", {
            "callback_query_id": query["id"],
            "text": "غير مصرح لك بهذا الإجراء",
            "show_alert": True,
        })
        return

    order = get_order(order_id)
    if not order:
        tg_call("answerCallbackQuery", {
            "callback_query_id": query["id"],
            "text": "الطلب غير موجود",
            "show_alert": True,
        })
        return

    if order["status"] != "pending":
        tg_call("answerCallbackQuery", {
            "callback_query_id": query["id"],
            "text": "تم اتخاذ قرار بهذا الطلب مسبقًا",
            "show_alert": True,
        })
        return

    new_status = "approved" if action == "approve" else "rejected"
    update_order(order_id, {"status": new_status})

    decision_text = "✅ تمت الموافقة على الطلب" if new_status == "approved" else "❌ تم رفض الطلب"

    message = query.get("message", {})
    if message:
        original_text = message.get("text", "")
        tg_call("editMessageText", {
            "chat_id": message["chat"]["id"],
            "message_id": message["message_id"],
            "text": f"{original_text}\n\n*{decision_text}*",
            "parse_mode": "Markdown",
        })

    tg_call("answerCallbackQuery", {
        "callback_query_id": query["id"],
        "text": decision_text,
    })


def telegram_polling_loop():
    if not TELEGRAM_BOT_TOKEN or "ضع_" in TELEGRAM_BOT_TOKEN:
        print("⚠️  لم تضع توكن بوت التلجرام — لن يعمل استقبال الموافقات.")
        return

    print("🤖 بوت التلجرام يعمل الآن (polling)...")
    offset = 0
    while True:
        try:
            r = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            data = r.json()
            if not data.get("ok"):
                time.sleep(3)
                continue

            for update in data["result"]:
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_callback_query(update["callback_query"])
        except Exception as e:
            print("خطأ بحلقة استطلاع تلجرام:", e)
            time.sleep(5)


# --------------------------------- API ----------------------------------

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(os.path.join(BASE_DIR, "assets"), filename)


@app.route("/api/config")
def api_config():
    return jsonify({
        "brand": BRAND_NAME,
        "packages": PACKAGES,
        "shamCashNumber": SHAM_CASH_NUMBER,
        "shamCashName": SHAM_CASH_NAME,
        "shamBarcodeImage": SHAM_BARCODE_IMAGE,
        "syriatelCashNumber": SYRIATEL_CASH_NUMBER,
        "syriatelCashName": SYRIATEL_CASH_NAME,
        "exchangeRate": EXCHANGE_RATE_USD_TO_SYP,
    })


@app.route("/api/orders", methods=["POST"])
def api_create_order():
    body = request.get_json(force=True) or {}
    package_id = body.get("packageId")
    method = body.get("method")
    tx_code = body.get("txCode")

    if not all([package_id, method, tx_code]):
        return jsonify({"error": "الحقول المطلوبة ناقصة"}), 400

    if method not in ("sham_usd", "sham_syp", "syriatel", "binance"):
        return jsonify({"error": "طريقة دفع غير مدعومة"}), 400

    if method == "binance":
        return jsonify({"error": "الدفع عبر Binance غير متاح حاليًا"}), 400

    pkg = next((p for p in PACKAGES if p["id"] == package_id), None)
    if not pkg:
        return jsonify({"error": "الباقة غير موجودة"}), 400

    # السيرفر هو من يحسب المبلغ المطلوب، لا نثق بأي مبلغ يرسله المتصفح
    if method == "sham_usd":
        amount_text = f"{pkg['usd_price']}$"
    else:  # sham_syp أو syriatel
        amount_syp = pkg["usd_price"] * EXCHANGE_RATE_USD_TO_SYP
        amount_text = f"{amount_syp:,} SYP".replace(",", ",")

    order = {
        "id": uuid.uuid4().hex[:10],
        "packageId": pkg["id"],
        "packageName": pkg["name"],
        "tokens": pkg["tokens"],
        "method": method,
        "amountText": amount_text,
        "txCode": str(tx_code).strip(),
        "status": "pending",
        "createdAt": time.time(),
    }
    create_order(order)

    threading.Thread(target=send_approval_request, args=(order,), daemon=True).start()

    return jsonify({"orderId": order["id"]})


@app.route("/api/orders/<order_id>")
def api_get_order(order_id):
    order = get_order(order_id)
    if not order:
        return jsonify({"error": "الطلب غير موجود"}), 404
    return jsonify({
        "id": order["id"],
        "status": order["status"],
        "packageName": order["packageName"],
        "tokens": order["tokens"],
        "method": order["method"],
    })


@app.route("/api/orders/<order_id>/confirm", methods=["POST"])
def api_confirm(order_id):
    order = get_order(order_id)
    if not order:
        return jsonify({"error": "الطلب غير موجود"}), 404

    if order["status"] != "approved":
        return jsonify({"error": "لا يمكن إدخال رقم اللاعب قبل الموافقة على الطلب"}), 400

    body = request.get_json(force=True) or {}
    player_id = body.get("playerId")
    if not player_id:
        return jsonify({"error": "الرجاء إدخال رقم اللاعب"}), 400

    updated = update_order(order_id, {
        "status": "delivered",
        "playerId": str(player_id).strip(),
        "deliveredAt": time.time(),
    })

    threading.Thread(target=notify_player_id, args=(updated,), daemon=True).start()

    return jsonify({"ok": True})


# --------------------------------- تشغيل ---------------------------------

if __name__ == "__main__":
    threading.Thread(target=telegram_polling_loop, daemon=True).start()
    print(f"✅ الموقع يعمل الآن على http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
