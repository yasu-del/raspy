# -*- coding: utf-8 -*-
"""
sensor.py - BNO055 センサー制御モジュール
使用ライブラリ: smbus (Raspberry Pi 標準搭載)
動作確認済み: 2026-07-24
  - i2cdetect -y 1 でアドレス 0x28 に検出
  - MAGONLYモードで磁束密度の読み取り成功

2026-10-19 変更（未動作確認）:
  - 動作モードを MAGONLY -> NDOF に変更
    （線形加速度・クォータニオンはフュージョン出力のため NDOF が必要）
  - read_linear_acceleration() / read_quaternion() を追加（tracker.py 用）
"""
import smbus
import time
from collections import deque

_BNO055_ADDR        = 0x28
_REG_CHIP_ID        = 0x00  # 正常値 0xA0
_REG_OPR_MODE       = 0x3D
_REG_MAG_DATA_X_LSB = 0x0E
_REG_QUA_DATA_W_LSB = 0x20  # クォータニオン w,x,y,z (各2byte, 計8byte)
_REG_LIA_DATA_X_LSB = 0x28  # 線形加速度 x,y,z (各2byte, 計6byte)
_REG_CALIB_STAT     = 0x35
_MODE_CONFIG        = 0x00
_MODE_MAGONLY       = 0x02
_MODE_NDOF          = 0x0C  # 9軸フュージョン
_MAG_SCALE          = 16.0     # 1 μT = 16 LSB
_LIA_SCALE          = 100.0    # 1 m/s^2 = 100 LSB
_QUA_SCALE          = 16384.0  # 1.0 = 2^14 LSB
_MODE_SWITCH_DELAY  = 2.0

# ── 精度設定（慣性航法はノイズが2回積分で増幅されるため）──────────
FILTER_WINDOW = 5      # 移動平均のサンプル数
DEAD_ZONE_ACC = 0.05   # [m/s^2] これ未満の加速度は 0 とみなす（静止時ドリフト防止）
MIN_CALIB_SYS = 1      # この値未満のシステムキャリブレーションでは None を返す


class BNO055Sensor:
    def __init__(self):
        self._acc_buf  = deque(maxlen=FILTER_WINDOW)
        self._quat_buf = deque(maxlen=FILTER_WINDOW)
        try:
            self._bus  = smbus.SMBus(1)
            self._addr = _BNO055_ADDR
            chip_id = self._bus.read_byte_data(self._addr, _REG_CHIP_ID)
            if chip_id != 0xA0:
                raise RuntimeError(f"BNO055が見つかりません。チップID: {hex(chip_id)}（期待値: 0xa0）")
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.1)
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_NDOF)
            time.sleep(_MODE_SWITCH_DELAY)
        except OSError as e:
            raise RuntimeError(f"BNO055センサーへの接続に失敗しました（I2Cアドレス: {hex(_BNO055_ADDR)}）: {e}") from e

    def read_magnetic_vector(self):
        """戻り値: (mag_x, mag_y, mag_z) [μT] / 失敗時 None"""
        try:
            data = self._bus.read_i2c_block_data(self._addr, _REG_MAG_DATA_X_LSB, 6)
            mag_x = self._to_signed((data[1] << 8) | data[0]) / _MAG_SCALE
            mag_y = self._to_signed((data[3] << 8) | data[2]) / _MAG_SCALE
            mag_z = self._to_signed((data[5] << 8) | data[4]) / _MAG_SCALE
            return mag_x, mag_y, mag_z
        except OSError:
            return None

    def get_calibration_status(self):
        """戻り値: (sys, gyro, accel, mag) 各 0〜3 / 失敗時 (0, 0, 0, 0)"""
        try:
            calib = self._bus.read_byte_data(self._addr, _REG_CALIB_STAT)
            return ((calib >> 6) & 0x03, (calib >> 4) & 0x03,
                    (calib >> 2) & 0x03, calib & 0x03)
        except OSError:
            return (0, 0, 0, 0)

    def is_calibrated(self):
        """CALIB_STAT(0x35) の bit1-0 が 3 なら True"""
        try:
            calib = self._bus.read_byte_data(self._addr, _REG_CALIB_STAT)
            return (calib & 0x03) == 3
        except OSError:
            return False

    # ── tracker.py 向け（慣性航法の位置計算用）────────────────────
    # 加速度を2回積分して位置を出すため、ノイズは誤差として増幅される。
    # そのため移動平均とデッドゾーンでノイズ・静止時ドリフトを抑える。

    def read_linear_acceleration(self):
        """
        重力除去済みの線形加速度。
        戻り値: (ax, ay, az) [m/s^2] / 失敗・キャリブ不足時 None
        """
        if self.get_calibration_status()[0] < MIN_CALIB_SYS:
            return None
        try:
            data = self._bus.read_i2c_block_data(self._addr, _REG_LIA_DATA_X_LSB, 6)
        except OSError:
            return None
        raw = tuple(
            self._to_signed((data[2 * i + 1] << 8) | data[2 * i]) / _LIA_SCALE
            for i in range(3)
        )
        self._acc_buf.append(raw)
        n = len(self._acc_buf)
        avg = tuple(sum(s[i] for s in self._acc_buf) / n for i in range(3))
        return tuple(0.0 if abs(v) < DEAD_ZONE_ACC else v for v in avg)

    def read_quaternion(self):
        """
        姿勢クォータニオン（センサー座標 -> 世界座標）。
        戻り値: (w, x, y, z) / 失敗・キャリブ不足時 None
        """
        if self.get_calibration_status()[0] < MIN_CALIB_SYS:
            return None
        try:
            data = self._bus.read_i2c_block_data(self._addr, _REG_QUA_DATA_W_LSB, 8)
        except OSError:
            return None
        raw = tuple(
            self._to_signed((data[2 * i + 1] << 8) | data[2 * i]) / _QUA_SCALE
            for i in range(4)
        )
        self._quat_buf.append(raw)
        n = len(self._quat_buf)
        w, x, y, z = (sum(s[i] for s in self._quat_buf) / n for i in range(4))
        norm = (w * w + x * x + y * y + z * z) ** 0.5
        if norm == 0:
            return None
        return (w / norm, x / norm, y / norm, z / norm)

    @staticmethod
    def _to_signed(val):
        return val - 65536 if val > 32767 else val
