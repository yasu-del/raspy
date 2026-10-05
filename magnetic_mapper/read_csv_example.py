import csv
import os

def read_recorded_data(filename=None):
    if filename is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filename = os.path.join(base_dir, "data", "recorded_data.csv")
    
    data_list = []
    
    if not os.path.exists(filename):
        print(f"ファイルが見つかりません: {filename}")
        return data_list
        
    with open(filename, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 必要な形式に変換してリストに格納
            record = {
                'timestamp': row['timestamp'],
                'pos': (float(row['pos_x']), float(row['pos_y']), float(row['pos_z'])),
                'mag': (float(row['mag_x']), float(row['mag_y']), float(row['mag_z']))
            }
            data_list.append(record)
            
    return data_list

if __name__ == "__main__":
    # 実行例
    data = read_recorded_data()
    print(f"読み込んだデータ数: {len(data)}")
    
    # 最初の数件を表示
    for i, record in enumerate(data[:3]):
        print(f"[{i}] 時間: {record['timestamp']}")
        print(f"    位置: {record['pos']}")
        print(f"    磁力: {record['mag']}")
