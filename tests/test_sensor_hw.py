# -*- coding: utf-8 -*-
"""
test_sensor_hw.py - BNO055 実機動作確認 & データ取得スクリプト（ラズパイ上で実行）

方針: 精度より「データが取れること」を優先。
      1つの値の読み取りに失敗しても止めずに空欄として記録する。

使い方（リポジトリのルートで実行）:
    python3 tests/test_sensor_hw.py          # 段階1 → 段階2 を続けて実行
    python3 tests/test_sensor_hw.py raw      # 段階1 のみ（生ログ）
    python3 tests/test_sensor_hw.py grid     # 段階2 のみ（マス目測定）
    python3 tests/test_sensor_hw.py raw 30   # 生ログを 30 秒取る

出力（magnetic_mapper/data/ に保存）:
    raw_log.csv        : 全値の時系列ログ（tracker 担当の確認用）
    magnetic_data.csv  : visualizer.py がそのまま読める形式
                         (row, col, bx, by, bz, b_total)
"""
import csv
import math
import os
import sys
import time

# magnetic_mapper/src をパスに追加
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "magnetic_mapper", "src"))
DATA_DIR = os.path.join(ROOT, "magnetic_mapper", "data")

from sensor import BNO055Sensor  # noqa: E402


def safe_call(func, size):
    """センサー関数を呼び、失敗・None なら空欄のリストを返す（止めないため）。"""
    try:
        v = func()
    except Exception as e:  # 想定外のエラーも記録だけして続行
        print(f"  [warn] {func.__name__}: {e}")
        v = None
    return list(v) if v is not None else [""] * size


def fmt(vals):
    return ", ".join(f"{v:7.2f}" if isinstance(v, float) else "   ----" for v in vals)


# ── 段階1: 生ログ ───────────────────────────────────────────
def stage_raw(sensor, seconds=10.0, interval=0.05):
    path = os.path.join(DATA_DIR, "raw_log.csv")
    print(f"\n=== 段階1: 生ログ {seconds:.0f} 秒（センサーを8の字に振るとキャリブが進みます）===")
    counts = {"mag": 0, "acc": 0, "quat": 0, "total": 0}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag_x", "mag_y", "mag_z", "ax", "ay", "az",
                    "qw", "qx", "qy", "qz",
                    "cal_sys", "cal_gyr", "cal_acc", "cal_mag"])
        t0 = time.time()
        while time.time() - t0 < seconds:
            t = round(time.time() - t0, 3)
            m = safe_call(sensor.read_magnetic_vector, 3)
            a = safe_call(sensor.read_linear_acceleration, 3)
            q = safe_call(sensor.read_quaternion, 4)
            c = safe_call(sensor.get_calibration_status, 4)
            w.writerow([t] + m + a + q + c)

            counts["total"] += 1
            counts["mag"] += m[0] != ""
            counts["acc"] += a[0] != ""
            counts["quat"] += q[0] != ""
            print(f"t={t:6.2f} | mag[{fmt(m)}] | acc[{fmt(a)}] | cal(s,g,a,m)={c}")
            time.sleep(interval)

    n = counts["total"] or 1
    print("\n--- 段階1 結果 ---")
    print(f"  保存先      : {path}")
    print(f"  サンプル数  : {counts['total']}")
    print(f"  磁気 取得率 : {counts['mag'] / n:6.1%}")
    print(f"  加速度 取得率: {counts['acc'] / n:6.1%}  (0% なら cal_sys=0 で None の可能性)")
    print(f"  姿勢 取得率 : {counts['quat'] / n:6.1%}")


# ── 段階2: マス目測定（visualizer 形式）───────────────────────
def stage_grid(sensor, samples=20, interval=0.05):
    path = os.path.join(DATA_DIR, "magnetic_data.csv")
    print("\n=== 段階2: マス目測定 ===")
    print("センサーをマスに置いて '行 列' を入力して Enter（例: 0 0）")
    print("同じマスを入力し直すと上書き。終了は q")

    results = {}
    if os.path.exists(path):
        ans = input(f"既存の {os.path.basename(path)} に追記しますか？ [y/N] > ").strip().lower()
        if ans == "y":
            with open(path, newline="", encoding="utf-8") as f:
                r = csv.reader(f)
                next(r, None)
                for row in r:
                    if len(row) >= 6:
                        results[(int(row[0]), int(row[1]))] = row[2:6]

    def save():
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["row", "col", "bx", "by", "bz", "b_total"])
            for (r, c) in sorted(results):
                w.writerow([r, c] + list(results[(r, c)]))

    while True:
        txt = input("行 列 > ").strip()
        if txt.lower() == "q":
            break
        try:
            r, c = map(int, txt.split())
        except ValueError:
            print("  入力例: 0 0")
            continue

        got = []
        for _ in range(samples):
            try:
                v = sensor.read_magnetic_vector()
            except Exception:
                v = None
            if v is not None:
                got.append(v)
            time.sleep(interval)

        if not got:
            print("  読み取り失敗（配線・I2C を確認）。もう一度入力してください。")
            continue

        bx, by, bz = (sum(s[i] for s in got) / len(got) for i in range(3))
        bt = math.sqrt(bx * bx + by * by + bz * bz)
        results[(r, c)] = [round(bx, 2), round(by, 2), round(bz, 2), round(bt, 2)]
        save()  # 1マスごとに保存（途中で落ちてもデータが残る）
        print(f"  ({r},{c}) B={bt:6.1f} uT  [{bx:6.1f}, {by:6.1f}, {bz:6.1f}]  "
              f"({len(got)}/{samples} サンプル) 計 {len(results)} マス")

    print(f"\n--- 段階2 結果 ---\n  保存先: {path}\n  測定マス数: {len(results)}")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "all"
    seconds = float(args[1]) if len(args) > 1 else 10.0

    os.makedirs(DATA_DIR, exist_ok=True)

    print("BNO055 初期化中...（モード切替で約2秒待ちます）")
    try:
        sensor = BNO055Sensor()
    except Exception as e:
        print(f"[ERROR] 初期化失敗: {e}")
        print("  確認: `i2cdetect -y 1` で 28 が表示されるか / 配線 / I2C 有効化")
        sys.exit(1)
    print("初期化成功")

    try:
        if mode in ("all", "raw"):
            stage_raw(sensor, seconds)
        if mode in ("all", "grid"):
            stage_grid(sensor)
    except KeyboardInterrupt:
        print("\n中断しました（ここまでのデータは保存済み）")


if __name__ == "__main__":
    main()
