# 編集禁止ファイル・フォルダの制御ルール

このファイルは、AIアシスタント（Antigravity）がファイルを編集する際の制限をユーザー名ごとに切り替えるためのものです。

## Rules

- **実行中のPCユーザー名が `yasu`（全体統合・統括担当）の場合**:
  - 他のメンバーが開発する以下のファイルはAIによる編集を禁止します（読み取りのみ可能）。
    - `magnetic_mapper/src/sensor.py`
    - `magnetic_mapper/src/recorder.py`
    - `magnetic_mapper/src/visualizer.py`
  - `testcode/` ディレクトリ配下のすべてのファイルは編集禁止です。
  - ※ 統合作業時に一時的にAIに編集させたい場合は、このルールを一時的に外すか個別に指示してください。

- **実行中のPCユーザー名が `user`（センサー担当）の場合**:
  - 担当外の以下のファイルはAIによる編集を禁止します（読み取りのみ可能）。
    - `magnetic_mapper/src/recorder.py`
    - `magnetic_mapper/src/visualizer.py`
    - `magnetic_mapper/main.py`
    - `testcode/` ディレクトリ配下のすべてのファイル

- **実行中のPCユーザー名が `sato6`（データ記録担当）の場合**:
  - 担当外の以下のファイルはAIによる編集を禁止します（読み取りのみ可能）。
    - `magnetic_mapper/src/sensor.py`
    - `magnetic_mapper/src/visualizer.py`
    - `magnetic_mapper/main.py`
    - `testcode/` ディレクトリ配下のすべてのファイル

- **実行中のPCユーザー名が `kentaro`（データ可視化担当）の場合**:
  - 担当外の以下のファイルはAIによる編集を禁止します（読み取りのみ可能）。
    - `magnetic_mapper/src/sensor.py`
    - `magnetic_mapper/src/recorder.py`
    - `magnetic_mapper/main.py`
    - `testcode/` ディレクトリ配下のすべてのファイル

- **すべてのユーザーに共通するルール**:
  - ルールファイル自体（`.agents/AGENTS.md`）はユーザーの指示がない限り編集しないでください。

