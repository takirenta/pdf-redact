#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redact_core の検証スクリプト。

サンプル PDF (テキスト入り・画像入り) を生成し、
redact_core で黒塗りした後の PDF からテキスト抽出を行い、
黒塗り箇所のテキストが「絶対に出てこない」こと、黒塗り外の
テキストは残ること、画像が削除されることを assert する。

実行方法: python3 test_redact.py
"""

import os
import tempfile
import unittest

import fitz  # PyMuPDF

import redact_core as core

SECRET_A = "秘密情報A: 個人の氏名と住所"
SECRET_B = "秘密情報B: 連絡先電話番号"
PUBLIC_1 = "公開してよい情報: 会議の開催日時"
PUBLIC_2 = "公開してよい情報: 担当部署"
PUBLIC_3 = "末尾の公開情報"


def _new_doc(width=595, height=842):
    """A4 サイズの空ドキュメントを返す。"""
    doc = fitz.open()
    doc.new_page(width=width, height=height)
    return doc


def make_text_pdf(path):
    """テキスト入りサンプル PDF を生成する。

    行のベースライン y: 100 / 160 / 220 / 280 / 600
    黒塗り対象は y=160 と y=220 の行 (秘密情報A・B)。
    """
    doc = _new_doc()
    page = doc[0]
    page.insert_text((72, 100), PUBLIC_1, fontname="japan")
    page.insert_text((72, 160), SECRET_A, fontname="japan")
    page.insert_text((72, 220), SECRET_B, fontname="japan")
    page.insert_text((72, 280), PUBLIC_2, fontname="japan")
    page.insert_text((72, 600), PUBLIC_3, fontname="japan")
    doc.save(path)
    doc.close()


def make_image_pdf(path):
    """画像 (赤い矩形) 入りサンプル PDF を生成する。

    画像領域: Rect(50, 150, 250, 270)。周囲に公開テキストを配置。
    """
    doc = _new_doc()
    page = doc[0]
    page.insert_text((72, 100), PUBLIC_1, fontname="japan")
    page.insert_text((72, 320), PUBLIC_2, fontname="japan")
    w, h = 200, 120
    samples = bytearray()
    for _ in range(w * h):
        samples += bytes((200, 30, 30))  # 赤一色
    pixmap = fitz.Pixmap(fitz.csRGB, w, h, bytes(samples), False)
    page.insert_image(fitz.Rect(50, 150, 250, 270), pixmap=pixmap)
    doc.save(path)
    doc.close()


def make_multi_page_pdf(path):
    """3 ページ構成のサンプル PDF を生成する (ページ2のみに秘密情報)。"""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "ページ%d の公開情報" % (i + 1),
                         fontname="japan")
        if i == 1:
            page.insert_text((72, 160), SECRET_A, fontname="japan")
    doc.save(path)
    doc.close()


def make_password_pdf(path):
    """パスワード付きサンプル PDF を生成する。"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), SECRET_A, fontname="japan")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw="testpass", owner_pw="ownerpass")
    doc.close()


def make_broken_pdf(path):
    """壊れたファイル (PDF 形式でない) を生成する。"""
    with open(path, "wb") as f:
        f.write(b"this is not a pdf file at all %%%%")


class RedactCoreTest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="redact_test_")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _path(self, name):
        return os.path.join(self.tmpdir, name)

    # ---------- テキスト黒塗り ----------

    def test_text_redaction_removes_only_covered_text(self):
        src = self._path("text.pdf")
        out = self._path("redacted.pdf")
        make_text_pdf(src)

        doc = core.open_pdf(src)
        try:
            page = doc[0]
            # 秘密情報A・B の行を覆う黒塗り矩形 (y=140..270 の帯)
            rects = [
                fitz.Rect(40, 140, 555, 200),
                fitz.Rect(40, 200, 555, 260),
            ]
            core.save_redacted(doc, {0: rects}, out)
        finally:
            doc.close()

        with core.open_pdf(out) as doc2:
            text = doc2[0].get_text()

        # 黒塗り箇所のテキストは絶対に出てこない
        self.assertNotIn(SECRET_A, text)
        self.assertNotIn(SECRET_B, text)
        # 黒塗り外のテキストは残っている
        self.assertIn(PUBLIC_1, text)
        self.assertIn(PUBLIC_2, text)
        self.assertIn(PUBLIC_3, text)

    def test_original_file_is_not_modified(self):
        """元ファイルは変更されず、保存は別ファイルになること。"""
        src = self._path("text.pdf")
        out = self._path("redacted.pdf")
        make_text_pdf(src)
        with open(src, "rb") as f:
            before = f.read()

        doc = core.open_pdf(src)
        try:
            core.save_redacted(doc, {0: [fitz.Rect(40, 140, 555, 200)]}, out)
        finally:
            doc.close()

        with open(src, "rb") as f:
            after = f.read()
        self.assertEqual(before, after)
        self.assertTrue(os.path.exists(out))

    def test_redaction_is_black_on_page(self):
        """保存後の PDF の黒塗り領域が黒く焼き込まれていること。"""
        src = self._path("text.pdf")
        out = self._path("redacted.pdf")
        make_text_pdf(src)

        doc = core.open_pdf(src)
        try:
            core.save_redacted(
                doc, {0: [fitz.Rect(40, 140, 555, 200)]}, out)
        finally:
            doc.close()

        with core.open_pdf(out) as doc2:
            pix = doc2[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        n = pix.n  # RGB なら 3

        def pixel(x, y):  # PDF 座標 -> ピクセル色
            i = (int(y * 2) * pix.width + int(x * 2)) * n
            return tuple(pix.samples[i:i + 3])

        # 黒塗り矩形 (40,140,555,200) の内側は黒
        self.assertEqual(pixel(200, 170), (0, 0, 0))
        # 黒塗り外 (公開テキスト行の近く) は黒でない
        self.assertNotEqual(pixel(100, 100), (0, 0, 0))
        self.assertNotEqual(pixel(100, 280), (0, 0, 0))

    # ---------- 画像黒塗り ----------

    def test_image_redaction_removes_image(self):
        src = self._path("image.pdf")
        out = self._path("redacted.pdf")
        make_image_pdf(src)

        doc = core.open_pdf(src)
        try:
            page = doc[0]
            # 黒塗り前: 画像が存在する
            self.assertTrue(page.get_images(full=True))
            # 画像領域全体を覆う黒塗り矩形
            core.save_redacted(doc, {0: [fitz.Rect(30, 130, 270, 290)]}, out)
        finally:
            doc.close()

        with core.open_pdf(out) as doc2:
            page2 = doc2[0]
            # 画像が物理的に削除されている
            self.assertEqual(page2.get_images(full=True), [])
            text = page2.get_text()
            # 黒塗り外のテキストは残っている
            self.assertIn(PUBLIC_1, text)
            self.assertIn(PUBLIC_2, text)

    def test_image_partial_redaction_removes_whole_image(self):
        """画像の一部だけ黒塗りしても、画像全体が削除されること。

        PDF_REDACT_IMAGE_REMOVE の仕様により、黒塗り矩形と交差する
        画像は全体が削除される (情報漏えいを防ぐ安全側の動作)。
        """
        src = self._path("image.pdf")
        out = self._path("redacted.pdf")
        make_image_pdf(src)

        doc = core.open_pdf(src)
        try:
            # 画像 (50,150,250,270) の右半分だけを覆う
            core.save_redacted(
                doc, {0: [fitz.Rect(150, 130, 300, 290)]}, out)
        finally:
            doc.close()

        with core.open_pdf(out) as doc2:
            page2 = doc2[0]
            self.assertEqual(page2.get_images(full=True), [])
            text = page2.get_text()
            self.assertIn(PUBLIC_1, text)
            self.assertIn(PUBLIC_2, text)

    # ---------- 複数ページ ----------

    def test_multi_page_redaction_keeps_other_pages(self):
        src = self._path("multi.pdf")
        out = self._path("redacted.pdf")
        make_multi_page_pdf(src)

        doc = core.open_pdf(src)
        try:
            # ページ2 (index=1) のみ黒塗り
            core.save_redacted(doc, {1: [fitz.Rect(40, 140, 555, 200)]}, out)
        finally:
            doc.close()

        with core.open_pdf(out) as doc2:
            self.assertEqual(core.page_count(doc2), 3)
            self.assertNotIn(SECRET_A, doc2[1].get_text())
            self.assertIn("ページ1 の公開情報", doc2[0].get_text())
            self.assertIn("ページ3 の公開情報", doc2[2].get_text())

    # ---------- エラーハンドリング ----------

    def test_password_protected_pdf_raises_error(self):
        src = self._path("password.pdf")
        make_password_pdf(src)
        with self.assertRaises(core.RedactError):
            core.open_pdf(src)

    def test_broken_file_raises_error(self):
        src = self._path("broken.pdf")
        make_broken_pdf(src)
        with self.assertRaises(core.RedactError):
            core.open_pdf(src)

    def test_missing_file_raises_error(self):
        with self.assertRaises(core.RedactError):
            core.open_pdf(self._path("does_not_exist.pdf"))

    # ---------- 表示系ヘルパー ----------

    def test_render_page_returns_png_and_scale(self):
        src = self._path("text.pdf")
        make_text_pdf(src)
        doc = core.open_pdf(src)
        try:
            png, scale = core.render_page(doc, 0, max_size=(800, 1000))
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertGreater(scale, 0)
            # A4 (595x842pt) が 800x1000px に収まるスケールであること
            self.assertLessEqual(595 * scale, 800 + 0.001)
            self.assertLessEqual(842 * scale, 1000 + 0.001)
        finally:
            doc.close()

    def test_to_pdf_rect_and_clip(self):
        src = self._path("text.pdf")
        make_text_pdf(src)
        doc = core.open_pdf(src)
        try:
            page = doc[0]
            # スケール 2.0 でキャンバス座標 (10, 20)-(110, 120) は
            # PDF 座標 (5, 10)-(55, 60) になる
            r = core.to_pdf_rect(10, 20, 110, 120, 2.0)
            self.assertAlmostEqual(r.x0, 5.0)
            self.assertAlmostEqual(r.y0, 10.0)
            self.assertAlmostEqual(r.x1, 55.0)
            self.assertAlmostEqual(r.y1, 60.0)
            # ページ外にはみ出した矩形はページ内に切り詰められる
            c = core.clip_to_page(fitz.Rect(-50, -50, 10000, 10000), page)
            self.assertEqual((c.x0, c.y0), (0, 0))
            self.assertAlmostEqual(c.x1, page.rect.width)
            self.assertAlmostEqual(c.y1, page.rect.height)
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
