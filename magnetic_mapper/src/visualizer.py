# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import math
import os
import csv

class Camera3D:
    """3D空間上の視点操作・透視投影処理クラス"""
    def __init__(self):
        self.yaw = math.pi / 4
        self.pitch = math.pi / 6
        self.distance = 30.0
        self.fov = 800.0
        self.center_x = 0
        self.center_y = 0

    def rotate(self, dx, dy):
        self.yaw -= dx * 0.01
        self.pitch += dy * 0.01
        self.pitch = max(-math.pi/2 + 0.01, min(math.pi/2 - 0.01, self.pitch))

    def zoom(self, delta):
        self.distance *= (1.0 - delta * 0.1)
        self.distance = max(5.0, min(200.0, self.distance))

    def project(self, x, y, z):
        # Yaw
        xy_cos, xy_sin = math.cos(self.yaw), math.sin(self.yaw)
        x1 = x * xy_cos - y * xy_sin
        y1 = x * xy_sin + y * xy_cos
        
        # Pitch
        yz_cos, yz_sin = math.cos(self.pitch), math.sin(self.pitch)
        y2 = y1 * yz_cos - z * yz_sin
        z2 = y1 * yz_sin + z * yz_cos

        z2 += self.distance
        if z2 <= 0.1: z2 = 0.1

        factor = self.fov / z2
        px = x1 * factor + self.center_x
        py = -y2 * factor + self.center_y
        return px, py, z2


class UnifiedMagneticVisualizer:
    """2D / 3D 統合 磁気マップ・ビジュアライザ (ライトモード固定版)"""
    
    THEME = {
        "BG_MAIN": "#f2f2f7",
        "BG_CARD": "#ffffff",
        "BG_INPUT": "#e5e5ea",
        "FG_MAIN": "#1c1c1e",
        "FG_MUTED": "#636366",
        "ACCENT": "#007aff",
        "GRID_BORDER": "#d1d1d6",
        "SELECTION": "#007aff",
        "HIGHLIGHT": "#ff3b30" # 3D選択時の赤色リング
    }

    def __init__(self, data_file="data/magnetic_data.csv"):
        self.data_file = data_file
        self.loaded_file_path = ""
        self.measuring_data_2d = {}
        self.measuring_data_3d = []
        
        self.rows = 10
        self.cols = 10
        self.selected_cell = (0, 0)
        self.selected_3d_index = None  # 3Dモードで選択中のデータインデックス
        
        self.camera = Camera3D()
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        # UIコントロール変数
        self.root = None
        self.mode_var = None
        self.colormap_var = None
        self.autoscale_var = None
        self.vector_show_2d_var = None
        self.show_axes_3d_var = None
        self.vector_scale_3d_var = None
        self.min_ut_var = None
        self.max_ut_var = None

    def _parse_csv(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        new_data_2d = {}
        new_data_3d = []
        max_r, max_c = 0, 0

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            is_timestamp = header and len(header) >= 7 and "timestamp" in header[0].lower()

            for row in reader:
                if not row: continue
                try:
                    if is_timestamp:
                        if len(row) < 7: continue
                        orig_x, orig_y, orig_z = float(row[1]), float(row[2]), float(row[3])
                        bx, by, bz = float(row[4]), float(row[5]), float(row[6])
                        c, r = int(round(orig_x)), int(round(orig_y))
                    else:
                        if len(row) < 6: continue
                        r, c = int(float(row[0])), int(float(row[1]))
                        orig_x, orig_y, orig_z = float(c), float(r), 0.0
                        bx, by, bz = float(row[2]), float(row[3]), float(row[4])

                    b_total = math.sqrt(bx**2 + by**2 + bz**2)
                    item = {
                        "bx": bx, "by": by, "bz": bz, "b_total": b_total,
                        "orig_x": orig_x, "orig_y": orig_y, "orig_z": orig_z
                    }
                    new_data_2d[(r, c)] = item
                    new_data_3d.append(item)

                    if r > max_r: max_r = r
                    if c > max_c: max_c = c
                except ValueError:
                    continue

        if not new_data_3d: return

        # 3Dセンタリング
        cx = sum(d['orig_x'] for d in new_data_3d) / len(new_data_3d)
        cy = sum(d['orig_y'] for d in new_data_3d) / len(new_data_3d)
        cz = sum(d['orig_z'] for d in new_data_3d) / len(new_data_3d)

        max_dist = 0.1
        for d in new_data_3d:
            d['x'], d['y'], d['z'] = d['orig_x'] - cx, d['orig_y'] - cy, d['orig_z'] - cz
            dist = math.sqrt(d['x']**2 + d['y']**2 + d['z']**2)
            if dist > max_dist: max_dist = dist

        self.measuring_data_2d = new_data_2d
        self.measuring_data_3d = new_data_3d
        self.rows = max_r + 1 if new_data_2d else 10
        self.cols = max_c + 1 if new_data_2d else 10
        self.loaded_file_path = file_path

        self.camera = Camera3D()
        self.camera.distance = max(10.0, max_dist * 2.5)

    def plot_field_lines(self):
        self.root = tk.Tk()
        self.root.title("BNO055 磁気マップ・ビジュアライザ (ライトモード/3D選択対応)")
        self.root.geometry("1080x720")
        self.root.minsize(920, 600)

        self.mode_var = tk.StringVar(value="2D")
        self.colormap_var = tk.StringVar(value="Viridis")
        self.autoscale_var = tk.BooleanVar(value=True)
        self.vector_show_2d_var = tk.BooleanVar(value=True)
        self.show_axes_3d_var = tk.BooleanVar(value=True)
        self.vector_scale_3d_var = tk.DoubleVar(value=0.1)
        self.min_ut_var = tk.DoubleVar(value=20.0)
        self.max_ut_var = tk.DoubleVar(value=100.0)

        self.apply_theme()
        self._build_ui()

        if self.data_file and os.path.exists(self.data_file):
            self._load_file(self.data_file)

        self.root.mainloop()

    def apply_theme(self):
        """UI全体のスタイルをライトモードに設定"""
        t = self.THEME
        self.root.configure(bg=t["BG_MAIN"])
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=t["BG_MAIN"], foreground=t["FG_MAIN"])
        style.configure("TFrame", background=t["BG_MAIN"])
        style.configure("Card.TFrame", background=t["BG_CARD"], relief="flat")
        style.configure("TLabel", background=t["BG_MAIN"], foreground=t["FG_MAIN"], font=("Helvetica", 10))
        style.configure("Card.TLabel", background=t["BG_CARD"], foreground=t["FG_MAIN"], font=("Helvetica", 9))
        style.configure("Header.TLabel", background=t["BG_CARD"], foreground=t["ACCENT"], font=("Helvetica", 11, "bold"))
        style.configure("Title.TLabel", background=t["BG_MAIN"], foreground=t["ACCENT"], font=("Helvetica", 16, "bold"))
        style.configure("TButton", background=t["BG_INPUT"], foreground=t["FG_MAIN"], borderwidth=0, font=("Helvetica", 9, "bold"))
        style.configure("Accent.TButton", background=t["ACCENT"], foreground="#ffffff")

    def _build_ui(self):
        t = self.THEME
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="磁気マッピング・ビジュアライザ", style="Title.TLabel").pack(anchor="w", pady=(0, 15))

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)

        left_panel = ttk.Frame(content_frame, width=340)
        left_panel.pack(side="left", fill="y", padx=(0, 20))
        left_panel.pack_propagate(False)

        right_panel = ttk.Frame(content_frame)
        right_panel.pack(side="right", fill="both", expand=True)

        # 1. 表示モード設定
        mode_card = ttk.Frame(left_panel, style="Card.TFrame", padding=12)
        mode_card.pack(fill="x", pady=(0, 10))
        ttk.Label(mode_card, text="表示モード設定", style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        
        row_mode = ttk.Frame(mode_card, style="Card.TFrame")
        row_mode.pack(fill="x", pady=2)
        for m in ["2D", "3D"]:
            tk.Radiobutton(
                row_mode, text=f"{m}モード", value=m, variable=self.mode_var,
                command=self.on_mode_change, font=("Helvetica", 9, "bold"),
                bg=t["BG_CARD"], activebackground=t["BG_CARD"]
            ).pack(side="left", padx=10)

        # 2. ファイル選択
        file_card = ttk.Frame(left_panel, style="Card.TFrame", padding=12)
        file_card.pack(fill="x", pady=(0, 10))
        ttk.Label(file_card, text="データファイル選択", style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Button(file_card, text="別のCSVを開く", command=self.load_csv_dialog, style="Accent.TButton").pack(fill="x", pady=2)
        self.file_label = ttk.Label(file_card, text="ファイル未選択", wraplength=280)
        self.file_label.pack(anchor="w", pady=(4, 0))

        # 3. 可視化設定
        color_card = ttk.Frame(left_panel, style="Card.TFrame", padding=12)
        color_card.pack(fill="x", pady=(0, 10))
        ttk.Label(color_card, text="可視化・カラーマップ設定", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(color_card, text="配色パターン:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.cmap_combo = ttk.Combobox(color_card, textvariable=self.colormap_var, values=["Viridis", "Modern Dark", "Rainbow", "Heat"], state="readonly", width=14)
        self.cmap_combo.grid(row=1, column=1, sticky="e", pady=3)
        self.cmap_combo.bind("<<ComboboxSelected>>", lambda e: self.redraw())

        self.chk_auto = tk.Checkbutton(color_card, text="オートスケール（自動調整）", variable=self.autoscale_var, command=self.redraw, bg=t["BG_CARD"])
        self.chk_auto.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        self.chk_vec2d = tk.Checkbutton(color_card, text="[2D] 磁気ベクトル（矢印）表示", variable=self.vector_show_2d_var, command=self.redraw, bg=t["BG_CARD"])
        self.chk_vec2d.grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        self.chk_axes3d = tk.Checkbutton(color_card, text="[3D] XYZガイド軸を表示", variable=self.show_axes_3d_var, command=self.redraw, bg=t["BG_CARD"])
        self.chk_axes3d.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)

        self.slider_vecscale3d = ttk.Scale(color_card, from_=0.01, to=2.0, variable=self.vector_scale_3d_var, command=lambda _: self.redraw())
        self.slider_vecscale3d.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(3, 8))

        ttk.Label(color_card, text="最小強度 (uT):", style="Card.TLabel").grid(row=6, column=0, sticky="w", pady=3)
        self.spin_min = tk.Spinbox(color_card, from_=0, to=1000, width=6, textvariable=self.min_ut_var, command=self.redraw)
        self.spin_min.grid(row=6, column=1, sticky="e", pady=3)

        ttk.Label(color_card, text="最大強度 (uT):", style="Card.TLabel").grid(row=7, column=0, sticky="w", pady=3)
        self.spin_max = tk.Spinbox(color_card, from_=1, to=10000, width=6, textvariable=self.max_ut_var, command=self.redraw)
        self.spin_max.grid(row=7, column=1, sticky="e", pady=3)

        # 4. データ概要と選択情報
        self.stats_card = ttk.Frame(left_panel, style="Card.TFrame", padding=12)
        self.stats_card.pack(fill="both", expand=True)
        ttk.Label(self.stats_card, text="データ概要", style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        self.stats_label = ttk.Label(self.stats_card, text="CSVファイルを読み込んでください。", wraplength=300)
        self.stats_label.pack(anchor="w", pady=2)

        ttk.Separator(self.stats_card, orient="horizontal").pack(fill="x", pady=10)
        
        ttk.Label(self.stats_card, text="選択中のベクトル情報", style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        self.selection_label = ttk.Label(self.stats_card, text="矢印またはセルをクリックしてください", font=("Consolas", 10), foreground=t["ACCENT"], justify="left")
        self.selection_label.pack(anchor="w", pady=2)

        # 右側キャンバス
        self.canvas_frame = ttk.Frame(right_panel, style="Card.TFrame", padding=8)
        self.canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bd=0, highlightthickness=0, bg=t["BG_INPUT"])
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)

        self.update_control_states()

    def update_control_states(self):
        is_2d = (self.mode_var.get() == "2D")
        state = "normal" if is_2d else "disabled"
        self.chk_vec2d.configure(state=state)
        
        state3d = "disabled" if is_2d else "normal"
        self.chk_axes3d.configure(state=state3d)
        self.slider_vecscale3d.configure(state=state3d)
        
        if is_2d:
            self.update_cell_info_label()
        else:
            self.update_3d_selection_info()

    def on_mode_change(self):
        self.update_control_states()
        self.redraw()

    def get_color(self, val):
        if self.autoscale_var.get():
            if not self.measuring_data_3d: return self.THEME["BG_INPUT"]
            vals = [d["b_total"] for d in self.measuring_data_3d]
            min_val, max_val = min(vals), max(vals)
            self.min_ut_var.set(round(min_val, 1))
            self.max_ut_var.set(round(max_val, 1))
        else:
            min_val, max_val = self.min_ut_var.get(), self.max_ut_var.get()

        v = 0.5 if max_val == min_val else (val - min_val) / (max_val - min_val)
        v = max(0.0, min(1.0, v))
        cmap = self.colormap_var.get()

        if cmap == "Viridis": stops = [(0.0, (68, 1, 84)), (0.33, (49, 104, 142)), (0.66, (53, 183, 121)), (1.0, (253, 231, 37))]
        elif cmap == "Modern Dark": stops = [(0.0, (49, 18, 77)), (0.25, (0, 180, 216)), (0.5, (57, 255, 20)), (0.75, (255, 121, 0)), (1.0, (255, 0, 127))]
        elif cmap == "Heat": stops = [(0.0, (20, 0, 30)), (0.33, (200, 20, 20)), (0.66, (255, 160, 0)), (1.0, (255, 255, 220))]
        else:
            h = 240.0 * (1.0 - v)
            c = 0.95 * 0.85
            x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
            m = 0.95 - c
            if 0 <= h < 60: r, g, b = c, x, 0
            elif 60 <= h < 120: r, g, b = x, c, 0
            elif 120 <= h < 180: r, g, b = 0, c, x
            elif 180 <= h < 240: r, g, b = 0, x, c
            else: r, g, b = c, 0, c
            return f"#{int((r+m)*255):02x}{int((g+m)*255):02x}{int((b+m)*255):02x}"

        for i in range(len(stops) - 1):
            t1, c1 = stops[i]
            t2, c2 = stops[i+1]
            if t1 <= v <= t2:
                ratio = (v - t1) / (t2 - t1) if t2 > t1 else 0.0
                r = int(c1[0] + ratio * (c2[0] - c1[0]))
                g = int(c1[1] + ratio * (c2[1] - c1[1]))
                b = int(c1[2] + ratio * (c2[2] - c1[2]))
                return f"#{r:02x}{g:02x}{b:02x}"
        return f"#{stops[-1][1][0]:02x}{stops[-1][1][1]:02x}{stops[-1][1][2]:02x}"

    def redraw(self):
        if self.mode_var.get() == "2D": self.draw_2d_grid()
        else: self.draw_3d_scene()

    def draw_2d_grid(self):
        self.canvas.delete("all")
        t = self.THEME

        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1 or h <= 1 or not self.measuring_data_2d: return

        self.cell_w, self.cell_h = w / self.cols, h / self.rows

        for r in range(self.rows):
            for c in range(self.cols):
                x1, y1 = c * self.cell_w, r * self.cell_h
                x2, y2 = (c + 1) * self.cell_w, (r + 1) * self.cell_h

                fill_col = t["BG_INPUT"]
                if (r, c) in self.measuring_data_2d:
                    fill_col = self.get_color(self.measuring_data_2d[(r, c)]["b_total"])

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill_col, outline=t["GRID_BORDER"])

                if self.vector_show_2d_var.get() and (r, c) in self.measuring_data_2d:
                    d = self.measuring_data_2d[(r, c)]
                    b_horiz = math.sqrt(d["bx"]**2 + d["by"]**2)
                    if b_horiz > 1e-4:
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                        arrow_len = max(5.0, min(1.0, b_horiz / 100.0) * min(self.cell_w, self.cell_h) * 0.4)
                        self.canvas.create_line(cx, cy, cx + (d["bx"]/b_horiz)*arrow_len, cy - (d["by"]/b_horiz)*arrow_len, arrow=tk.LAST, fill="#ffffff", width=2)

        # 2D選択枠
        if self.measuring_data_2d:
            r, c = self.selected_cell
            self.canvas.create_rectangle(c*self.cell_w+2, r*self.cell_h+2, (c+1)*self.cell_w-2, (r+1)*self.cell_h-2, outline=t["SELECTION"], width=3)

    def draw_3d_scene(self):
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1 or h <= 1 or not self.measuring_data_3d: return

        self.camera.center_x, self.camera.center_y = w / 2, h / 2
        render_list = []

        if self.show_axes_3d_var.get():
            px0, py0, z0 = self.camera.project(0, 0, 0)
            for ax, ay, az, col in [(5,0,0,"#ff3b30"), (0,5,0,"#34c759"), (0,0,5,"#007aff")]:
                px, py, z1 = self.camera.project(ax, ay, az)
                render_list.append({'type': 'axis', 'depth': (z0+z1)/2, 'x1': px0, 'y1': py0, 'x2': px, 'y2': py, 'color': col})

        scale = self.vector_scale_3d_var.get()
        for i, d in enumerate(self.measuring_data_3d):
            px1, py1, z1 = self.camera.project(d['x'], d['y'], d['z'])
            px2, py2, z2 = self.camera.project(d['x'] + d['bx']*scale, d['y'] + d['by']*scale, d['z'] + d['bz']*scale)
            
            render_list.append({
                'type': 'vector', 'depth': (z1+z2)/2,
                'x1': px1, 'y1': py1, 'x2': px2, 'y2': py2, 
                'color': self.get_color(d['b_total']), 'b_total': d['b_total'],
                'is_selected': (i == self.selected_3d_index)
            })

        render_list.sort(key=lambda item: item['depth'], reverse=True)

        for item in render_list:
            if item['depth'] <= 0.2: continue
            if item['type'] == 'axis':
                self.canvas.create_line(item['x1'], item['y1'], item['x2'], item['y2'], fill=item['color'], width=2, arrow=tk.LAST, dash=(4, 4))
            elif item['type'] == 'vector':
                min_v, max_v = self.min_ut_var.get(), self.max_ut_var.get()
                mag_ratio = max(0.4, min(2.5, 0.4 + 1.6 * ((item['b_total'] - min_v) / (max_v - min_v)) if max_v > min_v else 1.0))
                depth_scale = max(0.5, min(4.0, 30.0 / item['depth']))
                thickness = max(1.0, 2.0 * depth_scale * mag_ratio)

                self.canvas.create_line(item['x1'], item['y1'], item['x2'], item['y2'], fill=item['color'], width=thickness, arrow=tk.LAST, 
                                        arrowshape=(int(10*depth_scale*mag_ratio), int(12*depth_scale*mag_ratio), int(4*depth_scale*mag_ratio)))
                
                # ドットの描画とハイライト
                r = thickness * 1.5
                self.canvas.create_oval(item['x1']-r, item['y1']-r, item['x1']+r, item['y1']+r, fill=item['color'], outline="")
                
                if item.get('is_selected'):
                    r_high = r + 4
                    self.canvas.create_oval(item['x1']-r_high, item['y1']-r_high, item['x1']+r_high, item['y1']+r_high, outline=self.THEME["HIGHLIGHT"], width=2)

    def on_mouse_press(self, event):
        if self.mode_var.get() == "2D":
            if not self.measuring_data_2d: return
            c, r = int(event.x / self.cell_w), int(event.y / self.cell_h)
            if 0 <= c < self.cols and 0 <= r < self.rows:
                self.selected_cell = (r, c)
                self.draw_2d_grid()
                self.update_cell_info_label()
        else:
            self.last_mouse_x, self.last_mouse_y = event.x, event.y
            if not self.measuring_data_3d: return
            
            # ヒットテスト（クリックした位置に近い矢印を探す）
            min_dist_sq = 225  # 半径15ピクセル以内
            best_idx = -1
            for i, d in enumerate(self.measuring_data_3d):
                px, py, z = self.camera.project(d['x'], d['y'], d['z'])
                if z <= 0.2: continue
                dist_sq = (event.x - px)**2 + (event.y - py)**2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    best_idx = i
            
            self.selected_3d_index = best_idx if best_idx != -1 else None
            self.update_3d_selection_info()
            self.draw_3d_scene()

    def on_mouse_drag(self, event):
        if self.mode_var.get() == "3D":
            self.camera.rotate(event.x - self.last_mouse_x, event.y - self.last_mouse_y)
            self.last_mouse_x, self.last_mouse_y = event.x, event.y
            self.draw_3d_scene()

    def on_mouse_wheel(self, event):
        if self.mode_var.get() == "3D":
            self.camera.zoom(-1 if event.num == 4 or event.delta > 0 else 1)
            self.draw_3d_scene()

    def update_cell_info_label(self):
        r, c = self.selected_cell
        data = self.measuring_data_2d.get((r, c))
        if data:
            self.selection_label.configure(text=f"【2D】セル({c}, {r})\n Bx: {data['bx']:.1f}, By: {data['by']:.1f}, Bz: {data['bz']:.1f}\n 総強度: {data['b_total']:.2f} uT")
        else:
            self.selection_label.configure(text=f"【2D】セル({c}, {r})\n データ無し")

    def update_3d_selection_info(self):
        if self.selected_3d_index is not None and 0 <= self.selected_3d_index < len(self.measuring_data_3d):
            d = self.measuring_data_3d[self.selected_3d_index]
            self.selection_label.configure(
                text=f"位置: X:{d['orig_x']:.1f}, Y:{d['orig_y']:.1f}, Z:{d['orig_z']:.1f}\n"
                     f"成分: Bx:{d['bx']:.1f}, By:{d['by']:.1f}, Bz:{d['bz']:.1f}\n"
                     f"強度: {d['b_total']:.2f} uT"
            )
        else:
            self.selection_label.configure(text="矢印をクリックして\n情報を表示します")

    def _load_file(self, file_path):
        try:
            self._parse_csv(file_path)
            self.file_label.configure(text=os.path.basename(file_path))
            self.selected_cell = (0, 0)
            self.selected_3d_index = None
            
            vals = [d["b_total"] for d in self.measuring_data_3d]
            self.stats_label.configure(text=f"データ数: {len(vals)} 空間点\n最大: {max(vals):.1f} / 最小: {min(vals):.1f} uT")
            
            self.update_control_states()
            self.redraw()
        except Exception as e:
            messagebox.showerror("エラー", f"読込失敗: {e}")

    def load_csv_dialog(self):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if p: self._load_file(p)

if __name__ == "__main__":
    app = UnifiedMagneticVisualizer()
    app.plot_field_lines()