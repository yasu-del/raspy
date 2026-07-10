#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import smbus
import time
import struct
import sys

# BNO055 Constant Definitions
BNO055_ADDRESS = 0x28

# Registers
BNO055_CHIP_ID_ADDR     = 0x00
BNO055_PAGE_ID_ADDR     = 0x07
BNO055_EULER_H_LSB      = 0x1A
BNO055_QUATERNION_W_LSB = 0x20
BNO055_TEMP_ADDR        = 0x34
BNO055_CALIB_STAT_ADDR  = 0x35
BNO055_OPR_MODE_ADDR    = 0x3D
BNO055_PWR_MODE_ADDR    = 0x3E
BNO055_SYS_TRIGGER_ADDR = 0x3F

# Operation Modes
OPR_MODE_CONFIG = 0x00
OPR_MODE_NDOF   = 0x0C

class BNO055:
    def __init__(self, bus_num=1):
        try:
            self.bus = smbus.SMBus(bus_num)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {bus_num}: {e}")

        # Check connection & Chip ID
        try:
            chip_id = self.bus.read_byte_data(BNO055_ADDRESS, BNO055_CHIP_ID_ADDR)
        except Exception as e:
            raise RuntimeError(f"Could not communicate with BNO055 at address 0x28: {e}")

        if chip_id != 0xA0:
            raise RuntimeError(f"Incorrect Chip ID (Expected 0xA0, got 0x{chip_id:02X}).")

        # Reset the device
        print("Resetting BNO055...")
        try:
            self.bus.write_byte_data(BNO055_ADDRESS, BNO055_SYS_TRIGGER_ADDR, 0x20)
        except IOError:
            pass # Sometimes reset write doesn't ACK, ignore and wait
        time.sleep(0.8)  # Wait for sensor to boot

        # Set power mode to NORMAL
        self.bus.write_byte_data(BNO055_ADDRESS, BNO055_PWR_MODE_ADDR, 0x00)
        time.sleep(0.05)

        # Set page ID to 0
        self.bus.write_byte_data(BNO055_ADDRESS, BNO055_PAGE_ID_ADDR, 0x00)
        time.sleep(0.05)

        # Set operation mode to NDOF (9 Degrees of Freedom Fusion Mode)
        print("Setting operation mode to NDOF...")
        self.bus.write_byte_data(BNO055_ADDRESS, BNO055_OPR_MODE_ADDR, OPR_MODE_NDOF)
        time.sleep(0.2)  # Wait for sensor to stabilize in NDOF mode

    def _read_signed_16(self, reg):
        """Read 16-bit signed integer with short delay to prevent I2C issues."""
        for _ in range(5):
            try:
                low = self.bus.read_byte_data(BNO055_ADDRESS, reg)
                time.sleep(0.002)
                high = self.bus.read_byte_data(BNO055_ADDRESS, reg + 1)
                time.sleep(0.002)
                val = (high << 8) | low
                if val & 0x8000:
                    val -= 65536
                return val
            except IOError:
                time.sleep(0.01)
        raise IOError(f"I2C read failed at register {hex(reg)}")

    def read_euler(self):
        """Read Euler angles: Heading (Yaw), Roll, Pitch in degrees."""
        heading = self._read_signed_16(BNO055_EULER_H_LSB)
        roll    = self._read_signed_16(BNO055_EULER_H_LSB + 2)
        pitch   = self._read_signed_16(BNO055_EULER_H_LSB + 4)
        return heading / 16.0, roll / 16.0, pitch / 16.0

    def read_quaternion(self):
        """Read Quaternion data (w, x, y, z)."""
        w = self._read_signed_16(BNO055_QUATERNION_W_LSB)
        x = self._read_signed_16(BNO055_QUATERNION_W_LSB + 2)
        y = self._read_signed_16(BNO055_QUATERNION_W_LSB + 4)
        z = self._read_signed_16(BNO055_QUATERNION_W_LSB + 6)
        scale = 1.0 / 16384.0
        return w * scale, x * scale, y * scale, z * scale

    def read_temp(self):
        """Read temperature in Celsius."""
        for _ in range(5):
            try:
                temp = self.bus.read_byte_data(BNO055_ADDRESS, BNO055_TEMP_ADDR)
                time.sleep(0.002)
                if temp & 0x80:
                    temp -= 256
                if -40 < temp < 85: # Sensor range check
                    return temp
            except IOError:
                time.sleep(0.01)
        return -999

    def read_calibration_status(self):
        """Read calibration status."""
        for _ in range(5):
            try:
                calib = self.bus.read_byte_data(BNO055_ADDRESS, BNO055_CALIB_STAT_ADDR)
                time.sleep(0.002)
                sys = (calib >> 6) & 0x03
                gyro = (calib >> 4) & 0x03
                accel = (calib >> 2) & 0x03
                mag = calib & 0x03
                return sys, gyro, accel, mag
            except IOError:
                time.sleep(0.01)
        return 0, 0, 0, 0

def main():
    print("=========================================")
    print(" BNO055 Real-time Data Reader ")
    print("=========================================")
    
    try:
        sensor = BNO055()
    except Exception as e:
        print(f"Initialization Failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nInitialization Complete. Reading data...")
    print("Press Ctrl+C to exit.\n")
    
    try:
        while True:
            # Read Sensor Values
            heading, roll, pitch = sensor.read_euler()
            qw, qx, qy, qz = sensor.read_quaternion()
            temp = sensor.read_temp()
            sys_cal, gyro_cal, accel_cal, mag_cal = sensor.read_calibration_status()
            
            # Print formatted output
            output = (
                f"\033[H\033[J"
                f"--- BNO055 Sensor Readings ---\n"
                f"Euler Angles:\n"
                f"  Heading (Yaw): {heading:7.2f}°\n"
                f"  Roll:          {roll:7.2f}°\n"
                f"  Pitch:         {pitch:7.2f}°\n\n"
                f"Quaternion:\n"
                f"  W: {qw:6.3f}, X: {qx:6.3f}, Y: {qy:6.3f}, Z: {qz:6.3f}\n\n"
                f"Sensor Temp:     {temp}°C\n\n"
                f"Calibration Status (0=Uncalibrated, 3=Fully Calibrated):\n"
                f"  System: {sys_cal} | Gyro: {gyro_cal} | Accel: {accel_cal} | Mag: {mag_cal}\n"
                f"----------------------------------------"
            )
            print(output, end="", flush=True)
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nProgram terminated by user.")
    except Exception as e:
        print(f"\n\nError occurred during runtime: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
