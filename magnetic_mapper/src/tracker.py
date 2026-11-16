# -*- coding: utf-8 -*-
"""
tracker.py - 慣性航法（デッドレコニング）による位置推定モジュール

改善点 (2026年改修):
  - 積分アルゴリズムを単純オイラー法から「台形積分 (Trapezoidal Rule)」に変更し、数値誤差を低減。
  - 静止判定（ZUPT: Zero Velocity Update）の強化とダンピング処理によるドリフト抑制。
  - メインループの遅れによる位置誤差を解消するため、高速バックグラウンド追跡を行う
    BackgroundPositionTracker クラスを追加（50Hz〜100Hzで独立サンプリング）。
"""

import time
import threading


class PositionTracker:
    """加速度とクォータニオンから、世界座標系での位置を推定するクラス。

    処理の流れ:
        1. センサー座標系の線形加速度をクォータニオンで世界座標系に回転変換する
        2. 台形積分により加速度から速度を求める
        3. 台形積分により速度から位置を求める
    """

    def __init__(self, zero_velocity_threshold=0.06, damping_factor=0.98):
        """
        Args:
            zero_velocity_threshold (float): 静止判定閾値 [m/s^2]。
            damping_factor (float): 速度ダンピング係数 (0.95〜1.0)。微小ドリフトの減衰用。
        """
        # 現在の推定位置 [m]
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

        # 現在の推定速度 [m/s]
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._vel_z = 0.0

        # 直前の世界座標系加速度 [m/s^2] (台形積分用)
        self._prev_world_acc = None

        # 前回の update_position() 呼び出し時刻
        self._last_time = None

<<<<<<< Updated upstream
        # 静止判定の閾値 [m/s^2]
        # 加速度のノルム（大きさ）がこの値以下のとき、センサーは静止していると見なし
        # 速度を 0 にリセットする（ドリフト誤差の蓄積を軽減するため）
        self.zero_velocity_threshold = 0.12
=======
        # 静止判定閾値とダンピング
        self.zero_velocity_threshold = zero_velocity_threshold
        self.damping_factor = damping_factor
        self._still_frames = 0
>>>>>>> Stashed changes

    def update_position(self, accel, quaternion, timestamp=None):
        """加速度とクォータニオンから位置を更新し、現在の推定座標を返す。

        Args:
            accel: (ax, ay, az) [m/s^2]
            quaternion: (w, x, y, z)
            timestamp: time.time() の値 (Noneの場合はメソッド内で取得)

        Returns:
            tuple[float, float, float]: 世界座標系での推定位置 (x, y, z) [m]
        """
        if accel is None or quaternion is None:
            return self.pos_x, self.pos_y, self.pos_z

        now = timestamp if timestamp is not None else time.time()
        if self._last_time is None:
            self._last_time = now
            self._prev_world_acc = self._rotate_vector_by_quaternion(accel, quaternion)
            return self.pos_x, self.pos_y, self.pos_z

        dt = now - self._last_time
        self._last_time = now

        # dtが異常値の場合はスキップ（再開時など）
        if dt <= 0.0 or dt > 0.5:
            self._prev_world_acc = self._rotate_vector_by_quaternion(accel, quaternion)
            return self.pos_x, self.pos_y, self.pos_z

        # ステップ1: センサー座標系加速度を世界座標系に変換
        world_accel = self._rotate_vector_by_quaternion(accel, quaternion)
        accel_norm = (world_accel[0]**2 + world_accel[1]**2 + world_accel[2]**2) ** 0.5

        if self._prev_world_acc is None:
            self._prev_world_acc = world_accel

        # ステップ2: 静止判定 (ZUPT: Zero-Velocity Update)
        if accel_norm < self.zero_velocity_threshold:
            self._still_frames += 1
            # 連続して静止している場合は速度を強制ゼロにしてドリフトを遮断
            if self._still_frames >= 2:
                self._vel_x = 0.0
                self._vel_y = 0.0
                self._vel_z = 0.0
                self._prev_world_acc = world_accel
                return self.pos_x, self.pos_y, self.pos_z
        else:
            self._still_frames = 0

        # ステップ3: 加速度を台形積分して速度を更新
        # v = v_prev + (a_prev + a_curr) / 2 * dt
        dv_x = (self._prev_world_acc[0] + world_accel[0]) * 0.5 * dt
        dv_y = (self._prev_world_acc[1] + world_accel[1]) * 0.5 * dt
        dv_z = (self._prev_world_acc[2] + world_accel[2]) * 0.5 * dt

<<<<<<< Updated upstream
        # ★★★ ここに2行追加！速度の減衰（摩擦）を入れる ★★★
        DAMPING = 0.90  # 毎フレーム10%ずつ速度をブレーキする
        self._vel_x *= DAMPING
        self._vel_y *= DAMPING
        self._vel_z *= DAMPING

        # ステップ4: 速度を積分して位置を更新する
        self.pos_x += self._vel_x * dt
        self.pos_y += self._vel_y * dt
        self.pos_z += self._vel_z * dt
=======
        prev_vx = self._vel_x
        prev_vy = self._vel_y
        prev_vz = self._vel_z
>>>>>>> Stashed changes

        self._vel_x = (self._vel_x + dv_x) * self.damping_factor
        self._vel_y = (self._vel_y + dv_y) * self.damping_factor
        self._vel_z = (self._vel_z + dv_z) * self.damping_factor

        # ステップ4: 速度を台形積分して位置を更新
        # pos = pos_prev + (v_prev + v_curr) / 2 * dt
        self.pos_x += (prev_vx + self._vel_x) * 0.5 * dt
        self.pos_y += (prev_vy + self._vel_y) * 0.5 * dt
        self.pos_z += (prev_vz + self._vel_z) * 0.5 * dt

        self._prev_world_acc = world_accel
        return self.pos_x, self.pos_y, self.pos_z

    def reset(self, x=0.0, y=0.0, z=0.0):
        """推定位置を既知の座標にリセットし、速度・履歴を初期化"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._vel_z = 0.0
        self._prev_world_acc = None
        self._last_time = None
        self._still_frames = 0

    def get_position(self):
        """現在の推定位置を返す"""
        return self.pos_x, self.pos_y, self.pos_z

    @staticmethod
    def _rotate_vector_by_quaternion(vector, quaternion):
        """クォータニオンを使って3Dベクトルを世界座標系に回転変換"""
        vx, vy, vz = vector
        w, x, y, z = quaternion

        rx = vx * (1 - 2*(y*y + z*z)) + vy * 2*(x*y - w*z) + vz * 2*(x*z + w*y)
        ry = vx * 2*(x*y + w*z) + vy * (1 - 2*(x*x + z*z)) + vz * 2*(y*z - w*x)
        rz = vx * 2*(x*z - w*y) + vy * 2*(y*z + w*x) + vz * (1 - 2*(x*x + y*y))

        return rx, ry, rz


class BackgroundPositionTracker:
    """高精度化のためのバックグラウンド・スレッド式ポジショントラッカー。
    
    メインスレッドが磁気測定（数百ms）を行っている間も、
    独立したスレッドで 50Hz (20ms) 以上の高周波サンプリングで
    加速度・クォータニオンを連続積分し、位置ドリフトを劇的に低減します。
    """

    def __init__(self, sensor, sample_rate_hz=50):
        self.sensor = sensor
        self.interval = 1.0 / sample_rate_hz
        self.tracker = PositionTracker()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        """バックグラウンド更新を開始"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """バックグラウンド更新を停止"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _update_loop(self):
        while self._running:
            start_t = time.time()
            try:
                acc = self.sensor.read_linear_acceleration()
                quat = self.sensor.read_quaternion()
                with self._lock:
                    self.tracker.update_position(acc, quat, timestamp=start_t)
            except Exception:
                pass

            elapsed = time.time() - start_t
            sleep_t = max(0.001, self.interval - elapsed)
            time.sleep(sleep_t)

    def get_position(self):
        """現在の高精度推定位置を取得"""
        with self._lock:
            return self.tracker.get_position()

    def reset(self, x=0.0, y=0.0, z=0.0):
        with self._lock:
            self.tracker.reset(x, y, z)
