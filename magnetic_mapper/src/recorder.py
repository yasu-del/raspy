import csv
import os
import math
from datetime import datetime


class DataRecorder:
    """磁気マッピングデータ記録・誤差低減フィルタリングクラス。
    
    リアルタイム記録時の各種ノイズ低減フィルタ（外れ値判定、EMA平滑化、
    同一セル加重平均、スパイクノイズ除去など）およびCSV出力機能を提供します。
    """
    # 信頼フラグ判定に使う標準偏差のデフォルト閾値 [μT]
    RELIABLE_STD_THRESHOLD = 3.0
    DEFAULT_SPIKE_THRESHOLD = 150.0  # 突発的な飛び値（スパイク）判定閾値 [μT]

    def __init__(self, filename=None, buffer_size=1, on_record_callback=None,
                 reliable_std_threshold=3.0,
                 filter_unreliable=False,
                 enable_ema=False,
                 ema_alpha=0.7,
                 enable_cell_merging=False,
                 spike_threshold=DEFAULT_SPIKE_THRESHOLD):
        """
        Args:
            filename               : 出力CSVファイルパス。省略時は data/recorded_data.csv。
            buffer_size            : バッファサイズ（1なら即時ファイル書き込み）。
            on_record_callback     : リアルタイム処理用の通知コールバック関数。
            reliable_std_threshold : 信頼できるとみなす標準偏差の上限値 [μT]（デフォルト: 3.0）。
            filter_unreliable      : Trueの場合、信頼性の低いデータ(is_reliable=0)をCSVに書き込まずスキップ。
            enable_ema             : Trueの場合、同一位置近辺での指数移動平均(EMA)フィルタを適用してノイズ低減。
            ema_alpha              : EMAの平滑化係数 (0.0 < alpha <= 1.0)。小さいほど滑らかになる。
            enable_cell_merging    : Trueの場合、同一グリッド座標(r, c)の重複測定を加重平均して統合。
            spike_threshold        : 直前測定値からの急激な変化量 [μT] をスパイク（外れ値）として検知する閾値。
        """
        if filename is None:
            # このファイル(recorder.py)の位置から3階層上(raspy/)のパスを取得
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.filename = os.path.join(base_dir, "data", "recorded_data.csv")
        else:
            self.filename = filename

        # リアルタイム性を高めるため、デフォルトでバッファサイズを1に設定
        self.buffer_size = buffer_size
        self.buffer = []

        # リアルタイム処理用のコールバック関数（GUI等に直接データを送るため）
        self.on_record_callback = on_record_callback

        # 誤差低減フィルタ関連のパラメータ
        self.reliable_std_threshold = reliable_std_threshold
        self.filter_unreliable = filter_unreliable
        self.enable_ema = enable_ema
        self.ema_alpha = max(0.01, min(1.0, ema_alpha))
        self.enable_cell_merging = enable_cell_merging
        self.spike_threshold = spike_threshold

        # 直前データの保持（スパイク判定・EMA平滑化用）
        self.prev_mag = None       # (bx, by, bz)
        self.prev_pos = None       # (c, r)

        # 同一セル統合用キャッシュ: {(round_c, round_r): [bx_sum, by_sum, bz_sum, total_n]}
        self.cell_history = {}

        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        # 初期化時にファイルを新規作成し、ヘッダーを書き込む
        with open(self.filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'r', 'c',
                'bx', 'by', 'bz', 'b_total',
                'n_samples',
                'bx_std', 'by_std', 'bz_std',
                'bx_min', 'bx_max',
                'by_min', 'by_max',
                'bz_min', 'bz_max',
                'is_reliable',
                'timestamp'
            ])

    def record(self, position, mag_vector, timestamp=None,
               n_samples=1,
               mag_std=(0.0, 0.0, 0.0),
               mag_min=(None, None, None),
               mag_max=(None, None, None),
               offset_tare=(0.0, 0.0, 0.0)):
        """位置情報・磁束密度・統計情報を検証・補正して記録する。

        Args:
            position   : (x, y) または (x, y, z) のタプル。c=x, r=y として記録。
            mag_vector : (bx, by, bz) [μT]。複数サンプルの平均値を渡すこと。
            timestamp  : ISO形式の文字列。省略時は現在時刻を使用。
            n_samples  : 平均に使用したサンプル数。
            mag_std    : (bx_std, by_std, bz_std) 各軸の標準偏差 [μT]。
            mag_min    : (bx_min, by_min, bz_min) 各軸のサンプル最小値 [μT]。
            mag_max    : (bx_max, by_max, bz_max) 各軸のサンプル最大値 [μT]。
            offset_tare: (tare_x, tare_y, tare_z) 環境磁界相殺オフセット [μT]。
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        c = float(position[0])  # pos_x
        r = float(position[1])  # pos_y
        bx = float(mag_vector[0]) - float(offset_tare[0])
        by = float(mag_vector[1]) - float(offset_tare[1])
        bz = float(mag_vector[2]) - float(offset_tare[2])

        # ── 1. 異常値・NaN・Inf ガード ──
        if any(math.isnan(v) or math.isinf(v) for v in (bx, by, bz, c, r)):
            return False

        bx_std, by_std, bz_std = mag_std

        # ── 2. スパイクノイズ（突発的な飛び値）の検知 ──
        is_spike = False
        if self.prev_mag is not None and self.spike_threshold is not None:
            diff_mag = math.sqrt(
                (bx - self.prev_mag[0]) ** 2 +
                (by - self.prev_mag[1]) ** 2 +
                (bz - self.prev_mag[2]) ** 2
            )
            # 位置の移動量が小さいにもかかわらず磁界が激変した場合はスパイクと判定
            pos_dist = 0.0
            if self.prev_pos is not None:
                pos_dist = math.sqrt((c - self.prev_pos[0]) ** 2 + (r - self.prev_pos[1]) ** 2)

            if pos_dist < 1.0 and diff_mag > self.spike_threshold:
                is_spike = True

        # ── 3. 指数移動平均 (EMA) フィルタによる微小ジッター・ノイズ低減 ──
        if self.enable_ema and self.prev_mag is not None and not is_spike:
            # 静止または微小移動時のみ平滑化を適用（急激な移動時は追従性を保つ）
            pos_dist = 0.0
            if self.prev_pos is not None:
                pos_dist = math.sqrt((c - self.prev_pos[0]) ** 2 + (r - self.prev_pos[1]) ** 2)

            if pos_dist < 0.5:
                bx = self.ema_alpha * bx + (1.0 - self.ema_alpha) * self.prev_mag[0]
                by = self.ema_alpha * by + (1.0 - self.ema_alpha) * self.prev_mag[1]
                bz = self.ema_alpha * bz + (1.0 - self.ema_alpha) * self.prev_mag[2]

        # ── 4. 同一グリッドセルの加重平均（重複測定による精度向上） ──
        if self.enable_cell_merging:
            cell_key = (round(c, 2), round(r, 2))
            if cell_key in self.cell_history:
                prev_entry = self.cell_history[cell_key]
                # 加重平均: (既存平均 * 過去サンプル数 + 今回値 * 今回サンプル数) / 合計サンプル数
                total_n = prev_entry['n'] + n_samples
                bx = (prev_entry['bx'] * prev_entry['n'] + bx * n_samples) / total_n
                by = (prev_entry['by'] * prev_entry['n'] + by * n_samples) / total_n
                bz = (prev_entry['bz'] * prev_entry['n'] + bz * n_samples) / total_n
                n_samples = total_n
                self.cell_history[cell_key] = {'bx': bx, 'by': by, 'bz': bz, 'n': total_n}
            else:
                self.cell_history[cell_key] = {'bx': bx, 'by': by, 'bz': bz, 'n': n_samples}

        # 更新された値から b_total を再計算
        b_total = math.sqrt(bx**2 + by**2 + bz**2)

        # 直前値の更新
        self.prev_mag = (bx, by, bz)
        self.prev_pos = (c, r)

        # min/max が渡されていない場合は値で代用
        bx_min = mag_min[0] if mag_min[0] is not None else bx
        bx_max = mag_max[0] if mag_max[0] is not None else bx
        by_min = mag_min[1] if mag_min[1] is not None else by
        by_max = mag_max[1] if mag_max[1] is not None else by
        bz_min = mag_min[2] if mag_min[2] is not None else bz
        bz_max = mag_max[2] if mag_max[2] is not None else bz

        # ── 5. 厳格な信頼度判定 (is_reliable) ──
        # 条件:
        #   - 各軸の標準偏差が閾値以下
        #   - 突発的スパイクでない
        #   - サンプル数が1より多い（1サンプルの場合はブレの判定ができないため警告フラグ0とする）
        std_ok = (
            bx_std <= self.reliable_std_threshold and
            by_std <= self.reliable_std_threshold and
            bz_std <= self.reliable_std_threshold
        )
        sample_ok = (n_samples >= 2) or (n_samples == 1 and std_ok)

        is_reliable = int(std_ok and sample_ok and not is_spike)

        # 不良データの書き込み除外オプション
        if self.filter_unreliable and is_reliable == 0:
            return False

        row = [
            r, c,
            round(bx, 4), round(by, 4), round(bz, 4), round(b_total, 4),
            n_samples,
            round(bx_std, 4), round(by_std, 4), round(bz_std, 4),
            round(bx_min, 4), round(bx_max, 4),
            round(by_min, 4), round(by_max, 4),
            round(bz_min, 4), round(bz_max, 4),
            is_reliable,
            timestamp
        ]
        self.buffer.append(row)

        # バッファが規定値に達したらファイルへ書き込む
        if len(self.buffer) >= self.buffer_size:
            self.flush()

        # リアルタイムで外部（可視化プログラム等）にデータを通知
        if self.on_record_callback:
            self.on_record_callback(row)

        return True

    def flush(self):
        """バッファ内のデータをファイルに追記してバッファをクリアする"""
        if not self.buffer:
            return
        with open(self.filename, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(self.buffer)
        self.buffer.clear()

    def save_to_csv(self, filename=None):
        """互換性のためのメソッド。現在は残りのバッファをフラッシュする役割を持つ。"""
        self.flush()

    @staticmethod
    def clean_csv(input_filepath, output_filepath=None,
                  remove_unreliable=True,
                  deduplicate_cells=True,
                  max_std_threshold=3.0):
        """既存のCSVファイルから誤差の大きいデータを除去・統合してクリーンなCSVを生成する後処理関数。

        Args:
            input_filepath    : 入力元CSVパス。
            output_filepath   : 出力先CSVパス（省略時は input_filepath + '_clean.csv'）。
            remove_unreliable : Trueの場合、is_reliable=0 の行を除外。
            deduplicate_cells : Trueの場合、同一 (r, c) セルの重複測定を平均化。
            max_std_threshold : 許容する最大標準偏差 [μT]。これを超える行は除外。

        Returns:
            str: 生成されたクリーンCSVのパス
        """
        if not os.path.exists(input_filepath):
            raise FileNotFoundError(f"ファイルが見つかりません: {input_filepath}")

        if output_filepath is None:
            base, ext = os.path.splitext(input_filepath)
            output_filepath = f"{base}_clean{ext}"

        cell_data = {}  # {(r, c): [rows]}
        valid_rows = []
        header = None

        with open(input_filepath, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)

            for row in reader:
                if not row or len(row) < 17:
                    continue
                try:
                    r = float(row[0])
                    c = float(row[1])
                    bx = float(row[2])
                    by = float(row[3])
                    bz = float(row[4])
                    b_tot = float(row[5])
                    n_samp = int(row[6]) if row[6] else 1
                    bx_std = float(row[7])
                    by_std = float(row[8])
                    bz_std = float(row[9])
                    is_rel = int(row[16])

                    # 誤差フィルター判定
                    if remove_unreliable and is_rel == 0:
                        continue
                    if max(bx_std, by_std, bz_std) > max_std_threshold:
                        continue

                    key = (round(r, 2), round(c, 2))
                    if deduplicate_cells:
                        if key not in cell_data:
                            cell_data[key] = []
                        cell_data[key].append((bx, by, bz, n_samp, row))
                    else:
                        valid_rows.append(row)

                except ValueError:
                    continue

        if deduplicate_cells:
            # 重複セルの平均化
            for (r, c), entries in cell_data.items():
                if len(entries) == 1:
                    valid_rows.append(entries[0][4])
                else:
                    tot_n = sum(e[3] for e in entries)
                    avg_bx = sum(e[0] * e[3] for e in entries) / tot_n
                    avg_by = sum(e[1] * e[3] for e in entries) / tot_n
                    avg_bz = sum(e[2] * e[3] for e in entries) / tot_n
                    avg_btot = math.sqrt(avg_bx**2 + avg_by**2 + avg_bz**2)

                    # 代表のタイムスタンプ等は最新のものを利用
                    base_row = list(entries[-1][4])
                    base_row[0] = r
                    base_row[1] = c
                    base_row[2] = round(avg_bx, 4)
                    base_row[3] = round(avg_by, 4)
                    base_row[4] = round(avg_bz, 4)
                    base_row[5] = round(avg_btot, 4)
                    base_row[6] = tot_n
                    base_row[16] = 1  # 統合後は信頼フラグ1
                    valid_rows.append(base_row)

        # ソート (r昇順, c昇順)
        valid_rows.sort(key=lambda x: (float(x[0]), float(x[1])))

        with open(output_filepath, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if header:
                writer.writerow(header)
            writer.writerows(valid_rows)

        return output_filepath

