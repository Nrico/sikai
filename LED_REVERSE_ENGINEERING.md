# LED Reverse Engineering Plan

## What we know

The macro pad is USB `1189:8890`.

Raw USB descriptors:

```text
interface 0: HID boot keyboard, endpoint 0x81 in
interface 1: HID vendor-ish programming channel, endpoint 0x02 out, 64-byte interrupt writes
interface 2: HID input, endpoint 0x83 in
interface 3: HID boot mouse, endpoint 0x82 in
```

The open-source `ch57x-keyboard-tool` successfully writes key mappings through interface `1`,
endpoint `0x02`.

For `0x8890`, its known LED command is:

```text
03 a1 01 00 00 00 00 00 00
03 b0 18 MODE 00 00 00 00 00
03 aa a1 00 00 00 00 00 00
```

Each 9-byte message is padded with zeros to a 64-byte interrupt OUT transfer.

Modes `0` through `8` were accepted by the device but did not visibly change LEDs on this unit.

## MYKB.app inspection

`/Applications/MYKB.app` was inspected on May 27, 2026. It is a PyInstaller
Python/Qt app, version `3.0.6`, with bundled modules named like Vial/QMK tooling:

- `protocol.keyboard_comm`
- `editor.rgb_configurator`
- `vial_device`
- `hidproxy`

Its strings and bytecode references include VIA/Vial commands such as
`CMD_VIA_SET_KEYCODE`, `CMD_VIA_LIGHTING_SET_VALUE`, `VIALRGB_SET_MODE`, and
serial markers like `vial:f64c2b3c`. I did not find the Sikai/CH57x USB ID
`1189:8890` or the known `0x8890` packet sequence used by `ch57x-keyboard-tool`.

Conclusion: MYKB appears to target Vial/VIA-compatible QMK devices over raw HID.
It may be useful background for RGB concepts, but it does not appear to speak
the CH57x `1189:8890` programming protocol for this pad.

## Replay utility

Build:

```sh
/usr/bin/clang ch57x_send.c -I/opt/homebrew/include -L/opt/homebrew/lib -lusb-1.0 -o ch57x_send
```

Replay the known LED mode `1` packet:

```sh
./ch57x_send \
  0x03 0xa1 0x01 0 0 0 0 0 0 \
  0x03 0xb0 0x18 0x01 0 0 0 0 0 \
  0x03 0xaa 0xa1 0 0 0 0 0 0
```

## Capture goal

We need a USB capture from the vendor Windows software while changing LED settings.

Capture only a few clean actions:

1. Plug in the pad.
2. Start capture.
3. Open the vendor software.
4. Change LED to one obvious state, such as red steady.
5. Change LED to another obvious state, such as blue steady.
6. Stop capture.

The useful packets should be interrupt OUT transfers to endpoint `0x02` on USB ID `1189:8890`.
They will likely be 64 bytes each.

## Windows capture recipe

1. Install Wireshark with USBPcap enabled.
2. Plug the macro pad into the Windows machine.
3. In Wireshark, start capture on the USBPcap interface that contains the pad.
4. Use the vendor app to change one LED setting.
5. Stop capture.
6. Filter for the device and endpoint if possible:

```text
usb.idVendor == 0x1189 && usb.idProduct == 0x8890
```

Then look for URB interrupt OUT packets to endpoint `0x02`.

Export or copy the hex payloads for the packets sent during each LED change.

## macOS replay

Once we have the hex bytes, replay them on macOS with `ch57x_send`.
If the capture payload is 64 bytes, the first 9 non-zero/meaningful bytes are often the command;
keep the full grouping when in doubt and test one command group at a time.
