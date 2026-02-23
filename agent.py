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

# Load .env so OPENAI_API_KEY etc. are set (agent dir first, then cwd; override so .env wins)
def _load_env():
    try:
        from dotenv import load_dotenv
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(agent_dir, ".env"), override=True)
        load_dotenv(".env", override=True)
    except ImportError:
        pass

_load_env()

# OCR debug logs: use a dedicated handler so they always show in the terminal
log = logging.getLogger("viber_agent.ocr")
log.setLevel(logging.DEBUG)
_h = logging.StreamHandler(sys.stderr)
_h.setFormatter(logging.Formatter("%(asctime)s [OCR] %(message)s"))
log.addHandler(_h)
log.propagate = False

from flask import Flask, request, jsonify, Response, send_file

# Screenshot: mss (screen grab) + optional PrintWindow (window buffer, works when RDP disconnected)
try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _PrintWindow = _user32.PrintWindow
    _PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _PrintWindow.restype = wintypes.BOOL
    PW_DEFAULT = 0
    PW_RENDERFULLCONTENT = 2
    HAS_PRINTWINDOW = True
except Exception:
    HAS_PRINTWINDOW = False

# Window bounds + close app (pip install pywinauto)
try:
    from pywinauto import Application
    from pywinauto import findwindows
    from pywinauto.keyboard import send_keys as _keyboard_send_keys
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False
    findwindows = None  # type: ignore
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
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
    return resp


@app.before_request
def _require_api_key():
    """If AGENT_API_KEY is set, require X-API-Key or Authorization: Bearer for protected routes."""
    if not AGENT_API_KEY:
        return None
    if request.method == "OPTIONS" or request.path in ("/health", "/api", "/api/v1", "/openapi.json", "/docs"):
        return None
    key = request.headers.get("X-API-Key", "").strip()
    if not key and request.headers.get("Authorization", "").startswith("Bearer "):
        key = request.headers.get("Authorization", "").replace("Bearer ", "", 1).strip()
    if key != AGENT_API_KEY:
        return jsonify(error="Unauthorized"), 401


@app.route("/check-number", methods=["OPTIONS"])
@app.route("/check-number-base64", methods=["OPTIONS"])
@app.route("/send-message", methods=["OPTIONS"])
def _cors_preflight():
    return "", 204


# Default Viber path on Windows (%LOCALAPPDATA%\Viber\Viber.exe)
VIBER_EXE = os.environ.get("VIBER_EXE") or os.path.expandvars(
    r"%LOCALAPPDATA%\Viber\Viber.exe"
)

# Load .env again so keys are definitely available (e.g. when run from another cwd)
_load_env()

# OpenAI API key for GPT Vision OCR. Set in .env only.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

# Optional: require X-API-Key header for agent endpoints. Set AGENT_API_KEY on agent and in Vercel (for proxy).
AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "").strip()

API_VERSION = "1.0"

if HAS_OPENAI:
    if OPENAI_API_KEY:
        print("[viber-agent] OPENAI_API_KEY: set", flush=True)
    else:
        _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        print("[viber-agent] OPENAI_API_KEY: not set (add to %s)" % _env_path, flush=True)


def _get_openai_key() -> str:
    return OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")

# Delays (seconds) — tune for your PC (increase if "internet needed" or empty panel)
INITIAL_WAIT = float(os.environ.get("INITIAL_WAIT", "0.25"))  # after opening link, before first window poll
PANEL_LOAD_WAIT = float(os.environ.get("PANEL_LOAD_WAIT", "0.5"))  # after window found, before capture
WINDOW_WAIT_TIMEOUT = 14  # max seconds to wait for Viber window to appear
WINDOW_POLL_INTERVAL = 0.10  # between poll attempts (smaller = find window sooner once it's ready)
CONNECT_TIMEOUT = float(os.environ.get("CONNECT_TIMEOUT", "0.25"))  # fail fast when Viber not ready
RETRY_EXTRA_WAIT = 1.0  # before retry if window not found
SKIP_FIX_NAME = os.environ.get("SKIP_FIX_NAME", "0").strip().lower() in ("1", "true", "yes")  # skip GPT fix-name call to save ~0.8s
MESSAGE_INPUT_WAIT = 2.0  # after chat opens, before typing (so input is focused)

# Panel crop: RIGHT side. Skip PANEL_TOP + PANEL_STRIP_TOP from window top (removes white bar), then 290×280.
PANEL_TOP = int(os.environ.get("PANEL_TOP", "40"))
PANEL_STRIP_TOP = int(os.environ.get("PANEL_STRIP_TOP", "30"))  # extra px to skip from top (strips white bar)
PANEL_WIDTH = int(os.environ.get("PANEL_WIDTH", "290"))
PANEL_HEIGHT = int(os.environ.get("PANEL_HEIGHT", "250"))
PANEL_LEFT = os.environ.get("PANEL_LEFT", "0").strip().lower() in ("1", "true", "yes")  # 0 = right side (default), 1 = left
PANEL_USE_FULL_WIDTH = os.environ.get("PANEL_USE_FULL_WIDTH", "0").strip().lower() in ("1", "true", "yes")
# If PrintWindow panel PNG is smaller than this, treat as likely blank and fall back to mss
PANEL_MIN_BYTES = 20_000
DEBUG_SAVE_PANEL = os.environ.get("DEBUG_SAVE_PANEL", "").strip().lower() in ("1", "true", "yes")

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


# Strings we never treat as a person's name (app labels, UI text, etc.)
_NOT_PERSON_NAMES = frozenset({
    "viber out", "viber", "chat", "no name found", "no name", "unknown", "contact",
    "no contact", "no contact found", "n/a", "—", "-", ""
})


def _is_plausible_person_name(name: str) -> bool:
    """
    Return True only if the string looks like a real person's name.
    Rejects app labels, numbers, single chars, and obvious non-names so we return "no contact" when appropriate.
    """
    if not name or not isinstance(name, str):
        return False
    s = name.strip()
    if len(s) < 2 or len(s) > 80:
        return False
    if s.lower() in _NOT_PERSON_NAMES:
        return False
    # Reject if it's mostly digits (e.g. phone number)
    letters = sum(1 for c in s if c.isalpha())
    if letters < 2 or letters < len(s) * 0.5:
        return False
    # Reject if it's a single repeated character or no letters
    if not any(c.isalpha() for c in s):
        return False
    return True


def _looks_like_clean_name(s: str) -> bool:
    """True if s looks like a single name (letters, spaces, hyphen; 2–50 chars) — skip fix API to save time."""
    if not s or len(s) < 2 or len(s) > 50:
        return False
    for c in s:
        if c in (" ", "-", "'"):
            continue
        if not c.isalpha():
            return False
    return True


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
                        "This is text extracted from a messaging app as a possible contact name. It may be mixed Latin/Cyrillic or have OCR errors.\n\n"
                        "Tasks:\n"
                        "1. If the input is a real person's name (first/last name): convert to correct Cyrillic if needed, fix spelling, reply with ONLY that name. No quotes.\n"
                        "2. If the input is NOT a person's name (e.g. 'Viber Out', app label, button text, phone number, 'Chat', placeholder, garbage), reply with exactly: No name found\n\n"
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
                            "text": (
                                "This image is a crop from a Viber chat window (right-side panel). The CONTACT NAME (the person's name) is in the BOTTOM-LEFT of this image. "
                                "Your task: On the FIRST line write ONLY the real person's name (first/last name). On the next line write a dash '-', then list any other text. "
                                "If you only see app labels (e.g. 'Viber Out', buttons, icons) or no clear person name, write 'No name found' on the first line."
                            ),
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
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        contact_name = ""
        # First line is the contact name; skip only obvious non-names
        _skip = {"", "no name found", "-", "viber out", "viber"}
        for line in lines:
            if line.lower() in _skip:
                continue
            line = line.strip()
            if SKIP_FIX_NAME or _looks_like_clean_name(line):
                contact_name = line
                log.debug("OCR name used as-is (skip fix): %r", contact_name)
            else:
                contact_name = gpt_fix_contact_name(line)
            if not _is_plausible_person_name(contact_name):
                log.debug("OCR name rejected (not a person name): %r", contact_name)
                contact_name = ""
            break
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
    Uses find_windows() + connect(handle=) first (fast Win32 enum); falls back to UIA connect(path=) if needed.
    """
    if not HAS_PYWINAUTO or not os.path.isfile(VIBER_EXE):
        return None, None, "pywinauto not installed or Viber path not found"

    deadline = time.monotonic() + WINDOW_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        try:
            # Fast path: find window by title via Win32 (lightweight), then connect by handle
            if findwindows is not None:
                handles = findwindows.find_windows(title_re=".*Viber.*")
                if handles:
                    app = Application(backend="win32").connect(handle=handles[0])
                    dlg = app.window(handle=handles[0])
                    try:
                        dlg.restore()
                        dlg.set_focus()
                    except Exception:
                        pass
                    time.sleep(0.12)
                    rect = dlg.rectangle()
                    left = int(rect.left)
                    top = int(rect.top)
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    if width > 0 and height > 0:
                        rect_dict = {"left": left, "top": top, "width": width, "height": height}
                        return app, rect_dict, None
            # Fallback: UIA connect by title or path (can be slow on VPS)
            try:
                app = Application(backend="uia").connect(title_re=".*Viber.*", timeout=CONNECT_TIMEOUT)
            except Exception:
                app = Application(backend="uia").connect(path=VIBER_EXE, timeout=CONNECT_TIMEOUT)
            dlg = app.top_window()
            try:
                dlg.restore()
                dlg.set_focus()
            except Exception:
                pass
            time.sleep(0.12)
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


def _save_last_capture(panel_png: bytes | None, window_png: bytes | None) -> None:
    """Always save last capture to last_panel.png / last_window.png; log success or failure."""
    _agent_dir = os.path.dirname(os.path.abspath(__file__))
    if panel_png is None:
        print("[viber-agent] WARNING: no panel image — nothing to save as last_panel.png", flush=True)
    else:
        try:
            _path = os.path.join(_agent_dir, "last_panel.png")
            with open(_path, "wb") as f:
                f.write(panel_png)
            print("[viber-agent] last_panel.png saved: %s (%s bytes)" % (_path, len(panel_png)), flush=True)
        except Exception as e:
            print("[viber-agent] ERROR: could not save last_panel.png — %s" % e, flush=True)
    if window_png is None:
        print("[viber-agent] (no full window this run; only_panel=true or no window capture)", flush=True)
    else:
        try:
            _path = os.path.join(_agent_dir, "last_window.png")
            with open(_path, "wb") as f:
                f.write(window_png)
            print("[viber-agent] last_window.png saved: %s (%s bytes)" % (_path, len(window_png)), flush=True)
        except Exception as e:
            print("[viber-agent] ERROR: could not save last_window.png — %s" % e, flush=True)


def _panel_rect_from_window(rect_dict: dict) -> dict:
    """Crop region for the panel: RIGHT side, PANEL_TOP+PANEL_STRIP_TOP below top (no white bar), PANEL_WIDTH×PANEL_HEIGHT."""
    left = rect_dict["left"]
    top = rect_dict["top"]
    width = rect_dict["width"]
    height = rect_dict["height"]
    panel_top = top + PANEL_TOP + PANEL_STRIP_TOP
    panel_top = max(top, panel_top)
    if PANEL_USE_FULL_WIDTH:
        panel_left = left
        panel_w = width
    elif PANEL_LEFT:
        panel_left = left
        panel_w = min(PANEL_WIDTH, width)
    else:
        panel_left = left + width - PANEL_WIDTH
        panel_left = max(left, panel_left)
        panel_w = min(PANEL_WIDTH, left + width - panel_left)
    return {
        "left": panel_left,
        "top": panel_top,
        "width": panel_w,
        "height": min(PANEL_HEIGHT, top + height - panel_top),
    }


def _capture_window_printwindow(hwnd: int, rect_dict: dict) -> tuple[bytes | None, bytes | None]:
    """
    Capture window via PrintWindow (window draws into a buffer). Works when RDP is disconnected.
    Returns (window_png_bytes, panel_png_bytes). Returns (None, None) on failure.
    """
    if not HAS_PRINTWINDOW:
        return None, None
    try:
        from PIL import Image
        import win32gui
        import win32ui
    except ImportError:
        return None, None

    w, h = rect_dict["width"], rect_dict["height"]
    if w <= 0 or h <= 0:
        return None, None

    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None, None
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bitmap)

        # Try flag 0 first (some apps render better), then 2 (PW_RENDERFULLCONTENT)
        for pw_flag in (PW_DEFAULT, PW_RENDERFULLCONTENT):
            result = _PrintWindow(hwnd, save_dc.GetSafeHdc(), pw_flag)
            if not result:
                continue
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            try:
                im = Image.frombuffer(
                    "RGB",
                    (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                    bmpstr,
                    "raw",
                    "BGRX",
                    0,
                    1,
                )
            except Exception:
                continue
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            window_png = buf.getvalue()
            if PANEL_USE_FULL_WIDTH:
                panel_w = w
                panel_left = 0
            elif PANEL_LEFT:
                panel_w = min(PANEL_WIDTH, w)
                panel_left = 0
            else:
                panel_w = min(PANEL_WIDTH, w)
                panel_left = max(0, w - PANEL_WIDTH)
            crop_top = min(PANEL_TOP + PANEL_STRIP_TOP, h - 1)
            panel_h = min(PANEL_HEIGHT, h - crop_top)
            if panel_w <= 0 or panel_h <= 0:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                save_dc.DeleteDC()
                return window_png, None
            panel_im = im.crop((panel_left, crop_top, panel_left + panel_w, crop_top + panel_h))
            buf2 = io.BytesIO()
            panel_im.save(buf2, format="PNG")
            panel_png = buf2.getvalue()
            if len(panel_png) >= PANEL_MIN_BYTES:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                save_dc.DeleteDC()
                return window_png, panel_png

        win32gui.ReleaseDC(hwnd, hwnd_dc)
        save_dc.DeleteDC()
        return None, None
    except Exception as e:
        log.debug("PrintWindow capture failed: %s", e)
        return None, None


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

    # 5) Capture window + right panel. Prefer PrintWindow (works when RDP disconnected); fallback to mss.
    t0 = time.monotonic()
    window_png = None
    panel_png = None
    try:
        hwnd = None
        try:
            dlg = viber_app.top_window()
            hwnd = getattr(dlg, "handle", None) or getattr(dlg, "handle_id", None)
        except Exception:
            pass

        if hwnd and HAS_PRINTWINDOW:
            window_png, panel_png = _capture_window_printwindow(hwnd, rect_dict)
            if DEBUG_SAVE_PANEL and panel_png:
                _debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_debug.png")
                try:
                    with open(_debug_path, "wb") as f:
                        f.write(panel_png)
                    print("[viber-agent] DEBUG_SAVE_PANEL: saved to", _debug_path, flush=True)
                except Exception as e:
                    print("[viber-agent] DEBUG_SAVE_PANEL save failed:", e, flush=True)
            # Use PrintWindow only if panel looks substantial (tiny PNG = likely blank/wrong)
            use_pw = panel_png and len(panel_png) >= PANEL_MIN_BYTES
            if only_panel and use_pw:
                print("[viber-agent] screenshot capture (PrintWindow, works when RDP disconnected)", flush=True)
                _log_step("screenshot capture (PrintWindow)", time.monotonic() - t0)
                _save_last_capture(panel_png, None)
                return None, panel_png, None
            if not only_panel and window_png and use_pw:
                print("[viber-agent] screenshot capture (PrintWindow, works when RDP disconnected)", flush=True)
                _log_step("screenshot capture (PrintWindow)", time.monotonic() - t0)
                _save_last_capture(panel_png, window_png)
                return window_png, panel_png, None
            if panel_png and len(panel_png) < PANEL_MIN_BYTES:
                print("[viber-agent] PrintWindow panel too small (%s bytes), using mss fallback" % len(panel_png), flush=True)

        # Fallback: mss (screen grab; requires session to be drawn, e.g. RDP connected)
        with mss.mss() as sct:
            panel_rect = _panel_rect_from_window(rect_dict)
            if only_panel:
                if panel_rect["width"] <= 0 or panel_rect["height"] <= 0:
                    return None, None, "Panel region invalid"
                panel_shot = sct.grab(panel_rect)
                panel_png = mss.tools.to_png(panel_shot.rgb, panel_shot.size)
                window_png = None
            else:
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

    _save_last_capture(panel_png, window_png)
    return window_png, panel_png, None


def _send_message_via_uia(hwnd: int, message: str) -> str | None:
    """
    Use UI Automation: set text on the chat Edit and invoke Send button.
    Works without keyboard focus (e.g. when RDP is disconnected). Returns None on success, error string on failure.
    """
    try:
        time.sleep(1.5)  # let chat UI finish loading before querying UIA
        app_uia = Application(backend="uia").connect(handle=hwnd)
        dlg = app_uia.window(handle=hwnd)
        if os.environ.get("DEBUG_UIA_DUMP", "").strip().lower() in ("1", "true", "yes"):
            _agent_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(_agent_dir, "viber_uia_tree.txt")
            try:
                dlg.print_control_identifiers(depth=None, filename=path)
                print("[viber-agent] UIA tree dumped to %s" % path, flush=True)
            except Exception as dump_err:
                print("[viber-agent] UIA dump failed: %s" % dump_err, flush=True)
        # Message input: Viber's typing box is the Edit whose automation_id contains QQuickTextEdit (UIA tree).
        # Send button: automation_id contains SendToolbarButton. UIA backend has no auto_id_re, so match from descendants.
        def _auto_id(ctrl):
            try:
                return getattr(getattr(ctrl, "element_info", None), "automation_id", None) or ""
            except Exception:
                return ""

        edit = None
        for c in dlg.descendants(control_type="Edit"):
            if "QQuickTextEdit" in _auto_id(c):
                edit = c
                break
        if edit is None:
            edits = dlg.descendants(control_type="Edit")
            if not edits:
                return "No Edit control found"
            edit = edits[-1]
        edit.set_focus()
        edit.set_edit_text(message)
        time.sleep(0.2)

        send_btn = None
        for b in dlg.descendants(control_type="Button"):
            if "SendToolbarButton" in _auto_id(b):
                send_btn = b
                break
        if send_btn is None:
            for b in dlg.descendants(control_type="Button"):
                try:
                    if (b.window_text() or "").strip() in ("Send", "Изпрати", "Senden", "Envoyer", "Enviar"):
                        send_btn = b
                        break
                except Exception:
                    continue
        if send_btn is None:
            return "Send button not found"
        try:
            send_btn.invoke()
        except Exception:
            try:
                send_btn.click()
            except Exception as click_err:
                return "Send button invoke/click failed: %s" % click_err
        return None
    except Exception as e:
        return str(e)


def do_viber_send_message(phone_number: str, message: str) -> str | None:
    """
    Open Viber chat with the given number, type the message, send it, then close Viber.
    Tries UIA first (Edit + Send button; works when RDP disconnected). Falls back to keyboard if UIA fails.
    Returns None on success, or an error message string.
    """
    if not HAS_PYWINAUTO:
        return "pywinauto not installed"
    if not message or not message.strip():
        return "Message is empty"
    msg = message.strip()

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

    hwnd = getattr(dlg, "handle", None) or getattr(dlg, "handle_id", None)
    t0 = time.monotonic()
    sent = False

    uia_error = None
    if hwnd:
        err_uia = _send_message_via_uia(hwnd, msg)
        if err_uia is None:
            sent = True
            print("[viber-agent] send message via UIA (Edit + Send button)", flush=True)
        else:
            uia_error = err_uia
            print("[viber-agent] UIA send failed: %s — falling back to keyboard" % (err_uia,), flush=True)

    if not sent and _keyboard_send_keys is not None:
        try:
            import win32gui
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.2)
        except Exception:
            pass
        safe = msg.replace("{", "{{").replace("}", "}}")
        for attempt in range(2):
            try:
                _keyboard_send_keys(safe + "{ENTER}", with_spaces=True)
                sent = True
                break
            except Exception as e:
                err_msg = str(e).strip()
                if "inserted only 0" in err_msg.lower() or "0 out of" in err_msg:
                    err_msg = (
                        "UIA path failed (%s). Keyboard fallback failed because RDP is not in the foreground. "
                        "Keep RDP connected and the Viber window visible, or ensure Viber exposes the message box and Send button to UI Automation."
                    ) % (uia_error or "unknown")
                if attempt == 0 and hwnd:
                    try:
                        import win32gui
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.5)
                    except Exception:
                        pass
                    continue
                _log_step("type message", time.monotonic() - t0)
                return f"Failed to type/send: {err_msg}"
    elif not sent:
        _log_step("type message", time.monotonic() - t0)
        return "Could not send via UIA and keyboard not available"

    _log_step("type message + Send", time.monotonic() - t0)

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


@app.route("/api", methods=["GET"])
@app.route("/api/v1", methods=["GET"])
def api_info():
    """API info and discovery."""
    base = request.url_root.rstrip("/")
    return jsonify(
        name="Viber Agent API",
        version=API_VERSION,
        docs="%s/docs" % base,
        openapi="%s/openapi.json" % base,
        endpoints={
            "health": {"method": "GET", "path": "/health", "description": "Service health and capabilities"},
            "lookup": {"method": "POST", "path": "/check-number-base64", "description": "Look up a number and get contact name + panel image (base64)"},
            "send_message": {"method": "POST", "path": "/send-message", "description": "Send a message to a number via Viber"},
        },
    )


def _openapi_spec():
    base = request.url_root.rstrip("/")
    return {
        "openapi": "3.0.3",
        "info": {"title": "Viber Agent API", "version": API_VERSION, "description": "Automate Viber lookups and send messages via this agent (runs on Windows with Viber desktop)."},
        "servers": [{"url": base}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "operationId": "health",
                    "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "viber_exists": {"type": "boolean"}, "ocr": {"type": "boolean"}}}}}}},
                }
            },
            "/check-number-base64": {
                "post": {
                    "summary": "Look up number",
                    "operationId": "lookup",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "required": ["number"], "properties": {"number": {"type": "string", "description": "Phone number"}, "only_panel": {"type": "boolean", "default": True}}}}}},
                    "responses": {
                        "200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {"number": {}, "contact_name": {}, "panel_base64": {}, "panel_text": {}}}}}},
                        "400": {"description": "Bad request", "content": {"application/json": {"schema": {"type": "object", "properties": {"error": {"type": "string"}}}}}},
                        "500": {"description": "Server error", "content": {"application/json": {"schema": {"type": "object", "properties": {"error": {"type": "string"}}}}}},
                    },
                }
            },
            "/send-message": {
                "post": {
                    "summary": "Send message",
                    "operationId": "sendMessage",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "required": ["number", "message"], "properties": {"number": {"type": "string"}, "message": {"type": "string"}}}}}},
                    "responses": {
                        "200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {"ok": {"type": "boolean"}, "number": {"type": "string"}}}}}},
                        "400": {"description": "Bad request"},
                        "500": {"description": "Server error"},
                    },
                }
            },
        },
        "components": {"securitySchemes": {"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key", "description": "Required if AGENT_API_KEY is set on the server"}}, "security": []},
    }


@app.route("/openapi.json", methods=["GET"])
def openapi_json():
    return jsonify(_openapi_spec())


@app.route("/docs", methods=["GET"])
def docs():
    """Serve Swagger UI for the API."""
    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Viber Agent API – Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "%s/openapi.json",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis],
    });
  </script>
</body>
</html>""" % request.url_root.rstrip("/")
    return Response(html, mimetype="text/html")


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
    if ocr_image_bytes and not _has_gpt_ocr():
        print("[viber-agent] OCR skipped: OPENAI_API_KEY not set (add to .env on the VPS)", flush=True)
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
    parser.add_argument("--dev", action="store_true", help="Use Flask dev server (default: use Waitress if installed)")
    args = parser.parse_args()
    try:
        if args.dev:
            raise ImportError("use Flask")
        import waitress
        print("[viber-agent] Using Waitress WSGI server", flush=True)
        waitress.serve(app, host=args.host, port=args.port, threads=6)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
