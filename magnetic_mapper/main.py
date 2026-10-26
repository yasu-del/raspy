#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Magnetic Field Mapper - Raspberry Pi メイン制御プログラム (main.py)

機能概要:
  - 磁気センサー(BNO055)からのデータ取得・統計計算
  - 慣性航法(PositionTracker)およびグリッド走査による位置推定
  - DataRecorderによるリアルタイムCSV記録
  - UnifiedMagneticVisualizerによる2D/3D可視化
  - センサーキャリブレーション確認・リアルタイムモニター
  - コマンドライン引数(CLI)および対話式メニュー両対応
"""

import sys
import os
import time
import math
import argparse
import random
from datetime import datetime

# モジュール検索パスに src ディレクトリを追加
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
DATA_DIR = os.path.join(BASE_DIR, "data")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from recorder import DataRecorder
from tracker import PositionTracker

# センサーモジュールのインポート判定
try:
    from sensor import BNO055Sensor
    SENSOR_AVAILABLE = True
except (ImportError, RuntimeError):
    SENSOR_AVAILABLE = False

# 可視化モジュールのインポート判定
try:
    from visualizer import UnifiedMagneticVisualizer
    VISUALIZER_AVAILABLE = True
except (ImportError, RuntimeError):
    VISUALIZER_AVAILABLE = False


# ==============================================================================
# 共通定数・サンプリング処理
# ==============================================================================
DEFAULT_SAMPLES_PER_CELL = 5
DEFAULT_SAMPLE_INTERVAL = 0.02   # 20ms
DEFAULT_STEP_INTERVAL = 0.2      # 200ms
DEFAULT_GRID_COLS = 10
DEFAULT_GRID_ROWS = 10
DEFAULT_CSV_PATH = os.path.join(DATA_DIR, "recorded_data.csv")


def compute_stats(bx_list, by_list, bz_list):
    """サンプリングリストから平均・標準偏差・最小・最大を計算して返す"""
    n = len(bx_list)
    if n == 0:
        return None

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


def sample_sensor_magnetic_stats(sensor, n=DEFAULT_SAMPLES_PER_CELL, interval=DEFAULT_SAMPLE_INTERVAL):
    """センサーから指定回数サンプリングして統計情報を取得"""
    bx_list, by_list, bz_list = [], [], []
    for _ in range(n):
        mag = sensor.read_magnetic_vector()
        if mag is not None:
            bx_list.append(mag[0])
            by_list.append(mag[1])
            bz_list.append(mag[2])
        time.sleep(interval)

    if not bx_list:
        return None

    return compute_stats(bx_list, by_list, bz_list)


def sample_mock_magnetic_stats(pos_x, pos_y, n=DEFAULT_SAMPLES_PER_CELL, interval=DEFAULT_SAMPLE_INTERVAL):
    """テスト用: 疑似磁気データとノイズを生成"""
    bx_list, by_list, bz_list = [], [], []
    for _ in range(n):
        # 空間位置に応じた緩やかな磁場変化と微小ノイズ
        bx = 25.0 + math.sin(pos_x * 0.4) * 15.0 + random.uniform(-1.0, 1.0)
        by = 15.0 + math.cos(pos_y * 0.4) * 10.0 + random.uniform(-1.0, 1.0)
        bz = -35.0 + (pos_x + pos_y) * 0.5 + random.uniform(-0.5, 0.5)
        bx_list.append(bx)
        by_list.append(by)
        bz_list.append(bz)
        time.sleep(interval)

    return compute_stats(bx_list, by_list, bz_list)


def initialize_sensor():
    """BNO055 センサーの初期化を試行し、インスタンスまたは None を返す"""
    if not SENSOR_AVAILABLE:
        return None
    try:
        sensor = BNO055Sensor()
        return sensor
    except (RuntimeError, OSError) as e:
        print(f"[警告] BNO055センサーの初期化に失敗しました: {e}")
        return None


# ==============================================================================
# サブコマンド 1: キャリブレーション確認 (calibrate)
# ==============================================================================
def run_calibration(sensor=None):
    """BNO055のキャリブレーション状況をリアルタイム表示"""
    print("\n" + "=" * 60)
    print("   BNO055 センサー・キャリブレーション確認モード")
    print("=" * 60)
    print("キャリブレーション手順:")
    print("  - 磁気 (Mag) : センサーをゆっくり8の字（∞）に動かしてください。")
    print("  - ジャイロ(Gyro): センサーを平らな場所に置いて静止させてください。")
    print("  - 加速度 (Acc) : センサーの各面（6面）を順に上に向けて静止させてください。")
    print("  ※ 各項目が 3 になればキャリブレーション完了です。")
    print("  ※ 終了するには Ctrl+C を押してください。\n")

    if sensor is None:
        sensor = initialize_sensor()

    if sensor is None:
        print("[エラー] センサー実機が検出されないため、キャリブレーションを実行できません。")
        return

    def get_status_bar(val):
        filled = "#" * val
        empty = "-" * (3 - val)
        return f"[{filled}{empty}] ({val}/3)"

    try:
        while True:
            sys_stat, gyro_stat, accel_stat, mag_stat = sensor.get_calibration_status()
            sys.stdout.write(
                f"\rSys: {get_status_bar(sys_stat)}  "
                f"Gyro: {get_status_bar(gyro_stat)}  "
                f"Accel: {get_status_bar(accel_stat)}  "
                f"Mag: {get_status_bar(mag_stat)}  "
            )
            sys.stdout.flush()

            if sys_stat == 3 and gyro_stat == 3 and accel_stat == 3 and mag_stat == 3:
                print("\n\n[成功] すべてのセンサーが完全にキャリブレーションされました！")
                break

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nキャリブレーション確認を終了しました。")


# ==============================================================================
# サブコマンド 2: リアルタイムモニター (monitor)
# ==============================================================================
def run_monitor(sensor=None, use_mock=False):
    """現在のセンサー値をリアルタイムにターミナル表示"""
    print("\n" + "=" * 60)
    print("   BNO055 リアルタイム・センサーモニター")
    print("=" * 60)
    print("終了するには Ctrl+C を押してください。\n")

    if not use_mock and sensor is None:
        sensor = initialize_sensor()
        if sensor is None:
            print("[情報] センサー実機が見つからないため、モック表示に切り替えます。")
            use_mock = True

    tracker = PositionTracker()

    try:
        while True:
            if not use_mock and sensor is not None:
                mag = sensor.read_magnetic_vector()
                acc = sensor.read_linear_acceleration()
                quat = sensor.read_quaternion()
                calib = sensor.get_calibration_status()
                pos = tracker.update_position(acc, quat)

                bx = mag[0] if mag else 0.0
                by = mag[1] if mag else 0.0
                bz = mag[2] if mag else 0.0
                b_total = math.sqrt(bx**2 + by**2 + bz**2)

                ax = acc[0] if acc else 0.0
                ay = acc[1] if acc else 0.0
                az = acc[2] if acc else 0.0

                qw = quat[0] if quat else 1.0
                qx = quat[1] if quat else 0.0
                qy = quat[2] if quat else 0.0
                qz = quat[3] if quat else 0.0

                calib_str = f"S:{calib[0]} G:{calib[1]} A:{calib[2]} M:{calib[3]}"
            else:
                bx = 20.0 + random.uniform(-1, 1)
                by = 10.0 + random.uniform(-1, 1)
                bz = -30.0 + random.uniform(-1, 1)
                b_total = math.sqrt(bx**2 + by**2 + bz**2)
                ax, ay, az = 0.0, 0.0, 0.0
                qw, qx, qy, qz = 1.0, 0.0, 0.0, 0.0
                pos = (0.0, 0.0, 0.0)
                calib_str = "MOCK"

            line = (
                f"\r[Mag] {b_total:6.1f} uT (X:{bx:5.1f}, Y:{by:5.1f}, Z:{bz:5.1f}) | "
                f"[Pos] ({pos[0]:4.1f}, {pos[1]:4.1f}, {pos[2]:4.1f})m | "
                f"[Acc] ({ax:4.1f}, {ay:4.1f}, {az:4.1f}) | "
                f"[{calib_str}]"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nモニターを終了しました。")


# ==============================================================================
# サブコマンド 3: 測定・データ記録 (record)
# ==============================================================================
def run_record(output=DEFAULT_CSV_PATH,
               tracking_mode="tracker",
               samples_per_cell=DEFAULT_SAMPLES_PER_CELL,
               sample_interval=DEFAULT_SAMPLE_INTERVAL,
               step_interval=DEFAULT_STEP_INTERVAL,
               grid_cols=DEFAULT_GRID_COLS,
               grid_rows=DEFAULT_GRID_ROWS,
               use_mock=False):
    """磁束密度と位置情報を連続サンプリングしてCSVに記録"""
    print("\n" + "=" * 60)
    print("   磁気マッピング・データ記録モード (Record)")
    print("=" * 60)

    sensor = None
    if not use_mock:
        sensor = initialize_sensor()
        if sensor is None:
            print("[警告] センサー実機が見つからないため、モックデータで記録します。")
            use_mock = True

    tracker = PositionTracker()
    recorder = DataRecorder(filename=output)

    print(f"  ・保存先ファイル   : {recorder.filename}")
    print(f"  ・トラッキング方式 : {tracking_mode}")
    print(f"  ・1点サンプリング数 : {samples_per_cell} 回")
    print(f"  ・センサー動作モード: {'モック(シミュレーション)' if use_mock else 'BNO055実機 (NDOF)'}")
    if tracking_mode == "grid":
        print(f"  ・グリッドサイズ   : {grid_cols} x {grid_rows} マス")
    print("  ・中断・終了方法   : Ctrl+C を押すと保存を完了して安全に終了します\n")

    count = 0
    cur_c, cur_r = 0, 0

    try:
        if tracking_mode == "manual":
            print("【マニュアル測定モード】")
            print("位置を固定し、Enterキーを押すたびに現在の位置で磁気を1点サンプリングします。")
            print("位置を変更する場合は 'c r' (例: '2 3') を入力して Enter を押してください。")
            print("終了する場合は 'q' を入力するか Ctrl+C を押してください。\n")

            while True:
                user_input = input(f"測定点 #{count + 1} (現在位置: x={cur_c}, y={cur_r}) [Enterで測定 / 'x y'で移動 / 'q'で終了]: ").strip()
                if user_input.lower() == 'q':
                    break
                if user_input:
                    parts = user_input.split()
                    if len(parts) >= 2:
                        try:
                            cur_c, cur_r = float(parts[0]), float(parts[1])
                        except ValueError:
                            print("入力形式エラー: 'x y' は数値で指定してください。")
                            continue

                pos = (cur_c, cur_r, 0.0)
                if not use_mock and sensor is not None:
                    stats = sample_sensor_magnetic_stats(sensor, n=samples_per_cell, interval=sample_interval)
                else:
                    stats = sample_mock_magnetic_stats(pos[0], pos[1], n=samples_per_cell, interval=sample_interval)

                if stats is None:
                    print("  [エラー] センサー読み取りに失敗しました。再試行してください。")
                    continue

                mag_avg, mag_std, mag_min, mag_max, n = stats
                recorder.record(pos, mag_avg, n_samples=n, mag_std=mag_std, mag_min=mag_min, mag_max=mag_max)
                count += 1
                b_tot = math.sqrt(sum(v**2 for v in mag_avg))
                print(f"  -> 記録完了 #{count}: Pos=({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}), |B|={b_tot:.2f} uT (±{max(mag_std):.2f})")

        else:
            # 連続自動取得ループ (tracker または grid)
            while True:
                now = time.time()

                if not use_mock and sensor is not None:
                    # センサーから加速度とクォータニオンを取得して位置推定を更新
                    acc = sensor.read_linear_acceleration()
                    quat = sensor.read_quaternion()
                    pos_tracker = tracker.update_position(acc, quat, timestamp=now)

                    if tracking_mode == "tracker":
                        pos = pos_tracker
                    else:  # grid
                        pos = (cur_c, cur_r, 0.0)

                    stats = sample_sensor_magnetic_stats(sensor, n=samples_per_cell, interval=sample_interval)
                else:
                    if tracking_mode == "tracker":
                        # モック用の微小な揺らぎ位置
                        pos = (cur_c * 0.5, cur_r * 0.5, 0.0)
                    else:
                        pos = (cur_c, cur_r, 0.0)

                    stats = sample_mock_magnetic_stats(pos[0], pos[1], n=samples_per_cell, interval=sample_interval)

                if stats is not None:
                    mag_avg, mag_std, mag_min, mag_max, n = stats
                    recorder.record(pos, mag_avg, n_samples=n, mag_std=mag_std, mag_min=mag_min, mag_max=mag_max)
                    count += 1
                    b_tot = math.sqrt(sum(v**2 for v in mag_avg))

                    sys.stdout.write(
                        f"\r[{count:4d}件] Pos:({pos[0]:5.2f}, {pos[1]:5.2f}, {pos[2]:5.2f})m | "
                        f"|B|: {b_tot:6.2f}uT (Bx:{mag_avg[0]:5.1f}, By:{mag_avg[1]:5.1f}, Bz:{mag_avg[2]:5.1f}) "
                        f"std:±{max(mag_std):4.2f} "
                    )
                    sys.stdout.flush()

                # グリッドモードの場合は次のマスへインクリメント
                if tracking_mode == "grid":
                    cur_c += 1
                    if cur_c >= grid_cols:
                        cur_c = 0
                        cur_r += 1
                        if cur_r >= grid_rows:
                            print("\n\n全グリッドマスの走査が完了しました！")
                            break

                time.sleep(step_interval)

    except KeyboardInterrupt:
        pass
    finally:
        recorder.flush()
        print("\n\n" + "-" * 60)
        print("--- 記録を停止しました ---")
        print(f"合計 {count} 件のデータを保存しました。")
        print(f"保存先: {recorder.filename}")
        print("-" * 60)


# ==============================================================================
# サブコマンド 4: 可視化 (visualize)
# ==============================================================================
def run_visualize(file_path=None):
    """磁気マッピングビジュアライザ (GUI) を起動"""
    print("\n" + "=" * 60)
    print("   磁力線マッピング・可視化 (Visualize)")
    print("=" * 60)

    # 読み込むCSVの探索
    candidates = []
    if file_path:
        candidates.append(file_path)
    candidates.extend([
        os.path.join(DATA_DIR, "recorded_data.csv"),
        os.path.join(DATA_DIR, "magnetic_data.csv"),
        os.path.join(DATA_DIR, "test_run.csv")
    ])

    target_file = None
    for cand in candidates:
        if os.path.exists(cand):
            target_file = cand
            break

    if target_file:
        print(f"読み込み対象ファイル: {target_file}")
    else:
        print("[注意] 有効なCSVデータファイルが見つかりません。起動後に画面から選択してください。")

    if not VISUALIZER_AVAILABLE:
        print("\n[エラー] 可視化モジュール (tkinter) が利用できません。")
        print("Raspberry PiのGUIデスクトップ環境で実行するか、'ssh -X' 等のX11転送をご利用ください。")
        _show_csv_cli_summary(target_file)
        return

    # DISPLAY環境変数のチェック（ヘッドレスSSH等の対策）
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        print("\n[エラー] DISPLAY環境変数が設定されていません (GUI画面がありません)。")
        print("ターミナルのみの接続ではGUIを表示できません。")
        print("・Raspberry Piデスクトップ上のターミナルから実行するか")
        print("・PCから 'ssh -X pi@raspberrypi.local' で接続するか")
        print("・VNCリモートデスクトップをご利用ください。\n")
        _show_csv_cli_summary(target_file)
        return

    try:
        app = UnifiedMagneticVisualizer(data_file=target_file if target_file else "")
        app.plot_field_lines()
    except Exception as e:
        print(f"\n[エラー] ビジュアライザ起動中に例外が発生しました: {e}")
        _show_csv_cli_summary(target_file)


def _show_csv_cli_summary(file_path):
    """GUIが使えない場合のためにコンソール上でCSV概要を表示"""
    if not file_path or not os.path.exists(file_path):
        return
    print(f"\n--- CSVデータ概要 (コンソール表示: {os.path.basename(file_path)}) ---")
    try:
        import csv
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)

        print(f"  総データ行数 : {len(rows)} 件")
        print(f"  ヘッダー構成 : {header}")
        if rows:
            print("  直近のデータ例 (末尾3件):")
            for r in rows[-3:]:
                print(f"    {r}")
    except Exception as err:
        print(f"CSV読み込みエラー: {err}")


# ==============================================================================
# 対話式メニュー (CLI引数なしで実行された場合)
# ==============================================================================
def run_interactive_menu():
    """対話式テキストメニュー"""
    while True:
        print("\n" + "=" * 60)
        print("   Raspberry Pi 磁力線マッピングシステム (Magnetic Field Mapper)")
        print("=" * 60)
        print("  1. 磁気測定・データ記録 (Record)")
        print("  2. 磁気マップ可視化 (Visualize)")
        print("  3. センサーキャリブレーション確認 (Calibrate)")
        print("  4. リアルタイム・センサーモニター (Monitor)")
        print("  5. 終了 (Exit)")
        print("-" * 60)
        choice = input("操作番号を入力してください [1-5]: ").strip()

        if choice == "1":
            print("\nトラッキング方式を選択してください:")
            print("  a. 慣性航法 (PositionTracker デッドレコニング) [推奨]")
            print("  b. グリッド走査 (Grid Walk)")
            print("  c. マニュアル測定 (Enterキーで1点ずつ)")
            t_choice = input("選択 [a/b/c] (デフォルト: a): ").strip().lower()
            mode_map = {"a": "tracker", "b": "grid", "c": "manual"}
            t_mode = mode_map.get(t_choice, "tracker")

            run_record(tracking_mode=t_mode)
        elif choice == "2":
            custom_path = input(f"読み込むCSVパス (空欄でデフォルト '{DEFAULT_CSV_PATH}'): ").strip()
            run_visualize(custom_path if custom_path else None)
        elif choice == "3":
            run_calibration()
        elif choice == "4":
            run_monitor()
        elif choice in ("5", "q", "exit"):
            print("プログラムを終了します。お疲れ様でした！")
            break
        else:
            print("[警告] 1〜5 の番号を入力してください。")


# ==============================================================================
# メイン・エントリーポイント (引数解析)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Raspberry Pi 磁力線マッピングシステム (Magnetic Field Mapper)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python main.py                           # 対話メニュー起動
  python main.py --mode record             # データ記録開始 (慣性航法)
  python main.py record -t grid -s 5       # グリッドモードで記録
  python main.py record -t manual          # Enterキーで1点ずつマニュアル測定
  python main.py --mode visualize          # 可視化GUIを起動
  python main.py visualize -f data/test_run.csv # 指定CSVの可視化
  python main.py calibrate                 # キャリブレーション支援画面
  python main.py monitor                   # リアルタイムセンサーモニター
        """
    )

    # 従来の --mode オプション（READMEとの完全互換用）
    parser.add_argument(
        "--mode",
        choices=["record", "visualize", "calibrate", "monitor"],
        help="実行モード (record / visualize / calibrate / monitor)"
    )

    # サブコマンド対応 (record / visualize / calibrate / monitor)
    subparsers = parser.add_subparsers(dest="subcommand", help="サブコマンド")

    # record サブコマンド
    p_record = subparsers.add_parser("record", help="磁気データ測定・記録")
    p_record.add_argument("-o", "--output", default=DEFAULT_CSV_PATH, help=f"出力CSVファイルパス (デフォルト: {DEFAULT_CSV_PATH})")
    p_record.add_argument("-t", "--tracking", choices=["tracker", "grid", "manual"], default="tracker", help="位置トラッキング方式")
    p_record.add_argument("-s", "--samples", type=int, default=DEFAULT_SAMPLES_PER_CELL, help="1マス/測定点あたりのサンプル数")
    p_record.add_argument("-i", "--interval", type=float, default=DEFAULT_STEP_INTERVAL, help="測定ループ周期 [秒]")
    p_record.add_argument("--cols", type=int, default=DEFAULT_GRID_COLS, help="グリッド走査時の横マス数")
    p_record.add_argument("--rows", type=int, default=DEFAULT_GRID_ROWS, help="グリッド走査時の縦マス数")
    p_record.add_argument("--mock", action="store_true", help="センサー実機を使わずモックで実行")

    # visualize サブコマンド
    p_vis = subparsers.add_parser("visualize", help="磁力線・マップ可視化GUI")
    p_vis.add_argument("-f", "--file", default=None, help="読み込むCSVファイルパス")

    # calibrate サブコマンド
    subparsers.add_parser("calibrate", help="BNO055 キャリブレーション支援")

    # monitor サブコマンド
    p_mon = subparsers.add_parser("monitor", help="リアルタイムセンサー値モニター")
    p_mon.add_argument("--mock", action="store_true", help="モック値で表示")

    args = parser.parse_args()

    # --mode と サブコマンド の統合判定
    mode = args.subcommand or args.mode

    if mode == "record":
        output = getattr(args, "output", DEFAULT_CSV_PATH)
        tracking = getattr(args, "tracking", "tracker")
        samples = getattr(args, "samples", DEFAULT_SAMPLES_PER_CELL)
        interval = getattr(args, "interval", DEFAULT_STEP_INTERVAL)
        cols = getattr(args, "cols", DEFAULT_GRID_COLS)
        rows = getattr(args, "rows", DEFAULT_GRID_ROWS)
        mock = getattr(args, "mock", False)
        run_record(
            output=output,
            tracking_mode=tracking,
            samples_per_cell=samples,
            step_interval=interval,
            grid_cols=cols,
            grid_rows=rows,
            use_mock=mock
        )
    elif mode == "visualize":
        file_path = getattr(args, "file", None)
        run_visualize(file_path=file_path)
    elif mode == "calibrate":
        run_calibration()
    elif mode == "monitor":
        mock = getattr(args, "mock", False)
        run_monitor(use_mock=mock)
    else:
        # 引数なしの場合は対話式メニューを起動
        run_interactive_menu()


if __name__ == "__main__":
    main()

