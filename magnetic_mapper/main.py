#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Magnetic Field Mapper - Raspberry Pi メイン制御プログラム (main.py)

機能概要:
  - 磁気センサー(BNO055)からの高精度データ取得・外れ値除去統計計算
  - 慣性航法(PositionTracker/BackgroundPositionTracker)およびグリッド走査による位置推定
  - DataRecorderによるリアルタイムCSV記録
  - UnifiedMagneticVisualizerによる2D/3D可視化
  - センサーキャリブレーション確認・保存/復元・リアルタイムモニター
  - 環境磁界ゼロ点補正（Tare）機能

誤差低減対策 (2026年改修):
  1. サンプリング間隔の適正化 (20Hz ODR同期・重複読み取り防止)
  2. 外れ値除去 (トリム平均 / 最大最小カット) によるスパイクノイズ低減
  3. バックグラウンド高速トラッキングスレッド (50Hz) による積分の数値誤差・ドリフト劇的低減
  4. 動作モード NDOF_FMC_OFF 対応 (磁石接近による自動キャリブレーション誤作動防止)
  5. 地磁気・環境磁気ゼロ点相殺 (Tare) 機能
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
from tracker import PositionTracker, BackgroundPositionTracker

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
# BNO055の地磁気センサーODR (20Hz = 50ms) に合わせたサンプリング間隔
DEFAULT_SAMPLES_PER_CELL = 7     # 外れ値除去(トリム平均)を行うため7サンプル推奨
DEFAULT_SAMPLE_INTERVAL = 0.05   # 50ms (20Hz更新周期に同期)
DEFAULT_STEP_INTERVAL = 0.2      # 200ms
DEFAULT_GRID_COLS = 10
DEFAULT_GRID_ROWS = 10
DEFAULT_CSV_PATH = os.path.join(DATA_DIR, "recorded_data.csv")
CALIBRATION_PROFILE_PATH = os.path.join(DATA_DIR, "bno055_calib_profile.json")

# グローバルなゼロ点オフセット (Tare)
GLOBAL_TARE_OFFSET = [0.0, 0.0, 0.0]


def compute_stats(bx_list, by_list, bz_list, use_trimmed=True):
    """サンプリングリストから外れ値を除去した統計値（平均・標準偏差・最小・最大）を計算"""
    n = len(bx_list)
    if n == 0:
        return None

    def calc_component(lst):
        n_elem = len(lst)
        if n_elem == 0:
            return 0.0, 0.0
        if not use_trimmed or n_elem < 4:
            # サンプル数が少ない場合は通常の相加平均
            m = sum(lst) / n_elem
            std = math.sqrt(sum((v - m) ** 2 for v in lst) / max(1, n_elem - 1)) if n_elem > 1 else 0.0
            return m, std
        
        # トリム平均: 最大値と最小値を1つずつ除外してスパイクノイズを除去
        sorted_lst = sorted(lst)
        trimmed = sorted_lst[1:-1]
        n_t = len(trimmed)
        m = sum(trimmed) / n_t
        std = math.sqrt(sum((v - m) ** 2 for v in trimmed) / max(1, n_t - 1))
        return m, std

    bx_m, bx_std = calc_component(bx_list)
    by_m, by_std = calc_component(by_list)
    bz_m, bz_std = calc_component(bz_list)

    return (
        (bx_m, by_m, bz_m),
        (bx_std, by_std, bz_std),
        (min(bx_list), min(by_list), min(bz_list)),
        (max(bx_list), max(by_list), max(bz_list)),
        n
    )


def sample_sensor_magnetic_stats(sensor, n=DEFAULT_SAMPLES_PER_CELL,
                                interval=DEFAULT_SAMPLE_INTERVAL,
                                tare_offset=(0.0, 0.0, 0.0)):
    """センサーから指定回数サンプリングして統計情報を取得（重複防止・外れ値除去）"""
    bx_list, by_list, bz_list = [], [], []
    last_raw = None

    for _ in range(n):
        # センサーレジスタ更新を待つ重複防止ループ
        for retry in range(3):
            mag = sensor.read_magnetic_vector()
            current_raw = sensor.get_last_mag_raw() if hasattr(sensor, "get_last_mag_raw") else None

            if mag is not None:
                # 生データが更新されたか、あるいはリトライ最終回なら採用
                if last_raw is None or current_raw != last_raw or retry == 2:
                    last_raw = current_raw
                    bx_list.append(mag[0] - tare_offset[0])
                    by_list.append(mag[1] - tare_offset[1])
                    bz_list.append(mag[2] - tare_offset[2])
                    break
            time.sleep(0.015)

        time.sleep(interval)

    if not bx_list:
        return None

    return compute_stats(bx_list, by_list, bz_list)


def sample_mock_magnetic_stats(pos_x, pos_y, n=DEFAULT_SAMPLES_PER_CELL,
                               interval=DEFAULT_SAMPLE_INTERVAL,
                               tare_offset=(0.0, 0.0, 0.0)):
    """テスト用: 疑似磁気データとノイズを生成"""
    bx_list, by_list, bz_list = [], [], []
    for _ in range(n):
        bx = 25.0 + math.sin(pos_x * 0.4) * 15.0 + random.uniform(-0.8, 0.8) - tare_offset[0]
        by = 15.0 + math.cos(pos_y * 0.4) * 10.0 + random.uniform(-0.8, 0.8) - tare_offset[1]
        bz = -35.0 + (pos_x + pos_y) * 0.5 + random.uniform(-0.4, 0.4) - tare_offset[2]
        bx_list.append(bx)
        by_list.append(by)
        bz_list.append(bz)
        time.sleep(interval)

    return compute_stats(bx_list, by_list, bz_list)


def initialize_sensor(mode="NDOF_FMC_OFF"):
    """BNO055 センサーの初期化を試行し、インスタンスまたは None を返す"""
    if not SENSOR_AVAILABLE:
        return None
    try:
        sensor = BNO055Sensor(mode=mode)
        # 保存済みキャリブレーションプロファイルが存在すれば自動ロード
        if os.path.exists(CALIBRATION_PROFILE_PATH):
            if sensor.load_calibration_profile(CALIBRATION_PROFILE_PATH):
                print(f"[情報] キャリブレーション設定をロードしました: {CALIBRATION_PROFILE_PATH}")
        return sensor
    except (RuntimeError, OSError) as e:
        print(f"[警告] BNO055センサーの初期化に失敗しました: {e}")
        return None


# ==============================================================================
# サブコマンド 1: キャリブレーション確認 & 保存 (calibrate)
# ==============================================================================
def run_calibration(sensor=None):
    """BNO055のキャリブレーション状況をリアルタイム表示し、完了時にプロファイル保存"""
    print("\n" + "=" * 60)
    print("   BNO055 センサー・キャリブレーション確認モード")
    print("=" * 60)
    print("キャリブレーション手順:")
    print("  - 磁気 (Mag) : センサーをゆっくり8の字（∞）に動かしてください。")
    print("  - ジャイロ(Gyro): センサーを平らな場所に置いて静止させてください。")
    print("  - 加速度 (Acc) : センサーの各面（6面）を順に上に向けて静止させてください。")
    print("  ※ 各項目が 3 になればキャリブレーション完了です。")
    print("  ※ 完了後、自動的に設定プロファイルがファイルに保存されます。")
    print("  ※ 終了するには Ctrl+C を押してください。\n")

    if sensor is None:
        sensor = initialize_sensor(mode="NDOF")  # キャリブレーション時はNDOFで実行

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

            if sys_stat >= 2 and gyro_stat == 3 and accel_stat >= 2 and mag_stat == 3:
                print("\n\n[成功] キャリブレーションが十分な水準に達しました！")
                save_ans = input("このキャリブレーション設定を保存しますか？ [Y/n]: ").strip().lower()
                if save_ans in ("", "y", "yes"):
                    if sensor.save_calibration_profile(CALIBRATION_PROFILE_PATH):
                        print(f"-> 設定を保存しました: {CALIBRATION_PROFILE_PATH}")
                    else:
                        print("-> 保存に失敗しました。")
                break

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nキャリブレーション確認を終了しました。")


# ==============================================================================
# 環境磁気ゼロ点相殺 (Tare / ゼロ点補正)
# ==============================================================================
def run_tare(sensor=None, use_mock=False):
    """現在の環境磁界（地磁気や室内の定常磁界）をサンプリングし、ゼロ点として登録"""
    global GLOBAL_TARE_OFFSET
    print("\n" + "=" * 60)
    print("   環境磁界 ゼロ点補正 (Tare Calibration)")
    print("=" * 60)
    print("測定対象（磁石や電流源）を十分に離した状態で、現在のバックグラウンド環境磁界を測定します。")
    input("準備ができたら Enter キーを押してください...")

    if not use_mock and sensor is None:
        sensor = initialize_sensor()
        if sensor is None:
            use_mock = True

    print("環境磁界をサンプリング中 (15サンプル)...")
    if not use_mock and sensor is not None:
        stats = sample_sensor_magnetic_stats(sensor, n=15, interval=0.05, tare_offset=(0, 0, 0))
    else:
        stats = sample_mock_magnetic_stats(0, 0, n=15, interval=0.05, tare_offset=(0, 0, 0))

    if stats:
        mag_avg = stats[0]
        GLOBAL_TARE_OFFSET = [mag_avg[0], mag_avg[1], mag_avg[2]]
        b_tot = math.sqrt(sum(v**2 for v in mag_avg))
        print(f"\n[完了] ゼロ点オフセットを設定しました:")
        print(f"  Bx_offset = {mag_avg[0]:.2f} uT")
        print(f"  By_offset = {mag_avg[1]:.2f} uT")
        print(f"  Bz_offset = {mag_avg[2]:.2f} uT (Total: {b_tot:.2f} uT)")
        print("  ※ 以降の測定では、このオフセットが差し引かれた相対磁界が記録されます。")
    else:
        print("[エラー] ゼロ点サンプリングに失敗しました。")


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

                bx = (mag[0] - GLOBAL_TARE_OFFSET[0]) if mag else 0.0
                by = (mag[1] - GLOBAL_TARE_OFFSET[1]) if mag else 0.0
                bz = (mag[2] - GLOBAL_TARE_OFFSET[2]) if mag else 0.0
                b_total = math.sqrt(bx**2 + by**2 + bz**2)

                ax = acc[0] if acc else 0.0
                ay = acc[1] if acc else 0.0
                az = acc[2] if acc else 0.0

                calib_str = f"S:{calib[0]} G:{calib[1]} A:{calib[2]} M:{calib[3]}"
            else:
                bx = 20.0 + random.uniform(-1, 1) - GLOBAL_TARE_OFFSET[0]
                by = 10.0 + random.uniform(-1, 1) - GLOBAL_TARE_OFFSET[1]
                bz = -30.0 + random.uniform(-1, 1) - GLOBAL_TARE_OFFSET[2]
                b_total = math.sqrt(bx**2 + by**2 + bz**2)
                ax, ay, az = 0.0, 0.0, 0.0
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
               use_mock=False,
               tare=False):
    """磁束密度と位置情報を高精度サンプリングしてCSVに記録"""
    print("\n" + "=" * 60)
    print("   磁気マッピング・高精度データ記録モード (Record)")
    print("=" * 60)

    sensor = None
    if not use_mock:
        sensor = initialize_sensor(mode="NDOF_FMC_OFF")
        if sensor is None:
            print("[警告] センサー実機が見つからないため、モックデータで記録します。")
            use_mock = True

    # ゼロ点補正の確認
    if tare:
        run_tare(sensor=sensor, use_mock=use_mock)

    # センサーキャリブレーション状態の事前確認
    if not use_mock and sensor is not None:
        calib = sensor.get_calibration_status()
        if calib[3] < 2:
            print(f"[注意] 磁気センサーのキャリブレーション状態が低いです (Mag: {calib[3]}/3)。")
            print("       測定精度を高めるため、事前に 'python main.py calibrate' で")
            print("       センサーを8の字に動かして校正することを強く推奨します。\n")

    # トラッカーの初期化
    # trackerモードかつ実機センサーがある場合、50Hzのバックグラウンドスレッドで高精度追跡
    bg_tracker = None
    if tracking_mode == "tracker":
        if not use_mock and sensor is not None:
            bg_tracker = BackgroundPositionTracker(sensor, sample_rate_hz=50)
            bg_tracker.start()
            print("  ・トラッキングエンジン: 50Hz 高速バックグラウンド追跡スレッド稼働中")
        else:
            simple_tracker = PositionTracker()
    else:
        simple_tracker = PositionTracker()

    recorder = DataRecorder(filename=output)

    print(f"  ・保存先ファイル   : {recorder.filename}")
    print(f"  ・トラッキング方式 : {tracking_mode}")
    print(f"  ・1点サンプリング数 : {samples_per_cell} 回 (トリム平均フィルタ適用)")
    print(f"  ・サンプリング間隔 : {sample_interval*1000:.0f} ms (ODR同期)")
    print(f"  ・センサー動作モード: {'モック' if use_mock else 'BNO055実機 (NDOF_FMC_OFF: 強磁場保護)'}")
    if any(GLOBAL_TARE_OFFSET):
        print(f"  ・環境磁界相殺(Tare): 有効 (X:{GLOBAL_TARE_OFFSET[0]:.1f}, Y:{GLOBAL_TARE_OFFSET[1]:.1f}, Z:{GLOBAL_TARE_OFFSET[2]:.1f})")
    if tracking_mode == "grid":
        print(f"  ・グリッドサイズ   : {grid_cols} x {grid_rows} マス")
    print("  ・中断・終了方法   : Ctrl+C を押すと保存を完了して安全に終了します\n")

    count = 0
    cur_c, cur_r = 0, 0

    try:
        if tracking_mode == "manual":
            print("【マニュアル測定モード - 最も位置誤差が小さい測定方式】")
            print("方眼紙等のマーク位置にセンサーを静止させ、Enterキーを押して測定します。")
            print("位置を変更する場合は 'x y' (例: '2 3') を入力して Enter を押してください。")
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
                    stats = sample_sensor_magnetic_stats(sensor, n=samples_per_cell,
                                                         interval=sample_interval,
                                                         tare_offset=GLOBAL_TARE_OFFSET)
                else:
                    stats = sample_mock_magnetic_stats(pos[0], pos[1], n=samples_per_cell,
                                                       interval=sample_interval,
                                                       tare_offset=GLOBAL_TARE_OFFSET)

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

                if tracking_mode == "tracker":
                    if bg_tracker:
                        pos = bg_tracker.get_position()
                    else:
                        pos = (cur_c * 0.5, cur_r * 0.5, 0.0)
                else:  # grid
                    pos = (cur_c, cur_r, 0.0)

                if not use_mock and sensor is not None:
                    stats = sample_sensor_magnetic_stats(sensor, n=samples_per_cell,
                                                         interval=sample_interval,
                                                         tare_offset=GLOBAL_TARE_OFFSET)
                else:
                    stats = sample_mock_magnetic_stats(pos[0], pos[1], n=samples_per_cell,
                                                       interval=sample_interval,
                                                       tare_offset=GLOBAL_TARE_OFFSET)

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
        if bg_tracker:
            bg_tracker.stop()
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

    # DISPLAY環境変数のチェック
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        print("\n[エラー] DISPLAY環境変数が設定されていません (GUI画面がありません)。")
        print("ターミナルのみの接続ではGUIを表示できません。")
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
        print("  3. センサーキャリブレーション確認・保存 (Calibrate)")
        print("  4. 環境磁界 ゼロ点補正 (Tare: 地磁気・環境磁気相殺)")
        print("  5. リアルタイム・センサーモニター (Monitor)")
        print("  6. 終了 (Exit)")
        print("-" * 60)
        choice = input("操作番号を入力してください [1-6]: ").strip()

        if choice == "1":
            print("\nトラッキング方式を選択してください:")
            print("  a. 慣性航法 (50Hz高速バックグラウンド追跡)")
            print("  b. グリッド走査 (Grid Walk: 治具やマス目に最適・位置誤差小)")
            print("  c. マニュアル測定 (Enterキーで1点ずつ: 最も位置誤差小・推奨)")
            t_choice = input("選択 [a/b/c] (デフォルト: c): ").strip().lower()
            mode_map = {"a": "tracker", "b": "grid", "c": "manual"}
            t_mode = mode_map.get(t_choice, "manual")

            run_record(tracking_mode=t_mode)
        elif choice == "2":
            custom_path = input(f"読み込むCSVパス (空欄でデフォルト '{DEFAULT_CSV_PATH}'): ").strip()
            run_visualize(custom_path if custom_path else None)
        elif choice == "3":
            run_calibration()
        elif choice == "4":
            run_tare()
        elif choice == "5":
            run_monitor()
        elif choice in ("6", "q", "exit"):
            print("プログラムを終了します。お疲れ様でした！")
            break
        else:
            print("[警告] 1〜6 の番号を入力してください。")


# ==============================================================================
# メイン・エントリーポイント (引数解析)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Raspberry Pi 磁力線マッピングシステム (Magnetic Field Mapper)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python main.py                           # 対話メニュー起動
  python main.py record -t manual          # マニュアル測定（位置誤差最小・推奨）
  python main.py record -t grid -s 7       # グリッドモードで7サンプル測定
  python main.py record --tare             # 事前ゼロ点補正を行ってから記録
  python main.py tare                      # 単独で環境磁界ゼロ点補正を実行
  python main.py calibrate                 # キャリブレーション確認とプロファイル保存
  python main.py monitor                   # リアルタイムセンサーモニター
        """
    )

    # 従来の --mode オプション（完全互換用）
    parser.add_argument(
        "--mode",
        choices=["record", "visualize", "calibrate", "monitor", "tare"],
        help="実行モード"
    )

    # サブコマンド対応
    subparsers = parser.add_subparsers(dest="subcommand", help="サブコマンド")

    # record サブコマンド
    p_record = subparsers.add_parser("record", help="磁気データ測定・記録")
    p_record.add_argument("-o", "--output", default=DEFAULT_CSV_PATH, help=f"出力CSVファイルパス (デフォルト: {DEFAULT_CSV_PATH})")
    p_record.add_argument("-t", "--tracking", choices=["tracker", "grid", "manual"], default="manual", help="位置トラッキング方式 (推奨: manual または grid)")
    p_record.add_argument("-s", "--samples", type=int, default=DEFAULT_SAMPLES_PER_CELL, help=f"1測定点あたりのサンプル数 (デフォルト: {DEFAULT_SAMPLES_PER_CELL})")
    p_record.add_argument("-i", "--interval", type=float, default=DEFAULT_STEP_INTERVAL, help="測定ループ周期 [秒]")
    p_record.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL, help=f"センサー読み取り間隔 [秒] (デフォルト: {DEFAULT_SAMPLE_INTERVAL})")
    p_record.add_argument("--cols", type=int, default=DEFAULT_GRID_COLS, help="グリッド走査時の横マス数")
    p_record.add_argument("--rows", type=int, default=DEFAULT_GRID_ROWS, help="グリッド走査時の縦マス数")
    p_record.add_argument("--tare", action="store_true", help="測定前に環境磁界のゼロ点補正を実行する")
    p_record.add_argument("--mock", action="store_true", help="センサー実機を使わずモックで実行")

    # visualize サブコマンド
    p_vis = subparsers.add_parser("visualize", help="磁力線・マップ可視化GUI")
    p_vis.add_argument("-f", "--file", default=None, help="読み込むCSVファイルパス")

    # calibrate サブコマンド
    subparsers.add_parser("calibrate", help="BNO055 キャリブレーション支援・プロファイル保存")

    # tare サブコマンド
    subparsers.add_parser("tare", help="環境磁界のゼロ点相殺 (Tare) 実行")

    # monitor サブコマンド
    p_mon = subparsers.add_parser("monitor", help="リアルタイムセンサー値モニター")
    p_mon.add_argument("--mock", action="store_true", help="モック値で表示")

    args = parser.parse_args()

    # --mode と サブコマンド の統合判定
    mode = args.subcommand or args.mode

    if mode == "record":
        output = getattr(args, "output", DEFAULT_CSV_PATH)
        tracking = getattr(args, "tracking", "manual")
        samples = getattr(args, "samples", DEFAULT_SAMPLES_PER_CELL)
        interval = getattr(args, "interval", DEFAULT_STEP_INTERVAL)
        s_interval = getattr(args, "sample_interval", DEFAULT_SAMPLE_INTERVAL)
        cols = getattr(args, "cols", DEFAULT_GRID_COLS)
        rows = getattr(args, "rows", DEFAULT_GRID_ROWS)
        mock = getattr(args, "mock", False)
        tare_flag = getattr(args, "tare", False)
        run_record(
            output=output,
            tracking_mode=tracking,
            samples_per_cell=samples,
            sample_interval=s_interval,
            step_interval=interval,
            grid_cols=cols,
            grid_rows=rows,
            use_mock=mock,
            tare=tare_flag
        )
    elif mode == "visualize":
        file_path = getattr(args, "file", None)
        run_visualize(file_path=file_path)
    elif mode == "calibrate":
        run_calibration()
    elif mode == "tare":
        run_tare()
    elif mode == "monitor":
        mock = getattr(args, "mock", False)
        run_monitor(use_mock=mock)
    else:
        run_interactive_menu()


if __name__ == "__main__":
    main()
