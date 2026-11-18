# Soil rover software

An Rover for Soil. It uses Laser and camera to detect soil type and structure and suggest crops according to it.It also has a thermal camera used to find the place with more water. so that user can use that spot as water source.


I hope this rover help many poor farmers without knowing soil type and place with more water. This is powered by Raspberry Pi as micro controller and transmitts data through Wifi to users mobile phone.

## Connections
| Function | Pins |
|---|---|
| Left TB6612 (FL, RL) | IN 5/6 + PWM 12, IN 16/20 + PWM 13 |
| Right TB6612 (FR, RR) | IN 22/24 + PWM 18, IN 25/26 + PWM 19 |
| Probe actuator (DRV8871) | IN1 10, IN2 11 |
| Laser (via transistor) | 9 |
| Encoders A-channel | left 4, right 27 |
| RS485 soil sensor | UART 14/15, DE+RE 17 |
| GPS NEO-6M TX | 23 (bit-bang serial) |
| AS7341, MLX90640 | I2C 2/3 |

<img src="images/soil_rover_schematic.png">


## How it decides
* **Texture:** By Using Laser.
* **Colour:** dark = black soil, red-brown = red soil, light and coarse = sandy, dark and smooth = clay, otherwise loam.
* **Crops:** 
* **Water spots:** By Using Thermal Camera

## Safety and limits
* The drive refuses to move while a job runs or the probe is not fully up.
* Motors stop if the phone stops sending commands for 0.6 s.
* The Values taken are just test values not real ones 