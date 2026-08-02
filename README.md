# PDF黒塗りツール

情報公開請求に対応するために、開示する PDF の該当箇所を**黒塗り（墨塗り）**して
保存するデスクトップツールです。役所の職員が使用することを想定しています。

単に見た目に黒い矩形を重ねるのではなく、保存時に PyMuPDF の
`add_redact_annot()` + `apply_redactions()` を使って**黒塗り領域の
テキスト・画像を PDF から物理的に削除**します。保存後の PDF から
テキスト抽出しても、黒塗り部分の中身が取り出されることはありません。

## すぐ使う（推奨）

Python 環境を用意せず、ビルド済みの配布物を**ダウンロードしてダブルクリック**するだけで使えます。

### Windows

1. GitHub Releases から **`pdf-redact.exe`** をダウンロードします。
2. ダウンロードした `pdf-redact.exe` を**ダブルクリック**して起動します。

インストールは不要です。

### macOS

1. GitHub Releases から **`pdf-redact-macos.zip`** をダウンロードします。
2. zip を解凍すると **`pdf-redact.app`** が現れます。
3. `pdf-redact.app` を**ダブルクリック**して起動します。

> **初回起動時**: コード署名をしていないアプリのため、初回は「開発元を
> 確認できないため開けません」と表示される場合があります。その場合は
> `pdf-redact.app` を**右クリック →「開く」** を選び、確認ダイアログで
> **「開く」** をクリックすると起動できます（2 回目以降はダブルクリックで
> 起動できます）。

## 動作環境

- **配布版（`pdf-redact.exe` / `pdf-redact.app`）**
  - OS: Windows 10 / 11（64bit）
  - macOS 12 以上（Apple Silicon / Intel）
  - インストール不要、ダブルクリックで起動
- **開発者向け（Python で直接実行）**
  - Python 3.9 以上（3.9+ の構文のみを使用）
  - OS: Windows / macOS / Linux（Linux は Python 環境での実行のみ対応）
  - 依存ライブラリ: **PyMuPDF（pymupdf）のみ**
  - GUI は標準ライブラリの tkinter を使用（PyQt 等は不要）

## 開発者向け: インストール（Python 環境）

仮想環境（venv）を作成し、PyMuPDF をインストールします。

### Windows (PowerShell)

```powershell
cd pdf-redact
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

### macOS / Linux

```bash
cd pdf-redact
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

> **注意**: macOS / Linux の場合、システムの Python に tkinter が含まれていない
> ことがあります（例: Ubuntu の `python3`）。その場合は以下のパッケージを
> インストールしてください。
>
> - Ubuntu/Debian: `sudo apt install python3-tk`
> - Fedora: `sudo dnf install python3-tkinter`
>
> macOS の場合は [python.org](https://www.python.org/) のインストーラ版
> Python を使うと tkinter が同梱されています。

## 起動方法

```bash
python3 redact.py    # Windows では: python redact.py
```

## 使い方

1. **「PDFを開く」** ボタンで黒塗りしたい PDF を選択します。
2. ページが表示されるので、**マウスをドラッグ**して黒塗り範囲（黒い矩形）を
   指定します。複数箇所・複数ページに指定できます。
3. ページは **「前のページ」「次のページ」** ボタン（または ← / → キー）で
   移動します。
4. 誤って描いた矩形は次のどちらかで削除します。
   - 矩形を**クリックして選択**（赤枠で表示）→ **Delete キー**（または BackSpace キー）
   - 矩形を**ダブルクリック**
5. **「保存」** ボタンで、黒塗りを適用した PDF を**別名で保存**します。
   保存前に確認ダイアログが表示されます。
   - 元の PDF ファイルは変更されません。
   - 保存時、黒塗り領域に含まれるテキスト・画像が PDF から物理的に削除されます。

### ショートカットキー

| キー | 動作 |
| --- | --- |
| ← / → | 前のページ / 次のページ |
| Delete / BackSpace | 選択中の黒塗り矩形を削除 |
| Ctrl+O | PDFを開く |
| Ctrl+S | 保存 |

## 仕組み

- `redact_core.py`: PyMuPDF を使った黒塗りロジック（GUI 非依存）。
  - `apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)` を指定し、
    黒塗り領域と交差する**画像も物理的に削除**します。
  - 保存時は `garbage=4` を指定し、削除されたテキスト・画像の残骸
    （未参照オブジェクト）をファイルから取り除きます。
  - スキャン画像 PDF（テキストなし）でも、ドラッグで指定した領域を
    画像ごと削除できるため対応可能です。
- `redact.py`: tkinter による GUI。ページをピクセルマップにレンダリングして
  Canvas に表示し、マウス座標を PDF 座標に変換して黒塗り矩形を管理します。
- `test_redact.py`: 検証スクリプト（下記参照）。

## 動作テスト

サンプル PDF（テキスト入り・画像入り）を生成し、黒塗り適用後に
テキスト抽出して「黒塗り箇所の中身が消えていること」「黒塗り外の
テキストが残っていること」「画像が削除されていること」を検証します。

```bash
python3 test_redact.py
```

## 制限事項・注意

- **パスワード付き PDF** は開けません。事前にパスワードを解除してください。
- 壊れた PDF・PDF 形式でないファイルを開こうとすると、日本語の
  エラーメッセージを表示します。
- 元ファイルは上書きせず、常に別名で保存します。
- 黒塗りは「領域と交差するテキスト行・画像」を対象に削除するため、
  行の一部が領域に掛かった場合もその行全体が削除されます。また
  画像の一部だけを黒塗りした場合も、その画像**全体**が削除されます
  （いずれも情報漏えいを防ぐため安全側に働きます）。行内の一部の
  文字だけを残したい場合は、黒塗り範囲を細かく指定してください。

## ファイル構成

```
redact.py         tkinter GUI アプリ本体（エントリポイント）
redact_core.py    PyMuPDF を使った黒塗りロジック（GUI 非依存）
test_redact.py    検証スクリプト
requirements.txt  依存ライブラリ（pymupdf）
build.spec        PyInstaller のビルド設定（exe / .app 生成用）
.github/          ビルド・リリース用の GitHub Actions ワークフロー
README.md         このファイル
```
