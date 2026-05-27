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
The vendor 6-key software labels these as `LED_Mode0`, `LED_Mode1`,
`LED_Mode2`, and so on. Based on the app's IL, `LED_Mode0` appears to be off
and `LED_Mode1` is the primary on/steady mode to test.

The same app appears to encode color in the high nibble of the mode byte:

```text
white/default 0x00
red           0x10
orange        0x20
yellow        0x30
green         0x40
cyan          0x50
blue          0x60
purple        0x70
```

That means red + `LED_Mode1` becomes `0x11`, blue + `LED_Mode1` becomes
`0x61`, and so on. The web editor sends this encoded byte now. Per-key LED
addressing is still unconfirmed; the packet shape we know for `1189:8890`
contains only `b0 18 MODE`, so the physical device may treat the command as
global even when the editor records a selected key.

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

## Vendor Windows app inspection

`~/Downloads/New English software is set in the upgrade model-20250318` was
inspected on May 27, 2026. This is a Qt/MinGW Windows app named
`MINI_KEYBOARD.exe` with `hidapi.dll` and unstripped `.o` object files. The
object files preserve useful symbols:

```text
Widget::HID_write()
Widget::SetRgb_Led_Key(int)
Widget::Set_Rgb_KeyColor()
Widget::Read_RgbLed_DataDsp()
Widget::read_Hidkey_Data(unsigned char, unsigned char, unsigned char)
Widget::Read_CurKeyBoard_Data()
Widget::SendLayer(int)
Widget::Set_Keyboard_6Key()
Widget::Set_Keyboard_6add1()
Widget::Set_Keyboard_6add2()
```

The app includes keyboard profiles such as:

```text
KB_6key_0VT
BT_6key_0VT
KB_6key_2VT
BT_6key_2VT
```

It also contains strings for `Layer1`, `Layer2`, `Layer3`, `LED Mode0` through
`LED Mode5`, `LED_color_1` through `LED_color_56`, `KEY1` through `KEY15`, and
device status strings like `Device Connect` and `Device Disconnect USB`.

The preserved data section confirms the same LED color-byte pattern we inferred
earlier. Near the app's LED color table are:

```text
20 30 40 50 60 70 00 01 02 03 04 05
```

That matches color high nibbles `0x20..0x70` and mode low nibbles `0..5`.

Important new clue: `SetRgb_Led_Key(int)` writes into the per-key
`PHY_KEY_Value` table instead of only sending the global mode command. In the
disassembly it sets a key record to start with bytes equivalent to:

```text
fe b0 <layer-or-record> <selected-key> ...
```

and then updates byte `0x0b` of that key record with the encoded LED color/mode
value. `HID_write()` later walks modified key records and calls `hid_write`
with length `0x41`, meaning a 65-byte HID report. This suggests the vendor app
may support per-key LED programming by writing complete key records, not by
using the shorter `03 b0 18 MODE` command.

`HID_write()` appears to walk three layer-sized blocks of `0x3c` key slots. A
normal key record stride is `0x41` bytes, and the app writes reports that begin
with bytes equivalent to:

```text
03 fe ...
```

For a different hardware/profile path, it writes a footer-like report beginning:

```text
03 fd fe ff ...
```

`read_Hidkey_Data(...)` uses a corresponding read command beginning:

```text
03 fa ...
```

That read path copies returned 64-byte reports back into the same
`PHY_KEY_Value` table. So the vendor protocol likely has a richer read/write
configuration path than the shorter LED mode command we tested earlier.

The profile selector function `Set_Keyboard_Ver_SLOT(int)` sends a 65-byte HID
report beginning with:

```text
03 fc fc ...
```

and writes a profile code at bytes `3..4`. The cases include codes such as
`0x0006` for `6KEY`, `0x0106` for `6+1KEY`, and `0x0206` for `6+2KEY`. After a
successful profile write, the app calls `SetRgb_Led_Key(0x5e)`,
`SetRgb_Led_Key(0x57)`, then `HID_write()`, which looks like an automatic
default LED/key-record refresh after switching keyboard model.

The global app data also contains VID/PID values for the keyboard family. The
default PID symbol in this build points at `0x8840`, while the product-family
table includes several `0x88xx` PIDs and VID `0x1189`. Our pad remains
`1189:8890`, so the app likely chooses a profile/PID at runtime rather than
hardcoding a single product ID.

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

Replay `LED_Mode1` red:

```sh
./ch57x_send \
  0x03 0xa1 0x01 0 0 0 0 0 0 \
  0x03 0xb0 0x18 0x11 0 0 0 0 0 \
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
