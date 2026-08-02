#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 黒塗りコアロジック (GUI 非依存)。

情報公開請求対応のため、黒塗りは「見た目に黒い矩形を重ねる」のではなく、
PyMuPDF (fitz) の add_redact_annot() + apply_redactions() を使い、
該当領域のテキスト・画像を PDF 上から物理的に削除する。
"""

import fitz  # PyMuPDF

__all__ = [
    "RedactError",
    "open_pdf",
    "page_count",
    "render_page",
    "to_pdf_rect",
    "clip_to_page",
    "make_redacted_document",
    "save_redacted",
]

# 黒塗りに使う色 (黒)
REDACT_FILL = (0, 0, 0)


class RedactError(Exception):
    """黒塗り処理中に発生するエラー。日本語メッセージを持つ。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def open_pdf(path):
    """PDF を開いて Document を返す。

    パスワード付き PDF・破損ファイル・PDF 形式でないファイルは
    RedactError を送出する。開いたドキュメントは呼び出し側で
    close() すること。
    """
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise RedactError(
            "PDF を開けませんでした。\n"
            "ファイルが破損しているか、PDF 形式ではない可能性があります。\n"
            "元のファイルを確認してください。"
        ) from exc
    try:
        if doc.needs_pass:
            raise RedactError(
                "この PDF はパスワードで保護されています。\n"
                "パスワードを解除してから開き直してください。"
            )
    except RedactError:
        doc.close()
        raise
    except Exception as exc:
        doc.close()
        raise RedactError("PDF を開けませんでした。") from exc
    return doc


def page_count(doc):
    """ドキュメントのページ数を返す。"""
    return len(doc)


def render_page(doc, page_index, max_size, dpi_limit=150):
    """ページをピクセルマップにレンダリングする。

    max_size=(width, height): 表示サイズの上限 (ピクセル)。
    ページ全体が max_size に収まるように、かつ dpi が dpi_limit を
    超えないように表示スケールを決める。

    戻り値: (png_bytes, scale)
      png_bytes: PNG 形式の画像データ (tkinter.PhotoImage で表示可能)
      scale:     表示 1 ピクセルあたりの PDF ポイント数
                 (PDF 座標 = キャンバス座標 / scale)
    """
    if page_index < 0 or page_index >= len(doc):
        raise RedactError("ページ番号が範囲外です。")
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    max_w, max_h = max_size
    if max_w <= 0 or max_h <= 0:
        raise RedactError("表示サイズが不正です。")
    # dpi 上限相当のスケール (150dpi なら 150/72) と、
    # ページがキャンバスに収まるスケールの小さい方を使う。
    scale = min(dpi_limit / 72.0, max_w / pw, max_h / ph)
    if scale <= 0:
        raise RedactError("ページのサイズが不正です。")
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pix.tobytes("png"), scale


def to_pdf_rect(x0, y0, x1, y1, scale):
    """キャンバス座標 (左上原点・下向き Y) の矩形を PDF 座標に変換する。

    PDF も原点は左上で Y 軸が下向きのため、スケールで割り戻すだけでよい。
    """
    return fitz.Rect(x0 / scale, y0 / scale, x1 / scale, y1 / scale)


def clip_to_page(rect, page):
    """矩形をページ領域内に切り詰める (ドラッグのはみ出し対策)。"""
    pr = page.rect
    return fitz.Rect(
        max(rect.x0, pr.x0),
        max(rect.y0, pr.y0),
        min(rect.x1, pr.x1),
        min(rect.y1, pr.y1),
    )


def make_redacted_document(doc, redactions):
    """黒塗りを適用した新しいドキュメントを返す (元の doc は変更しない)。

    redactions: {page_index: [fitz.Rect, ...]} の辞書。
    新規ドキュメントに全ページをコピーし、各ページに赤act注釈を追加して
    apply_redactions() を実行する。images=PDF_REDACT_IMAGE_REMOVE により
    黒塗り領域に交差する画像も物理的に削除される。

    戻り値はメモリ上の Document。呼び出し側で close() すること。
    """
    out = fitz.open()
    try:
        out.insert_pdf(doc)
        for page_index, rects in redactions.items():
            if not rects:
                continue
            page = out[page_index]
            for rect in rects:
                if rect.is_empty:
                    continue
                page.add_redact_annot(rect, fill=REDACT_FILL)
            # images=PDF_REDACT_IMAGE_REMOVE: 黒塗り領域と交差する画像を
            # 完全に削除する (PDF_REDACT_IMAGE_NONE=0 は「画像を無視」なので
            # 使わないこと。PDF_REDACT_IMAGE_PIXELS=2 は画像を残して
            # ピクセルのみ消すため情報公開用途には不十分)。
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
    except Exception as exc:
        out.close()
        raise RedactError("黒塗り処理に失敗しました: %s" % exc) from exc
    return out


def save_redacted(doc, redactions, out_path):
    """黒塗りを適用した PDF を別名保存する。

    garbage=4 で不要になったオブジェクト (削除された画像データ等) も
    確実にファイルから取り除く。
    """
    out = make_redacted_document(doc, redactions)
    try:
        out.save(out_path, garbage=4, deflate=True)
    except Exception as exc:
        raise RedactError("保存に失敗しました: %s" % exc) from exc
    finally:
        out.close()
