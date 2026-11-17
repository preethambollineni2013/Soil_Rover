"""Pin map and calibration for the soil rover (BCM GPIO numbers, matches the schematic)."""

# --- drive: name -> (IN1, IN2, PWM, invert). Flip "invert" if a wheel spins the wrong way.
MOTORS = {
    "FL": (5, 6, 12, False), "RL": (16, 20, 13, False),     # TB6612 #1 (left side)
    "FR": (22, 24, 18, False), "RR": (25, 26, 19, False),   # TB6612 #2 (right side)
}
LEFT, RIGHT = ("FL", "RL"), ("FR", "RR")
PWM_HZ = 1000
WATCHDOG_S = 0.6            # motors stop if no drive command arrives for this long
ENC_LEFT, ENC_RIGHT = 4, 27
TICKS_PER_MM = 3.7          # CALIBRATE: drive 1 m, divide encoder ticks by 1000
SPEED_MM_S = 120.0          # rough full-speed ground speed, used only as a timeout guess

# --- probe actuator (DRV8871) and laser
ACT_IN1, ACT_IN2 = 10, 11
ACT_INVERT = False          # swap if "down" retracts the probe
PROBE_TRAVEL_S = 7.0        # MEASURE: seconds the actuator needs for its full stroke
PROBE_SETTLE_S = 4.0        # wait after insertion before reading the soil sensor
LASER_PIN = 9

# --- RS485 soil sensor (Modbus RTU). Check your sensor datasheet for baud, address, registers.
RS485_PORT, RS485_BAUD, RS485_DE_RE = "/dev/serial0", 4800, 17
NPK_ADDR, NPK_START = 1, 0
NPK_REGS = [("moisture", 0.1), ("temp_c", 0.1), ("ec", 1.0), ("ph", 0.1), ("n", 1.0), ("p", 1.0), ("k", 1.0)]

# --- GPS (NEO-6M TX -> GPIO23, read with pigpio bit-bang serial)
GPS_RX, GPS_BAUD = 23, 9600

# --- camera and laser texture analysis
FRAME_SIZE = (800, 600)
LENS_POSITION = 6.5         # Camera Module 3 manual focus in dioptres (1 / distance in m); ignored on other cameras
PX_PER_MM = 5.0             # CALIBRATE with a ruler in view
TRI_ANGLE_DEG = 30.0        # angle between laser beam and camera axis
LASER_THRESH = 25           # minimum red increase (0-255) that counts as laser
ROUGH_SMOOTH_MM, ROUGH_COARSE_MM = 0.8, 2.5   # laser-line roughness limits: smooth / medium / coarse

# --- nutrient levels (mg/kg as reported by cheap RS485 probes: treat as relative, not lab values)
N_LEVELS, P_LEVELS, K_LEVELS = (40, 100), (20, 60), (80, 180)
MOISTURE_DRY, MOISTURE_WET = 15.0, 35.0       # percent

# --- simulation
SIM_TIME_SCALE = 0.05       # sleeps shrink to this fraction in --sim mode
DATA_DIR = "data"
