import csv
import os
from datetime import datetime

class DataRecorder:
    def __init__(self, filename=None, buffer_size=100):
        if filename is None:
            # このファイル(recorder.py)の位置から3階層上(raspy/)のパスを取得
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.filename = os.path.join(base_dir, "data", "recorded_data.csv")
        else:
            self.filename = filename
            
        self.buffer_size = buffer_size
        self.buffer = []
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        
        # 初期化時にファイルを新規作成し、ヘッダーを書き込む
        with open(self.filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['r', 'c', 'bx', 'by', 'bz', 'b_total', 'timestamp'])

    def record(self, position, mag_vector, timestamp=None):
        """位置情報と磁束密度をバッファに記録し、一定数に達したらファイルへ追記する"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        import math
        r = position[1] # pos_y
        c = position[0] # pos_x
        bx, by, bz = mag_vector[0], mag_vector[1], mag_vector[2]
        b_total = math.sqrt(bx**2 + by**2 + bz**2)
        
        row = [r, c, bx, by, bz, b_total, timestamp]
        self.buffer.append(row)
        
        if len(self.buffer) >= self.buffer_size:
            self.flush()

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
