import sys
import os

# スクリプトがあるディレクトリ（raspy直下）を取得
repo_path = os.path.dirname(os.path.abspath(__file__))
if repo_path not in sys.path:
    sys.path.append(repo_path)

from magnetic_mapper.src.recorder import DataRecorder

def main():
    print("Testing DataRecorder initialization...")
    # 既存のファイルを削除せずに、新しいテスト用ファイル名を使用する
    test_file = os.path.join(repo_path, "data", "test_recorded_data.csv")
    
    # バッファサイズ2で初期化
    recorder = DataRecorder(filename=test_file, buffer_size=2)
    print(f"Data file initialized at: {recorder.filename}")
    
    print("Writing 1st record...")
    recorder.record([1.1, 2.2, 3.3], [10.1, 10.2, 10.3])
    
    print("Writing 2nd record (this should trigger flush)...")
    recorder.record([4.4, 5.5, 6.6], [20.1, 20.2, 20.3])
    
    print("Writing 3rd record...")
    recorder.record([7.7, 8.8, 9.9], [30.1, 30.2, 30.3])
    
    print("Flushing manually...")
    recorder.flush()
    
    print("\n--- Content of the CSV file ---")
    with open(recorder.filename, 'r', encoding='utf-8') as f:
        print(f.read())

if __name__ == "__main__":
    main()
