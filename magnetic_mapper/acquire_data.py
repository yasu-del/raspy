import sys
import os
import time
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
from recorder import DataRecorder

try:
    from sensor import BNO055Sensor
    SENSOR_AVAILABLE = True
except ImportError:
    SENSOR_AVAILABLE = False
    import random
    print("[警告] センサーモジュールが読み込めません。モックデータを使用して記録を続行します。")

# =====================================================
# 取得設定 - ここを変えると密度・精度を調整できます
# =====================================================

# 1マスあたり何回センサーを読んで平均を取るか（多いほど安定・高精度）
SAMPLES_PER_CELL = 5

# 複数サンプリング時の1回あたりの読み取り間隔 [秒]
SAMPLE_INTERVAL = 0.02  # 20ms

# 歩行時の次のマスへ移動する間隔 [秒]（人が歩くペース）
STEP_INTERVAL = 0.2

# グリッドの最大サイズ（部屋の広さに合わせて調整）
GRID_COLS = 30  # 横方向のマス数
GRID_ROWS = 30  # 縦方向のマス数

# =====================================================


def _compute_stats(bx_list, by_list, bz_list):
    """各軸のリストから平均・標準偏差・最小・最大を計算して返す。

    Returns:
        tuple: (mag_avg, mag_std, mag_min, mag_max, n)
            mag_avg : (bx_mean, by_mean, bz_mean)
            mag_std : (bx_std, by_std, bz_std)
            mag_min : (bx_min, by_min, bz_min)
            mag_max : (bx_max, by_max, bz_max)
            n       : サンプル数
    """
    n = len(bx_list)

    def mean(lst):
        return sum(lst) / n

    def std(lst, m):
        if n < 2:
            return 0.0
        return math.sqrt(sum((v - m) ** 2 for v in lst) / (n - 1))

    bx_m, by_m, bz_m = mean(bx_list), mean(by_list), mean(bz_list)

    return (
        (bx_m, by_m, bz_m),
        (std(bx_list, bx_m), std(by_list, by_m), std(bz_list, bz_m)),
        (min(bx_list), min(by_list), min(bz_list)),
        (max(bx_list), max(by_list), max(bz_list)),
        n
    )


def sample_magnetic_stats(sensor, n=SAMPLES_PER_CELL):
    """指定回数センサーを読み取り、平均・標準偏差・min/max・サンプル数を返す（ノイズ除去）。

    Returns:
        tuple | None: (_compute_stats の返り値) または None（全サンプル失敗時）
    """
    bx_list, by_list, bz_list = [], [], []
    for _ in range(n):
        mag = sensor.read_magnetic_vector()
        if mag is not None:
            bx_list.append(mag[0])
            by_list.append(mag[1])
            bz_list.append(mag[2])
        time.sleep(SAMPLE_INTERVAL)

    if not bx_list:
        return None

    return _compute_stats(bx_list, by_list, bz_list)


def mock_sample_stats(mock_c, mock_r, n=SAMPLES_PER_CELL):
    """モック用: 複数サンプリングしてノイズ入りの統計情報を生成"""
    bx_list, by_list, bz_list = [], [], []
    for _ in range(n):
        bx_list.append(10 + mock_c * 3 + random.uniform(-2, 2))
        by_list.append(20 + mock_r * 2 + random.uniform(-2, 2))
        bz_list.append(5 + random.uniform(-0.5, 0.5))
        time.sleep(SAMPLE_INTERVAL)
    return _compute_stats(bx_list, by_list, bz_list)


def acquire_data_loop():
    global SENSOR_AVAILABLE
    print("--- データの継続取得・記録を開始します ---")
    print(f"  ・1マスあたり {SAMPLES_PER_CELL} 回サンプリングして平均値・統計情報を記録")
    print(f"  ・グリッドサイズ: {GRID_COLS} x {GRID_ROWS} マス")
    print("  ・停止する場合は Ctrl+C を押してください")

    recorder = DataRecorder()
    print(f"保存先: {recorder.filename}\n")

    if SENSOR_AVAILABLE:
        try:
            sensor = BNO055Sensor()
            print("BNO055 センサーからのデータ取得を開始します...")
        except RuntimeError as e:
            print(f"センサーの初期化に失敗しました: {e}")
            SENSOR_AVAILABLE = False

    mock_r, mock_c = 0, 0
    count = 0

    try:
        while True:
            if SENSOR_AVAILABLE:
                # 複数回サンプリングして統計情報を取得
                stats = sample_magnetic_stats(sensor)
                pos = (0, 0, 0)  # 実際にはトラッカーから位置を取得

                if stats is not None:
                    mag_avg, mag_std, mag_min, mag_max, n = stats
                    recorder.record(pos, mag_avg,
                                    n_samples=n,
                                    mag_std=mag_std,
                                    mag_min=mag_min,
                                    mag_max=mag_max)
                    count += 1
                    print(
                        f"[{count}件] 記録 bx={mag_avg[0]:.2f}±{mag_std[0]:.2f}, "
                        f"by={mag_avg[1]:.2f}±{mag_std[1]:.2f}, "
                        f"bz={mag_avg[2]:.2f}±{mag_std[2]:.2f} "
                        f"(n={n})"
                    )
            else:
                # モック: 複数サンプリング統計
                stats = mock_sample_stats(mock_c, mock_r)
                mag_avg, mag_std, mag_min, mag_max, n = stats
                pos = (mock_c, mock_r, 0)

                recorder.record(pos, mag_avg,
                                n_samples=n,
                                mag_std=mag_std,
                                mag_min=mag_min,
                                mag_max=mag_max)
                count += 1

                if count % 10 == 0:
                    print(
                        f"[{count}件] モック記録 (位置: r={mock_r}, c={mock_c}) "
                        f"bx={mag_avg[0]:.2f}±{mag_std[0]:.2f}, "
                        f"by={mag_avg[1]:.2f}±{mag_std[1]:.2f}, "
                        f"bz={mag_avg[2]:.2f}±{mag_std[2]:.2f} "
                        f"(n={n})"
                    )

                # 次のマスへ（ジグザグ走査）
                mock_c += 1
                if mock_c >= GRID_COLS:
                    mock_c = 0
                    mock_r += 1
                    if mock_r >= GRID_ROWS:
                        print("\n全マスの記録が完了しました！")
                        break

            time.sleep(STEP_INTERVAL)

    except KeyboardInterrupt:
        recorder.flush()
        print("\n--- 記録を停止しました ---")
        print(f"合計 {count} 件のデータを保存しました。")

if __name__ == "__main__":
    acquire_data_loop()

