# Installing SerialTerminal

SerialTerminal uses `pyproject.toml` as the authoritative Python dependency
definition. A separate `requirements.txt` is intentionally not maintained, so there
is only one dependency source to keep in sync.

Python 3.10 or newer is required.

## Recommended installation on a new Linux host

On Debian/Ubuntu/Linux Mint, install the system prerequisites first:

```bash
sudo apt update
sudo apt install python3 python3-venv bluez
```

`bluez` is needed for Classic Bluetooth discovery/SPP tools such as
`bluetoothctl` and `sdptool`. USB Serial use does not require BlueZ.

Clone the repository and create an isolated virtual environment:

```bash
git clone <repository-url> serialterminal
cd serialterminal

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

For the normal full SerialTerminal installation, including BLE support:

```bash
python -m pip install -e '.[ble]'
```

The editable install keeps the command wired directly to the checked-out source tree,
which is convenient for normal development and testing: source edits do not require a
new install step.

Run the installed command:

```bash
serialterminal
```

For the bundled LoRa-Chatter profile:

```bash
serialterminal --profile chatter
```

The repository launcher remains available too:

```bash
python3 serialterminal.py
python3 serialterminal.py --profile chatter
```

## Generic-only / USB Serial installation

If BLE support is not needed, install only the base package:

```bash
python -m pip install -e .
```

The base dependencies are declared in `pyproject.toml` and currently include
`pyserial` and `prompt-toolkit`.

## Optional Codec2 voice-message prerequisites

Store-and-forward voice messages are optional and are not Python package dependencies.
On Debian/Ubuntu/Linux Mint install the ALSA command-line tools:

```bash
sudo apt install alsa-utils
which arecord
which aplay
```

Build the separate pinned `codec2-sdk` project and pass the produced portable SDK tree
explicitly to the human TUI; SerialTerminal never falls back to a system `libcodec2`:

```bash
serialterminal --profile chatter \
  --codec2-sdk-dir ../codec2-sdk/dist/linux-x86_64
```

The selected directory must contain `manifest.json` and `lib/libcodec2.so*` from the
pinned Codec2 1.2.0 build. The library is loaded lazily only when voice is used, so a
missing/mismatched SDK does not prevent ordinary terminal startup. `arecord` and `aplay`
use the host ALSA default device; choose/configure USB/Bluetooth routing at the OS/ALSA
layer. An optional `--voice-temp-dir PATH` changes only the outgoing finalized voice
file scratch directory.

The first voice implementation has no automatic recording duration/size cutoff: `F12`
starts capture and the next `F12` finalizes/sends it. Capture is streaming, and normal
filesystem/process errors abort safely rather than silently sending a partial file.

## Development installation

For source development with BLE and the repository test/lint tools:

```bash
python -m pip install -e '.[ble,dev]'
```

Then the usual validation commands are available inside the same virtual environment:

```bash
python -m compileall -q src serialterminal.py tools
ruff check src tests serialterminal.py tools
pytest -q
```

## Returning to the project later

From a new shell:

```bash
cd serialterminal
source .venv/bin/activate
```

Leave the environment with:

```bash
deactivate
```

The repository ignores both `.venv/` and `venv/`; virtual-environment files must
not be committed.

## Classic Bluetooth checks

For Classic Bluetooth scanner/SPP support:

```bash
which bluetoothctl
which sdptool
```

Both should resolve after the BlueZ package is installed.

## Dependency ownership

Keep Python runtime and development dependencies in `pyproject.toml`.

Do not add a parallel hand-maintained `requirements.txt` merely for installation.
If a deployment environment later needs a fully pinned lock file, treat that as a
separate reproducibility artifact generated from the package metadata rather than a
second manually maintained dependency list.
