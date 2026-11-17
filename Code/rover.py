"""Rover controller: ties the drivers together and runs the sample / survey sequences."""
import json
import os
import threading
import time

from PIL import Image

import analysis
import config as C
from hardware import (IO, Camera, Encoders, GPS, Laser, Motors, Probe, SoilSensor, Spectral, Thermal)


def _json_default(o):
    return o.item() if hasattr(o, "item") else str(o)


class Rover:
    def __init__(self, sim=False, data_dir=None):
        self.io = IO(sim)
        self.motors = Motors(self.io)
        self.enc = Encoders(self.io, self.motors)
        self.probe = Probe(self.io)
        self.laser = Laser(self.io)
        self.soil = SoilSensor(self.io)
        self.gps = GPS(self.io, self.enc)
        self.spectral = Spectral(self.io)
        self.thermal = Thermal(self.io)
        self.camera = Camera(self.io, self.laser)
        self.dir = data_dir or C.DATA_DIR
        os.makedirs(os.path.join(self.dir, "photos"), exist_ok=True)
        self.log_path = os.path.join(self.dir, "samples.jsonl")
        self.samples = self._load()
        self.busy, self.msg = "", "homing probe"
        self.cancel_flag = threading.Event()
        self.lock = threading.Lock()
        threading.Thread(target=self._boot, daemon=True).start()

    def _boot(self):
        try:
            self.probe.home()
            self.msg = "ready"
        except Exception as e:
            self.msg = f"probe homing failed: {e}"

    def _load(self):
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path) as f:
            return [json.loads(line) for line in f if line.strip()]

    # ---------------------------------------------------------------- manual control
    def drive(self, left, right):
        """Refuses to move while a job is running or the probe is not fully up."""
        if self.busy or self.probe.state != "up":
            self.motors.stop()
            return False
        self.motors.drive(left, right)
        return True

    def stop(self):
        self.cancel_flag.set()
        self.motors.stop()

    def set_laser(self, on):
        self.laser.set(on)

    def move_probe(self, down):
        if self.busy:
            return False
        self.motors.stop()
        threading.Thread(target=self.probe.move, args=(down,), daemon=True).start()
        return True

    # ---------------------------------------------------------------- jobs
    def start_sample(self):
        if self.probe.state != "up" or not self.lock.acquire(blocking=False):
            return False
        self.busy = "sampling"
        threading.Thread(target=self._job, args=(lambda: self._sample(),), daemon=True).start()
        return True

    def start_survey(self, n, step_mm, speed=0.6):
        if self.probe.state != "up" or not self.lock.acquire(blocking=False):
            return False
        self.busy = "surveying"
        self.cancel_flag.clear()
        threading.Thread(target=self._job, args=(lambda: self._survey(n, step_mm, speed),), daemon=True).start()
        return True

    def _job(self, fn):
        try:
            fn()
        except Exception as e:
            self.msg = f"job failed: {e}"
        finally:
            self.motors.stop()
            self.laser.set(False)
            self.busy = ""
            self.lock.release()

    def _drive_distance(self, mm, speed):
        self.enc.reset()
        timeout = time.time() + max(3.0, 2.5 * mm / (C.SPEED_MM_S * max(speed, 0.2)))
        while self.enc.distance_mm() < mm and time.time() < timeout and not self.cancel_flag.is_set():
            self.motors.drive(speed, speed)
            time.sleep(0.05)
        self.motors.stop()

    def _survey(self, n, step_mm, speed):
        for i in range(n):
            if self.cancel_flag.is_set():
                break
            self.msg = f"driving to stop {i + 1} of {n}"
            self._drive_distance(step_mm, speed)
            if self.cancel_flag.is_set():
                break
            self._sample()
        self.msg = "survey stopped" if self.cancel_flag.is_set() else "survey finished"

    def _sample(self):
        errors = []
        self.motors.stop()
        self.io.sleep(0.5)
        s = {"id": len(self.samples) + 1, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "gps": self.gps.fix, "errors": errors}
        off = on = None
        try:
            self.msg = "photographing"
            self.laser.set(False)
            off = self.camera.fresh_frame()
            self.laser.set(True)
            on = self.camera.fresh_frame()
        except Exception as e:
            errors.append(f"camera: {e}")
        finally:
            self.laser.set(False)
        for key, fn in (("spectral", self.spectral.read), ("thermal", self.thermal.read)):
            self.msg = f"reading {key}"
            try:
                s[key] = fn()
            except Exception as e:
                errors.append(f"{key}: {e}")
        soil = None
        try:
            self.msg = "probing the soil"
            self.probe.move(True)
            self.io.sleep(C.PROBE_SETTLE_S)
            soil = self.soil.read()
        except Exception as e:
            errors.append(f"soil sensor: {e}")
        finally:
            self.msg = "retracting probe"
            self.probe.move(False)
        s["soil"] = soil
        if off is not None:
            s.update(analysis.analyse(on, off, soil, s.get("thermal")))
            Image.fromarray(off).save(os.path.join(self.dir, "photos", f"sample_{s['id']}.jpg"), quality=90)
            if on is not None:
                Image.fromarray(on).save(os.path.join(self.dir, "photos", f"sample_{s['id']}_laser.jpg"), quality=90)
        self.samples.append(s)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(s, default=_json_default) + "\n")
        self.msg = f"sample {s['id']} done"

    # ---------------------------------------------------------------- reporting
    def state(self):
        return {"busy": self.busy, "msg": self.msg, "probe": self.probe.state, "laser": self.laser.on,
                "gps": self.gps.fix, "drive": self.motors.cmd, "distance_mm": round(self.enc.distance_mm()),
                "n_samples": len(self.samples), "water": analysis.water_rank(self.samples)[:3],
                "last": self.samples[-1] if self.samples else None}

    def to_csv(self):
        cols = ["id", "time", "lat", "lon", "moisture", "temp_c", "ec", "ph", "n", "p", "k", "soil_class",
                "texture", "roughness_mm", "thermal_mean", "top_crop"]
        rows = [",".join(cols)]
        for s in self.samples:
            g, so = s.get("gps") or {}, s.get("soil") or {}
            crops = s.get("crops") or [{}]
            vals = [s["id"], s["time"], g.get("lat"), g.get("lon"), so.get("moisture"), so.get("temp_c"),
                    so.get("ec"), so.get("ph"), so.get("n"), so.get("p"), so.get("k"), s.get("soil_class"),
                    s.get("texture"), (s.get("laser") or {}).get("roughness_mm"),
                    (s.get("thermal") or {}).get("mean"), crops[0].get("name")]
            rows.append(",".join("" if v is None else str(v) for v in vals))
        return "\n".join(rows) + "\n"
