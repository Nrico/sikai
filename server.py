#!/usr/bin/env python3
import json
import subprocess
from copy import deepcopy
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
UPLOAD_CONFIG = ROOT / ".sikaicase-upload.yaml"
LED_SENDER = ROOT / "ch57x_send"
LED_RAW_SENDER = ROOT / "ch57x_raw_send"
LED_COLOR_CODES = {
    "#ffffff": 0x00,
    "#ef4444": 0x10,
    "#f97316": 0x20,
    "#eab308": 0x30,
    "#22c55e": 0x40,
    "#06b6d4": 0x50,
    "#3b82f6": 0x60,
    "#8b5cf6": 0x70,
}


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
        if path == "/api/device":
            return self.send_json(self.device_status())
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
            upload_path = self.write_upload_config()
            command = [str(TOOL), "--vendor-id", "0x1189", "--product-id", "0x8890"]
            if address:
                command.extend(["--address", address])
            command.extend(["upload", str(upload_path)])
            result = self.run(command)
            status_data = {
                "ok": result.returncode == 0,
                "address": address,
                "exitCode": result.returncode,
                "completedAt": datetime.now().isoformat(timespec="seconds"),
                "command": " ".join(command),
                "uploadedFile": str(upload_path),
                "mirroredLayer": 1,
                "stdout": result.stdout,
                "stderr": result.stderr
                or (
                    "Layer 1 was mirrored to all hardware layers for upload."
                    if address
                    else "USB address was not auto-detected; upload tried without --address."
                ),
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
            key = str(data.get("key", "all"))
            protocol = str(data.get("protocol", "vendor")).lower()
            if str(layer) not in settings:
                settings[str(layer)] = {"keys": {}}
            settings[str(layer)].setdefault("keys", {})
            settings[str(layer)]["keys"][key] = {"mode": mode, "color": color}
            LED_SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")

            color_code = LED_COLOR_CODES.get(color.lower(), 0)
            encoded_mode = (color_code | (mode & 0x0F)) & 0xFF
            commands = self.led_commands(protocol, layer, key, encoded_mode)
            results = [self.run(command) for command in commands]
            result = results[-1] if results else self.empty_result(2, "No LED command was generated.")
            ok = bool(commands) and all(item.returncode == 0 for item in results)
            return self.send_json(
                {
                    "ok": ok,
                    "address": detect_address(),
                    "protocol": protocol,
                    "command": " && ".join(" ".join(command) for command in commands),
                    "reportCount": len(commands),
                    "reports": [command[-64:] for command in commands if command and command[0] == str(LED_RAW_SENDER)],
                    "encodedMode": f"0x{encoded_mode:02x}",
                    "settings": settings,
                    "stdout": "\n".join(item.stdout for item in results if item.stdout),
                    "stderr": "\n".join(item.stderr for item in results if item.stderr)
                    or self.led_status_message(protocol, key),
                },
                status=200 if ok else 500,
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

    def write_upload_config(self):
        config = load_config(DEFAULT_CONFIG)
        self.normalize_config(config)
        if config.layers:
            live_layer = deepcopy(config.layers[0])
            config.layers = [deepcopy(live_layer) for _ in config.layers]
        save_config(config, UPLOAD_CONFIG)
        return UPLOAD_CONFIG

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
            return self.normalize_led_settings(json.loads(LED_SETTINGS.read_text()))
        return {
            "1": {"keys": {"all": {"mode": 1, "color": "#ffffff"}}},
            "2": {"keys": {"all": {"mode": 1, "color": "#14b8a6"}}},
            "3": {"keys": {"all": {"mode": 1, "color": "#6366f1"}}},
        }

    def normalize_led_settings(self, settings):
        normalized = {}
        for layer, value in settings.items():
            if "keys" in value:
                normalized[layer] = value
            else:
                normalized[layer] = {"keys": {"all": value}}
        return normalized

    def led_commands(self, protocol, layer, key, encoded_mode):
        if protocol == "global":
            return [self.global_led_command(encoded_mode)]
        return self.vendor_led_commands(layer, key, encoded_mode)

    def global_led_command(self, encoded_mode):
        if LED_SENDER.exists():
            return [
                str(LED_SENDER),
                "0x03",
                "0xa1",
                "0x01",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0x03",
                "0xb0",
                "0x18",
                f"0x{encoded_mode:02x}",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0x03",
                "0xaa",
                "0xa1",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
            ]
        return [str(TOOL), "--vendor-id", "0x1189", "--product-id", "0x8890", "led", str(encoded_mode)]

    def vendor_led_commands(self, layer, key, encoded_mode):
        if not LED_RAW_SENDER.exists():
            return [self.global_led_command(encoded_mode)]

        config = load_config(DEFAULT_CONFIG)
        key_numbers = range(1, config.rows * config.columns + 1) if key == "all" else [int(key)]
        commands = []
        for key_number in key_numbers:
            report = self.vendor_led_report(layer, key_number, encoded_mode)
            commands.append([str(LED_RAW_SENDER), *[f"0x{byte:02x}" for byte in report]])
        commands.extend(
            [str(LED_RAW_SENDER), *[f"0x{byte:02x}" for byte in self.vendor_led_commit_report(layer_index)]]
            for layer_index in range(3)
        )
        return commands

    def vendor_led_report(self, layer, key_number, encoded_mode):
        report = [0] * 64
        # Vendor Windows app shape: report ID 0x03 followed by a per-key record
        # beginning fe b0. Byte 0x0b within that record stores color|LED_Mode.
        record = [
            0xFE,
            0xB0,
            max(1, min(int(layer), 3)),
            max(1, min(int(key_number), 15)),
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            encoded_mode,
        ]
        report[0] = 0x03
        report[1 : 1 + len(record)] = record
        return report

    def vendor_led_commit_report(self, layer_index):
        report = [0] * 64
        report[0] = 0x03
        report[1] = 0xFE
        report[2] = 0xB0
        report[3] = max(0, min(int(layer_index), 2))
        report[5] = 0x01
        return report

    def led_status_message(self, protocol, key):
        if protocol == "global":
            return "Global LED mode packet sent. This was the older 0x8890 path and may affect all LEDs at once."
        target = "all keys" if key == "all" else f"key {key}"
        return (
            f"Vendor-style per-key LED record sent for {target}. "
            "This follows the PC software packet shape; if a mapping changes, click Upload to restore the saved layout."
        )

    def empty_result(self, code, stderr):
        return subprocess.CompletedProcess(args=[], returncode=code, stdout="", stderr=stderr)

    def device_status(self):
        address = detect_address()
        detector_available = (ROOT / "usb_list").exists()
        connected = bool(address) if detector_available else None
        if connected:
            message = f"SikaiCase connected at USB address {address}."
        elif detector_available:
            message = "SikaiCase USB device 1189:8890 was not found."
        else:
            message = "USB detector helper is not installed, so connection status is unknown."
        return {
            "connected": connected,
            "address": address,
            "detectorAvailable": detector_available,
            "vendorId": "0x1189",
            "productId": "0x8890",
            "checkedAt": datetime.now().isoformat(timespec="seconds"),
            "message": message,
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
