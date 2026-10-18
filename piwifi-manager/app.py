from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

import subprocess
import json
import os
import hmac
import secrets
import socket
import time
from copy import deepcopy
from pathlib import Path
from observer import current as collect, history, events, ipc_read
from state import read as read_state
from hardware import status as gpio_status
import hub
import media


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 65536
app.jinja_env.globals['asset_version'] = Path(__file__).resolve().parent.name
app.secret_key = os.environ.get("PIWIFI_SECRET", "change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

WEB_USER = os.environ.get("PIWIFI_USER", "admin")
WEB_PASS = os.environ.get("PIWIFI_PASS", "")
HELPER = "/usr/local/sbin/piwifi-helper"
_read_cache = {}

def cached_read(key, ttl, function):
    now = time.monotonic()
    old = _read_cache.get(key)
    if old and now - old[0] < ttl:
        return deepcopy(old[1])
    value = function()
    _read_cache[key] = (now, deepcopy(value))
    return value


def helper(*args):
    process = subprocess.run(
        ["/usr/bin/sudo", HELPER, *[str(x) for x in args]],
        text=True,
        capture_output=True,
        timeout=35,
    )

    raw = process.stdout.strip()
    try:
        result = json.loads(raw)
    except Exception:
        raise RuntimeError(process.stderr.strip() or raw or "Helper không phản hồi")

    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Unknown helper error"))
    return result.get("data")


def queue_network(action, target):
    _read_cache.clear()
    return helper('submit-operation', action, target)

@app.route('/api/gpio/status')
def api_gpio_status():
    return jsonify(ok=True,data=cached_read('gpio',10,gpio_status))

@app.route('/api/gpio/control',methods=['POST'])
def api_gpio_control():
    try: check_csrf()
    except RuntimeError as exc: return jsonify(ok=False,error=str(exc)),403
    return jsonify(ok=False,error='GPIO_CONTROL_DISABLED: điều khiển chưa được kích hoạt'),403

@app.route('/api/security')
def api_security():
    data=collect()
    security=data.get('ssh_security',{'supported':False,'reason':'Bộ giám sát chưa có dữ liệu SSH'})
    return jsonify(ok=True,data=dict(security,stale=data.get('stale',True)))

@app.route('/api/history')
def api_history():
    hours = request.args.get('hours', '24')
    if hours not in ('1', '24', '168'):
        return jsonify(ok=False, error='Khoảng thời gian không hợp lệ'), 400
    return jsonify(ok=True, data=cached_read('history:'+hours, 30, lambda:history(int(hours))))


@app.route('/api/storage-writes')
def api_storage_writes():
    hours=request.args.get('hours','24');days=request.args.get('days','30')
    if hours not in ('1','24','168') or days not in ('30','90','0'):
        return jsonify(ok=False,error='Khoảng thống kê không hợp lệ'),400
    data=ipc_read('storage-writes',int(hours),int(days))
    if not isinstance(data,dict):data=dict(available=False,error='Chưa kết nối được bộ giám sát')
    return jsonify(ok=True,data=data)

@app.route('/api/events')
def api_events():
    return jsonify(ok=True, data=cached_read('events', 10, events))

@app.route('/api/operation')
def api_operation():
    data = read_state('operation.json', {})
    data['server_time'] = int(time.time())
    if data.get('stage') in ('queued', 'connecting') and time.time() - data.get('updated', 0) > 150:
        data.update(stage='unknown', message='Tác vụ quá thời hạn; cần kiểm tra kết nối thực tế')
    return jsonify(ok=True, data=data)

@app.route('/api/operation/ack', methods=['POST'])
def api_operation_ack():
    try:
        check_csrf()
        result=helper('ack-operation', request.form['id'])
        _read_cache.clear()
        return jsonify(ok=True, data=result)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.route('/api/deployments')
def api_deployments():
    try:
        return jsonify(ok=True, data=cached_read('deployments', 30, lambda:helper('deployments')))
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500

@app.route('/service/restart', methods=['POST'])
def service_restart():
    try:
        check_csrf()
        helper('service-restart', request.form['name'])
        flash('Đã lên lịch khởi động lại dịch vụ', 'success')
    except Exception as exc:
        flash(str(exc), 'error')
    return redirect(url_for('index', _anchor='storage'))

@app.route('/deploy/rollback', methods=['POST'])
def deploy_rollback():
    try:
        check_csrf()
        helper('rollback-latest')
        flash('Đã lên lịch phục hồi bản trước. Dashboard có thể ngắt trong giây lát.', 'success')
    except Exception as exc:
        flash(str(exc), 'error')
    return redirect(url_for('index', _anchor='storage'))

@app.after_request
def no_store(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def logged_in():
    return session.get("logged_in") is True


@app.before_request
def security_check():
    if request.endpoint in {"login", "static"}:
        return None
    if not logged_in():
        return redirect(url_for("login"))
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(24)
    return None


def check_csrf():
    payload = request.get_json(silent=True) if request.is_json else request.form
    if request.is_json and payload is not None and not isinstance(payload,dict):
        raise RuntimeError("Dữ liệu CSRF không hợp lệ")
    supplied = request.headers.get("X-CSRF-Token") or (payload or {}).get("csrf", "")
    if not isinstance(supplied,str): raise RuntimeError("CSRF token không hợp lệ")
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise RuntimeError("CSRF token không hợp lệ")


@app.route('/api/media', methods=['GET','POST'])
def api_media():
    if request.method=='POST':
        try:check_csrf()
        except RuntimeError:return jsonify(ok=False,error='Phiên không hợp lệ'),403
    payload=request.get_json(silent=True) if request.method=='POST' else {'action':'status'}
    if not isinstance(payload,dict):return jsonify(ok=False,error='Yêu cầu không hợp lệ'),400
    try:return jsonify(ok=True,data=media.call(payload))
    except ValueError as exc:return jsonify(ok=False,error=str(exc)),400
    except (OSError,RuntimeError):return jsonify(ok=False,error='Media chưa sẵn sàng; kiểm tra phiên desktop Pi.'),503

@app.route('/api/audio', methods=['GET','POST'])
def api_audio():
    if request.method=='POST' and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','')):
        return jsonify(ok=False,error='Phiên không hợp lệ'),403
    payload=request.get_json(silent=True) if request.method=='POST' else {'action':'status'}
    if not isinstance(payload,dict):return jsonify(ok=False,error='Yêu cầu không hợp lệ'),400
    try:return jsonify(ok=True,data=media.call({'action':'audio','payload':payload}))
    except ValueError as exc:return jsonify(ok=False,error=str(exc)),400
    except (OSError,RuntimeError):return jsonify(ok=False,error='Âm thanh chưa sẵn sàng; kiểm tra phiên desktop Pi.'),503


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if hmac.compare_digest(username, WEB_USER) and hmac.compare_digest(password, WEB_PASS):
            session.clear()
            session["logged_in"] = True
            session["csrf"] = secrets.token_hex(24)
            return redirect(url_for("index"))
        error = "Sai username hoặc password"

    return render_template("index.html", login_mode=True, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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
            "profiles": [],
        }
        error = str(e)

    return render_template(
        "index.html",
        login_mode=False,
        data=data,
        error=error,
        csrf=session["csrf"],
        hostname=socket.gethostname(),
        metrics=collect(),
    )

@app.route('/api/metrics')
def api_metrics():
    response = jsonify({'ok': True, 'data': collect()})
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/hub')
def api_hub():
    try:
        network = cached_read('network', 60, lambda:helper('status'))
        return jsonify(ok=True, data=cached_read('hub', 15, lambda:hub.applications(network)))
    except Exception:
        return jsonify(ok=False, error='Chưa đọc được kết nối Pi. Thử lại sau.'), 503


@app.route('/api/dns-check', methods=['POST'])
def dns_check():
    try:
        check_csrf()
    except RuntimeError:
        return jsonify(ok=False, error='Phiên làm việc không hợp lệ'), 403
    current = session.get('dns_check')
    if current and time.time() - current['started'] < 10:
        return jsonify(ok=False, error='Đợi 10 giây trước lần thử tiếp theo'), 429
    domain = secrets.token_hex(12) + '.example.com'
    session['dns_check'] = dict(domain=domain, started=time.time())
    return jsonify(ok=True, data=dict(domain=domain, expires_in=60))


@app.route('/api/dns-check')
def dns_check_result():
    current = session.get('dns_check')
    if not current or time.time()-current['started'] > 60:
        return jsonify(ok=False, error='Phép thử hết hạn; bấm kiểm tra lại'), 400
    try:
        seen = hub.query_seen(current['domain'], current['started'])
        blocked = hub.dns_probe()
        status = 'verified' if seen and blocked else ('filter_error' if seen else 'unconfirmed')
        return jsonify(ok=True, data=dict(seen=seen, filtering=blocked, status=status, checked_at=int(time.time()),
            message=('AdGuard Home đã nhận truy vấn thử từ thiết bị hoặc DNS trung gian của bạn.' if seen else 'Chưa nhận truy vấn thử. Có thể DNS đi đường khác, trình duyệt dùng cache hoặc chặn phép thử.')))
    except Exception:
        return jsonify(ok=False, error='Chưa kiểm tra được AdGuard Home. Không kết luận DNS thiết bị bị lỗi.'), 503


@app.route("/api/status")
def api_status():
    try:
        response = jsonify({"ok": True, "data": cached_read('network', 60, lambda:helper("status"))})
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/scan")
def api_scan():
    try:
        return jsonify({"ok": True, "data": helper("scan")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/wifi/save", methods=["POST"])
def wifi_save():
    try:
        check_csrf()
        _read_cache.clear()
        ssid = request.form.get("ssid", "")
        password = request.form.get("password", "")
        priority = request.form.get("priority", "80")
        mode = request.form.get("mode", "save")

        result = helper("save", ssid, password, priority)
        profile = result["profile"]

        if mode == "connect":
            operation = queue_network('connect', profile)
            return render_template(
                "index.html",
                login_mode=False,
                switching=True,
                switching_ssid=ssid,
                operation=operation, csrf=session['csrf'],
            )

        flash(f"Đã lưu Wi-Fi {ssid}", "success")
    except Exception as e:
        flash(str(e), "error")

    return redirect(url_for("index"))


@app.route("/wifi/priority", methods=["POST"])
def wifi_priority():
    try:
        check_csrf()
        _read_cache.clear()
        helper("priority", request.form["name"], request.form["priority"])
        flash("Đã cập nhật priority", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("index"))


@app.route("/wifi/delete", methods=["POST"])
def wifi_delete():
    try:
        check_csrf()
        _read_cache.clear()
        helper("delete", request.form["name"])
        flash("Đã xóa Wi-Fi", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("index"))


@app.route("/wifi/connect", methods=["POST"])
def wifi_connect():
    try:
        check_csrf()
        name = request.form["name"]
        ssid = request.form.get("ssid", name)
        operation = queue_network('connect', name)
        return render_template(
            "index.html",
            login_mode=False,
            switching=True,
            switching_ssid=ssid,
            operation=operation, csrf=session['csrf'],
        )
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("index"))


@app.route("/hotspot", methods=["POST"])
def hotspot():
    try:
        check_csrf()
        operation = queue_network('hotspot', 'Pi-Fallback')
        return render_template(
            "index.html",
            login_mode=False,
            switching=True,
            switching_ssid="RaspPI4OfTT",
            hotspot_switch=True,
            operation=operation, csrf=session['csrf'],
        )
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18765, debug=False)
