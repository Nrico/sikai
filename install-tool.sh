#!/usr/bin/env sh
set -eu

TOOL_URL="https://github.com/kriomant/ch57x-keyboard-tool/releases/download/v1.7.0/ch57x-keyboard-tool-universal-apple-darwin.tar.gz"
TOOL_SHA256="2ca4b93c9624486a8f68351f2195ed812c36d981c92bb314d5019b0d93db29b1"
ARCHIVE="ch57x-keyboard-tool-universal-apple-darwin.tar.gz"

if [ -x "./ch57x-keyboard-tool" ]; then
  echo "ch57x-keyboard-tool is already installed."
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

curl -L "$TOOL_URL" -o "$ARCHIVE"

ACTUAL_SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$TOOL_SHA256" ]; then
  echo "Checksum mismatch for $ARCHIVE" >&2
  echo "expected: $TOOL_SHA256" >&2
  echo "actual:   $ACTUAL_SHA256" >&2
  exit 1
fi

tar -xzf "$ARCHIVE"
chmod +x ./ch57x-keyboard-tool
echo "Installed ./ch57x-keyboard-tool"
