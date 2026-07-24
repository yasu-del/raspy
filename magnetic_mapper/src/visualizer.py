
# -*- coding: utf-8 -*-

class MagneticVisualizer:
    def __init__(self, data_file="data/magnetic_data.csv"):
        self.data_file = data_file
        self.recorder = DataRecorder()
        self.loaded_file_path = ""
        
        # グリッドサイズ初期値
        self.rows = 10
        self.cols = 10
        self.selected_cell = (0, 0)
        
        # Tkinter関連の変数は後で初期化するためここではNone
        self.root = None
        self.autoscale_var = None
        self.vector_show_var = None
        self.min_ut_var = None
        self.max_ut_var = None

    def plot_field_lines(self):
        """磁力線やベクトル場を可視化する（GUI起動）"""
        self.root = tk.Tk()
        self.root.title("BNO055 磁気マップ・ビジュアライザ")
        self.root.geometry("1020x680")
        self.root.minsize(900, 550)
        
        # 画面状態のバインド変数を初期化
        self.autoscale_var = tk.BooleanVar(value=True)
        self.vector_show_var = tk.BooleanVar(value=True)  # ベクトル矢印表示
        self.min_ut_var = tk.DoubleVar(value=20.0)
        self.max_ut_var = tk.DoubleVar(value=100.0)
        
        # スタイル設定とUIの構築
        self._setup_styles()
        self._build_ui()
        
        # 初期データファイルが指定されており、存在する場合は自動で読み込む
        if self.data_file and os.path.exists(self.data_file):
            self._load_file(self.data_file)
            
        # GUIループ開始
        self.root.mainloop()

   