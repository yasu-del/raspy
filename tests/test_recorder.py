import sys
import os

# srcディレクトリをパスに追加
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'magnetic_mapper', 'src'))

from recorder import DataRecorder

def test_recorder():
    print("--- DataRecorder テスト開始 ---")
    recorder = DataRecorder()
    
    # ダミーデータを記録
    print("ダミーデータを記録中...")
    recorder.record(position=(1.0, 2.0, 3.0), mag_vector=(10.5, 20.5, 30.5))
    recorder.record(position=(1.1, 2.1, 3.1), mag_vector=(11.5, 21.5, 31.5))
    
    # 追加したtimestamp引数のテスト
    recorder.record(position=(1.2, 2.2, 3.2), mag_vector=(12.5, 22.5, 32.5), timestamp="2026-01-01T12:00:00")
    
    # CSVに保存
    print("CSVファイルに保存中...")
    recorder.save_to_csv()
    
    # 保存されたか確認
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    expected_csv_path = os.path.join(base_dir, "data", "recorded_data.csv")
    
    if os.path.exists(expected_csv_path):
        print(f"成功: ファイルが作成されました -> {expected_csv_path}")
        with open(expected_csv_path, 'r') as f:
            print("\n[ファイル内容]")
            print(f.read())
    else:
        print("エラー: ファイルが作成されませんでした。")

if __name__ == "__main__":
    test_recorder()
