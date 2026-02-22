"""
Client to request a screenshot from the Viber agent running on another PC.
Usage:
  python client.py <agent_url> <phone_number> [output.png]
  python client.py --panel <agent_url> <phone_number> [output.png]   # only highlighted part
  python client.py --photo <agent_url> <phone_number> [output_prefix]  # two PNGs: ..._window.png, ..._panel.png
Example:
  python client.py http://127.0.0.1:5050 +1234567890 screenshot.png
  python client.py --photo http://127.0.0.1:5050 +1234567890 viber   # -> viber_window.png, viber_panel.png
"""

import sys
import requests
from email import policy
from email.parser import BytesParser


def main():
    args = sys.argv[1:]
    only_panel = False
    include_photo = False
    if args and args[0] == "--panel":
        only_panel = True
        args = args[1:]
    elif args and args[0] == "--photo":
        include_photo = True
        args = args[1:]

    if len(args) < 2:
        print("Usage: client.py [--panel | --photo] <agent_url> <phone_number> [output_file]")
        print("  --panel  only the highlighted part (right panel: photo + name + icons)")
        print("  --photo  two screenshots: <prefix>_window.png and <prefix>_panel.png")
        sys.exit(1)

    base_url = args[0].rstrip("/")
    number = args[1]
    output_file = args[2] if len(args) > 2 else "viber_screenshot"
    if not include_photo and not only_panel:
        if not output_file.lower().endswith(".png"):
            output_file = output_file + ".png"

    url = f"{base_url}/check-number"
    try:
        r = requests.post(
            url,
            json={"number": number, "only_panel": only_panel, "include_photo": include_photo},
            timeout=60,
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text if "r" in dir() else str(e)
        print(f"Request failed: {err}")
        sys.exit(2)

    ct = r.headers.get("content-type") or ""
    if include_photo and "multipart" in ct:
        msg = BytesParser(policy=policy.default).parsebytes(r.content)
        prefix = output_file.rstrip(".png") if output_file.lower().endswith(".png") else output_file
        names = {"viber_window.png": f"{prefix}_window.png", "contact_panel.png": f"{prefix}_panel.png"}
        for part in msg.iter_parts():
            name = part.get_filename()
            fn = names.get(name, name or f"{prefix}_part.png")
            with open(fn, "wb") as f:
                f.write(part.get_content())
            print(f"Saved: {fn}")
    else:
        with open(output_file, "wb") as f:
            f.write(r.content)
        print(f"Saved: {output_file}")


if __name__ == "__main__":
    main()
