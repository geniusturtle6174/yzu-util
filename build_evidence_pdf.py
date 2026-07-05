#!/usr/bin/env python3
r"""
build_evidence_pdf.py

把多份教學佐證資料（圖檔 / PDF / doc、docx）依清單上的描述，合併成一份排版一致的 PDF。
每一頁版面：上方是描述文字（多頁項目會自動加上「(第幾頁/總頁數)」），下方是等比例縮放後的原始內容。

輸入資料夾規則（每門課、每學期一個資料夾，自我完整、可整包搬動）：
    a_dir_name/
    ├── items.csv          固定檔名，清單檔
    ├── cover.pdf          選用，固定檔名（也可以是 cover.doc 或 cover.docx），有放就自動當封面
    └── ...                items.csv 裡引用到的圖檔、PDF、doc/docx

使用方式：
    python build_evidence_pdf.py a_dir_name
    python build_evidence_pdf.py a_dir_name --output final.pdf --dpi 300

不指定 --output 時，預設輸出到目前工作目錄下的 evidence.pdf（注意：是執行指令時所在的資料夾，不是本程式所在的資料夾）。

CSV 清單格式（UTF-8 或 Big5 編碼，第一列為標頭）：
    檔案路徑,描述
    quiz1.jpg,第1次小考，高分，95
    report.docx,期中書面報告

CSV 裡的檔案路徑可以是絕對路徑，也可以是相對於 items.csv 所在資料夾（也就是 input_dir）的相對路徑。

支援的檔案類型：
    圖檔：.jpg / .jpeg / .png / .bmp / .tif / .tiff / .webp
    PDF： .pdf
    Word：.doc / .docx（需要系統安裝 LibreOffice，且 soffice 指令可在終端機執行）
    PowerPoint：.ppt / .pptx（同樣需要 LibreOffice；預設每 2 張投影片（PPTX_GRID_COLS ×
                PPTX_GRID_ROWS）合成一張網格圖片再縮放進評鑑頁面，可調整程式開頭的常數）
    其他副檔名：一律試著當純文字／程式碼開啟（UTF-8 或 Big5），打不開才報錯，
                所以不用為每一種程式碼副檔名額外列清單

需要安裝的套件：
    pip install reportlab pypdf pypdfium2 pillow

字型：
    --font 預設值寫死在 parse_args() 裡（目前是 D:\doc_00\WenQuanYiZenHei.ttf），
    請依實際安裝位置修改該預設值，或執行時用 --font 指定其他路徑。
    這個字型檔會直接內嵌進輸出的 PDF，所以開啟端的電腦不需要另外裝中文字型。
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from PIL import Image, ImageDraw, ImageOps
from pypdf import PdfWriter
import pypdfium2 as pdfium
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
PDF_EXTENSIONS = {'.pdf'}
WORD_EXTENSIONS = {'.doc', '.docx'}
PPTX_EXTENSIONS = {'.ppt', '.pptx'}

ITEMS_CSV_FILENAME = 'items.csv'
COVER_BASENAME = 'cover'
COVER_EXTENSIONS = ('.docx', '.doc', '.pdf')

FONT_NAME = 'EvidenceCJK'

MARGIN = 36
MIN_HEADER_HEIGHT_RATIO = 0.05

PPTX_GRID_COLS = 1
PPTX_GRID_ROWS = 2
PPTX_GRID_GAP_PX = 12

TEXT_ENCODINGS = ('utf-8-sig', 'cp950')
TEXT_FONT_SIZE = 10
TEXT_TAB_WIDTH = 4

MAX_PAGES_PER_ITEM = 5


@dataclass
class EvidenceItem:
    file_path: Path
    description: str


def read_csv_rows(csv_path: Path) -> list[dict]:
    """讀取 CSV 內容，自動容錯處理 UTF-8 與 Big5（Excel 在台灣常用的存檔編碼）。"""
    for encoding in TEXT_ENCODINGS:
        try:
            with open(csv_path, encoding=encoding, newline='') as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        '/'.join(TEXT_ENCODINGS), b'', 0, 1,
        f'{csv_path} 無法用 UTF-8 或 Big5 解碼，請確認 CSV 存檔編碼。',
    )


def read_item_list(csv_path: Path) -> list[EvidenceItem]:
    """讀取 CSV 清單，回傳每一份佐證資料的檔案路徑與描述。"""
    items = []
    rows = read_csv_rows(csv_path)
    for row_number, row in enumerate(rows, start=2):
        file_field = (row.get('檔案路徑') or row.get('file_path') or '').strip()
        description = (row.get('描述') or row.get('description') or '').strip()
        if not file_field:
            continue
        file_path = Path(file_field).expanduser()
        if not file_path.is_absolute():
            file_path = (csv_path.parent / file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f'CSV 第 {row_number} 列找不到檔案：{file_path}')
        items.append(EvidenceItem(file_path=file_path, description=description))
    if not items:
        raise ValueError(f'{csv_path} 裡沒有讀到任何有效的資料列')
    return items


def find_cover_file(input_dir: Path) -> Optional[Path]:
    """在輸入資料夾裡尋找固定檔名的封面檔（cover.pdf / cover.doc / cover.docx）。

    如果同時存在多個，選擇最近修改的那一個並印出警告；
    修改時間相同則依 COVER_EXTENSIONS 的順序（docx > doc > pdf）決定。
    """
    candidates = [input_dir / f'{COVER_BASENAME}{ext}' for ext in COVER_EXTENSIONS]
    found = [path for path in candidates if path.exists()]
    if not found:
        return None
    if len(found) == 1:
        return found[0]

    extension_rank = {ext: rank for rank, ext in enumerate(COVER_EXTENSIONS)}
    found.sort(key=lambda path: (-path.stat().st_mtime, extension_rank[path.suffix.lower()]))
    chosen = found[0]
    ignored = '、'.join(path.name for path in found[1:])
    print(
        f'警告：在 {input_dir} 找到多個封面檔案（{"、".join(p.name for p in found)}），'
        f'已選擇最近修改的 {chosen.name}，忽略 {ignored}。',
        file=sys.stderr,
    )
    return chosen


def convert_office_to_pdf(office_path: Path, workdir: Path) -> Path:
    """用 LibreOffice 把 doc/docx/ppt/pptx 轉成 PDF，回傳轉出來的 PDF 路徑。"""
    soffice = shutil.which('soffice') or shutil.which('libreoffice')
    if soffice is None:
        raise RuntimeError(
            '找不到 soffice / libreoffice 指令，doc/docx/ppt/pptx 轉換需要先安裝 LibreOffice。'
        )
    profile_dir = workdir / f'lo_profile_{office_path.stem}'
    out_dir = workdir / f'{office_path.stem}_pdf'
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        '--headless',
        '--norestore',
        f'-env:UserInstallation={profile_dir.resolve().as_uri()}',
        '--convert-to', 'pdf',
        '--outdir', str(out_dir),
        str(office_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    pdf_path = out_dir / f'{office_path.stem}.pdf'
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f'轉換 {office_path.name} 失敗：{result.stderr or result.stdout}')
    return pdf_path


def render_pdf_to_images(pdf_path: Path, workdir: Path, dpi: int) -> list[Path]:
    """把 PDF 每一頁轉成一張圖片，回傳依頁碼排序好的圖片路徑清單。"""
    out_dir = workdir / f'{pdf_path.stem}_pages'
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72
    pdf = pdfium.PdfDocument(str(pdf_path))
    image_paths = []
    for page_index in range(len(pdf)):
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        image_path = out_dir / f'page_{page_index + 1:03d}.png'
        pil_image.save(image_path)
        image_paths.append(image_path)
    return image_paths


ORIENTATION_TAG_ID = 0x0112


def normalize_image_orientation(image_path: Path, workdir: Path) -> Path:
    """套用圖片的 EXIF 方向資訊（手機拍照常見會有），避免內容被轉錯方向。

    手機拍照時，實際存的像素資料常常是橫的，靠 EXIF 的 Orientation 標籤告訴看圖軟體
    要轉幾度才是正確方向；一般相簿、瀏覽器會自動套用，但直接讀檔案不會，所以這裡手動處理。
    沒有需要轉正的標籤時直接回傳原始路徑，不額外耗時。
    """
    image = Image.open(image_path)
    orientation = image.getexif().get(ORIENTATION_TAG_ID, 1)
    if orientation == 1:
        return image_path

    oriented = ImageOps.exif_transpose(image)
    if image_path.suffix.lower() in {'.jpg', '.jpeg'} and oriented.mode in ('RGBA', 'P'):
        oriented = oriented.convert('RGB')

    out_dir = workdir / 'normalized_images'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / image_path.name
    oriented.save(out_path)
    return out_path


def render_pptx_to_grid_images(
    pptx_path: Path,
    workdir: Path,
    dpi: int,
    grid_cols: int = PPTX_GRID_COLS,
    grid_rows: int = PPTX_GRID_ROWS,
) -> list[Path]:
    """把投影片轉成 PDF 後，每 grid_cols × grid_rows 張投影片合成一張網格圖片。

    例如預設 2×1：投影片 1、2 合成一張圖片（一頁），3、4 合成下一張，依此類推。
    最後一批張數不足時，多出來的格子留白。
    """
    converted_pdf = convert_office_to_pdf(pptx_path, workdir)
    slide_images = render_pdf_to_images(converted_pdf, workdir, dpi)

    out_dir = workdir / f'{pptx_path.stem}_grid'
    out_dir.mkdir(parents=True, exist_ok=True)
    batch_size = grid_cols * grid_rows
    grid_image_paths = []

    for batch_index in range(0, len(slide_images), batch_size):
        batch = slide_images[batch_index:batch_index + batch_size]
        slides = [Image.open(path) for path in batch]
        cell_width = max(slide.width for slide in slides)
        cell_height = max(slide.height for slide in slides)

        grid_width = cell_width * grid_cols + PPTX_GRID_GAP_PX * (grid_cols + 1)
        grid_height = cell_height * grid_rows + PPTX_GRID_GAP_PX * (grid_rows + 1)
        grid_image = Image.new('RGB', (grid_width, grid_height), 'white')
        draw = ImageDraw.Draw(grid_image)

        for slot_index, slide in enumerate(slides):
            col = slot_index % grid_cols
            row = slot_index // grid_cols
            cell_x = PPTX_GRID_GAP_PX + col * (cell_width + PPTX_GRID_GAP_PX)
            cell_y = PPTX_GRID_GAP_PX + row * (cell_height + PPTX_GRID_GAP_PX)
            paste_x = cell_x + (cell_width - slide.width) // 2
            paste_y = cell_y + (cell_height - slide.height) // 2
            grid_image.paste(slide, (paste_x, paste_y))
            draw.rectangle(
                [cell_x, cell_y, cell_x + cell_width - 1, cell_y + cell_height - 1],
                outline='gray',
            )

        grid_image_path = out_dir / f'grid_{batch_index // batch_size + 1:03d}.png'
        grid_image.save(grid_image_path)
        grid_image_paths.append(grid_image_path)

    return grid_image_paths


def read_text_file(text_path: Path) -> str:
    """讀取純文字檔案內容，自動容錯處理 UTF-8 與 Big5；兩種都讀不到就報錯，不沉默放行。"""
    for encoding in TEXT_ENCODINGS:
        try:
            return text_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f'{text_path.name} 不像是文字檔（UTF-8、Big5 都無法解碼），不支援這種檔案類型。',
    )


def wrap_line_to_width(line: str, font_size: float, max_width: float) -> list[str]:
    """把一行文字依實際畫出來的寬度自動換行，效果跟複製貼上時的自動換行一樣，不會遺漏字元。"""
    if not line:
        return ['']
    wrapped_lines = []
    current_line = ''
    for character in line:
        candidate = current_line + character
        if current_line and pdfmetrics.stringWidth(candidate, FONT_NAME, font_size) > max_width:
            wrapped_lines.append(current_line)
            current_line = character
        else:
            current_line = candidate
    wrapped_lines.append(current_line)
    return wrapped_lines


def render_text_to_images(text_path: Path, workdir: Path, dpi: int) -> list[Path]:
    """把純文字／程式碼檔案逐行畫成圖片，自動換行、自動分頁。

    用低階的 drawString 逐行畫出來，不經過任何標記語言解析，所以內容裡的 < > & 等字元
    不會被誤判成排版標籤；副檔名沒被歸類成圖檔/PDF/Word/PowerPoint 的檔案都會走這條路徑。
    """
    content = read_text_file(text_path)
    raw_lines = content.splitlines() or ['']

    content_width = A4[0] - 2 * MARGIN
    content_height = A4[1] - 2 * MARGIN - A4[1] * MIN_HEADER_HEIGHT_RATIO
    line_height = TEXT_FONT_SIZE * 1.2
    lines_per_page = max(1, int(content_height // line_height))

    rendered_lines = []
    for raw_line in raw_lines:
        expanded_line = raw_line.expandtabs(TEXT_TAB_WIDTH)
        rendered_lines.extend(wrap_line_to_width(expanded_line, TEXT_FONT_SIZE, content_width))

    out_dir = workdir / f'{text_path.stem}_text'
    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []

    for page_index, start in enumerate(range(0, len(rendered_lines), lines_per_page), start=1):
        page_lines = rendered_lines[start:start + lines_per_page]
        chunk_pdf_path = out_dir / f'chunk_{page_index:03d}.pdf'
        c = canvas.Canvas(str(chunk_pdf_path), pagesize=(content_width, content_height))
        c.setFont(FONT_NAME, TEXT_FONT_SIZE)
        y = content_height - line_height
        for page_line in page_lines:
            c.drawString(0, y, page_line)
            y -= line_height
        c.showPage()
        c.save()

        chunk_image_paths = render_pdf_to_images(chunk_pdf_path, out_dir, dpi)
        image_paths.append(chunk_image_paths[0])

    return image_paths


def get_page_images(item: EvidenceItem, workdir: Path, dpi: int) -> list[Path]:
    """依檔案類型，回傳這份佐證資料展開後、每一頁對應的圖片路徑清單。

    圖檔/PDF/Word/PowerPoint 用各自的白名單分類處理；其他副檔名一律試著當純文字開啟，
    打不開（不是合法文字編碼）才報錯，這樣不用為每一種程式碼副檔名都列一筆。
    """
    suffix = item.file_path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return [normalize_image_orientation(item.file_path, workdir)]
    if suffix in PDF_EXTENSIONS:
        return render_pdf_to_images(item.file_path, workdir, dpi)
    if suffix in WORD_EXTENSIONS:
        converted_pdf = convert_office_to_pdf(item.file_path, workdir)
        return render_pdf_to_images(converted_pdf, workdir, dpi)
    if suffix in PPTX_EXTENSIONS:
        return render_pptx_to_grid_images(item.file_path, workdir, dpi)
    return render_text_to_images(item.file_path, workdir, dpi)


def build_single_page_pdf(
    image_path: Path,
    header_text: str,
    out_pdf_path: Path,
    page_size=A4,
    margin: float = MARGIN,
    min_header_height: Optional[float] = None,
    font_size: float = 13,
) -> None:
    """產生一頁 PDF：上方是描述文字，下方是等比例縮放、置中的圖片。"""
    page_width, page_height = page_size
    if min_header_height is None:
        min_header_height = page_height * MIN_HEADER_HEIGHT_RATIO

    style = ParagraphStyle(
        'header', fontName=FONT_NAME, fontSize=font_size, leading=font_size * 1.35,
        alignment=TA_CENTER,
    )
    paragraph = Paragraph(xml_escape(header_text), style)
    available_width = page_width - 2 * margin
    _, required_height = paragraph.wrap(available_width, page_height)
    header_height = max(min_header_height, required_height + 16)

    c = canvas.Canvas(str(out_pdf_path), pagesize=page_size)

    frame = Frame(
        margin, page_height - margin - header_height,
        available_width, header_height,
        leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=8,
        showBoundary=0,
    )
    frame.addFromList([paragraph], c)

    content_top = page_height - margin - header_height
    content_bottom = margin
    content_width = available_width
    content_height = content_top - content_bottom

    image_reader = ImageReader(str(image_path))
    image_width, image_height = image_reader.getSize()
    scale = min(content_width / image_width, content_height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    draw_x = margin + (content_width - draw_width) / 2
    draw_y = content_bottom + (content_height - draw_height) / 2
    c.drawImage(
        image_reader, draw_x, draw_y, width=draw_width, height=draw_height,
        preserveAspectRatio=True, anchor='c',
    )

    c.showPage()
    c.save()


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> None:
    """依序合併多個 PDF 檔案成一個輸出檔案。"""
    writer = PdfWriter()
    for pdf_path in pdf_paths:
        writer.append(str(pdf_path))
    with open(output_path, 'wb') as f:
        writer.write(f)


def build_evidence_pdf(
    input_dir: Path,
    output_path: Path,
    font_path: Path,
    dpi: int = 200,
    max_pages_per_item: int = MAX_PAGES_PER_ITEM,
    keep_workdir: bool = False,
) -> None:
    if not input_dir.is_dir():
        raise FileNotFoundError(f'找不到輸入資料夾：{input_dir}')

    csv_path = input_dir / ITEMS_CSV_FILENAME
    if not csv_path.exists():
        raise FileNotFoundError(f'{input_dir} 裡找不到 {ITEMS_CSV_FILENAME}')

    pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))
    items = read_item_list(csv_path)
    cover_file = find_cover_file(input_dir)

    workdir = Path(tempfile.mkdtemp(prefix='evidence_pdf_'))
    try:
        page_pdf_paths = []
        if cover_file is not None:
            if cover_file.suffix.lower() in WORD_EXTENSIONS:
                cover_file = convert_office_to_pdf(cover_file, workdir)
            page_pdf_paths.append(cover_file)

        for item_index, item in enumerate(items, start=1):
            print(f'[{item_index}/{len(items)}] 處理：{item.file_path.name}', file=sys.stderr)
            page_images = get_page_images(item, workdir, dpi)
            if len(page_images) > max_pages_per_item:
                print(
                    f'警告：{item.file_path.name} 共有 {len(page_images)} 頁，'
                    f'超過上限 {max_pages_per_item} 頁，只取前 {max_pages_per_item} 頁。',
                    file=sys.stderr,
                )
                page_images = page_images[:max_pages_per_item]
            total_pages = len(page_images)
            for page_number, image_path in enumerate(page_images, start=1):
                if total_pages == 1:
                    header_text = item.description
                else:
                    header_text = f'{item.description} ({page_number}/{total_pages})'
                page_pdf_path = workdir / f'item{item_index:03d}_page{page_number:03d}.pdf'
                build_single_page_pdf(image_path, header_text, page_pdf_path)
                page_pdf_paths.append(page_pdf_path)

        merge_pdfs(page_pdf_paths, output_path)
        print(f'完成，輸出至：{output_path}', file=sys.stderr)
    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='把佐證資料圖檔、PDF、doc/docx 合併成一份標準格式的 PDF。',
    )
    parser.add_argument('input_dir', type=Path, help='輸入資料夾（裡面需有 items.csv，可選 cover.pdf/.doc/.docx）')
    parser.add_argument('--output', default='evidence.pdf', help='輸出的 PDF 路徑，預設為本程式同目錄下的 evidence.pdf')
    parser.add_argument('--dpi', type=int, default=200, help='PDF、doc/docx 轉成圖片時的解析度，預設 200')
    parser.add_argument('--font', default='D:\\doc_00\\WenQuanYiZenHei.ttf', help='標頭文字使用的中文字型檔（.ttf）')
    parser.add_argument('--keep-workdir', action='store_true', help='保留處理過程中的暫存檔案，方便除錯')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_evidence_pdf(
        input_dir=args.input_dir,
        output_path=Path(args.output),
        font_path=Path(args.font),
        dpi=args.dpi,
        keep_workdir=args.keep_workdir,
    )


if __name__ == '__main__':
    main()
