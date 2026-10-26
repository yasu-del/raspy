# -*- coding: utf-8 -*-
import sys
# Windows コンソールを UTF-8 モードに切り替える（cp932 での文字化け防止）
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # Python 3.6 以前では reconfigure が使えない
"""
test_realtime_display.py - BNO055 リアルタイムデータ表示スクリプト

磁束密度 (μT)、加速度 (m/s²)、クォータニオン (w, x, y, z) を
コンソールにリアルタイムで表示する。

対象センサー : BNO055 (9軸慣性センサ, I2C接続)
実行環境     : Raspberry Pi (smbus使用) または Windows (モック動作)
実行方法     : python tests/test_realtime_display.py

動作モード
----------
- Raspberry Pi : BNO055を NDOF モードで動作させ実データを表示
- Windows 等   : smbus が存在しない場合はモックデータで動作確認

キー操作
--------
Ctrl+C でいつでも終了できる。
"""


import time
import math
import os

# ─── BNO055 レジスタ定義 ────────────────────────────────────────────────────
_BNO055_ADDR           = 0x28

_REG_CHIP_ID           = 0x00   # チップID (正常値: 0xA0)
_REG_OPR_MODE          = 0x3D   # 動作モード設定
_REG_CALIB_STAT        = 0x35   # キャリブレーションステータス

_REG_ACC_DATA_X_LSB    = 0x08   # 加速度データ先頭（重力含む）
_REG_MAG_DATA_X_LSB    = 0x0E   # 磁束密度データ先頭
_REG_QUA_DATA_W_LSB    = 0x20   # クォータニオンデータ先頭
_REG_LIA_DATA_X_LSB    = 0x28   # 線形加速度データ先頭（重力除去済み）

_MODE_CONFIG           = 0x00   # 設定モード
_MODE_NDOF             = 0x0C   # 9軸フュージョンモード (加速度+磁気+ジャイロ)

_ACC_SCALE             = 100.0  # 1 m/s² = 100 LSB
_MAG_SCALE             = 16.0   # 1 μT   = 16 LSB
_QUA_SCALE             = 16384.0  # 1.0 (単位なし) = 2^14 LSB

_MODE_SWITCH_DELAY     = 0.7    # モード切替後の待機 [秒]

# 表示更新間隔 [秒]
_UPDATE_INTERVAL       = 0.1


# ─── smbus インポート (Raspberry Pi 以外はモック) ──────────────────────────
try:
    import smbus
    _SMBUS_AVAILABLE = True
except ImportError:
    _SMBUS_AVAILABLE = False


# ─── モック SMBus (Windows / CI 環境向け) ─────────────────────────────────
class _MockSMBus:
    """smbus が利用できない環境でシミュレーションデータを返すモック。

    BNO055 の各レジスタに対する読み取りをシミュレートする。
    値はサイン波等を使って時間経過とともに変化させる。
    """

    def read_byte_data(self, addr, reg):
        if reg == _REG_CHIP_ID:
            return 0xA0
        if reg == _REG_CALIB_STAT:
            # sys=3, gyro=3, acc=3, mag=3 (完全キャリブレーション済み)
            return 0xFF
        return 0x00

    def write_byte_data(self, addr, reg, value):
        pass  # モックなので何もしない

    def read_i2c_block_data(self, addr, reg, length):
        t = time.time()

        if reg == _REG_ACC_DATA_X_LSB:
            # 重力加速度 ≈ 9.8 m/s² をZ軸に、XY軸は軽微な振動
            ax = int(0.1 * math.sin(t * 0.7) * _ACC_SCALE)
            ay = int(0.1 * math.cos(t * 0.5) * _ACC_SCALE)
            az = int(9.80665 * _ACC_SCALE)
            return _pack_xyz(ax, ay, az)

        if reg == _REG_MAG_DATA_X_LSB:
            # 地磁気をシミュレート (東京付近の概算値 μT)
            mx = int((30.0 + 2.0 * math.sin(t * 0.3)) * _MAG_SCALE)
            my = int((-5.0 + 1.5 * math.cos(t * 0.4)) * _MAG_SCALE)
            mz = int((40.0 + 1.0 * math.sin(t * 0.2)) * _MAG_SCALE)
            return _pack_xyz(mx, my, mz)

        if reg == _REG_QUA_DATA_W_LSB:
            # ゆっくり回転するクォータニオンをシミュレート
            angle = t * 0.1  # [rad]
            w = int(math.cos(angle / 2) * _QUA_SCALE)
            x = int(0.0 * _QUA_SCALE)
            y = int(math.sin(angle / 2) * _QUA_SCALE)
            z = int(0.0 * _QUA_SCALE)
            # BNO055 の順序: W, X, Y, Z
            return _pack_wxyz(w, x, y, z)

        if reg == _REG_LIA_DATA_X_LSB:
            # 線形加速度（重力除去済み）をシミュレート：手振れ的な動き
            lx = int(2.0 * math.sin(t * 1.3) * _ACC_SCALE)
            ly = int(1.5 * math.cos(t * 1.7) * _ACC_SCALE)
            lz = int(0.5 * math.sin(t * 2.1) * _ACC_SCALE)
            return _pack_xyz(lx, ly, lz)

        return [0] * length


def _pack_xyz(x, y, z):
    """(x, y, z) を BNO055 形式の 6 バイトリストにパックする。"""
    def to_bytes(v):
        v = int(v) & 0xFFFF
        return [v & 0xFF, (v >> 8) & 0xFF]
    return to_bytes(x) + to_bytes(y) + to_bytes(z)


def _pack_wxyz(w, x, y, z):
    """(w, x, y, z) を BNO055 形式の 8 バイトリストにパックする。"""
    def to_bytes(v):
        v = int(v) & 0xFFFF
        return [v & 0xFF, (v >> 8) & 0xFF]
    return to_bytes(w) + to_bytes(x) + to_bytes(y) + to_bytes(z)


# ─── BNO055 読み取りクラス ──────────────────────────────────────────────────
class BNO055RealtimeReader:
    """BNO055から磁気・加速度・クォータニオンをリアルタイムで読み取るクラス。

    Raspberry Pi では smbus 経由で実データを取得。
    Windows 等の環境ではモックデータを使用する。
    """

    def __init__(self):
        if _SMBUS_AVAILABLE:
            self._bus = smbus.SMBus(1)
            print("[INFO] smbus を使用してBNO055に接続します...")
        else:
            self._bus = _MockSMBus()
            print("[MOCK] smbus が見つかりません。モックデータで動作します。")

        self._addr = _BNO055_ADDR
        self._init_sensor()

    def _init_sensor(self):
        """BNO055をNDOFモードで初期化する。"""
        if _SMBUS_AVAILABLE:
            chip_id = self._bus.read_byte_data(self._addr, _REG_CHIP_ID)
            if chip_id != 0xA0:
                raise RuntimeError(
                    f"BNO055が見つかりません。チップID: {hex(chip_id)}"
                    f" (期待値: 0xa0)"
                )
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_CONFIG)
            time.sleep(0.1)
            self._bus.write_byte_data(self._addr, _REG_OPR_MODE, _MODE_NDOF)
            time.sleep(_MODE_SWITCH_DELAY)
            print("[INFO] BNO055を NDOF モードで起動しました。")

    def read_accelerometer(self):
        """加速度 (ax, ay, az) [m/s²] を返す。失敗時は None。"""
        try:
            data = self._bus.read_i2c_block_data(
                self._addr, _REG_ACC_DATA_X_LSB, 6
            )
            ax = _to_signed16((data[1] << 8) | data[0]) / _ACC_SCALE
            ay = _to_signed16((data[3] << 8) | data[2]) / _ACC_SCALE
            az = _to_signed16((data[5] << 8) | data[4]) / _ACC_SCALE
            return ax, ay, az
        except OSError:
            return None

    def read_magnetic(self):
        """磁束密度 (mx, my, mz) [μT] を返す。失敗時は None。"""
        try:
            data = self._bus.read_i2c_block_data(
                self._addr, _REG_MAG_DATA_X_LSB, 6
            )
            mx = _to_signed16((data[1] << 8) | data[0]) / _MAG_SCALE
            my = _to_signed16((data[3] << 8) | data[2]) / _MAG_SCALE
            mz = _to_signed16((data[5] << 8) | data[4]) / _MAG_SCALE
            return mx, my, mz
        except OSError:
            return None

    def read_quaternion(self):
        """クォータニオン (qw, qx, qy, qz) を返す。失敗時は None。"""
        try:
            # BNO055は W, X, Y, Z の順に 8 バイト
            data = self._bus.read_i2c_block_data(
                self._addr, _REG_QUA_DATA_W_LSB, 8
            )
            qw = _to_signed16((data[1] << 8) | data[0]) / _QUA_SCALE
            qx = _to_signed16((data[3] << 8) | data[2]) / _QUA_SCALE
            qy = _to_signed16((data[5] << 8) | data[4]) / _QUA_SCALE
            qz = _to_signed16((data[7] << 8) | data[6]) / _QUA_SCALE
            return qw, qx, qy, qz
        except OSError:
            return None

    def read_linear_accel(self):
        """線形加速度 (lx, ly, lz) [m/s²] を返す。重力成分を除去済み。失敗時は None。

        BNO055 の NDOFモードが重力を内部で推定・除去するため、
        このレジスタには「手で動かした時の純粋な加速度」のみが入る。
        静止時は 0 に近い値になる。
        """
        try:
            data = self._bus.read_i2c_block_data(
                self._addr, _REG_LIA_DATA_X_LSB, 6
            )
            lx = _to_signed16((data[1] << 8) | data[0]) / _ACC_SCALE
            ly = _to_signed16((data[3] << 8) | data[2]) / _ACC_SCALE
            lz = _to_signed16((data[5] << 8) | data[4]) / _ACC_SCALE
            return lx, ly, lz
        except OSError:
            return None

    def read_calibration_status(self):
        """キャリブレーション状態 (sys, gyro, acc, mag) を 0〜3 で返す。"""
        try:
            calib = self._bus.read_byte_data(self._addr, _REG_CALIB_STAT)
            sys_stat  = (calib >> 6) & 0x03
            gyro_stat = (calib >> 4) & 0x03
            acc_stat  = (calib >> 2) & 0x03
            mag_stat  =  calib       & 0x03
            return sys_stat, gyro_stat, acc_stat, mag_stat
        except OSError:
            return None


def _to_signed16(val):
    """16ビット符号なし整数を符号付きに変換する。"""
    return val - 65536 if val > 32767 else val


# ─── 表示ヘルパー ───────────────────────────────────────────────────────────
def _clear_screen():
    """コンソールをクリアする（Windows / Linux 共通）。"""
    os.system("cls" if sys.platform == "win32" else "clear")


def _calib_bar(level):
    """キャリブレーションレベル (0〜3) をバーで表示する。"""
    filled = "#" * level
    empty  = "-" * (3 - level)
    return f"[{filled}{empty}] {level}/3"


def _vec3_str(label, x, y, z, unit):
    """3軸ベクトルを整形して返す。"""
    return (
        f"  {label:<12}"
        f"X: {x:+8.3f}  "
        f"Y: {y:+8.3f}  "
        f"Z: {z:+8.3f}  [{unit}]"
    )


def _quat_str(w, x, y, z):
    """クォータニオンを整形して返す。"""
    norm = math.sqrt(w**2 + x**2 + y**2 + z**2)
    return (
        f"  {'Quaternion':<12}"
        f"W: {w:+7.4f}  "
        f"X: {x:+7.4f}  "
        f"Y: {y:+7.4f}  "
        f"Z: {z:+7.4f}  "
        f"(norm: {norm:.4f})"
    )


# ─── メインループ ───────────────────────────────────────────────────────────
def main():
    """リアルタイム表示のメインループ。"""
    print("=" * 65)
    print("  BNO055 リアルタイムセンサー表示")
    print("  磁束密度 / 加速度 / クォータニオン")
    print("=" * 65)
    print("  センサーを初期化中...")

    try:
        reader = BNO055RealtimeReader()
    except RuntimeError as e:
        print(f"\n[ERROR] 初期化失敗: {e}")
        sys.exit(1)

    print(f"\n  更新間隔: {_UPDATE_INTERVAL * 1000:.0f} ms")
    print("  終了するには Ctrl+C を押してください。\n")
    time.sleep(1.0)

    frame = 0
    try:
        while True:
            mag   = reader.read_magnetic()
            acc   = reader.read_accelerometer()
            lia   = reader.read_linear_accel()
            quat  = reader.read_quaternion()
            calib = reader.read_calibration_status()

            _clear_screen()

            # ヘッダー
            print("=" * 70)
            print(f"  BNO055 リアルタイムモニター  "
                  f"  フレーム: {frame:>6}  "
                  f"  時刻: {time.strftime('%H:%M:%S')}")
            print("=" * 70)

            # キャリブレーション状態
            if calib:
                sys_s, gyro_s, acc_s, mag_s = calib
                print()
                print("  ── キャリブレーション状態 ──")
                print(f"    Sys : {_calib_bar(sys_s)}")
                print(f"    Gyro: {_calib_bar(gyro_s)}")
                print(f"    Acc : {_calib_bar(acc_s)}")
                print(f"    Mag : {_calib_bar(mag_s)}")
            else:
                print("  [WARNING] キャリブレーション状態取得失敗")

            # 磁束密度
            print()
            print("  ── 磁束密度 ──────────────────────────────────────────")
            if mag:
                print(_vec3_str("Magnetic", *mag, "μT"))
                strength = math.sqrt(sum(v**2 for v in mag))
                print(f"  {'強度 (|B|)':<12}{strength:.3f} μT")
            else:
                print("  [WARNING] 磁束密度データ取得失敗")

            # 加速度（重力含む）
            print()
            print("  ── 加速度（重力含む） ────────────────────────────────")
            if acc:
                print(_vec3_str("Accel", *acc, "m/s²"))
                g = math.sqrt(sum(v**2 for v in acc))
                print(f"  {'合成加速度':<12}{g:.3f} m/s²  ※静止時 ≈ 9.8 m/s² (重力)")
            else:
                print("  [WARNING] 加速度データ取得失敗")

            # 線形加速度（重力除去済み）
            print()
            print("  ── 線形加速度（重力除去済み） ────────────────────────")
            if lia:
                print(_vec3_str("LinearAccel", *lia, "m/s²"))
                lia_mag = math.sqrt(sum(v**2 for v in lia))
                print(f"  {'動き強度':<12}{lia_mag:.3f} m/s²  ※静止時 ≈ 0 / 動くと増加")
            else:
                print("  [WARNING] 線形加速度データ取得失敗")

            # クォータニオン
            print()
            print("  ── クォータニオン ────────────────────────────────────")
            if quat:
                print(_quat_str(*quat))
                # クォータニオンからオイラー角へ変換（roll, pitch, yaw）
                qw, qx, qy, qz = quat
                roll  = math.degrees(math.atan2(
                    2*(qw*qx + qy*qz), 1 - 2*(qx**2 + qy**2)
                ))
                pitch = math.degrees(math.asin(
                    max(-1.0, min(1.0, 2*(qw*qy - qz*qx)))
                ))
                yaw   = math.degrees(math.atan2(
                    2*(qw*qz + qx*qy), 1 - 2*(qy**2 + qz**2)
                ))
                print(
                    f"  {'Euler角':<12}"
                    f"Roll: {roll:+8.2f}°  "
                    f"Pitch: {pitch:+8.2f}°  "
                    f"Yaw: {yaw:+8.2f}°"
                )
            else:
                print("  [WARNING] クォータニオンデータ取得失敗")

            print()
            print("─" * 70)
            print("  Ctrl+C で終了")

            frame += 1
            time.sleep(_UPDATE_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n  終了しました。\n")


if __name__ == "__main__":
    main()
