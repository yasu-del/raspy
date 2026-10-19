import csv
import os
from datetime import datetime


class DataRecorder:
    # 信頼フラグ判定に使う標準偏差の閾値 [μT]
    # この値以下ならノイズが少なく信頼できるデータとみなす
    RELIABLE_STD_THRESHOLD = 3.0

    def __init__(self, filename=None, buffer_size=1, on_record_callback=None):
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

        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        # 初期化時にファイルを新規作成し、ヘッダーを書き込む
        # 拡張列の説明:
        #   n_samples  : 平均に使ったサンプル数
        #   bx_std, by_std, bz_std : 各軸の標準偏差 [μT]（小さいほど安定）
        #   bx_min, bx_max, by_min, by_max, bz_min, bz_max : 各軸の最小・最大値 [μT]
        #   is_reliable: 全軸の std がしきい値以下なら 1、それ以外は 0
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
               mag_max=(None, None, None)):
        """位置情報・磁束密度・統計情報をバッファに記録し、一定数に達したらファイルへ追記する。

        Args:
            position   : (x, y) または (x, y, z) のタプル。c=x, r=y として記録。
            mag_vector : (bx, by, bz) [μT]。複数サンプルの平均値を渡すこと。
            timestamp  : ISO形式の文字列。省略時は現在時刻を使用。
            n_samples  : 平均に使用したサンプル数。
            mag_std    : (bx_std, by_std, bz_std) 各軸の標準偏差 [μT]。
            mag_min    : (bx_min, by_min, bz_min) 各軸のサンプル最小値 [μT]。
                         None の場合は mag_vector の値をそのまま使用。
            mag_max    : (bx_max, by_max, bz_max) 各軸のサンプル最大値 [μT]。
                         None の場合は mag_vector の値をそのまま使用。
        """
        import math

        if timestamp is None:
            timestamp = datetime.now().isoformat()

        r = position[1]  # pos_y
        c = position[0]  # pos_x
        bx, by, bz = mag_vector[0], mag_vector[1], mag_vector[2]
        b_total = math.sqrt(bx**2 + by**2 + bz**2)

        bx_std, by_std, bz_std = mag_std

        # min/max が渡されていない場合は平均値で代用
        bx_min = mag_min[0] if mag_min[0] is not None else bx
        bx_max = mag_max[0] if mag_max[0] is not None else bx
        by_min = mag_min[1] if mag_min[1] is not None else by
        by_max = mag_max[1] if mag_max[1] is not None else by
        bz_min = mag_min[2] if mag_min[2] is not None else bz
        bz_max = mag_max[2] if mag_max[2] is not None else bz

        # 全軸の標準偏差がしきい値以下の場合に信頼できるデータと判定
        is_reliable = int(
            bx_std <= self.RELIABLE_STD_THRESHOLD and
            by_std <= self.RELIABLE_STD_THRESHOLD and
            bz_std <= self.RELIABLE_STD_THRESHOLD
        )

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

        # バッファが規定値に達したらファイルへ書き込む（buffer_size=1なら即時書き込み）
        if len(self.buffer) >= self.buffer_size:
            self.flush()

        # リアルタイムで外部（可視化プログラム等）にデータを通知する
        if self.on_record_callback:
            self.on_record_callback(row)

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
