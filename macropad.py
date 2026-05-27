#!/usr/bin/env python3
import argparse
import ast
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "sikaicase-starter.yaml"
TOOL = ROOT / "ch57x-keyboard-tool"
USB_LIST = ROOT / "usb_list"

ALIASES = {
    "copy": "cmd-c",
    "paste": "cmd-v",
    "cut": "cmd-x",
    "undo": "cmd-z",
    "redo": "cmd-shift-z",
    "save": "cmd-s",
    "spotlight": "cmd-space",
    "enter": "enter",
    "esc": "escape",
    "escape": "escape",
    "mute": "mute",
    "volup": "volumeup",
    "voldown": "volumedown",
    "play": "play",
    "next": "next",
    "prev": "previous",
    "previous": "previous",
}


@dataclass
class Config:
    orientation: str
    rows: int
    columns: int
    knobs: int
    layers: list


def normalize_action(action: str) -> str:
    action = action.strip()
    normalized = ALIASES.get(action.lower(), action)
    return normalized.replace("+", "-")


def load_config(path: Path) -> Config:
    text = path.read_text()
    orientation = re.search(r"^orientation:\s*(\S+)", text, re.M)
    rows = re.search(r"^rows:\s*(\d+)", text, re.M)
    columns = re.search(r"^columns:\s*(\d+)", text, re.M)
    knobs = re.search(r"^knobs:\s*(\d+)", text, re.M)
    if not all([orientation, rows, columns, knobs]):
        raise SystemExit(f"Could not read required pad settings from {path}")

    row_count = int(rows.group(1))
    column_count = int(columns.group(1))
    knob_count = int(knobs.group(1))

    layers = []
    current = None
    in_buttons = False
    in_knobs = False
    current_knob = None

    for raw in text.splitlines():
        line = raw.strip()
        if line == "- buttons:":
            current = {"buttons": [], "knobs": []}
            layers.append(current)
            in_buttons = True
            in_knobs = False
            current_knob = None
            continue
        if line == "buttons:":
            in_buttons = True
            in_knobs = False
            continue
        if line == "knobs:":
            in_buttons = False
            in_knobs = True
            current_knob = None
            continue
        if current is None:
            continue

        if in_buttons and line.startswith("- ["):
            try:
                row = ast.literal_eval(line[2:])
            except (SyntaxError, ValueError) as exc:
                raise SystemExit(f"Could not parse button row: {line}") from exc
            current["buttons"].append(row)
            continue

        if in_knobs and line.startswith("- ccw:"):
            current_knob = {"ccw": value_after_colon(line), "press": "", "cw": ""}
            current["knobs"].append(current_knob)
            continue

        if in_knobs and current_knob is not None and line.startswith("press:"):
            current_knob["press"] = value_after_colon(line)
            continue

        if in_knobs and current_knob is not None and line.startswith("cw:"):
            current_knob["cw"] = value_after_colon(line)
            continue

    if not layers:
        raise SystemExit(f"No layers found in {path}")

    for idx, layer in enumerate(layers, start=1):
        if len(layer["buttons"]) != row_count:
            raise SystemExit(f"Layer {idx} has {len(layer['buttons'])} button rows, expected {row_count}")
        for row in layer["buttons"]:
            if len(row) != column_count:
                raise SystemExit(f"Layer {idx} has a row with {len(row)} buttons, expected {column_count}")
        while len(layer["knobs"]) < knob_count:
            layer["knobs"].append({"ccw": "", "press": "", "cw": ""})

    return Config(orientation.group(1), row_count, column_count, knob_count, layers)


def value_after_colon(line: str) -> str:
    value = line.split(":", 1)[1].strip()
    if value.startswith('"') and value.endswith('"'):
        return ast.literal_eval(value)
    return value


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_config(config: Config, path: Path) -> None:
    lines = [
        f"orientation: {config.orientation}",
        f"rows: {config.rows}",
        f"columns: {config.columns}",
        f"knobs: {config.knobs}",
        "",
        "layers:",
    ]
    for layer in config.layers:
        lines.append("  - buttons:")
        for row in layer["buttons"]:
            lines.append("      - [" + ", ".join(quote(item) for item in row) + "]")
        lines.append("    knobs:")
        for knob in layer["knobs"]:
            lines.append(f"      - ccw: {quote(knob.get('ccw', ''))}")
            lines.append(f"        press: {quote(knob.get('press', ''))}")
            lines.append(f"        cw: {quote(knob.get('cw', ''))}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")


def config_to_dict(config: Config) -> dict:
    return {
        "orientation": config.orientation,
        "rows": config.rows,
        "columns": config.columns,
        "knobs": config.knobs,
        "layers": config.layers,
    }


def config_from_dict(data: dict) -> Config:
    return Config(
        data.get("orientation", "normal"),
        int(data.get("rows", 3)),
        int(data.get("columns", 2)),
        int(data.get("knobs", 1)),
        data.get("layers", []),
    )


def show(config: Config) -> None:
    print(f"{config.rows}x{config.columns} + {config.knobs} knob macro pad")
    for layer_index, layer in enumerate(config.layers, start=1):
        print(f"\nLayer {layer_index}")
        for row_index, row in enumerate(layer["buttons"], start=1):
            cells = [f"r{row_index}c{col_index}={value}" for col_index, value in enumerate(row, start=1)]
            print("  " + " | ".join(cells))
        for knob_index, knob in enumerate(layer["knobs"], start=1):
            print(
                f"  knob{knob_index}: ccw={knob.get('ccw', '')} "
                f"press={knob.get('press', '')} cw={knob.get('cw', '')}"
            )


def button_number_to_position(config: Config, number: int) -> tuple[int, int]:
    if not (1 <= number <= config.rows * config.columns):
        raise SystemExit(f"Button number must be 1-{config.rows * config.columns}")
    row = (number - 1) // config.columns
    column = (number - 1) % config.columns
    return row, column


def apply_batch(config: Config, layer: int, assignments: list[str]) -> None:
    knob_aliases = {"ccw": "ccw", "cw": "cw", "knob": "press", "press": "press"}
    layer_index = layer - 1

    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"Invalid assignment '{assignment}', expected name=action")
        target, action = assignment.split("=", 1)
        target = target.strip().lower()
        action = normalize_action(action)

        if target in knob_aliases:
            config.layers[layer_index]["knobs"][0][knob_aliases[target]] = action
            print(f"Set layer {layer} knob {knob_aliases[target]} to {action}")
            continue

        try:
            number = int(target)
        except ValueError as exc:
            raise SystemExit(f"Invalid target '{target}', use 1-6, ccw, press, knob, or cw") from exc

        row, column = button_number_to_position(config, number)
        config.layers[layer_index]["buttons"][row][column] = action
        print(f"Set layer {layer} button {number} to {action}")


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = path.with_suffix(path.suffix + f".bak-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def run_tool(args: list[str]) -> int:
    return subprocess.call([str(TOOL), *args], cwd=ROOT)


def detect_address() -> str | None:
    if not USB_LIST.exists():
        return None
    proc = subprocess.run([str(USB_LIST)], cwd=ROOT, text=True, capture_output=True)
    for line in proc.stdout.splitlines():
        match = re.search(r"bus\s+(\d+)\s+addr\s+(\d+)\s+id\s+1189:8890", line)
        if match:
            return f"{int(match.group(1))}:{int(match.group(2))}"
    return None


def upload(path: Path, address: str | None) -> int:
    args = ["--vendor-id", "0x1189", "--product-id", "0x8890"]
    if address:
        args.extend(["--address", address])
    args.extend(["upload", str(path)])
    return run_tool(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit and upload the SikaiCase 3x2+knob macro-pad mapping.")
    parser.add_argument("--file", default=str(DEFAULT_CONFIG), help="mapping YAML file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="show current mapping")
    sub.add_parser("keys", help="show actions supported by ch57x-keyboard-tool")
    sub.add_parser("validate", help="validate the mapping")
    sub.add_parser("upload", help="upload the mapping to the macro pad")
    sub.add_parser("backup", help="copy the current mapping to a timestamped backup")

    set_cmd = sub.add_parser("set", help="set a button action")
    set_cmd.add_argument("layer", type=int, help="layer number, starting at 1")
    set_cmd.add_argument("row", type=int, help="row number, starting at 1")
    set_cmd.add_argument("column", type=int, help="column number, starting at 1")
    set_cmd.add_argument("action", help="action, such as copy, cmd-c, f13, click, wheelup")

    knob_cmd = sub.add_parser("knob", help="set a knob action")
    knob_cmd.add_argument("layer", type=int, help="layer number, starting at 1")
    knob_cmd.add_argument("direction", choices=["ccw", "press", "cw"])
    knob_cmd.add_argument("action", help="action, such as voldown, mute, volumeup, left, enter")

    batch_cmd = sub.add_parser("batch", help="set several controls at once, e.g. layer=1 1=copy 2=paste cw=volup")
    batch_cmd.add_argument("assignments", nargs="+", help="assignments such as layer=2, 1=cmd-c, ccw=voldown")

    args = parser.parse_args()
    path = Path(args.file).resolve()

    if args.command == "keys":
        return run_tool(["show-keys"])

    if args.command == "validate":
        return run_tool(["validate", str(path)])

    if args.command == "upload":
        address = detect_address()
        if not address:
            print("Could not auto-detect USB address; trying upload without --address.", file=sys.stderr)
        return upload(path, address)

    if args.command == "backup":
        print(backup(path))
        return 0

    config = load_config(path)

    if args.command == "show":
        show(config)
        return 0

    if args.command == "set":
        if not (1 <= args.layer <= len(config.layers)):
            raise SystemExit(f"Layer must be 1-{len(config.layers)}")
        if not (1 <= args.row <= config.rows):
            raise SystemExit(f"Row must be 1-{config.rows}")
        if not (1 <= args.column <= config.columns):
            raise SystemExit(f"Column must be 1-{config.columns}")
        backup_path = backup(path)
        action = normalize_action(args.action)
        config.layers[args.layer - 1]["buttons"][args.row - 1][args.column - 1] = action
        save_config(config, path)
        print(f"Set layer {args.layer} row {args.row} column {args.column} to {action}")
        print(f"Backup: {backup_path}")
        return run_tool(["validate", str(path)])

    if args.command == "knob":
        if not (1 <= args.layer <= len(config.layers)):
            raise SystemExit(f"Layer must be 1-{len(config.layers)}")
        backup_path = backup(path)
        action = normalize_action(args.action)
        config.layers[args.layer - 1]["knobs"][0][args.direction] = action
        save_config(config, path)
        print(f"Set layer {args.layer} knob {args.direction} to {action}")
        print(f"Backup: {backup_path}")
        return run_tool(["validate", str(path)])

    if args.command == "batch":
        layer = 1
        assignments = []
        for assignment in args.assignments:
            if assignment.lower().startswith("layer="):
                layer = int(assignment.split("=", 1)[1])
            else:
                assignments.append(assignment)
        if not (1 <= layer <= len(config.layers)):
            raise SystemExit(f"Layer must be 1-{len(config.layers)}")
        if not assignments:
            raise SystemExit("No key assignments provided")
        backup_path = backup(path)
        apply_batch(config, layer, assignments)
        save_config(config, path)
        print(f"Backup: {backup_path}")
        return run_tool(["validate", str(path)])

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
