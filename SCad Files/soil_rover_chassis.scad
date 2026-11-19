part = "assembly";
print_layout = true;     // true: export parts in print orientation (flat on the bed)
show_wheels = true;      // assembly view only
$fn = 48;

HW = 65;                // half of the body width (x)
HL = 105;               // half of the body length (y)
WALL = 3;               // tub wall thickness
FLOOR = 3;              // tub floor thickness
TUB_H = 34;             // floor underside to deck underside
DECK_T = 3;             // deck thickness
WHEEL_R = 30;           // wheel radius (60 mm wheels)
WHEEL_W = 8;            // wheel width
GC = 36;                // belly ground clearance (floor underside to ground)
CH_W = 12.2;            // N20 motor channel width
CH_H = 10.2;            // N20 motor channel height
POD_HW = 12.15;         // motor pod half width (y)
MOTOR_Y = 70;           // axle distance from the middle (y)
SPEC_Y = 90;            // y position of the AS7341 pod
SPOD_Z0 = -18;          // bottom of the AS7341 pod (below the floor)
ACT_Y = -83;            // y position of the probe actuator
CAM_TILT = 60;          // camera angle below horizontal (degrees)
CAM_Y = 90;             // camera head position (y)
CAM_Z = 75;             // camera head height above the floor underside

CH_Z = WHEEL_R-GC;                                          // axle height relative to the floor underside
POD_Z0 = CH_Z-(CH_H/2)-3.4;                                 // underside of the motor pods
DECK_TOP = TUB_H+DECK_T;                                    // top surface of the deck
LASER_Y = round(CAM_Y+(CAM_Z+GC)/tan(CAM_TILT));            // where the camera axis meets the ground

C_PART = [1, 0.45, 0];      // orange
C_WHEEL = [0.35, 0.35, 0.35];


module bx(x0, y0, z0, x1, y1, z1) {
  translate([min(x0, x1), min(y0, y1), min(z0, z1)]) cube([abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]);
}

module hz(a, b, r, lo, hi) { translate([a, b, lo]) cylinder(r = r, h = hi - lo); }
module hx(a, b, r, lo, hi) { translate([lo, a, b]) rotate([0, 90, 0]) cylinder(r = r, h = hi - lo); }
module hy(a, b, r, lo, hi) { translate([a, lo, b]) rotate([-90, 0, 0]) cylinder(r = r, h = hi - lo); }

module tb(cx, cy, ro, ri, z0, z1) {
  translate([cx, cy, min(z0, z1)]) difference() {
    cylinder(r = ro, h = abs(z1 - z0));
    translate([0, 0, -0.01]) cylinder(r = ri, h = abs(z1 - z0) + 0.02);
  }
}

module tray(cx, cy, w, l, z0, zdir = 1, pad = 1.5, clip_h = 3, t = 1.6, leg = 6, padsz = 5) {
  for (sx = [-1, 1]) for (sy = [-1, 1]) {
    xi = cx + sx * w / 2; yi = cy + sy * l / 2;
    xo = xi + sx * t;     yo = yi + sy * t;
    bx(xo, yi, z0, xo - sx * leg, yo, z0 + zdir * (pad + clip_h));
    bx(xi, yo, z0, xo, yo - sy * leg, z0 + zdir * (pad + clip_h));
    if (pad > 0) bx(xi, yi, z0, xi - sx * padsz, yi - sy * padsz, z0 + zdir * pad);
  }
}


module part_base() {
  difference() {
    union() {
      // floor and walls
      bx(-HW, -HL, 0, HW, HL, FLOOR);
      bx(-HW, -HL, FLOOR, -HW+WALL, HL, TUB_H);
      bx(HW-WALL, -HL, FLOOR, HW, HL, TUB_H);
      bx(-HW+WALL, HL-WALL, FLOOR, HW-WALL, HL, TUB_H);
      bx(-HW+WALL, -HL, FLOOR, HW-WALL, -HL+WALL, TUB_H);

      bx(-32.7, -39.2, FLOOR, -31.2, 39.2, 15);
      bx(31.2, -39.2, FLOOR, 32.7, 39.2, 15);
      bx(-31.2, -40.7, FLOOR, -12, -39.2, 13);
      bx(12, -40.7, FLOOR, 31.2, -39.2, 13);
      bx(-31.2, 39.2, FLOOR, -12, 40.7, 13);
      bx(12, 39.2, FLOOR, 31.2, 40.7, 13);

      tray(-49.2, 0, 22.4, 56.6, FLOOR, 1, 1.5, 3, 1.6, 6, 5);
      tray(49.2, 0, 24.4, 52.4, FLOOR, 1, 1.5, 3, 1.6, 6, 5);
    }

    hz(-27, MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(-27, MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(-57, MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(-57, MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(-40, MOTOR_Y, 0.9, -1, FLOOR+1);
    hz(27, MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(27, MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(57, MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(57, MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(40, MOTOR_Y, 0.9, -1, FLOOR+1);
    hz(-27, -MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(-27, -MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(-57, -MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(-57, -MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(-40, -MOTOR_Y, 0.9, -1, FLOOR+1);
    hz(27, -MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(27, -MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(57, -MOTOR_Y+-9.1, 1.4, -1, FLOOR+1);
    hz(57, -MOTOR_Y+9.1, 1.4, -1, FLOOR+1);
    hz(40, -MOTOR_Y, 0.9, -1, FLOOR+1);

    bx(-35.2, 13, -1, -33, 27, FLOOR+1);
    bx(-35.2, -27, -1, -33, -13, FLOOR+1);
    bx(33, 13, -1, 35.2, 27, FLOOR+1);
    bx(33, -27, -1, 35.2, -13, FLOOR+1);

    bx(-13.2, SPEC_Y-9.5, -1, 13.2, SPEC_Y+9.5, FLOOR+1);
    hz(-18.5, SPEC_Y, 1.4, -1, FLOOR+1);
    hz(18.5, SPEC_Y, 1.4, -1, FLOOR+1);

    bx(-40.75, -HL-1, 12.4, -19.25, -HL+4, 27.6);
    hy(30, 19, 4.2, -HL-1, -HL+4);

    bx(-15.5, ACT_Y-8, -1, 15.5, ACT_Y+8, FLOOR+1);
  }
  tb(-57.5, -99.5, 4.6, 1.25, FLOOR, TUB_H);
  tb(-57.5, 99.5, 4.6, 1.25, FLOOR, TUB_H);
  tb(57.5, -99.5, 4.6, 1.25, FLOOR, TUB_H);
  tb(57.5, 99.5, 4.6, 1.25, FLOOR, TUB_H);
  tb(-58.5, -45, 4.6, 1.25, FLOOR, TUB_H);
  tb(-58.5, 45, 4.6, 1.25, FLOOR, TUB_H);
  tb(58.5, -45, 4.6, 1.25, FLOOR, TUB_H);
  tb(58.5, 45, 4.6, 1.25, FLOOR, TUB_H);
}


module part_deck() {
  difference() {
    union() {
      bx(-HW, -HL, 0, HW, HL, DECK_T);
      // trays: TB6612 x2, DRV8871, RS485 module, GPS
      tray(-38, 60, 21.6, 21.6, DECK_T, 1, 1.5, 3, 1.6, 6, 5);
      tray(-12, 60, 21.6, 21.6, DECK_T, 1, 1.5, 3, 1.6, 6, 5);
      tray(16, 60, 24.6, 19.6, DECK_T, 1, 1.5, 3, 1.6, 6, 5);
      tray(-18, -14, 46.5, 17, DECK_T, 1, 1.5, 3, 1.6, 6, 5);
      tray(30, -14, 37.5, 26.5, DECK_T, 1, 1.2, 3, 1.6, 6, 5);
    }

    hz(-57.5, -99.5, 1.7, -1, DECK_T+1);
    hz(-57.5, 99.5, 1.7, -1, DECK_T+1);
    hz(57.5, -99.5, 1.7, -1, DECK_T+1);
    hz(57.5, 99.5, 1.7, -1, DECK_T+1);
    hz(-58.5, -45, 1.7, -1, DECK_T+1);
    hz(-58.5, 45, 1.7, -1, DECK_T+1);
    hz(58.5, -45, 1.7, -1, DECK_T+1);
    hz(58.5, 45, 1.7, -1, DECK_T+1);
    hz(-30, 84, 1.7, -1, DECK_T+1);
    hz(-30, 96, 1.7, -1, DECK_T+1);
    hz(30, 84, 1.7, -1, DECK_T+1);
    hz(30, 96, 1.7, -1, DECK_T+1);
    
    bx(-13.2, ACT_Y-13.2, -1, 13.2, ACT_Y+13.2, DECK_T+1);
    hz(-17.5, ACT_Y+-17.5, 1.7, -1, DECK_T+1);
    bx(-59.5, -32, -1, -54.5, -12, DECK_T+1);
    hz(-17.5, ACT_Y+17.5, 1.7, -1, DECK_T+1);
    bx(-59.5, 12, -1, -54.5, 32, DECK_T+1);
    hz(17.5, ACT_Y+-17.5, 1.7, -1, DECK_T+1);
    bx(54.5, -32, -1, 59.5, -12, DECK_T+1);
    hz(17.5, ACT_Y+17.5, 1.7, -1, DECK_T+1);
    bx(54.5, 12, -1, 59.5, 32, DECK_T+1);
  }
  tb(-29, 8.5, 3, 1.1, DECK_T, DECK_T+4.5);
  tb(-29, 31.5, 3, 1.1, DECK_T, DECK_T+4.5);
  tb(29, 8.5, 3, 1.1, DECK_T, DECK_T+4.5);
  tb(29, 31.5, 3, 1.1, DECK_T, DECK_T+4.5);
}


module part_clamp() {
  difference() {
    union() {
      bx(-22, ACT_Y-22, DECK_TOP, 22, ACT_Y+22, DECK_TOP+14);
    }
    bx(-13.2, ACT_Y-13.2, DECK_TOP-1, 13.2, ACT_Y+13.2, DECK_TOP+15);
    hz(-17.5, ACT_Y+-17.5, 1.7, DECK_TOP-1, DECK_TOP+15);
    hz(-17.5, ACT_Y+17.5, 1.7, DECK_TOP-1, DECK_TOP+15);
    hx(ACT_Y, DECK_TOP+7, 1.25, -23, -13);
    hz(17.5, ACT_Y+-17.5, 1.7, DECK_TOP-1, DECK_TOP+15);
    hz(17.5, ACT_Y+17.5, 1.7, DECK_TOP-1, DECK_TOP+15);
    hx(ACT_Y, DECK_TOP+7, 1.25, 13, 23);
  }
}


module part_head_local() {
  difference() {
    union() {

      bx(-35, -22, 0, 35, 22, 3);
      bx(35, -6, 0, 41.5, 6, 3);
      bx(-41.5, -6, 0, -35, 6, 3);

      tray(18, 0, 26.6, 18.6, 0, -1, 2, 3, 1.6, 6, 5);
    }

    bx(-25, -7, -1, -11, 7, 4);
    hz(18, 0, 6, -1, 4);
  }
  tb(-28.5, -6.25, 3, 1, -4, 0);
  tb(-28.5, 6.25, 3, 1, -4, 0);
  tb(-7.5, -6.25, 3, 1, -4, 0);
  tb(-7.5, 6.25, 3, 1, -4, 0);
}
module part_mast_body() {
  difference() {
    union() {

      bx(-41, 80, DECK_TOP, 41, 100, DECK_TOP+3);
      bx(-41, 84, DECK_TOP+3, -35, 96, 96);
      bx(35, 84, DECK_TOP+3, 41, 96, 96);
      bx(-41, 86, 90, 41, 94, 96);
      bx(-6, 86, 90, 6, LASER_Y+9, 96);
      bx(-9, LASER_Y-9, 74, 9, LASER_Y+9, 96);
    }

    hz(-30, 84, 1.7, DECK_TOP-1, DECK_TOP+4);
    hz(-30, 96, 1.7, DECK_TOP-1, DECK_TOP+4);
    hz(30, 84, 1.7, DECK_TOP-1, DECK_TOP+4);
    hz(30, 96, 1.7, DECK_TOP-1, DECK_TOP+4);
    hz(0, LASER_Y, 3.1, 70, 100);
    hx(LASER_Y, 85, 1.25, 3, 10);
  }
}
module part_mast() {
  part_mast_body();
  translate([0, CAM_Y, CAM_Z]) rotate([270 - CAM_TILT, 0, 0]) part_head_local();
}


module part_pod() {
  difference() {
    union() {
      bx(17, -POD_HW, POD_Z0, HW, POD_HW, 0);
    }

    bx(16, -CH_W/2, CH_Z-(CH_H/2), HW-2, CH_W/2, 1);
    hx(0, CH_Z, 3.5, HW-2.1, HW+1);
    hz(27, -9.1, 1, POD_Z0+4, 0.1);
    hz(27, 9.1, 1, POD_Z0+4, 0.1);
    hz(57, -9.1, 1, POD_Z0+4, 0.1);
    hz(57, 9.1, 1, POD_Z0+4, 0.1);
  }
}


module part_spec() {
  difference() {
    union() {

      bx(-15, SPEC_Y-11.3, SPOD_Z0, -13.2, SPEC_Y+11.3, 0);
      bx(13.2, SPEC_Y-11.3, SPOD_Z0, 15, SPEC_Y+11.3, 0);
      bx(-13.2, SPEC_Y-11.3, SPOD_Z0, 13.2, SPEC_Y-9.5, 0);
      bx(-13.2, SPEC_Y+9.5, SPOD_Z0, 13.2, SPEC_Y+11.3, 0);
      bx(-13.2, SPEC_Y-9.5, -15, 13.2, SPEC_Y+9.5, -13.5);
      bx(-22, SPEC_Y-4, -4.5, -15, SPEC_Y+4, 0);
      bx(15, SPEC_Y-4, -4.5, 22, SPEC_Y+4, 0);
    }

    bx(-11, SPEC_Y-7, -16, 11, SPEC_Y+7, -12.5);
    hz(-18.5, SPEC_Y, 1.1, -4.4, 0.1);
    hz(18.5, SPEC_Y, 1.1, -4.4, 0.1);
  }
}


module wheels() {
  color(C_WHEEL) for (sx = [-1, 1]) for (yc = [MOTOR_Y, -MOTOR_Y])
    translate([sx * (HW + 0.5 + WHEEL_W / 2), yc, CH_Z]) rotate([0, 90, 0]) cylinder(r = WHEEL_R, h = WHEEL_W, center = true);
}
module assembly() {
  color(C_PART) {
    part_base();
    translate([0, 0, TUB_H]) part_deck();
    part_clamp();
    part_mast();
    part_spec();
    for (yc = [MOTOR_Y, -MOTOR_Y]) {
      translate([0, yc, 0]) part_pod();
      translate([0, yc, 0]) rotate([0, 0, 180]) part_pod();
    }
  }
  if (show_wheels) wheels();
}

if (part == "assembly") assembly();
else if (part == "base") part_base();
else if (part == "deck") part_deck();
else if (part == "mast") { if (print_layout) translate([0, 0, -DECK_TOP]) part_mast(); else part_mast(); }
else if (part == "clamp") { if (print_layout) translate([0, 0, -DECK_TOP]) part_clamp(); else part_clamp(); }
else if (part == "pod") { if (print_layout) translate([0, 0, -POD_Z0]) part_pod(); else part_pod(); }
else if (part == "spec") { if (print_layout) rotate([0, 180, 0]) part_spec(); else part_spec(); }
