# -*- coding: utf-8 -*-
"""
tracker.py - 慣性航法（デッドレコニング）による位置推定モジュール

担当: 位置計算（加速度とクォータニオンから空間座標を推定）
入力: sensor.py の read_linear_acceleration() と read_quaternion() の戻り値
出力: 世界座標系における推定位置 (x, y, z) [m]

このモジュールは sensor.py を直接インポートしません（疎結合設計）。
main.py がセンサーから取得したデータを、このモジュールのメソッドに渡す構成です。
"""

import time


class PositionTracker:
    """加速度とクォータニオンから、世界座標系での位置を推定するクラス。

    処理の流れ:
        1. センサー座標系の線形加速度をクォータニオンで世界座標系に変換する
        2. 世界座標系の加速度を時間で積分して速度を求める
        3. 速度を時間で積分して位置を求める

    注意:
        慣性航法はドリフト誤差（時間とともに位置がズレる現象）が大きいため、
        長時間の連続測定には向きません。定期的に既知の位置でリセットすることを推奨します。
    """

    def __init__(self):
        """位置・速度・時刻を初期状態（原点・静止）にリセットする。"""
        # 現在の推定位置 [m]
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

        # 現在の推定速度 [m/s]
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._vel_z = 0.0

        # 前回の update_position() が呼ばれた時刻（UNIX秒）
        self._last_time = None

        # 静止判定の閾値 [m/s^2]
        # 加速度のノルム（大きさ）がこの値以下のとき、センサーは静止していると見なし
        # 速度を 0 にリセットする（ドリフト誤差の蓄積を軽減するため）
        self.zero_velocity_threshold = 0.05

    def update_position(self, accel, quaternion, timestamp=None):
        """加速度とクォータニオンから位置を更新し、現在の推定座標を返す。

        Args:
            accel (tuple[float, float, float] | None):
                センサー座標系の線形加速度 (ax, ay, az) [m/s^2]。
                sensor.read_linear_acceleration() の戻り値をそのまま渡す。
                None の場合は位置を更新せず、現在の位置をそのまま返す。
            quaternion (tuple[float, float, float, float] | None):
                センサーの姿勢を表すクォータニオン (w, x, y, z)。
                sensor.read_quaternion() の戻り値をそのまま渡す。
                None の場合は位置を更新せず、現在の位置をそのまま返す。
            timestamp (float | None):
                センサーデータを取得した時刻（time.time() の値）。
                指定することで、センサー読み出しと位置計算の間のタイムラグを解消できる。
                None の場合はメソッド内部で time.time() を取得する（後方互換）。

        Returns:
            tuple[float, float, float]: 世界座標系での推定位置 (x, y, z) [m]。
        """
        # センサーデータが取得できなかった場合は位置を更新しない
        if accel is None or quaternion is None:
            return self.pos_x, self.pos_y, self.pos_z

        # 経過時間（Δt）を計算する
        # timestamp が渡されていればそれを使用し、なければ現在時刻を取得する
        now = timestamp if timestamp is not None else time.time()
        if self._last_time is None:
            # 初回呼び出し時は Δt を計算できないため、時刻だけ記録して終わる
            self._last_time = now
            return self.pos_x, self.pos_y, self.pos_z

        dt = now - self._last_time
        self._last_time = now

        # Δt が異常に大きい場合（長時間停止後の再開など）はスキップする
        if dt <= 0.0 or dt > 1.0:
            return self.pos_x, self.pos_y, self.pos_z

        # ステップ1: センサー座標系の加速度を、世界座標系に回転変換する
        world_accel = self._rotate_vector_by_quaternion(accel, quaternion)

        # ステップ2: 静止判定 — 加速度のノルムが閾値以下なら速度をゼロにリセット
        accel_norm = (world_accel[0]**2 + world_accel[1]**2 + world_accel[2]**2) ** 0.5
        if accel_norm < self.zero_velocity_threshold:
            self._vel_x = 0.0
            self._vel_y = 0.0
            self._vel_z = 0.0
            return self.pos_x, self.pos_y, self.pos_z

        # ステップ3: 加速度を積分して速度を更新する（台形近似）
        self._vel_x += world_accel[0] * dt
        self._vel_y += world_accel[1] * dt
        self._vel_z += world_accel[2] * dt

        # ステップ4: 速度を積分して位置を更新する
        self.pos_x += self._vel_x * dt
        self.pos_y += self._vel_y * dt
        self.pos_z += self._vel_z * dt

        return self.pos_x, self.pos_y, self.pos_z

    def reset(self, x=0.0, y=0.0, z=0.0):
        """推定位置を既知の座標にリセットし、速度をゼロにする。

        測定中にドリフト誤差が蓄積した場合や、既知の位置にセンサーを置いた際に
        手動でリセットするために使用する。

        Args:
            x (float): リセット先の X 座標 [m]。デフォルトは 0.0。
            y (float): リセット先の Y 座標 [m]。デフォルトは 0.0。
            z (float): リセット先の Z 座標 [m]。デフォルトは 0.0。
        """
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._vel_z = 0.0
        self._last_time = None

    def get_position(self):
        """現在の推定位置を返す（位置の更新は行わない）。

        Returns:
            tuple[float, float, float]: 現在の推定位置 (x, y, z) [m]。
        """
        return self.pos_x, self.pos_y, self.pos_z

    @staticmethod
    def _rotate_vector_by_quaternion(vector, quaternion):
        """クォータニオンを使って3Dベクトルを回転させる。

        センサー座標系のベクトルを、世界座標系のベクトルに変換する。
        回転の計算式: v' = q * v * q^(-1)
        ここでは効率のためにクォータニオンの積を展開した直接計算を行う。

        Args:
            vector (tuple[float, float, float]):
                回転させたい3Dベクトル (vx, vy, vz)。
            quaternion (tuple[float, float, float, float]):
                回転を表すクォータニオン (w, x, y, z)。

        Returns:
            tuple[float, float, float]: 回転後のベクトル (vx', vy', vz')。
        """
        vx, vy, vz = vector
        w, x, y, z = quaternion

        # クォータニオンによる回転行列の各成分を展開して直接計算する
        # 参考: https://en.wikipedia.org/wiki/Quaternions_and_spatial_rotation
        rx = vx * (1 - 2*(y*y + z*z)) + vy * 2*(x*y - w*z) + vz * 2*(x*z + w*y)
        ry = vx * 2*(x*y + w*z) + vy * (1 - 2*(x*x + z*z)) + vz * 2*(y*z - w*x)
        rz = vx * 2*(x*z - w*y) + vy * 2*(y*z + w*x) + vz * (1 - 2*(x*x + y*y))

        return rx, ry, rz
