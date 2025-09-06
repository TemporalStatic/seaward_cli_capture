# Seaward CLI Capture

*A tiny, reliable CLI to download measurement data from Seaward PV200 / PV210 meters on Linux.*

![Seaward PV210](https://i.imgur.com/TFrKaE5.png)

---

- Auto-detects the USB–serial adapter (CP2102 on most PV200/210 kits).
- Waits for the meter to start sending.
- Captures streaming data from the meter and saves as CSV.

---

## Requirements

- Linux (any distro) with Python **3.8+**
- USB CP210x driver (already kernel built-in on most distros)
- Python package: `pyserial`

## Installation

1. **Download** `seaward_cli_capture.py` from this repository into a folder of your choice.

2. (Optional) Make it executable:
   ```bash
   chmod +x seaward_cli_capture.py
   ```

3. Ensure `pyserial` is installed 

   ```bash
   python3 -m pip install --upgrade pyserial
   ```

   ---

---

## Usage

Connect the meter via USB, then run:

```bash
python3 seaward_cli_capture.py
# (or ./seaward_cli_capture.py if you made it executable)
```

You’ll see something like:

```
Probing for Seaward 200/210 meter - please connect it now…

Found USB serial device(s) attached at startup.

Detected serial device:
  Device       : /dev/ttyUSB0
  Description  : CP2102 USB to UART Bridge Controller - CP2102 USB to UART Bridge Controller
  Manufacturer : Silicon Labs
  Product      : CP2102 USB to UART Bridge Controller
  VID:PID      : 0x10C4:0xEA60

Is this your Seaward meter? [Y/n]:
```

Hit **Enter** to accept the default (Yes). The app will begin to wait for data from the meter.  Follow the instructions to power it on, and initiate the data transfer.

### Button sequence on the meter

1) **Power on** (Riso + Mode held together):  
![Power buttons](https://i.imgur.com/JiORO5K.png)

2) **Start transmit** (hold the **Folder/Recall** button until numbers begin to show and release):  
![Folder button](https://i.imgur.com/EMt2Rfp.png)

The app will now begin to show data being received and automatically save a CSV when complete.


---

## Output

- CSV is saved to the `captures/` folder in the same directory as the script was run from.  
  File name format: `seaward_YYYY_MM_DD_HHMMSS.csv`

---

## Tips & Troubleshooting

- **Nothing happens / stuck on “listening…”**  
  Ensure you *hold* the Folder/Recall button long enough for the meter to begin the download. 

- **Device not listed**  
  Try unplug/replug. Other conflicting deceives may need to be temporarily unplugged. Check `dmesg | tail` to confirm you got `/dev/ttyUSB*`. If necessary:
  
  ```bash
  sudo chmod a+rw /dev/ttyUSB0
  ```
  Then re-run the script.
  
- **Wrong device auto-selected**  
  The script prefers Silicon Labs CP2102 (VID:PID `10C4:EA60`). If you have multiple adapters connected, just answer **n** and it will move to the next candidate.

---

## How it works (short technical version)

- Opens the confirmed `/dev/ttyUSB*` at **9600 8N1** (required by the Seaward protocol).
- While waiting for *first byte*, it silently sends:
  - `SYST:REM\r\n`
  - `MEM:DATA? ALL\r\n`
  once per second.
- After the first data arrives, it continues to read until 5 seconds of quiet.
- Detects and extracts the vendor CSV block and saves it unchanged.
  - Minor hygiene only: It **doesn’t change** field values, units, column order, quoting, or separators, only normalizes line endings (CRLF→LF) and trims any garbage before/after the CSV block so the saved file is clean.


---

## License

MIT, do whatever you like, no warranty, no support, use at your own risk, not liable for what you do.

---

## Attribution

This is a community-created personal project and is not affiliated with, authorized by, or endorsed by Seaward Group in any way.
 Huge thanks to Seaward for building a solid meter many of us have relied on for years.
