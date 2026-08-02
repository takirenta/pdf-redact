#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 黒塗りツール (tkinter GUI)。

情報公開請求対応のための PDF 黒塗りツール。
- PDF を開く / ページをめくる
- マウスドラッグで黒塗り範囲 (黒い矩形) を指定 (複数可)
- 矩形をクリックして選択し Delete キーで削除 (ダブルクリックでも削除)
- 保存時: redact_core により黒塗り領域のテキスト・画像を物理的に削除

依存: 標準ライブラリ tkinter と PyMuPDF (fitz) のみ。
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import redact_core as core


class RedactApp:
    """メインアプリケーション。"""

    def __init__(self, root):
        self.root = root
        root.title("PDF黒塗りツール")

        self.doc = None          # 編集中のドキュメント (fitz.Document)
        self.path = None         # 元ファイルのパス
        self.page_index = 0      # 表示中のページ番号
        self.redactions = {}     # {page_index: [fitz.Rect, ...]} 黒塗り矩形
        self.scale = 1.0         # 表示スケール (キャンバス px / PDF pt)
        self.photo = None        # PhotoImage の参照保持 (GC 対策)
        self.rect_items = {}     # {canvas_item_id: redactions 内の index}
        self.selected_item = None  # 選択中の矩形の canvas item id
        self.drag_start = None   # ドラッグ開始位置 (x, y)
        self.draft_item = None   # ドラッグ中プレビュー矩形の item id
        self._drag_moved = False
        self._last_size = (0, 0)

        self._build_ui()

    # ---------- UI 構築 ----------

    def _build_ui(self):
        # 上部: 操作ボタン
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        tk.Button(top, text="PDFを開く", command=self.open_pdf,
                  width=12).pack(side=tk.LEFT)
        tk.Button(top, text="保存", command=self.save,
                  width=10).pack(side=tk.LEFT, padx=6)
        tk.Label(
            top,
            text="ドラッグで黒塗り範囲を指定 / クリックで選択して Delete で削除",
            fg="gray20",
        ).pack(side=tk.LEFT, padx=12)

        # 中央: ページ表示キャンバス
        self.canvas = tk.Canvas(self.root, bg="#404040", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 下部: ページナビゲーション
        bottom = tk.Frame(self.root)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=6)
        tk.Button(bottom, text="前のページ", command=self.prev_page,
                  width=12).pack(side=tk.LEFT)
        tk.Button(bottom, text="次のページ", command=self.next_page,
                  width=12).pack(side=tk.LEFT, padx=6)
        self.page_label = tk.Label(bottom, text="")
        self.page_label.pack(side=tk.LEFT, padx=12)

        # マウス / キーボードイベント
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.root.bind("<Delete>", self.on_delete_key)
        self.root.bind("<BackSpace>", self.on_delete_key)
        self.root.bind("<Left>", lambda e: self.prev_page())
        self.root.bind("<Right>", lambda e: self.next_page())
        self.root.bind("<Control-o>", lambda e: self.open_pdf())
        self.root.bind("<Control-s>", lambda e: self.save())

        self.draw_page()

    # ---------- ファイル操作 ----------

    def open_pdf(self):
        path = filedialog.askopenfilename(
            title="PDFファイルを選択",
            filetypes=[("PDFファイル", "*.pdf"), ("すべてのファイル", "*.*")],
        )
        if not path:
            return
        try:
            doc = core.open_pdf(path)
        except core.RedactError as exc:
            messagebox.showerror("エラー", exc.message, parent=self.root)
            return
        if self.doc is not None:
            self.doc.close()
        self.doc = doc
        self.path = path
        self.page_index = 0
        self.redactions = {}
        self.root.title("PDF黒塗りツール - %s" % os.path.basename(path))
        self.draw_page()

    def save(self):
        if self.doc is None:
            messagebox.showwarning("保存", "先に PDF を開いてください。",
                                   parent=self.root)
            return
        if not self.redactions:
            if not messagebox.askyesno(
                    "保存",
                    "黒塗り範囲が指定されていません。\n"
                    "このまま黒塗りなしの PDF を保存しますか？",
                    parent=self.root):
                return
        initial = os.path.basename(self.path or "redacted.pdf")
        out_path = filedialog.asksaveasfilename(
            title="黒塗りPDFの保存先を選択",
            defaultextension=".pdf",
            filetypes=[("PDFファイル", "*.pdf")],
            initialfile=initial,
        )
        if not out_path:
            return
        if os.path.abspath(out_path) == os.path.abspath(self.path):
            messagebox.showerror(
                "保存",
                "元のファイルと同じパスには保存できません。\n"
                "別の名前を指定してください。",
                parent=self.root)
            return
        if not messagebox.askyesno(
                "保存",
                "黒塗りを適用した PDF を保存しますか？\n\n%s" % out_path,
                parent=self.root):
            return
        try:
            core.save_redacted(self.doc, self.redactions, out_path)
        except core.RedactError as exc:
            messagebox.showerror("保存エラー", exc.message, parent=self.root)
            return
        messagebox.showinfo("保存完了", "保存しました。\n%s" % out_path,
                            parent=self.root)

    # ---------- ページ表示 ----------

    def draw_page(self):
        """現在のページをキャンバスに描画する (ページ画像 + 黒塗り矩形)。"""
        self.canvas.delete("all")
        self.rect_items = {}
        self.selected_item = None
        if self.doc is None:
            self.page_label.config(text="PDFを開いてください")
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        try:
            png, self.scale = core.render_page(
                self.doc, self.page_index, (cw, ch))
        except core.RedactError as exc:
            messagebox.showerror("エラー", exc.message, parent=self.root)
            return
        self.photo = tk.PhotoImage(data=png)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        # 既存の黒塗り矩形を描画
        for idx, rect in enumerate(self.redactions.get(self.page_index, ())):
            item = self.canvas.create_rectangle(
                rect.x0 * self.scale, rect.y0 * self.scale,
                rect.x1 * self.scale, rect.y1 * self.scale,
                fill="black", outline="")
            self.rect_items[item] = idx
        self.page_label.config(
            text="%d / %d ページ" % (self.page_index + 1, len(self.doc)))

    def on_canvas_configure(self, event):
        """キャンバスサイズ変更時に再描画 (ドラッグ中は無視)。"""
        size = (event.width, event.height)
        if size == self._last_size or self.drag_start is not None:
            return
        self._last_size = size
        if self.doc is not None:
            self.draw_page()

    def prev_page(self):
        if self.doc is None or self.page_index <= 0:
            return
        self.page_index -= 1
        self.draw_page()

    def next_page(self):
        if self.doc is None or self.page_index >= len(self.doc) - 1:
            return
        self.page_index += 1
        self.draw_page()

    # ---------- 黒塗り矩形の操作 ----------

    def on_press(self, event):
        if self.doc is None:
            return
        self.drag_start = (event.x, event.y)
        self._drag_moved = False

    def on_drag(self, event):
        if self.drag_start is None or self.doc is None:
            return
        if (abs(event.x - self.drag_start[0]) > 3
                or abs(event.y - self.drag_start[1]) > 3):
            self._drag_moved = True
        if not self._drag_moved:
            return
        x0, y0 = self.drag_start
        # プレビュー: 枠線 + 半透明風 (stipple) の塗り
        if self.draft_item is None:
            self.draft_item = self.canvas.create_rectangle(
                x0, y0, x0, y0, outline="red", width=2,
                fill="gray", stipple="gray50")
        self.canvas.coords(self.draft_item, x0, y0, event.x, event.y)

    def on_release(self, event):
        if self.drag_start is None or self.doc is None:
            return
        if self._drag_moved:
            self._finish_rect(event.x, event.y)
        else:
            self._handle_click(event.x, event.y)
        if self.draft_item is not None:
            self.canvas.delete(self.draft_item)
            self.draft_item = None
        self.drag_start = None

    def on_double_click(self, event):
        """ダブルクリックした矩形を削除する。"""
        if self.doc is None:
            return
        item = self._find_rect_at(event.x, event.y)
        if item is not None:
            self._delete_item(item)

    def on_delete_key(self, event=None):
        """選択中の矩形を削除する (Delete / BackSpace キー)。"""
        if self.doc is None or self.selected_item is None:
            return
        self._delete_item(self.selected_item)

    def _finish_rect(self, x1, y1):
        """ドラッグ終了: 矩形を確定し黒塗りリストに追加する。"""
        x0, y0 = self.drag_start
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if x1 - x0 < 3 or y1 - y0 < 3:
            return  # 小さすぎるドラッグは矩形としない
        rect = core.to_pdf_rect(x0, y0, x1, y1, self.scale)
        rect = core.clip_to_page(rect, self.doc[self.page_index])
        if rect.is_empty:
            return
        rects = self.redactions.setdefault(self.page_index, [])
        rects.append(rect)
        item = self.canvas.create_rectangle(
            rect.x0 * self.scale, rect.y0 * self.scale,
            rect.x1 * self.scale, rect.y1 * self.scale,
            fill="black", outline="")
        self.rect_items[item] = len(rects) - 1
        self._select_item(item)

    def _handle_click(self, x, y):
        """クリック: 矩形があれば選択、なければ選択解除。"""
        item = self._find_rect_at(x, y)
        self._select_item(item)

    def _find_rect_at(self, x, y):
        """座標 (x, y) にある黒塗り矩形の canvas item を返す (なければ None)。"""
        for item in self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2):
            if item in self.rect_items:
                return item
        return None

    def _select_item(self, item):
        """矩形の選択状態を更新する (選択中は赤枠表示)。"""
        if self.selected_item is not None:
            self.canvas.itemconfig(self.selected_item, outline="", width=1)
        self.selected_item = item
        if item is not None:
            self.canvas.itemconfig(item, outline="red", width=3)

    def _delete_item(self, item):
        """指定した canvas item に対応する黒塗り矩形を削除する。"""
        if item not in self.rect_items:
            return
        idx = self.rect_items[item]
        page_index = self.page_index  # 矩形は表示中ページのもののみ
        del self.redactions[page_index][idx]
        if not self.redactions[page_index]:
            del self.redactions[page_index]
        self.draw_page()


def main():
    root = tk.Tk()
    root.minsize(640, 480)
    root.geometry("960x1080")
    RedactApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
