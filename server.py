#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from macropad import (
    DEFAULT_CONFIG,
    ROOT,
    TOOL,
    backup,
    config_from_dict,
    config_to_dict,
    detect_address,
    load_config,
    normalize_action,
    save_config,
)


UI_ROOT = ROOT / "ui"
LED_SETTINGS = ROOT / "led-settings.json"
UPLOAD_STATUS = ROOT / "upload-status.json"


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            return self.send_json(config_to_dict(load_config(DEFAULT_CONFIG)))
        if path == "/api/actions":
            return self.send_json({"actions": self.actions()})
        if path == "/api/led":
            return self.send_json(self.led_settings())
        if path == "/api/upload-status":
            return self.send_json(self.upload_status())
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            data = self.read_json()
            config = config_from_dict(data)
            self.normalize_config(config)
            backup_path = backup(DEFAULT_CONFIG)
            save_config(config, DEFAULT_CONFIG)
            validation = self.run([str(TOOL), "validate", str(DEFAULT_CONFIG)])
            status = 200 if validation.returncode == 0 else 400
            return self.send_json(
                {
                    "ok": validation.returncode == 0,
                    "backup": str(backup_path),
                    "stdout": validation.stdout,
                    "stderr": validation.stderr,
                },
                status=status,
            )
        if path == "/api/validate":
            result = self.run([str(TOOL), "validate", str(DEFAULT_CONFIG)])
            return self.send_json(
                {
                    "ok": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                status=200 if result.returncode == 0 else 400,
            )
        if path == "/api/upload":
            address = detect_address()
            command = [str(TOOL), "--vendor-id", "0x1189", "--product-id", "0x8890"]
            if address:
                command.extend(["--address", address])
            command.extend(["upload", str(DEFAULT_CONFIG)])
            result = self.run(command)
            status_data = {
                "ok": result.returncode == 0,
                "address": address,
                "exitCode": result.returncode,
                "completedAt": datetime.now().isoformat(timespec="seconds"),
                "command": " ".join(command),
                "stdout": result.stdout,
                "stderr": result.stderr
                or ("" if address else "USB address was not auto-detected; upload tried without --address."),
            }
            UPLOAD_STATUS.write_text(json.dumps(status_data, indent=2) + "\n")
            return self.send_json(
                status_data,
                status=200 if result.returncode == 0 else 500,
            )
        if path == "/api/led":
            data = self.read_json()
            settings = self.led_settings()
            layer = int(data.get("layer", 1))
            mode = int(data.get("mode", 1))
            color = str(data.get("color", "#ffffff"))
            settings[str(layer)] = {"mode": mode, "color": color}
            LED_SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")

            address = detect_address()
            command = [str(TOOL), "--vendor-id", "0x1189", "--product-id", "0x8890"]
            if address:
                command.extend(["--address", address])
            command.extend(["led", str(mode)])
            result = self.run(command)
            return self.send_json(
                {
                    "ok": result.returncode == 0,
                    "address": address,
                    "settings": settings,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                    or "0x8890 exposes LED mode numbers only; selected colors are saved in the editor but may not be supported by the pad.",
                },
                status=200 if result.returncode == 0 else 500,
            )
        self.send_error(404)

    def read_json(self):
        length = int(self.headers.get("content-length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def normalize_config(self, config):
        for layer in config.layers:
            for row in layer.get("buttons", []):
                for index, action in enumerate(row):
                    row[index] = normalize_action(str(action))
            for knob in layer.get("knobs", []):
                for direction in ("ccw", "press", "cw"):
                    knob[direction] = normalize_action(str(knob.get(direction, "")))

    def actions(self):
        return [
            "copy",
            "paste",
            "cut",
            "undo",
            "redo",
            "save",
            "spotlight",
            "volup",
            "voldown",
            "mute",
            "play",
            "next",
            "previous",
            "wheelup",
            "wheeldown",
            "click",
            "cmd-c",
            "cmd-v",
            "cmd-x",
            "cmd-z",
            "cmd-shift-z",
            "cmd-s",
            "cmd-space",
            "ctrl-c",
            "ctrl-v",
            "ctrl-z",
            "ctrl-shift-z",
            "enter",
            "escape",
            "tab",
            "space",
            "backspace",
            "delete",
            "left",
            "right",
            "up",
            "down",
            "home",
            "end",
            "pageup",
            "pagedown",
            "macbrightnessdown",
            "macbrightnessup",
            *[f"f{number}" for number in range(1, 25)],
            *list("abcdefghijklmnopqrstuvwxyz"),
            *[str(number) for number in range(10)],
        ]

    def led_settings(self):
        if LED_SETTINGS.exists():
            return json.loads(LED_SETTINGS.read_text())
        return {
            "1": {"mode": 1, "color": "#ffffff"},
            "2": {"mode": 2, "color": "#14b8a6"},
            "3": {"mode": 5, "color": "#6366f1"},
        }

    def upload_status(self):
        if UPLOAD_STATUS.exists():
            return json.loads(UPLOAD_STATUS.read_text())
        return {
            "ok": None,
            "address": None,
            "exitCode": None,
            "completedAt": None,
            "command": None,
            "stdout": "",
            "stderr": "No upload has been recorded yet.",
        }

    def run(self, args):
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)

    def log_message(self, format, *args):
        print(format % args)


def main():
    port = 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"SikaiCase editor running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
