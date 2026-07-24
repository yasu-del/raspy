# -*- coding: utf-8 -*-
"""
sensor.py - BNO055 磁気センサー制御モジュール

担当: センサーデータ取得（磁束密度 x, y, z）
使用センサー: BNO055 (9軸慣性センサ, I2C接続)
使用ライブラリ: smbus (Raspberry Pi 標準搭載)

動作確認済み: 2026-07-24
  - i2cdetect -y 1 でアドレス 0x28 に検出
  - MAGONLYモードで磁束密度の読み取り成功
"""

import smbus
import time


# BNO055 I2Cアドレス（デフォルト: 0x28, ジャンパで 0x29 に変更可能）
_BNO055_ADDR       = 0x28

# レジスタアドレス
_REG_CHIP_ID       = 0x00  # チップID（正常値: 0xA0）
_REG_OPR_MODE      = 0x3D  # 動作モード設定レジスタ
_REG_MAG_DATA_X_LSB = 0x0E  # 磁束密度データ先頭（X軸 LSB）

# 動作モード
_MODE_CONFIG       = 0x00  # 設定モード（モード切替時に経由）
_MODE_MAGONLY      = 0x02  # 磁気センサーのみ使用

# 磁束密度の変換係数: 1 μT = 16 LSB
_MAG_SCALE         = 16.0

# モード切替後の待機時間 [秒]
_MODE_SWITCH_DELAY = 2.0


class BNO055Sensor:
    """BNO055 磁気センサーを制御するクラス。

    I2Cで接続されたBNO055から磁束密度データ (x, y, z) を取得する。
    単位はマイクロテスラ (μT)。
    Adafruitライブラリは不要（smbus で直接レジスタを操作）。
    """

    def __init__(self):
        """I2Cバスを初期化し、BNO055をMAGONLYモードで起動する。

        Raises:
            RuntimeError: センサーへの接続に失敗した場合、
                          またはチップIDが一致しない場合。
        """
        try:
            self._bus  = smbus.SMBus(1)  # I2Cバス1番（Raspberry Pi標準）
            self._addr = _BNO055_ADDR

            # チップIDを確認（BNO055 は必ず 0xA0 を返す）
            chip_id = self._bus.read_byte_data(self._addr, _REG_CHIP_ID)
            if chip_id != 0xA0:
                raise RuntimeError(
                    f"BNO055が見つかりません。チップID: {hex(chip_id)}"
                    f"（期待値: 0xa0）"
                )

            # CONFIGモード → MAGONLYモードへ切り替え
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.1)
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_MAGONLY)
            time.sleep(_MODE_SWITCH_DELAY)

        except OSError as e:
            raise RuntimeError(
                f"BNO055センサーへの接続に失敗しました（I2Cアドレス: "
                f"{hex(_BNO055_ADDR)}）: {e}"
            ) from e

    def read_magnetic_vector(self):
        """磁束密度 (x, y, z) を取得する。

        Returns:
            tuple[float, float, float] | None: 磁束密度 (mag_x, mag_y, mag_z) [μT]。
                読み取りに失敗した場合は None を返す。
                ※ 呼び出し側で None チェックを行うこと。
        """
        try:
            # 0x0E から 6 バイト読む（X_LSB, X_MSB, Y_LSB, Y_MSB, Z_LSB, Z_MSB）
            data = self._bus.read_i2c_block_data(self._addr, _REG_MAG_DATA_X_LSB, 6)

            mag_x = self._to_signed((data[1] << 8) | data[0]) / _MAG_SCALE
            mag_y = self._to_signed((data[3] << 8) | data[2]) / _MAG_SCALE
            mag_z = self._to_signed((data[5] << 8) | data[4]) / _MAG_SCALE

            return mag_x, mag_y, mag_z

        except OSError:
            # I2C通信エラー（センサーが応答しない等）
            return None

    def is_calibrated(self):
        """磁気センサーのキャリブレーション状態を確認する。

        BNO055のキャリブレーションステータスレジスタ(0x35)から
        磁気センサーのステータス（0〜3）を取得する。
        3が最大（完全にキャリブレーション済み）。

        Returns:
            bool: 磁気センサーが完全にキャリブレーションされている場合 True。
        """
        # TODO: キャリブレーション完了を待つループが必要か検討する（recorder.pyと相談）
        try:
            calib = self._bus.read_byte_data(self._addr, 0x35)
            # ビット1〜0が磁気センサーのステータス
            mag_status = calib & 0x03
            return mag_status == 3
        except OSError:
            return False

    @staticmethod
    def _to_signed(val):
        """16ビット符号なし整数を符号付きに変換する。"""
        return val - 65536 if val > 32767 else val
