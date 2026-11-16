# -*- coding: utf-8 -*-
"""
sensor.py - BNO055 センサー制御モジュール
使用ライブラリ: smbus (Raspberry Pi 標準搭載)

改善点 (2026年改修):
  - 磁気測定時の精度向上のため、NDOF_FMC_OFF (高速自動磁気補正OFF) モードをサポート。
    ※ 強い磁石に近づけた際にBNO055が勝手にオフセットを再計算して測定値が歪むのを防止。
  - キャリブレーションデータ（0x55〜0x6A）の保存・復元機能を追加。
  - I2C通信の一時エラーに対する自動リトライ処理を追加。
  - 新規データ更新検出用キャッシュの導入。
"""
import smbus
import time
import json
import os
from collections import deque

_BNO055_ADDR          = 0x28
_REG_CHIP_ID          = 0x00  # 正常値 0xA0
_REG_OPR_MODE         = 0x3D
_REG_MAG_DATA_X_LSB   = 0x0E
_REG_QUA_DATA_W_LSB   = 0x20  # クォータニオン w,x,y,z (各2byte, 計8byte)
_REG_LIA_DATA_X_LSB   = 0x28  # 線形加速度 x,y,z (各2byte, 計6byte)
_REG_CALIB_STAT       = 0x35
_REG_CALIB_DATA_START = 0x55  # キャリブレーションオフセットレジスタ (計22byte)

_MODE_CONFIG          = 0x00
_MODE_MAGONLY         = 0x02
_MODE_IMU             = 0x08  # 加速度+ジャイロ (磁気干渉なし)
_MODE_NDOF_FMC_OFF    = 0x0B  # 9軸フュージョン (FMC無効: 強磁場でも自動オフセット変更で狂わない)
_MODE_NDOF            = 0x0C  # 9軸フュージョン (通常NDOF: FMC有効)

_MAG_SCALE            = 16.0     # 1 μT = 16 LSB
_LIA_SCALE            = 100.0    # 1 m/s^2 = 100 LSB
_QUA_SCALE            = 16384.0  # 1.0 = 2^14 LSB
_MODE_SWITCH_DELAY    = 0.05

# ── 精度設定（慣性航法はノイズが2回積分で増幅されるため）──────────
FILTER_WINDOW = 10      # 移動平均のサンプル数
DEAD_ZONE_ACC = 0.12   # [m/s^2] これ未満の加速度は 0 とみなす（静止時ドリフト防止）
MIN_CALIB_SYS = 2      # この値未満のシステムキャリブレーションでは None を返す


class BNO055Sensor:
    def __init__(self, mode="NDOF_FMC_OFF"):
        """
        BNO055センサーの初期化。
        
        Args:
            mode (str): 動作モード ("NDOF_FMC_OFF", "NDOF", "IMU", "MAGONLY")
                        デフォルトは "NDOF_FMC_OFF"。
                        磁気マッピングでは磁石の強磁界による誤補正を防ぐため FMC OFF が推奨。
        """
        self._acc_buf  = deque(maxlen=FILTER_WINDOW)
        self._quat_buf = deque(maxlen=FILTER_WINDOW)
        self._last_mag_raw = None
        self._current_mode = mode

        mode_map = {
            "NDOF_FMC_OFF": _MODE_NDOF_FMC_OFF,
            "NDOF": _MODE_NDOF,
            "IMU": _MODE_IMU,
            "MAGONLY": _MODE_MAGONLY
        }
        target_mode_reg = mode_map.get(mode, _MODE_NDOF_FMC_OFF)

        try:
            self._bus  = smbus.SMBus(1)
            self._addr = _BNO055_ADDR
            chip_id = self._bus.read_byte_data(self._addr, _REG_CHIP_ID)
            if chip_id != 0xA0:
                raise RuntimeError(f"BNO055が見つかりません。チップID: {hex(chip_id)}（期待値: 0xa0）")
            
            # CONFIGモードに移行してから目的の動作モードを設定
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.05)
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, target_mode_reg)
            time.sleep(_MODE_SWITCH_DELAY)
        except OSError as e:
            raise RuntimeError(f"BNO055センサーへの接続に失敗しました（I2Cアドレス: {hex(_BNO055_ADDR)}）: {e}") from e

    def set_mode(self, mode):
        """動作モードを変更する ("NDOF_FMC_OFF", "NDOF", "IMU", "MAGONLY")"""
        mode_map = {
            "CONFIG": _MODE_CONFIG,
            "NDOF_FMC_OFF": _MODE_NDOF_FMC_OFF,
            "NDOF": _MODE_NDOF,
            "IMU": _MODE_IMU,
            "MAGONLY": _MODE_MAGONLY
        }
        if mode not in mode_map:
            raise ValueError(f"未知の動作モード: {mode}")
        try:
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.05)
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, mode_map[mode])
            time.sleep(_MODE_SWITCH_DELAY)
            self._current_mode = mode
        except OSError as e:
            raise RuntimeError(f"動作モード変更に失敗しました: {e}") from e

    def read_magnetic_vector(self, max_retries=2):
        """戻り値: (mag_x, mag_y, mag_z) [μT] / 失敗時 None"""
        for _ in range(max_retries + 1):
            try:
                data = self._bus.read_i2c_block_data(self._addr, _REG_MAG_DATA_X_LSB, 6)
                self._last_mag_raw = tuple(data)
                mag_x = self._to_signed((data[1] << 8) | data[0]) / _MAG_SCALE
                mag_y = self._to_signed((data[3] << 8) | data[2]) / _MAG_SCALE
                mag_z = self._to_signed((data[5] << 8) | data[4]) / _MAG_SCALE
                return mag_x, mag_y, mag_z
            except OSError:
                time.sleep(0.005)
        return None

    def get_last_mag_raw(self):
        """直近に読み出した生バイト列を取得（更新チェック用）"""
        return self._last_mag_raw

    def get_calibration_status(self):
        """戻り値: (sys, gyro, accel, mag) 各 0〜3 / 失敗時 (0, 0, 0, 0)"""
        try:
            calib = self._bus.read_byte_data(self._addr, _REG_CALIB_STAT)
            return ((calib >> 6) & 0x03, (calib >> 4) & 0x03,
                    (calib >> 2) & 0x03, calib & 0x03)
        except OSError:
            return (0, 0, 0, 0)

    def is_calibrated(self):
        """CALIB_STAT(0x35) の bit1-0 (mag) が 3 なら True"""
        try:
            calib = self._bus.read_byte_data(self._addr, _REG_CALIB_STAT)
            return (calib & 0x03) == 3
        except OSError:
            return False

    def is_fully_calibrated(self):
        """Sys, Gyro, Accel, Mag すべてが 3 なら True"""
        stat = self.get_calibration_status()
        return all(s == 3 for s in stat)

    # ── キャリブレーションプロファイルの保存と復元 ───────────────
    def get_calibration_offsets(self):
        """センサー内部のキャリブレーションオフセット(22バイト)を読み出してリストで返す"""
        cur_mode = self._current_mode
        try:
            # オフセット読み出しのためにCONFIGモードへ
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.05)
            data = self._bus.read_i2c_block_data(self._addr, _REG_CALIB_DATA_START, 22)
            # 元のモードに戻す
            self.set_mode(cur_mode)
            return data
        except OSError:
            self.set_mode(cur_mode)
            return None

    def set_calibration_offsets(self, offsets):
        """キャリブレーションオフセット(22バイト)をセンサーに書き込む"""
        if len(offsets) != 22:
            raise ValueError("オフセットデータは22バイトである必要があります")
        cur_mode = self._current_mode
        try:
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.05)
            # 22バイトを一括書き込み
            self._bus.write_i2c_block_data(self._addr, _REG_CALIB_DATA_START, offsets)
            time.sleep(0.05)
            self.set_mode(cur_mode)
            return True
        except OSError:
            self.set_mode(cur_mode)
            return False

    def save_calibration_profile(self, filepath):
        """キャリブレーションオフセットをJSONファイルに保存"""
        data = self.get_calibration_offsets()
        if data is None:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({"offsets": data, "timestamp": time.time()}, f, indent=2)
        return True

    def load_calibration_profile(self, filepath):
        """JSONファイルからキャリブレーションオフセットを読み込んでセンサーに適用"""
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = json.load(f)
            offsets = content.get("offsets")
            if offsets and len(offsets) == 22:
                return self.set_calibration_offsets(offsets)
        except Exception:
            return False
        return False

    # ── tracker.py 向け（慣性航法の位置計算用）────────────────────
    def read_linear_acceleration(self, max_retries=1):
        """
        重力除去済みの線形加速度。
        戻り値: (ax, ay, az) [m/s^2] / 失敗・キャリブ不足時 None
        """
        if self.get_calibration_status()[0] < MIN_CALIB_SYS:
            return None
        for _ in range(max_retries + 1):
            try:
                data = self._bus.read_i2c_block_data(self._addr, _REG_LIA_DATA_X_LSB, 6)
                break
            except OSError:
                data = None
                time.sleep(0.003)
        if data is None:
            return None

        raw = tuple(
            self._to_signed((data[2 * i + 1] << 8) | data[2 * i]) / _LIA_SCALE
            for i in range(3)
        )
        self._acc_buf.append(raw)
        n = len(self._acc_buf)
        avg = tuple(sum(s[i] for s in self._acc_buf) / n for i in range(3))
        return tuple(0.0 if abs(v) < DEAD_ZONE_ACC else v for v in avg)

    def read_quaternion(self, max_retries=1):
        """
        姿勢クォータニオン（センサー座標 -> 世界座標）。
        戻り値: (w, x, y, z) / 失敗・キャリブ不足時 None
        """
        if self.get_calibration_status()[0] < MIN_CALIB_SYS:
            return None
        for _ in range(max_retries + 1):
            try:
                data = self._bus.read_i2c_block_data(self._addr, _REG_QUA_DATA_W_LSB, 8)
                break
            except OSError:
                data = None
                time.sleep(0.003)
        if data is None:
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
