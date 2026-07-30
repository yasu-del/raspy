import os
import sys
import unittest
from unittest.mock import patch, mock_open

# 元の pi_test フォルダのパスを追加して、そこにある recorder.py をインポートできるようにします
PI_TEST_DIR = r"C:\Users\sato6\.gemini\antigravity\scratch\pi_test"
if PI_TEST_DIR not in sys.path:
    sys.path.append(PI_TEST_DIR)

try:
    import recorder
except ImportError:
    # パスが見つからない等のエラー対策
    recorder = None

class TestCPURecorder(unittest.TestCase):
    """CPU温度レコーダー(recorder.py)の動作確認を行うテストクラスです。
    
    異なる実行環境（Linux/Windowsなど）における get_cpu_temp 関数の挙動や、
    ファイル読み込みエラー時のフォールバック処理が正しく機能するかを検証します。
    """
    
    def setUp(self):
        """テスト前処理。
        
        テスト対象の recorder モジュールが正しくインポートできているかを確認します。
        インポートに失敗している場合は、このテストクラス全体の実行をスキップします。
        """
        if recorder is None:
            self.skipTest(f"recorder.py が指定されたパス ({PI_TEST_DIR}) に見つかりません。")

    def test_get_cpu_temp_fallback(self):
        """フォールバック動作のテスト。
        
        Windows等のLinux以外の環境（/sys/class/... へのアクセスが失敗する環境）において、
        シミュレーション値（42.0 〜 48.0度）が float 型で正しく返されることを検証します。
        """
        temp = recorder.get_cpu_temp()
        # 戻り値が float であること
        self.assertIsInstance(temp, float)
        # シミュレーション値の範囲（42.0 〜 48.0）に収まっていること
        self.assertTrue(42.0 <= temp <= 48.0)

    @patch("builtins.open", new_callable=mock_open, read_data="45200")
    def test_get_cpu_temp_linux(self, mock_file):
        """Linux（ラズパイ）環境を模擬した動作のテスト。
        
        モック（mock_open）を利用して仮想的にシステム温度ファイルを読み込ませ、
        ファイル内の生データ（ミリ度）が正しい摂氏温度（度に変換）に計算されること、
        および正しいパスでファイルをオープンしていることを検証します。
        """
        temp = recorder.get_cpu_temp()
        # 45200ミリ度が 45.2度 に正しく変換されること
        self.assertEqual(temp, 45.2)
        # 正しいパスでオープンされたこと
        mock_file.assert_called_once_with("/sys/class/thermal/thermal_zone0/temp", "r")

if __name__ == "__main__":
    unittest.main()
