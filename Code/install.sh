#!/bin/sh
# Run once on the Raspberry Pi Zero 2 W (Raspberry Pi OS Bookworm), from inside this folder.
set -e
sudo apt update
sudo apt install -y pigpio python3-pigpio python3-picamera2 python3-numpy python3-pil python3-serial python3-pip
pip install --break-system-packages adafruit-circuitpython-as7341 adafruit-circuitpython-mlx90640
sudo systemctl enable --now pigpiod
echo "Now edit /boot/firmware/config.txt as described in README.md step 2, then reboot."
