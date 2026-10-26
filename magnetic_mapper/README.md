# Magnetic Field Mapper (磁力線マッピングシステム)

このプロジェクトは、Raspberry Piに接続された磁気センサー（BNO055など）から取得した磁束密度データと、測定した位置情報を紐づけて記録し、3次元空間上に磁力線や磁場をマッピング・可視化するためのシステムです。

---

## 📂 フォルダ・ファイル構成

* `magnetic_mapper/`
  * `data/` : 測定したCSVデータやキャリブレーション結果の保存先。
  * `src/` : ソースコードディレクトリ。
    * `sensor.py` : センサー制御・データ取得処理。
    * `recorder.py` : 位置と磁気データの記録処理。
    * `visualizer.py` : 磁力線やベクトル場の可視化処理。
  * `main.py` : プログラムのメイン実行ファイル（エントリーポイント）。
  * `requirements.txt` : 動作に必要なライブラリ一覧。
  * `README.md` : この説明ファイル。

---

## 🔌 動作環境と接続方法

### 必要ハードウェア
* Raspberry Pi
* 9軸慣性センサ BNO055 (I2C接続)

### 接続 (I2C)
* VCC -> 3.3V
* GND -> GND
* SDA -> SDA (GPIO2)
* SCL -> SCL (GPIO3)

---

## 🛠️ セットアップ手順

1. Raspberry PiのI2C通信を有効化します。
2. 必要な依存ライブラリをインストールします。
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 使い方

`main.py` はコマンドライン引数による直接実行および対話式メニューに対応しています。

### 0. 対話メニューで起動（初心者向け）
引数なしで実行するとメニューが表示され、キーボード選択で各機能を実行できます。
```bash
python main.py
```

### 1. センサーのキャリブレーション確認
測定前にBNO055のキャリブレーション状態（Sys/Gyro/Accel/Mag: 0〜3）を確認します。
```bash
python main.py calibrate
# または: python main.py --mode calibrate
```

### 2. データの測定・記録 (Record)
位置情報と紐づけて磁束密度を測定し、CSVに記録します。途中で中断したい場合は `Ctrl+C` を押すと安全に保存を完了します。

- **慣性航法（デッドレコニング）モード**（推奨: 加速度・姿勢クォータニオンから位置を自動推定）:
  ```bash
  python main.py record
  # または: python main.py --mode record
  ```
- **グリッド走査モード**（指定した列×行のグリッド上を走査）:
  ```bash
  python main.py record -t grid --cols 10 --rows 10
  ```
- **マニュアル測定モード**（Enterキーを押すたびに1点サンプリング）:
  ```bash
  python main.py record -t manual
  ```
- **オプション指定例**（サンプル数変更、出力ファイル指定、モック実行）:
  ```bash
  python main.py record -o data/my_experiment.csv -s 10 --mock
  ```

### 3. リアルタイム・センサーモニター (Monitor)
現在の磁束密度・加速度・クォータニオン・推定位置をリアルタイムにターミナル表示します。
```bash
python main.py monitor
```

### 4. 磁力線の可視化 (Visualize)
記録されたCSVデータを読み込み、2Dヒートマップおよび3D磁力線ベクトル場として可視化します。
```bash
python main.py visualize
# または: python main.py --mode visualize

# 任意のCSVファイルを指定して可視化:
python main.py visualize -f data/my_experiment.csv
```
※ SSH接続等でGUI画面がない場合は、コンソール上にデータサマリーが表示されます。


---

## 📊 記録データのフォーマット (data/magnetic_data.csv)

保存されるデータは以下のカラム（ヘッダー）を持つCSVファイルを想定しています。

| カラム名 | 説明 | 単位 |
| :--- | :--- | :--- |
| `timestamp` | 測定した時間（UNIX時間など） | 秒 |
| `x_pos` | 測定した空間上のX座標 | mm または m |
| `y_pos` | 測定した空間上のY座標 | mm または m |
| `z_pos` | 測定した空間上のZ座標 | mm または m |
| `mag_x` | X軸方向の磁束密度 | $\mu\text{T}$ (マイクロテスラ) |
| `mag_y` | Y軸方向 of 磁束密度 | $\mu\text{T}$ (マイクロテスラ) |
| `mag_z` | Z軸方向 of 磁束密度 | $\mu\text{T}$ (マイクロテスラ) |
