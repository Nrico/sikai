# SikaiCase Macro Pad Web Editor

A local web editor for programming a SikaiCase / CH57x 6-key + knob macro pad
on macOS. The browser UI edits the mapping; a small local Python server talks to
`ch57x-keyboard-tool`, which writes the mapping to the USB device.

## Why local?

A hosted GitHub Pages site cannot reliably control this keypad by itself. The
browser page needs a local companion server because USB access, file writes, and
the `ch57x-keyboard-tool` upload command happen on your Mac.

## Quick Start

Install Homebrew `libusb` if you do not already have it:

```sh
brew install libusb
```

Download the macOS programmer binary:

```sh
./install-tool.sh
```

Start the editor:

```sh
python3 server.py
```

Open:

```text
http://127.0.0.1:8765
```

Use the page to edit keys, save the mapping, and upload it to the connected pad.
The **Last Upload** panel confirms whether the upload command reached the
device and exited successfully.

If the upload works but the USB address is shown as unknown, the app simply did
not find the optional local `usb_list` helper. The programmer can still upload
when only one matching keypad is connected.

## Device found

macOS sees the macro pad as USB HID device `1189:8890`.

- Vendor ID: `0x1189` / decimal `4489`
- Product ID: `0x8890` / decimal `34960`
- HID collections exposed:
  - keyboard, usage page `1`, usage `6`
  - keyboard, usage page `1`, usage `6`
  - mouse, usage page `1`, usage `2`

Those IDs match common CH57x-based programmable macro pads.

## Tool

This project uses the macOS release of:

https://github.com/kriomant/ch57x-keyboard-tool

`install-tool.sh` downloads that release and verifies this SHA-256 checksum:

```sh
shasum -a 256 ch57x-keyboard-tool-universal-apple-darwin.tar.gz
```

Expected/current:

```text
2ca4b93c9624486a8f68351f2195ed812c36d981c92bb314d5019b0d93db29b1
```

The tool needs Homebrew `libusb`:

```sh
brew install libusb
```

## Web editor

Start the local editor:

```sh
python3 server.py
```

Then open:

```text
http://127.0.0.1:8765
```

The editor writes `sikaicase-starter.yaml`, creates backups before saving, and
uses the same upload command as `macropad.py`.

The on-screen pad is rotated 90 degrees counterclockwise from the YAML's normal
orientation: keys display as a two-row by three-column block, with the knob on
the right.

Layer 1 is the only practically usable layer at the moment. The tool can write
mappings for layers 2 and 3, but we do not have a working way to switch this
`0x8890` 6-key pad into those layers from the device. Until a layer-switch
mechanism is found, layers 2 and 3 should be treated as inaccessible/experimental.

The lighting panel stores a desired color per layer in the editor and can send
the `0x8890` LED mode command. This hardware/tool path exposes mode numbers
only, so colors may be visual notes unless we later find a working color
protocol for this exact pad.

## Macro helper

Use `macropad.py` for command-line key changes. Rows are numbered top to bottom,
columns left to right, and layers start at `1`.

Show the current mapping:

```sh
./macropad.py show
```

Set a button:

```sh
./macropad.py set 1 1 1 copy
./macropad.py set 1 1 2 paste
./macropad.py set 1 3 2 spotlight
```

Set the knob:

```sh
./macropad.py knob 1 ccw voldown
./macropad.py knob 1 press mute
./macropad.py knob 1 cw volup
```

Set several controls at once:

```sh
./macropad.py batch layer=1 1=copy 2=paste 3=undo 4=redo 5=save 6=spotlight ccw=voldown press=mute cw=volup
```

In batch mode, buttons `1` through `6` are row-major: top-left, top-right,
middle-left, middle-right, bottom-left, bottom-right.

Validate and upload:

```sh
./macropad.py validate
./macropad.py upload
```

Each edit makes a timestamped `.bak-*` backup next to the mapping file before
writing the new value. The helper understands short aliases like `copy`,
`paste`, `undo`, `redo`, `save`, `spotlight`, `volup`, and `voldown`. To see the
full list of actions supported by the underlying programmer:

```sh
./macropad.py keys
```

## Low-level commands

List supported key/action names:

```sh
./ch57x-keyboard-tool show-keys
```

Validate a mapping without writing to the device:

```sh
./ch57x-keyboard-tool validate sikaicase-starter.yaml
```

Upload a mapping to the device:

```sh
./ch57x-keyboard-tool --vendor-id 0x1189 --product-id 0x8890 --address 1:3 upload sikaicase-starter.yaml
```

Set LED mode on `1189:8890` pads:

```sh
./ch57x-keyboard-tool --vendor-id 0x1189 --product-id 0x8890 --address 1:3 led 1
```

Known-good write test:

```sh
./ch57x-keyboard-tool --vendor-id 0x1189 --product-id 0x8890 --address 1:3 upload sikaicase-starter.yaml
```

LED modes `1` through `5` were sent successfully. The tool accepts a mode number for this `0x8890`
device, but does not expose per-key RGB color arguments for this model.

For LED reverse engineering notes and packet replay, see `LED_REVERSE_ENGINEERING.md`.

## Related project

Justin Howell's `sikaicase-tool` confirms this model's protocol details and
uses a convenient CLI style that inspired the `batch` command here:

https://github.com/justinrhowell/sikaicase-tool
