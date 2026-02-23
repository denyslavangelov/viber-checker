"""
Viber screenshot agent — runs on the PC where Viber is installed.
Receives HTTP requests to open Viber, look up a number, capture the Viber window only, then close Viber.
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time
import base64
import uuid
import webbrowser

# Load .env from project root (same folder as agent.py) so OPENAI_API_KEY etc. can be set there
try:
    from dotenv import load_dotenv
    _agent_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_agent_dir, ".env"))
except ImportError:
    pass

# OCR debug logs: use a dedicated handler so they always show in the terminal
log = logging.getLogger("viber_agent.ocr")
log.setLevel(logging.DEBUG)
_h = logging.StreamHandler(sys.stderr)
_h.setFormatter(logging.Formatter("%(asctime)s [OCR] %(message)s"))
log.addHandler(_h)
log.propagate = False

from flask import Flask, request, jsonify, Response, send_file

# Screenshot (pip install mss)
try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

# Window bounds + close app (pip install pywinauto)
try:
    from pywinauto import Application
    from pywinauto.keyboard import send_keys as _keyboard_send_keys
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False
    _keyboard_send_keys = None

# OCR: GPT Vision only (set OPENAI_API_KEY)
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def _has_gpt_ocr() -> bool:
    return bool(HAS_OPENAI and _get_openai_key())

app = Flask(__name__)


@app.after_request
def _cors(resp):
    """Allow the Next.js app (different origin) to call this API."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/check-number", methods=["OPTIONS"])
@app.route("/check-number-base64", methods=["OPTIONS"])
@app.route("/send-message", methods=["OPTIONS"])
def _cors_preflight():
    return "", 204


# Default Viber path on Windows (%LOCALAPPDATA%\Viber\Viber.exe)
VIBER_EXE = os.environ.get("VIBER_EXE") or os.path.expandvars(
    r"%LOCALAPPDATA%\Viber\Viber.exe"
)

# OpenAI API key for GPT Vision OCR. Set in .env as OPENAI_API_KEY=sk-proj-...
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _get_openai_key() -> str:
    return OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")

# Delays (seconds) — tune for your PC (increase if "internet needed" or empty panel)
INITIAL_WAIT = float(os.environ.get("INITIAL_WAIT", "1.0"))  # after opening link, before first window poll
PANEL_LOAD_WAIT = float(os.environ.get("PANEL_LOAD_WAIT", "1.0"))  # after window found, before capture
WINDOW_WAIT_TIMEOUT = 14  # max seconds to wait for Viber window to appear
WINDOW_POLL_INTERVAL = 0.25  # between poll attempts
CONNECT_TIMEOUT = float(os.environ.get("CONNECT_TIMEOUT", "0.5"))  # fail fast when Viber not ready
RETRY_EXTRA_WAIT = 1.5  # before retry if window not found
MESSAGE_INPUT_WAIT = 2.0  # after chat opens, before typing (so input is focused)

# Right panel crop: the highlighted part (large contact photo + name + icons)
# Measured in Paint: 300×255, top padding is correct.
PANEL_WIDTH = 300
PANEL_TOP = 40  # skip top of window (title bar, Viber Out, settings)
PANEL_HEIGHT = 240

# Approximate OpenAI pricing USD per 1M tokens (for cost log)
_OPENAI_PRICE_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def _log_step(step_name: str, elapsed: float, extra: str = "") -> None:
    msg = f"[viber-agent] {step_name}: {elapsed:.2f}s"
    if extra:
        msg += f" — {extra}"
    print(msg, flush=True)


def _api_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_p, out_p = _OPENAI_PRICE_PER_1M.get(model, (0.15, 0.60))
    return (prompt_tokens * in_p + completion_tokens * out_p) / 1_000_000


def gpt_fix_contact_name(raw_name: str) -> str:
    """
    Ask GPT to correct the name: proper Cyrillic spelling, valid person's name. Returns corrected name or "".
    """
    if not raw_name or not _has_gpt_ocr():
        return raw_name or ""
    try:
        client = OpenAI(api_key=_get_openai_key())
        model = os.environ.get("OPENAI_OCR_MODEL", "gpt-4o-mini")
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "This is a contact name extracted from a messaging app image. It may be mixed Latin/Cyrillic or have OCR errors.\n\n"
                        "Tasks:\n"
                        "1. Convert to correct Cyrillic if it should be Cyrillic (e.g. Bulgarian, Russian names).\n"
                        "2. Fix any spelling mistakes and ensure it looks like a real person's name (first name, optionally last name).\n"
                        "3. Reply with ONLY the corrected name, nothing else. No quotes, no explanation.\n"
                        "4. If the input is clearly not a person's name (garbage, placeholder, etc.), reply with exactly: No name found\n\n"
                        f"Input: {raw_name}"
                    ),
                }
            ],
            max_tokens=80,
        )
        elapsed = time.monotonic() - t0
        out = (response.choices[0].message.content or "").strip()
        if not out or out.lower() == "no name found":
            out = ""
        usage = getattr(response, "usage", None)
        if usage:
            cost = _api_cost_usd(model, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)
            _log_step("GPT fix name (API)", elapsed, f"tokens in={getattr(usage,'prompt_tokens',0)} out={getattr(usage,'completion_tokens',0)} ~${cost:.6f}")
        else:
            _log_step("GPT fix name (API)", elapsed)
        log.debug("GPT fix name: %r -> %r", raw_name, out)
        return out
    except Exception as e:
        log.warning("GPT fix name failed: %s, using raw", e)
        return raw_name


def ocr_image_gpt(png_bytes: bytes) -> tuple[str, str]:
    """
    Use GPT Vision to extract text and contact name from the image. Returns (full_text, contact_name).
    Then ask GPT again to fix/normalize the name (Cyrillic, correct spelling).
    """
    if not _has_gpt_ocr():
        return "", ""
    try:
        client = OpenAI(api_key=_get_openai_key())
        b64 = base64.b64encode(png_bytes).decode("ascii")
        model = os.environ.get("OPENAI_OCR_MODEL", "gpt-4o-mini")
        log.debug("GPT Vision model=%s", model)
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Look at this image from a messaging app contact panel. Extract all visible text. On the first line write only the contact name (the person's name). On the next line write a dash, then on the following lines list any other text you see. If there is no clear name, write 'No name found' on the first line.",
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            max_tokens=300,
        )
        elapsed = time.monotonic() - t0
        raw = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        if usage:
            cost = _api_cost_usd(model, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)
            _log_step("GPT Vision OCR (API)", elapsed, f"tokens in={getattr(usage,'prompt_tokens',0)} out={getattr(usage,'completion_tokens',0)} ~${cost:.6f}")
        else:
            _log_step("GPT Vision OCR (API)", elapsed)
        log.debug("GPT raw=%r", raw[:300] if len(raw) > 300 else raw)
        lines = raw.splitlines()
        contact_name = ""
        if lines:
            first = lines[0].strip()
            if first and first.lower() != "no name found":
                contact_name = gpt_fix_contact_name(first)
        return raw, contact_name
    except Exception as e:
        log.exception("GPT OCR failed: %s", e)
        return "", ""


def _digits_only(phone_number: str) -> str:
    """Return digits only (no normalization)."""
    return "".join(c for c in phone_number if c.isdigit())


def _close_viber_window_if_open() -> None:
    """Close the Viber window (without killing the process) so the next viber:// opens the right chat."""
    if not HAS_PYWINAUTO or not os.path.isfile(VIBER_EXE):
        return
    try:
        app = Application(backend="uia").connect(path=VIBER_EXE, timeout=1)
        dlg = app.top_window()
        dlg.close()
        time.sleep(1.2)
    except Exception:
        pass


def open_viber_chat(phone_number: str) -> str | None:
    """
    Open Viber chat with the given number via viber://chat?number=...
    Uses digits as-is (e.g. 0877315132). On Windows uses os.startfile() so the link
    goes straight to Viber instead of via the browser (faster).
    Returns None on success, or an error message string.
    """
    digits = _digits_only(phone_number)
    if not digits:
        return "No valid phone number provided"
    url = f"viber://chat?number={digits}"
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            webbrowser.open(url)
        return None
    except Exception as e:
        return str(e)


def connect_to_viber_window():
    """
    Wait for Viber window to appear and return (Application, window_rect_dict) for mss.
    rect_dict is {"left", "top", "width", "height"} in screen coordinates.
    Returns (None, None, error_str) on failure.
    """
    if not HAS_PYWINAUTO or not os.path.isfile(VIBER_EXE):
        return None, None, "pywinauto not installed or Viber path not found"

    deadline = time.monotonic() + WINDOW_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        try:
            app = Application(backend="uia").connect(path=VIBER_EXE, timeout=CONNECT_TIMEOUT)
            dlg = app.top_window()
            try:
                dlg.restore()  # un-minimize if minimized
                dlg.set_focus()  # bring to foreground so we capture the right content
            except Exception:
                pass
            time.sleep(0.3)  # let window come to front
            rect = dlg.rectangle()
            left = int(rect.left)
            top = int(rect.top)
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                time.sleep(WINDOW_POLL_INTERVAL)
                continue
            rect_dict = {"left": left, "top": top, "width": width, "height": height}
            return app, rect_dict, None
        except Exception:
            time.sleep(WINDOW_POLL_INTERVAL)
    return None, None, f"Viber window did not appear within {WINDOW_WAIT_TIMEOUT}s"


def _panel_rect_from_window(rect_dict: dict) -> dict:
    """Crop region for the right panel: large contact photo + name + icon row (highlighted part)."""
    left = rect_dict["left"]
    top = rect_dict["top"]
    width = rect_dict["width"]
    height = rect_dict["height"]
    # Right panel: fixed width from right edge, skip top strip
    panel_left = left + width - PANEL_WIDTH
    panel_top = top + PANEL_TOP
    panel_left = max(left, panel_left)
    panel_top = max(top, panel_top)
    return {
        "left": panel_left,
        "top": panel_top,
        "width": min(PANEL_WIDTH, left + width - panel_left),
        "height": min(PANEL_HEIGHT, top + height - panel_top),
    }


def do_viber_search_and_screenshot(
    phone_number: str, only_panel: bool = False
) -> tuple[bytes | None, bytes | None, str | None]:
    """
    Open Viber chat via viber://chat?number=..., capture window + right panel (highlighted part), then close Viber.
    If only_panel is True, window_png is None and only the panel (highlighted part) is captured.
    Returns (window_png_bytes, panel_png_bytes, error_message). error_message is None on success.
    """
    if not HAS_MSS:
        return None, None, "mss not installed (pip install mss)"

    total_start = time.monotonic()
    print("[viber-agent] --- lookup start ---", flush=True)

    # 0) Skip closing window here — dlg.close() can block ~10s. Open link directly; if Viber is open it will switch chat.

    # 1) Open chat via Viber URI (launches Viber if needed, or brings to front and opens chat)
    t0 = time.monotonic()
    err = open_viber_chat(phone_number)
    _log_step("open viber:// link", time.monotonic() - t0)
    if err:
        return None, None, err

    # 2) Short wait then poll for window (don't wait full time — capture as soon as ready)
    t0 = time.monotonic()
    time.sleep(INITIAL_WAIT)
    _log_step("initial wait", time.monotonic() - t0)

    # 3) Find Viber window (retry once if cold start is slow)
    t0 = time.monotonic()
    viber_app, rect_dict, err = connect_to_viber_window()
    elapsed = time.monotonic() - t0
    _log_step("find Viber window", elapsed, "retry=0" if not err else f"err={err}")
    if err or not rect_dict:
        time.sleep(RETRY_EXTRA_WAIT)
        t0 = time.monotonic()
        viber_app, rect_dict, err = connect_to_viber_window()
        _log_step("find Viber window (retry)", time.monotonic() - t0)
    if err or not rect_dict:
        return None, None, err or "Could not get Viber window bounds"

    # 4) Brief wait for right panel to load then capture
    t0 = time.monotonic()
    time.sleep(PANEL_LOAD_WAIT)
    _log_step("panel load wait", time.monotonic() - t0)

    # 5) Capture window + right panel (highlighted: photo + name + icons)
    t0 = time.monotonic()
    try:
        with mss.mss() as sct:
            panel_rect = _panel_rect_from_window(rect_dict)
            if only_panel:
                if panel_rect["width"] <= 0 or panel_rect["height"] <= 0:
                    return None, None, "Panel region invalid"
                panel_shot = sct.grab(panel_rect)
                panel_png = mss.tools.to_png(panel_shot.rgb, panel_shot.size)
                return None, panel_png, None
            # Full window + panel
            shot = sct.grab(rect_dict)
            window_png = mss.tools.to_png(shot.rgb, shot.size)
            if panel_rect["width"] > 0 and panel_rect["height"] > 0:
                panel_shot = sct.grab(panel_rect)
                panel_png = mss.tools.to_png(panel_shot.rgb, panel_shot.size)
            else:
                panel_png = None
    finally:
        _log_step("screenshot capture", time.monotonic() - t0)
        # 6) Close Viber window (leave process running, e.g. in tray)
        if viber_app is not None:
            t0 = time.monotonic()
            try:
                dlg = viber_app.top_window()
                dlg.close()
            except Exception:
                pass
            _log_step("close window", time.monotonic() - t0)

    _log_step("TOTAL (Viber + capture)", time.monotonic() - total_start)
    print("[viber-agent] --- lookup done ---", flush=True)
    return window_png, panel_png, None


def do_viber_send_message(phone_number: str, message: str) -> str | None:
    """
    Open Viber chat with the given number, type the message, send it (Enter), then close Viber.
    Returns None on success, or an error message string.
    """
    if not HAS_PYWINAUTO or _keyboard_send_keys is None:
        return "pywinauto not installed"
    if not message or not message.strip():
        return "Message is empty"

    total_start = time.monotonic()
    print("[viber-agent] --- send message start ---", flush=True)

    t0 = time.monotonic()
    err = open_viber_chat(phone_number)
    _log_step("open viber:// link", time.monotonic() - t0)
    if err:
        return err

    time.sleep(INITIAL_WAIT)
    viber_app, _, err = connect_to_viber_window()
    if err or viber_app is None:
        return err or "Could not find Viber window"

    dlg = viber_app.top_window()
    try:
        dlg.restore()
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(MESSAGE_INPUT_WAIT)

    t0 = time.monotonic()
    try:
        # Type message and Enter into the focused window (chat input)
        _keyboard_send_keys(message.strip() + "{ENTER}", with_spaces=True)
    except Exception as e:
        _log_step("type message", time.monotonic() - t0)
        return f"Failed to type/send: {e}"
    _log_step("type message + Enter", time.monotonic() - t0)

    time.sleep(0.5)
    try:
        dlg = viber_app.top_window()
        dlg.close()
    except Exception:
        pass
    _log_step("TOTAL (send message)", time.monotonic() - total_start)
    print("[viber-agent] --- send message done ---", flush=True)
    return None


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        status="ok",
        viber_path=VIBER_EXE,
        viber_exists=os.path.isfile(VIBER_EXE),
        pywinauto=HAS_PYWINAUTO,
        ocr=_has_gpt_ocr(),
        ocr_backend="gpt" if _has_gpt_ocr() else False,
    )


@app.route("/check-number", methods=["POST"])
def check_number():
    """
    Body (JSON): { "number": "+1234567890", "only_panel": true } or { "include_photo": true }
    Opens Viber chat, captures screenshot(s), closes Viber.
    - only_panel: true  → returns single PNG of the highlighted part only (right panel: photo + name + icons).
    - include_photo: true → returns multipart response with two PNGs: viber_window.png and contact_panel.png.
    - otherwise → returns single PNG (full Viber window).
    """
    data = request.get_json(silent=True) or {}
    number = (data.get("number") or "").strip()
    if not number:
        return jsonify(error="Missing 'number' in JSON body"), 400
    only_panel = data.get("only_panel") is True
    include_photo = data.get("include_photo") is True

    window_png, panel_png, err = do_viber_search_and_screenshot(number, only_panel=only_panel)
    if err:
        return jsonify(error=err), 500

    if only_panel and panel_png is not None:
        return send_file(
            io.BytesIO(panel_png),
            mimetype="image/png",
            as_attachment=True,
            download_name="contact_panel.png",
        )

    if include_photo and panel_png is not None:
        boundary = uuid.uuid4().hex.encode()
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: attachment; filename="viber_window.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
            + window_png + b"\r\n"
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: attachment; filename="contact_panel.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
            + panel_png + b"\r\n"
            b"--" + boundary + b"--\r\n"
        )
        return Response(
            body,
            mimetype=f"multipart/mixed; boundary={boundary.decode()}",
        )

    return send_file(
        io.BytesIO(window_png),
        mimetype="image/png",
        as_attachment=True,
        download_name="viber_screenshot.png",
    )


@app.route("/check-number-base64", methods=["POST"])
def check_number_base64():
    """
    Same as /check-number but returns JSON.
    With only_panel: true → panel_base64 only. Otherwise screenshot_base64 and optionally contact_panel_base64.
    """
    request_start = time.monotonic()
    print("[viber-agent] POST /check-number-base64 received", flush=True)
    data = request.get_json(silent=True) or {}
    number = (data.get("number") or "").strip()
    if not number:
        return jsonify(error="Missing 'number' in JSON body"), 400
    only_panel = data.get("only_panel") is True

    window_png, panel_png, err = do_viber_search_and_screenshot(number, only_panel=only_panel)
    if err:
        return jsonify(error=err), 500

    out = {"number": number}
    # Run OCR on the image that contains the contact (panel if available, else full window)
    ocr_image_bytes = panel_png if panel_png is not None else window_png
    if ocr_image_bytes:
        log.debug("running on %s (%d bytes)", "panel" if panel_png is not None else "window", len(ocr_image_bytes))
    t0 = time.monotonic()
    panel_text, contact_name = ocr_image_gpt(ocr_image_bytes) if ocr_image_bytes else ("", "")
    if ocr_image_bytes:
        _log_step("OCR total (Vision + fix name)", time.monotonic() - t0)
    _log_step("REQUEST TOTAL", time.monotonic() - request_start)
    print("[viber-agent] --- request done ---", flush=True)

    if only_panel and panel_png is not None:
        out["panel_base64"] = base64.b64encode(panel_png).decode("ascii")
    else:
        out["screenshot_base64"] = base64.b64encode(window_png).decode("ascii")
        if panel_png is not None:
            out["contact_panel_base64"] = base64.b64encode(panel_png).decode("ascii")

    # Always include captured text so the UI can show it
    if panel_text:
        out["panel_text"] = panel_text
    else:
        out["panel_text"] = "(no text detected)" if _has_gpt_ocr() else "(set OPENAI_API_KEY for OCR)"
    if contact_name:
        out["contact_name"] = contact_name
    return jsonify(out)


@app.route("/send-message", methods=["POST"])
def send_message():
    """
    Body (JSON): { "number": "+123...", "message": "Hello" }.
    Opens Viber chat with the number, types the message, sends (Enter), then closes Viber.
    """
    data = request.get_json(silent=True) or {}
    number = (data.get("number") or "").strip()
    message = (data.get("message") or "").strip()
    if not number:
        return jsonify(error="Missing 'number' in JSON body"), 400
    if not message:
        return jsonify(error="Missing 'message' in JSON body"), 400

    err = do_viber_send_message(number, message)
    if err:
        return jsonify(error=err), 500
    return jsonify(ok=True, number=number)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Viber screenshot agent")
    parser.add_argument("--host", default="0.0.0.0", help="Listen on this host (0.0.0.0 = all interfaces)")
    parser.add_argument("--port", type=int, default=5050, help="Port to listen on")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
