
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import math
import os
import csv

class MagneticVisualizer:
    def __init__(self, data_file="data/magnetic_data.csv"):
        self.data_file = data_file
        self.loaded_file_path = ""
        self.measuring_data = {}  # データを内部で保持する辞書
        
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

    def _parse_csv(self, file_path):
        """CSVファイルを読み込み、内部データとグリッドサイズを更新する"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")
            
        new_data = {}
        max_r, max_c = 0, 0
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # ヘッダーをスキップ
            
            for row in reader:
                if not row or len(row) < 6:
                    continue
                try:
                    r = int(float(row[0]))
                    c = int(float(row[1]))
                    bx = float(row[2])
                    by = float(row[3])
                    bz = float(row[4])
                    b_total = float(row[5])
                    
                    new_data[(r, c)] = {
                        "bx": bx,
                        "by": by,
                        "bz": bz,
                        "b_total": b_total
                    }
                    if r > max_r: max_r = r
                    if c > max_c: max_c = c
                except ValueError:
                    continue
                    
        self.measuring_data = new_data
        self.rows = max_r + 1 if new_data else 10
        self.cols = max_c + 1 if new_data else 10
        self.loaded_file_path = file_path

    def plot_field_lines(self):
        """磁力線やベクトル場を可視化する（GUI起動）"""
        self.root = tk.Tk()
        self.root.title("BNO055 磁気マップ・ビジュアライザ")
        self.root.geometry("1020x680")
        self.root.minsize(900, 550)
        
        # 画面状態のバインド変数を初期化
        self.autoscale_var = tk.BooleanVar(value=True)
        self.vector_show_var = tk.BooleanVar(value=True)
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

    def _setup_styles(self):
        self.BG_MAIN = "#1e1e2e"
        self.BG_CARD = "#252538"
        self.BG_INPUT = "#313244"
        self.FG_MAIN = "#cdd6f4"
        self.FG_MUTED = "#a6adc8"
        self.ACCENT = "#89b4fa"
        
        self.root.configure(bg=self.BG_MAIN)
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.style.configure(".", background=self.BG_MAIN, foreground=self.FG_MAIN)
        self.style.configure("TFrame", background=self.BG_MAIN)
        self.style.configure("Card.TFrame", background=self.BG_CARD, relief="flat")
        self.style.configure("TLabel", background=self.BG_MAIN, foreground=self.FG_MAIN, font=("Helvetica", 10))
        self.style.configure("Card.TLabel", background=self.BG_CARD, foreground=self.FG_MAIN, font=("Helvetica", 10))
        self.style.configure("Header.TLabel", background=self.BG_CARD, foreground=self.ACCENT, font=("Helvetica", 12, "bold"))
        self.style.configure("Title.TLabel", background=self.BG_MAIN, foreground=self.ACCENT, font=("Helvetica", 16, "bold"))
        
        self.style.configure("TButton", background="#313244", foreground=self.FG_MAIN, borderwidth=0, font=("Helvetica", 10, "bold"))
        self.style.map("TButton", background=[("active", "#45475a"), ("pressed", "#585b70")], foreground=[("active", "#ffffff")])
        self.style.configure("Accent.TButton", background=self.ACCENT, foreground="#11111b")
        self.style.map("Accent.TButton", background=[("active", "#b4befe"), ("pressed", "#74c7ec")])

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="磁気マッピング・ビジュアライザ", style="Title.TLabel").pack(anchor="w", pady=(0, 15))
        
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)
        
        left_panel = ttk.Frame(content_frame, width=320)
        left_panel.pack(side="left", fill="y", padx=(0, 20))
        left_panel.pack_propagate(False)
        
        right_panel = ttk.Frame(content_frame)
        right_panel.pack(side="right", fill="both", expand=True)
        
        # カード1: ファイル選択
        file_card = ttk.Frame(left_panel, style="Card.TFrame", padding=15)
        file_card.pack(fill="x", pady=(0, 15))
        ttk.Label(file_card, text="データファイル選択", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Button(file_card, text="別のCSVを開く", command=self.load_csv_dialog, style="Accent.TButton").pack(fill="x", pady=5)
        self.file_label = ttk.Label(file_card, text="ファイルが選択されていません", font=("Helvetica", 9), wraplength=270, justify="left", style="Card.TLabel")
        self.file_label.pack(anchor="w", pady=(5, 0))
        
        # カード2: 可視化表示設定
        color_card = ttk.Frame(left_panel, style="Card.TFrame", padding=15)
        color_card.pack(fill="x", pady=(0, 15))
        ttk.Label(color_card, text="可視化表示設定", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        tk.Checkbutton(color_card, text="オートスケール（自動調整）", variable=self.autoscale_var, command=self.redraw_heatmap, bg=self.BG_CARD, fg=self.FG_MAIN, selectcolor=self.BG_MAIN, activebackground=self.BG_CARD, activeforeground=self.FG_MAIN).grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        tk.Checkbutton(color_card, text="磁気ベクトル（矢印）を表示", variable=self.vector_show_var, command=self.redraw_heatmap, bg=self.BG_CARD, fg=self.FG_MAIN, selectcolor=self.BG_MAIN, activebackground=self.BG_CARD, activeforeground=self.FG_MAIN).grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        
        ttk.Label(color_card, text="最小強度 (uT):", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        tk.Spinbox(color_card, from_=0, to=1000, width=5, bg=self.BG_INPUT, fg=self.FG_MAIN, insertbackground=self.FG_MAIN, buttonbackground=self.BG_INPUT, relief="flat", textvariable=self.min_ut_var, command=self.redraw_heatmap).grid(row=3, column=1, sticky="e", pady=5)
        
        ttk.Label(color_card, text="最大強度 (uT):", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=5)
        tk.Spinbox(color_card, from_=1, to=10000, width=5, bg=self.BG_INPUT, fg=self.FG_MAIN, insertbackground=self.FG_MAIN, buttonbackground=self.BG_INPUT, relief="flat", textvariable=self.max_ut_var, command=self.redraw_heatmap).grid(row=4, column=1, sticky="e", pady=5)
        
        # カード3: 統計・概要情報
        self.stats_card = ttk.Frame(left_panel, style="Card.TFrame", padding=15)
        self.stats_card.pack(fill="both", expand=True)
        ttk.Label(self.stats_card, text="データ概要", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        self.stats_label = ttk.Label(self.stats_card, text="CSVファイルを読み込んでください。", wraplength=270, justify="left", style="Card.TLabel")
        self.stats_label.pack(anchor="w", pady=5)
        
        # 右パネル
        self.canvas_frame = ttk.Frame(right_panel, style="Card.TFrame", padding=10)
        self.canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg=self.BG_INPUT, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        self.root.bind("<Up>", lambda e: self.move_selection(-1, 0))
        self.root.bind("<Down>", lambda e: self.move_selection(1, 0))
        self.root.bind("<Left>", lambda e: self.move_selection(0, -1))
        self.root.bind("<Right>", lambda e: self.move_selection(0, 1))
        
        self.info_frame = ttk.Frame(right_panel, style="Card.TFrame", padding=15)
        self.info_frame.pack(fill="x", side="bottom", pady=(15, 0))
        self.cell_label = ttk.Label(self.info_frame, text="選択セル値: マスをクリックすると詳細データが表示されます", font=("Consolas", 11), style="Card.TLabel")
        self.cell_label.pack(anchor="w")

    def on_canvas_configure(self, event):
        self.draw_grid()

    def draw_grid(self):
        self.canvas.delete("all")
        
        if not self.measuring_data:
            self.canvas.create_text(
                self.canvas.winfo_width()/2, 
                self.canvas.winfo_height()/2, 
                text="左上のボタンからデータを選択してください。", 
                fill=self.FG_MUTED, font=("Helvetica", 14), justify="center"
            )
            return

        self.canvas_width = self.canvas.winfo_width()
        self.canvas_height = self.canvas.winfo_height()
        if self.canvas_width <= 1 or self.canvas_height <= 1:
            return
            
        self.cell_w = self.canvas_width / self.cols
        self.cell_h = self.canvas_height / self.rows
        
        for r in range(self.rows):
            for c in range(self.cols):
                x1, y1 = c * self.cell_w, r * self.cell_h
                x2, y2 = (c + 1) * self.cell_w, (r + 1) * self.cell_h
                
                fill_color = self.BG_INPUT
                outline_color = "#44445c"
                text_color = self.FG_MUTED
                
                if (r, c) in self.measuring_data:
                    val = self.measuring_data[(r, c)]["b_total"]
                    fill_color = self.get_heatmap_color(val)
                    text_color = "#11111b" if fill_color != self.BG_INPUT else self.FG_MUTED
                
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline=outline_color, tags=f"cell_{r}_{c}")
                
                if self.vector_show_var.get() and (r, c) in self.measuring_data:
                    data = self.measuring_data[(r, c)]
                    bx, by = data["bx"], data["by"]
                    b_horiz = math.sqrt(bx**2 + by**2)
                    
                    if b_horiz > 1e-4:
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                        max_len = min(self.cell_w, self.cell_h) * 0.40
                        norm_len = min(1.0, b_horiz / 100.0)
                        arrow_len = max(5.0, norm_len * max_len)
                        
                        dx, dy = (bx / b_horiz) * arrow_len, -(by / b_horiz) * arrow_len
                        self.canvas.create_line(cx, cy, cx + dx, cy + dy, arrow=tk.LAST, fill="#ffffff", width=2, tags="arrow")
                
                if self.cell_w > 45 and self.cell_h > 25:
                    if (r, c) in self.measuring_data:
                        val = self.measuring_data[(r, c)]["b_total"]
                        y_pos = y2 - 10 if self.vector_show_var.get() else (y1 + y2)/2
                        self.canvas.create_text((x1 + x2)/2, y_pos, text=f"{val:.1f}", fill=text_color, font=("Helvetica", 8, "bold"), tags="text")
                    else:
                        self.canvas.create_text((x1 + x2)/2, (y1 + y2)/2, text=f"({c},{r})", fill="#44445c", font=("Helvetica", 8), tags="text")

        self.draw_selection_box()

    def draw_selection_box(self):
        if not self.measuring_data:
            return
        self.canvas.delete("selection")
        r, c = self.selected_cell
        x1, y1 = c * self.cell_w, r * self.cell_h
        x2, y2 = (c + 1) * self.cell_w, (r + 1) * self.cell_h
        self.canvas.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y2 - 2, outline=self.ACCENT, width=3, tags="selection")

    def move_selection(self, dr, dc):
        if not self.measuring_data: return
        r, c = self.selected_cell
        nr, nc = r + dr, c + dc
        if 0 <= nr < self.rows and 0 <= nc < self.cols:
            self.selected_cell = (nr, nc)
            self.draw_selection_box()
            self.update_cell_info_label()

    def on_canvas_click(self, event):
        if not self.measuring_data: return
        c, r = int(event.x / self.cell_w), int(event.y / self.cell_h)
        if 0 <= c < self.cols and 0 <= r < self.rows:
            self.selected_cell = (r, c)
            self.draw_selection_box()
            self.update_cell_info_label()

    def get_heatmap_color(self, val):
        if self.autoscale_var.get():
            if not self.measuring_data: return self.BG_INPUT
            vals = [d["b_total"] for d in self.measuring_data.values()]
            min_val, max_val = min(vals), max(vals)
            self.min_ut_var.set(round(min_val, 1))
            self.max_ut_var.set(round(max_val, 1))
        else:
            min_val, max_val = self.min_ut_var.get(), self.max_ut_var.get()
            
        v = 0.5 if max_val == min_val else (val - min_val) / (max_val - min_val)
        v = max(0.0, min(1.0, v))
        h = 240.0 * (1.0 - v)
        s, v_light = 0.85, 0.95
        c = v_light * s
        x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
        m = v_light - c
        
        if 0 <= h < 60: r, g, b = c, x, 0
        elif 60 <= h < 120: r, g, b = x, c, 0
        elif 120 <= h < 180: r, g, b = 0, c, x
        elif 180 <= h < 240: r, g, b = 0, x, c
        else: r, g, b = c, 0, c
            
        return f"#{int((r+m)*255):02x}{int((g+m)*255):02x}{int((b+m)*255):02x}"

    def redraw_heatmap(self):
        self.draw_grid()

    def update_cell_info_label(self):
        r, c = self.selected_cell
        data = self.measuring_data.get((r, c))
        if data is not None:
            self.cell_label.configure(
                text=f"選択セル({c}, {r}) 磁気強度: {data['b_total']:.2f} uT | "
                     f"Bx: {data['bx']:.2f}, By: {data['by']:.2f}, Bz: {data['bz']:.2f}"
            )
        else:
            self.cell_label.configure(text=f"選択セル({c}, {r}) 磁気強度: データ無し")

    def _load_file(self, file_path):
        try:
            self._parse_csv(file_path)
            self.file_label.configure(text=os.path.basename(file_path))
            self.update_statistics()
            self.selected_cell = (0, 0)
            self.draw_grid()
            self.update_cell_info_label()
        except Exception as e:
            messagebox.showerror("エラー", f"CSVファイルの読み込みに失敗しました: {e}")

    def load_csv_dialog(self):
        initial_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(initial_dir, exist_ok=True)
        file_path = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="磁気マップCSVデータを選択してロード"
        )
        if file_path:
            self._load_file(file_path)

    def update_statistics(self):
        if not self.measuring_data:
            self.stats_label.configure(text="データがありません。")
            return
            
        vals = [d["b_total"] for d in self.measuring_data.values()]
        min_v, max_v = min(vals), max(vals)
        mean_v = sum(vals) / len(vals)
        
        stats_text = (
            f"ファイル名:\n {os.path.basename(self.loaded_file_path)}\n\n"
            f"グリッド: {self.cols} x {self.rows}\n"
            f"測定数: {len(self.measuring_data)} / {self.cols * self.rows}\n\n"
            f"【磁気強度総和 (B_total)】\n"
            f"  ・最大: {max_v:.2f} uT\n"
            f"  ・最小: {min_v:.2f} uT\n"
            f"  ・平均: {mean_v:.2f} uT"
        )
        self.stats_label.configure(text=stats_text)

if __name__ == "__main__":
    test_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_magnet.csv")
    app = MagneticVisualizer(data_file=test_file if os.path.exists(test_file) else "")
    app.plot_field_lines()

   