#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, sys, time, subprocess, re
from datetime import datetime
from typing import Dict, Optional, List

# ---- pyserial ----
try:
    from serial.tools import list_ports
    import serial
except Exception:
    print("pyserial is required. Install with: pip install pyserial", file=sys.stderr)
    raise

# ---- serial params ----
SERIAL_BAUD     = 9600
SERIAL_BYTESIZE = serial.EIGHTBITS    # 8
SERIAL_PARITY   = serial.PARITY_NONE  # N
SERIAL_STOPBITS = serial.STOPBITS_ONE # 1
SERIAL_TIMEOUT  = 0.1                 # non-blocking-ish

REQ_PERIOD  = 1.0    # seconds between request retries 
QUIET_SECS  = 5.0    # applies only AFTER first byte is seen
CAPTURE_DIR = os.path.join("captures", "seaward")

CSV_REQ_LINES = (b"SYST:REM\r\n", b"MEM:DATA? ALL\r\n")

# ---- preferred USB-serial signature ----
PREF_VID = "0x10C4"   # Silicon Labs
PREF_PID = "0xEA60"   # CP2102

def rank_port(sig: dict) -> int:
    """
    Higher score = more likely to be the Seaward Meter.
    Priority: exact VID:PID match > CP2102 or Silicon Labs strings > ttyUSB
    """
    score = 0
    vid, pid = sig.get("vid"), sig.get("pid")
    manuf = (sig.get("manufacturer") or "").upper()
    prod  = (sig.get("product") or "").upper()
    desc  = (sig.get("description") or "").upper()
    dev   = (sig.get("device") or "").lower()

    if vid == PREF_VID and pid == PREF_PID:
        score += 100
    if "CP2102" in prod or "CP2102" in desc:
        score += 30
    if "SILICON LABS" in manuf:
        score += 20
    if dev.startswith("/dev/ttyusb"):
        score += 5
    if "USB" in desc:
        score += 2
    return score

# ---------- small utilities ----------
def port_signature(p) -> Dict[str, Optional[str]]:
    return {
        "device": getattr(p, "device", None),
        "name": getattr(p, "name", None),
        "description": getattr(p, "description", None),
        "hwid": getattr(p, "hwid", None),
        "manufacturer": getattr(p, "manufacturer", None),
        "product": getattr(p, "product", None),
        "serial_number": getattr(p, "serial_number", None),
        "vid": f"0x{p.vid:04X}" if getattr(p, "vid", None) is not None else None,
        "pid": f"0x{p.pid:04X}" if getattr(p, "pid", None) is not None else None,
        "location": getattr(p, "location", None),
        "interface": getattr(p, "interface", None),
    }

def same_port(a: Dict[str, Optional[str]], b: Dict[str, Optional[str]]) -> bool:
    return a.get("device") == b.get("device") and a.get("hwid") == b.get("hwid")

def pretty_print_port(sig: Dict[str, Optional[str]]) -> None:
    print("\nDetected serial device:")
    print(f"  Device       : {sig.get('device')}")
    print(f"  Description  : {sig.get('description')}")
    print(f"  Manufacturer : {sig.get('manufacturer')}")
    print(f"  Product      : {sig.get('product')}")
    print(f"  SerialNumber : {sig.get('serial_number')}")
    print(f"  VID:PID      : {sig.get('vid')}:{sig.get('pid')}")
    print(f"  HWID         : {sig.get('hwid')}")
    if sig.get("location") or sig.get("interface"):
        print(f"  Location/IF  : {sig.get('location')} / {sig.get('interface')}")

def is_usb_serial(sig: dict) -> bool:
    vid, pid = sig.get("vid"), sig.get("pid")
    if vid and pid: return True
    dev = (sig.get("device") or "").lower()
    if dev.startswith("/dev/ttyusb") or dev.startswith("/dev/ttyacm"): return True
    desc = " ".join(filter(None, [sig.get("description"), sig.get("product") or ""])).upper()
    return "USB" in desc

def device_key(sig: dict) -> str:
    return sig.get("hwid") or sig.get("device") or repr(sig)

def detect_seaward_device() -> Dict[str, Optional[str]]:
    print("Probing for Seaward 200/210 meter. Connect it now…\n")
    ignored: set[str] = set()
    try:
        def get_candidates():
            allp = [port_signature(p) for p in list_ports.comports()]
            cands = [sig for sig in allp if is_usb_serial(sig)]
            cands.sort(key=rank_port, reverse=True)
            return cands

        # Initial pass
        candidates = get_candidates()
        if candidates:
            print("Found USB serial device(s) attached at startup.\n")
            for sig in candidates:
                k = device_key(sig)
                if k in ignored:
                    continue
                pretty_print_port(sig)
                ans = input("\nIs this your Seaward meter? [Y/n]: ").strip().lower()
                if ans in ("", "y", "yes"):
                    return sig
                ignored.add(k)
                print("Okay, ignoring this device. Still listening...\n")
        else:
            print("Waiting for a USB serial device to appear...\n")

        # Hot-plug loop
        seen = [port_signature(p) for p in list_ports.comports()]
        while True:
            now_list = [port_signature(p) for p in list_ports.comports()]
            # find new/changed
            new_or_changed: List[Dict[str, Optional[str]]] = []
            for sig in now_list:
                if not is_usb_serial(sig):
                    continue
                if not any(same_port(sig, s) for s in seen):
                    new_or_changed.append(sig)

            if not new_or_changed:
                for sig in now_list:
                    if not is_usb_serial(sig):
                        continue
                    for s in seen:
                        if sig.get("device") == s.get("device") and sig.get("hwid") != s.get("hwid"):
                            new_or_changed.append(sig)
                            break

            if new_or_changed:
                new_or_changed.sort(key=rank_port, reverse=True)
                for sig in new_or_changed:
                    k = device_key(sig)
                    if k in ignored:
                        continue
                    pretty_print_port(sig)
                    ans = input("\nIs this your Seaward meter? [Y/n]: ").strip().lower()
                    if ans in ("", "y", "yes"):
                        return sig
                    ignored.add(k)
                    print("Okay, ignoring this device. Still listening...\n")

            seen = now_list
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)

def ensure_port_permissions(dev_path: str) -> None:
    if os.access(dev_path, os.R_OK | os.W_OK): return
    print(f"\n[!] Insufficient permissions on {dev_path}.")
    if os.geteuid() == 0:
        try:
            os.chmod(dev_path, 0o666); print(f"[✓] chmod 666 {dev_path} (running as root)."); return
        except Exception as e:
            print(f"[!] Failed to chmod {dev_path} as root: {e}"); sys.exit(1)
    try:
        print(f"[i] Attempting: sudo chmod a+rw {dev_path}")
        rc = subprocess.call(["sudo", "chmod", "a+rw", dev_path])
        if rc == 0: print("[✓] Permissions updated."); return
        else: print(f"[!] sudo chmod returned {rc}.")
    except Exception as e:
        print(f"[!] Error invoking sudo: {e}")
    print("\nPermanent fix:")
    print("  Arch/Manjaro : sudo usermod -aG uucp $USER && newgrp uucp")
    print("  Debian/Ubuntu: sudo usermod -aG dialout $USER && newgrp dialout")
    sys.exit(1)

# ---------- CSV helpers ----------
PRINTABLE = set(range(32,127)) | {9,10,13}
RE_SERIAL   = re.compile(r"(?i)^\s*serial\s*no\s*,")
RE_HEADER   = re.compile(r"(?i)^\s*index\s*,")
READING_LINE_RE = re.compile(r'^\s*\d+\s*,')

def looks_asciiish(chunk: bytes) -> bool:
    if not chunk: return False
    good = sum(1 for b in chunk if b in PRINTABLE)
    return (good / len(chunk)) >= 0.85

def maybe_csv_text(buffer: bytes) -> Optional[str]:
    if not buffer: return None
    if buffer.count(b",") < 5: return None
    if b"Serial no" not in buffer and b"Serial No" not in buffer: return None
    if b"Index," not in buffer: return None
    if not looks_asciiish(buffer): return None
    try:
        txt = buffer.decode("utf-8", errors="ignore")
    except Exception:
        txt = buffer.decode("latin1", errors="ignore")
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    m = re.search(r"(?im)^serial\s*no\s*,", txt)
    if not m: return None
    body = txt[m.start():]
    cut = re.search(r"\n{2,}|\n--END--", body, flags=re.M)
    if cut: body = body[:cut.start()]
    return body.strip() + "\n"

class CSVProgress:
    """Stream parser: prints Serial/FileVersion, header, and counts data lines (with byte sizes)."""
    def __init__(self):
        self.saw_serial = False
        self.serial = None
        self.filever = None
        self.saw_header = False
        self.readings = 0

    def on_line(self, line_text: str, line_bytes_len: int) -> None:
        s = line_text.strip("\r\n")
        if not s:
            return
        if not self.saw_serial and RE_SERIAL.match(s):
            toks = [t.strip() for t in s.split(",")]
            for i in range(len(toks) - 1):
                key = toks[i].lower()
                if key.startswith("serial"):
                    self.serial = toks[i + 1]
                if key.startswith("fileversion"):
                    self.filever = toks[i + 1]
            self.saw_serial = True
            if self.serial:  print(f"[✓] Serial Number {self.serial}")
            if self.filever: print(f"[✓] FileVersion {self.filever}")
            return
        if self.saw_serial and not self.saw_header and RE_HEADER.match(s):
            self.saw_header = True
            print(f"[!] Downloading: {s}")
            return
        if self.saw_header and READING_LINE_RE.match(s):
            self.readings += 1
            print(f"[←] {line_bytes_len:4d} bytes received: Reading {self.readings}")

# ---------- capture ----------
def listen_and_capture(dev_path: str) -> None:
    ensure_port_permissions(dev_path)

    print(f"\nListener Armed on {dev_path}")
    print("\nOn the Seaward meter:")
    print("  • Power on: press & hold Riso + Mode")
    print("  • Start transmit: press & hold Folder/Recall")
    print("\n(Ctrl+C to exit)\n")

    ascii_buf = bytearray()
    pending = bytearray()
    first_seen = False
    last_data_ts = 0.0
    last_req_ts  = 0.0
    total_bytes  = 0
    progress = CSVProgress()

    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    csv_path = os.path.join(CAPTURE_DIR, f"seaward_{stamp}.csv")

    try:
        with serial.Serial(
            dev_path,
            baudrate=SERIAL_BAUD,
            bytesize=SERIAL_BYTESIZE,
            parity=SERIAL_PARITY,
            stopbits=SERIAL_STOPBITS,
            timeout=SERIAL_TIMEOUT,
            write_timeout=0.5,
        ) as ser:
            try:
                ser.dtr = False; ser.rts = False
            except Exception:
                pass

            print("[i] Waiting for meter data")
            print("[→] listening...")
            while True:
                # Periodically send the two commands while waiting/reading (SILENT)
                t_now = time.time()
                if (t_now - last_req_ts) >= REQ_PERIOD:
                    for line in CSV_REQ_LINES:
                        ser.write(line); ser.flush(); time.sleep(0.02)
                    last_req_ts = t_now

                chunk = ser.read(4096)
                if chunk:
                    if not first_seen:
                        first_seen = True
                        print("[✓] Data detected - locking and continuing capture…")
                        # After lock, send one visible CSV request (periodic ones remain silent)
                        for line in CSV_REQ_LINES:
                            ser.write(line); ser.flush(); time.sleep(0.02)
                        print("[→] Sent CSV request")

                    ascii_buf.extend(chunk)
                    pending.extend(chunk)
                    last_data_ts = t_now
                    total_bytes += len(chunk)

                    # Stream-parse CSV lines for progress
                    while True:
                        nl = pending.find(b"\n")
                        if nl == -1:
                            break
                        raw_line = pending[:nl+1]; del pending[:nl+1]
                        try:
                            line = raw_line.decode("utf-8", errors="ignore").replace("\r", "")
                        except Exception:
                            line = raw_line.decode("latin1", errors="ignore").replace("\r", "")
                        progress.on_line(line, len(raw_line))
                else:
                    # Before first byte: never time out
                    if not first_seen:
                        time.sleep(0.02)
                        continue
                    # After first byte: apply quiet timeout
                    if (t_now - last_data_ts) >= QUIET_SECS:
                        print(f"\n[i] No data for {QUIET_SECS:.1f}s — assuming transmission complete.")
                        break
                    time.sleep(0.02)

    except KeyboardInterrupt:
        print("\n[!] Capture canceled by user.")

    # Process any trailing partial line
    if pending and b"\n" not in pending:
        try:
            line = pending.decode("utf-8", errors="ignore").replace("\r", "")
        except Exception:
            line = pending.decode("latin1", errors="ignore").replace("\r", "")
        progress.on_line(line, len(pending))

    # Save CSV if detected
    csv_block = maybe_csv_text(bytes(ascii_buf))
    if csv_block:
        if progress.readings:
            print(f"[✓] Total readings: {progress.readings} ({total_bytes} bytes)")
        clean = csv_block.rstrip("\x00 \t\r\n") + "\n"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            f.write(clean)
        print(f"\n[✓] Saved CSV → {csv_path}")
    else:
        print("\n[i] CSV not detected ")

    print("\n======== DONE ========")


# ---------- orchestrator ----------
def run(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Seaward capture with CSV trigger (9600 8N1)")
    ap.parse_args(argv)

    dev = detect_seaward_device()
    sel_line = f"{(dev.get('manufacturer') or '').strip()} {(dev.get('product') or '').strip()}".strip()
    if sel_line:
        print(f"\n{sel_line} selected")
    else:
        print(f"\n{dev.get('device') or 'Serial device'} selected")

    dev_path = dev.get("device") or ""
    if not dev_path:
        print("[!] No device path found; aborting."); sys.exit(1)

    listen_and_capture(dev_path)

if __name__ == "__main__":
    run()
