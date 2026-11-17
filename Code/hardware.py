"""Hardware drivers for the soil rover. IO(sim=True) runs everything without hardware."""
import io as _io
import math
import random
import struct
import threading
import time

import numpy as np

import config as C

try:
    import pigpio
except Exception:  # not on a Pi
    pigpio = None


class IO:
    """Shared handles: the pigpio connection and the I2C bus."""

    def __init__(self, sim=False):
        self.sim, self.pi, self.i2c = sim, None, None
        if sim:
            return
        if pigpio is None:
            raise RuntimeError("pigpio is missing (sudo apt install python3-pigpio) - or run with --sim")
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpiod is not running (sudo systemctl enable --now pigpiod)")
        try:
            import board
            import busio
            self.i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        except Exception as e:
            print("I2C unavailable:", e)

    def sleep(self, s):
        time.sleep(s * (C.SIM_TIME_SCALE if self.sim else 1.0))


# ------------------------------------------------------------------ drive
class Motors:
    def __init__(self, io):
        self.io, self.cmd, self.last = io, (0.0, 0.0), time.time()
        if not io.sim:
            pi = io.pi
            for in1, in2, pwm, _ in C.MOTORS.values():
                for p in (in1, in2, pwm):
                    pi.set_mode(p, pigpio.OUTPUT)
                pi.set_PWM_frequency(pwm, C.PWM_HZ)
        self.stop()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _set(self, name, v):
        in1, in2, pwm, inv = C.MOTORS[name]
        v = max(-1.0, min(1.0, -v if inv else v))
        if v > 0.03:
            a, b, duty = 1, 0, int(v * 255)
        elif v < -0.03:
            a, b, duty = 0, 1, int(-v * 255)
        else:
            a, b, duty = 1, 1, 255          # TB6612: IN1 = IN2 = high is a short brake
        if not self.io.sim:
            self.io.pi.write(in1, a)
            self.io.pi.write(in2, b)
            self.io.pi.set_PWM_dutycycle(pwm, duty)

    def drive(self, left, right):
        self.cmd, self.last = (float(left), float(right)), time.time()
        for n in C.LEFT:
            self._set(n, left)
        for n in C.RIGHT:
            self._set(n, right)

    def stop(self):
        self.drive(0.0, 0.0)

    def _watchdog(self):
        while True:
            time.sleep(0.1)
            if self.cmd != (0.0, 0.0) and time.time() - self.last > C.WATCHDOG_S:
                self.stop()


class Encoders:
    """One A-channel per side. Counts are magnitudes only (no direction)."""

    def __init__(self, io, motors):
        self.io, self.motors, self.n = io, motors, [0.0, 0.0]
        if io.sim:
            threading.Thread(target=self._sim, daemon=True).start()
        else:
            for i, pin in enumerate((C.ENC_LEFT, C.ENC_RIGHT)):
                io.pi.set_mode(pin, pigpio.INPUT)
                io.pi.set_pull_up_down(pin, pigpio.PUD_UP)
                io.pi.set_glitch_filter(pin, 100)
                io.pi.callback(pin, pigpio.RISING_EDGE, lambda g, l, t, i=i: self._tick(i))

    def _tick(self, i):
        self.n[i] += 1

    def _sim(self):
        while True:
            time.sleep(0.05)
            for i in (0, 1):
                self.n[i] += abs(self.motors.cmd[i]) * 1850 * 0.05

    def reset(self):
        self.n = [0.0, 0.0]

    def distance_mm(self):
        return (self.n[0] + self.n[1]) / 2.0 / C.TICKS_PER_MM


class Probe:
    """Linear actuator that pushes the soil sensor into the ground. Time-based (the actuator has end stops)."""

    def __init__(self, io):
        self.io, self.state = io, "unknown"
        if not io.sim:
            for p in (C.ACT_IN1, C.ACT_IN2):
                io.pi.set_mode(p, pigpio.OUTPUT)
                io.pi.write(p, 0)

    def _run(self, a, b, seconds):
        if not self.io.sim:
            self.io.pi.write(C.ACT_IN1, a)
            self.io.pi.write(C.ACT_IN2, b)
        self.io.sleep(seconds)
        if not self.io.sim:
            self.io.pi.write(C.ACT_IN1, 0)
            self.io.pi.write(C.ACT_IN2, 0)

    def move(self, down):
        target = "down" if down else "up"
        if self.state == target:
            return
        self.state = "moving"
        a, b = (1, 0) if down else (0, 1)
        if C.ACT_INVERT:
            a, b = b, a
        self._run(a, b, C.PROBE_TRAVEL_S + 0.5)
        self.state = target

    def home(self):
        """Retract fully. Called at start-up so the probe state is known."""
        self.state = "moving"
        a, b = (0, 1) if not C.ACT_INVERT else (1, 0)
        self._run(a, b, C.PROBE_TRAVEL_S + 1.0)
        self.state = "up"


class Laser:
    def __init__(self, io):
        self.io, self.on = io, False
        if not io.sim:
            io.pi.set_mode(C.LASER_PIN, pigpio.OUTPUT)
        self.set(False)

    def set(self, on):
        self.on = bool(on)
        if not self.io.sim:
            self.io.pi.write(C.LASER_PIN, 1 if on else 0)


# ------------------------------------------------------------------ soil sensor (Modbus RTU over RS485)
def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_read(addr, start, count):
    frame = struct.pack(">BBHH", addr, 3, start, count)
    return frame + struct.pack("<H", crc16(frame))


def parse_read(resp, addr, count):
    """Return a list of signed 16-bit register values, or raise ValueError."""
    need = 5 + 2 * count
    if len(resp) < need:
        raise ValueError(f"short reply ({len(resp)} of {need} bytes)")
    resp = resp[:need]
    if resp[0] != addr or resp[1] != 3 or resp[2] != 2 * count:
        raise ValueError("unexpected reply header")
    if struct.unpack("<H", resp[-2:])[0] != crc16(resp[:-2]):
        raise ValueError("CRC mismatch")
    return list(struct.unpack(">" + "h" * count, resp[3:-2]))


class SoilSensor:
    def __init__(self, io):
        self.io, self.ser, self.rng = io, None, random.Random(7)
        if not io.sim:
            import serial
            self.ser = serial.Serial(C.RS485_PORT, C.RS485_BAUD, timeout=0.5)
            io.pi.set_mode(C.RS485_DE_RE, pigpio.OUTPUT)
            io.pi.write(C.RS485_DE_RE, 0)

    def read_once(self):
        if self.io.sim:
            r = self.rng
            return {"moisture": round(r.uniform(8, 42), 1), "temp_c": round(r.uniform(22, 31), 1),
                    "ec": int(r.uniform(150, 900)), "ph": round(r.uniform(5.4, 7.8), 1),
                    "n": int(r.uniform(15, 140)), "p": int(r.uniform(8, 80)), "k": int(r.uniform(40, 230))}
        count = len(C.NPK_REGS)
        self.ser.reset_input_buffer()
        self.io.pi.write(C.RS485_DE_RE, 1)
        self.ser.write(build_read(C.NPK_ADDR, C.NPK_START, count))
        self.ser.flush()
        time.sleep(12.0 / C.RS485_BAUD)
        self.io.pi.write(C.RS485_DE_RE, 0)
        regs = parse_read(self.ser.read(5 + 2 * count), C.NPK_ADDR, count)
        return {name: round(v * scale, 1) for (name, scale), v in zip(C.NPK_REGS, regs)}

    def read(self, tries=3):
        """Median of a few good reads."""
        got, err = [], None
        for _ in range(tries):
            try:
                got.append(self.read_once())
            except Exception as e:
                err = e
            self.io.sleep(0.4)
        if not got:
            raise RuntimeError(f"soil sensor: {err}")
        return {k: float(np.median([g[k] for g in got])) for k in got[0]}


# ------------------------------------------------------------------ GPS
def nmea_ok(line):
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, cs = line[1:].partition("*")
    x = 0
    for ch in body:
        x ^= ord(ch)
    try:
        return x == int(cs[:2], 16)
    except ValueError:
        return False


def _deg(v, hemi):
    if not v:
        return None
    d = float(v[:v.index(".") - 2]) + float(v[v.index(".") - 2:]) / 60.0
    return -d if hemi in ("S", "W") else d


def parse_nmea(line):
    """Parse GGA or RMC into {lat, lon, fix, sats}. Returns None for other sentences or bad checksums."""
    line = line.strip()
    if not nmea_ok(line):
        return None
    f = line[1:line.index("*")].split(",")
    kind = f[0][-3:]
    if kind == "GGA" and len(f) > 7 and f[6] not in ("", "0"):
        return {"lat": _deg(f[2], f[3]), "lon": _deg(f[4], f[5]), "fix": int(f[6]), "sats": int(f[7] or 0)}
    if kind == "RMC" and len(f) > 6 and f[2] == "A":
        return {"lat": _deg(f[3], f[4]), "lon": _deg(f[5], f[6]), "fix": 1, "sats": None}
    return None


class GPS:
    def __init__(self, io, encoders):
        self.io, self.enc, self.fix, self.buf = io, encoders, None, b""
        if not io.sim:
            io.pi.bb_serial_read_open(C.GPS_RX, C.GPS_BAUD, 8)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            time.sleep(0.2 if not self.io.sim else 0.05)
            if self.io.sim:
                lat = 17.3850 + self.enc.distance_mm() / 1000.0 / 111320.0
                self.fix = {"lat": lat, "lon": 78.4867, "fix": 1, "sats": 9}
                continue
            n, data = self.io.pi.bb_serial_read(C.GPS_RX)
            if n:
                self.buf += data
                *lines, self.buf = self.buf.split(b"\n")
                self.buf = self.buf[-300:]
                for ln in lines:
                    p = parse_nmea(ln.decode("ascii", "ignore"))
                    if p:
                        self.fix = p


# ------------------------------------------------------------------ spectral + thermal
class Spectral:
    CH = ["415nm", "445nm", "480nm", "515nm", "555nm", "590nm", "630nm", "680nm", "clear", "nir"]

    def __init__(self, io):
        self.io, self.s = io, None
        if not io.sim and io.i2c is not None:
            try:
                from adafruit_as7341 import AS7341
                self.s = AS7341(io.i2c)
                self.s.led = False
            except Exception as e:
                print("AS7341 unavailable:", e)

    def read(self):
        if self.io.sim:
            r = random.Random()
            return {c: int(r.uniform(200, 4000)) for c in self.CH}
        if self.s is None:
            raise RuntimeError("AS7341 not found")
        try:
            self.s.led_current = 25
            self.s.led = True
            time.sleep(0.2)
        except Exception:
            pass
        out = {c: int(getattr(self.s, "channel_" + c)) for c in self.CH}
        try:
            self.s.led = False
        except Exception:
            pass
        return out


class Thermal:
    def __init__(self, io):
        self.io, self.m = io, None
        if not io.sim and io.i2c is not None:
            try:
                import adafruit_mlx90640
                self.m = adafruit_mlx90640.MLX90640(io.i2c)
                self.m.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
            except Exception as e:
                print("MLX90640 unavailable:", e)

    def read(self):
        if self.io.sim:
            r = random.Random()
            return {"mean": round(r.uniform(24, 34), 1), "min": 22.0, "max": 38.0}
        if self.m is None:
            raise RuntimeError("MLX90640 not found")
        frame = [0.0] * 768
        for _ in range(5):
            try:
                self.m.getFrame(frame)
                break
            except ValueError:
                continue
        a = np.array(frame)
        return {"mean": round(float(a.mean()), 1), "min": round(float(a.min()), 1), "max": round(float(a.max()), 1)}


# ------------------------------------------------------------------ camera
def sim_frame(laser_on, rng):
    h, w = C.FRAME_SIZE[1], C.FRAME_SIZE[0]
    img = np.empty((h, w, 3), np.float32)
    img[:] = (118, 84, 56)
    img += rng.normal(0, 10, (h, w, 1)).astype(np.float32)
    if laser_on:
        x = np.arange(w)
        y = 300 + 5 * np.sin(x / 35.0) + rng.normal(0, 1.6, w)
        rows = np.arange(h)[:, None]
        prof = np.exp(-((rows - y[None, :]) ** 2) / (2 * 1.6 ** 2))
        img[:, :, 0] += 200 * prof
        img[:, :, 1] -= 40 * prof
        img[:, :, 2] -= 40 * prof
    return np.clip(img, 0, 255).astype(np.uint8)


class Camera:
    def __init__(self, io, laser):
        self.io, self.laser = io, laser
        self.frame, self.jpg, self.seq = None, b"", 0
        self.cond = threading.Condition()
        self.rng = np.random.default_rng(3)
        self.cam = None
        if not io.sim:
            from picamera2 import Picamera2
            self.cam = Picamera2()
            self.cam.configure(self.cam.create_video_configuration(
                main={"size": C.FRAME_SIZE, "format": "RGB888"}))
            self.cam.start()
            try:
                from libcamera import controls
                self.cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": C.LENS_POSITION})
            except Exception:
                pass                                  # fixed-focus camera
        threading.Thread(target=self._loop, daemon=True).start()

    def _grab(self):
        if self.io.sim:
            time.sleep(0.12)
            return sim_frame(self.laser.on, self.rng)
        return self.cam.capture_array()[:, :, ::-1].copy()   # RGB888 arrives as BGR

    def _loop(self):
        from PIL import Image
        while True:
            fr = self._grab()
            buf = _io.BytesIO()
            Image.fromarray(fr).save(buf, "JPEG", quality=70)
            with self.cond:
                self.frame, self.jpg, self.seq = fr, buf.getvalue(), self.seq + 1
                self.cond.notify_all()
            time.sleep(0.05)

    def wait_new(self, last_seq, timeout=2.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout)
            return self.seq, self.jpg

    def fresh_frame(self):
        """A frame captured after this call (so laser changes have taken effect)."""
        seq0 = self.seq
        with self.cond:
            self.cond.wait_for(lambda: self.seq >= seq0 + 2, 3.0)
            return self.frame.copy()
