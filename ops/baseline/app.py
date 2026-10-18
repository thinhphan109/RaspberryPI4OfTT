from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

import subprocess
import json
import os
import hmac
import secrets
import socket
import threading
import time


app = Flask(__name__)

app.secret_key = os.environ.get(
    "PIWIFI_SECRET",
    "change-me"
)

WEB_USER = os.environ.get(
    "PIWIFI_USER",
    "admin"
)

WEB_PASS = os.environ.get(
    "PIWIFI_PASS",
    ""
)

HELPER = "/usr/local/sbin/piwifi-helper"


def helper(*args):
    process = subprocess.run(
        [
            "/usr/bin/sudo",
            HELPER,
            *[str(x) for x in args]
        ],
        text=True,
        capture_output=True
    )

    raw = process.stdout.strip()

    try:
        result = json.loads(raw)

    except Exception:
        raise RuntimeError(
            process.stderr.strip()
            or raw
            or "Helper không phản hồi"
        )

    if not result.get("ok"):
        raise RuntimeError(
            result.get(
                "error",
                "Unknown helper error"
            )
        )

    return result.get("data")


def schedule_helper(*args):
    def worker():
        time.sleep(2)

        subprocess.run(
            [
                "/usr/bin/sudo",
                HELPER,
                *[str(x) for x in args]
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()


def logged_in():
    return session.get("logged_in") is True


@app.before_request
def security_check():
    allowed = {
        "login",
        "static"
    }

    if request.endpoint in allowed:
        return

    if not logged_in():
        return redirect(
            url_for("login")
        )

    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(24)


def check_csrf():
    supplied = request.form.get(
        "csrf",
        ""
    )

    expected = session.get(
        "csrf",
        ""
    )

    if not hmac.compare_digest(
        supplied,
        expected
    ):
        raise RuntimeError(
            "CSRF token không hợp lệ"
        )


@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():
    error = None

    if request.method == "POST":
        username = request.form.get(
            "username",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            hmac.compare_digest(
                username,
                WEB_USER
            )
            and
            hmac.compare_digest(
                password,
                WEB_PASS
            )
        ):
            session.clear()

            session["logged_in"] = True
            session["csrf"] = secrets.token_hex(24)

            return redirect(
                url_for("index")
            )

        error = "Sai username hoặc password"

    return render_template(
        "index.html",
        login_mode=True,
        error=error
    )


@app.route("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("login")
    )


@app.route("/")
def index():
    try:
        data = helper("status")
        error = None

    except Exception as e:
        data = {
            "active": "",
            "active_ssid": "",
            "ip": "",
            "gateway": "",
            "dns": "",
            "signal": 0,
            "profiles": []
        }

        error = str(e)

    return render_template(
        "index.html",
        login_mode=False,
        data=data,
        error=error,
        csrf=session["csrf"],
        hostname=socket.gethostname()
    )


@app.route("/api/status")
def api_status():
    try:
        return jsonify({
            "ok": True,
            "data": helper("status")
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/scan")
def api_scan():
    try:
        return jsonify({
            "ok": True,
            "data": helper("scan")
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route(
    "/wifi/save",
    methods=["POST"]
)
def wifi_save():
    try:
        check_csrf()

        ssid = request.form.get(
            "ssid",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        priority = request.form.get(
            "priority",
            "80"
        )

        mode = request.form.get(
            "mode",
            "save"
        )

        result = helper(
            "save",
            ssid,
            password,
            priority
        )

        profile = result["profile"]

        if mode == "connect":
            schedule_helper(
                "connect",
                profile
            )

            return render_template(
                "index.html",
                login_mode=False,
                switching=True,
                switching_ssid=ssid
            )

        flash(
            f"Đã lưu Wi-Fi {ssid}",
            "success"
        )

    except Exception as e:
        flash(
            str(e),
            "error"
        )

    return redirect(
        url_for("index")
    )


@app.route(
    "/wifi/priority",
    methods=["POST"]
)
def wifi_priority():
    try:
        check_csrf()

        helper(
            "priority",
            request.form["name"],
            request.form["priority"]
        )

        flash(
            "Đã cập nhật priority",
            "success"
        )

    except Exception as e:
        flash(
            str(e),
            "error"
        )

    return redirect(
        url_for("index")
    )


@app.route(
    "/wifi/delete",
    methods=["POST"]
)
def wifi_delete():
    try:
        check_csrf()

        helper(
            "delete",
            request.form["name"]
        )

        flash(
            "Đã xóa Wi-Fi",
            "success"
        )

    except Exception as e:
        flash(
            str(e),
            "error"
        )

    return redirect(
        url_for("index")
    )


@app.route(
    "/wifi/connect",
    methods=["POST"]
)
def wifi_connect():
    try:
        check_csrf()

        name = request.form["name"]
        ssid = request.form.get(
            "ssid",
            name
        )

        schedule_helper(
            "connect",
            name
        )

        return render_template(
            "index.html",
            login_mode=False,
            switching=True,
            switching_ssid=ssid
        )

    except Exception as e:
        flash(
            str(e),
            "error"
        )

        return redirect(
            url_for("index")
        )


@app.route(
    "/hotspot",
    methods=["POST"]
)
def hotspot():
    try:
        check_csrf()

        schedule_helper("hotspot")

        return render_template(
            "index.html",
            login_mode=False,
            switching=True,
            switching_ssid="RaspPI4OfTT",
            hotspot_switch=True
        )

    except Exception as e:
        flash(
            str(e),
            "error"
        )

        return redirect(
            url_for("index")
        )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=18765,
        debug=False
    )
