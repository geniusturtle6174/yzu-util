# build_evidence_pdf

將多份教學佐證資料（圖檔、PDF、Word、PowerPoint、純文字）依照清單，合併成一份排版一致的 IEET 課程評鑑用 PDF。每頁上方為描述文字，下方為對應的資料內容，等比例縮放、置中呈現。

## 安裝需求

```
pip install reportlab pypdf pypdfium2 pillow numpy
```

如果清單中包含 `.doc`、`.docx`、`.ppt`、`.pptx`，還需要安裝 [LibreOffice](https://www.libreoffice.org/)，並確認 `soffice` 指令可在終端機直接執行。

**字型**：程式使用 [WenQuanYi Zen Hei](https://github.com/r-lyeh-archived/fortfont/blob/master/wq/WenQuanYiZenHei.ttf) 內嵌中文字型，請自行下載 `.ttf` 檔案後，依下方參數說明指定路徑。

## 使用方式

```
python build_evidence_pdf.py <input_dir> [--output OUTPUT] [--dpi DPI] [--font FONT]
```

| 參數 | 說明 | 預設值 |
|---|---|---|
| `input_dir` | 輸入資料夾路徑（位置參數） | 必填 |
| `--output` | 輸出 PDF 路徑 | 執行目錄下的 `evidence.pdf` |
| `--dpi` | PDF、Office 文件轉圖片的解析度 | `200` |
| `--font` | WenQuanYi Zen Hei 字型檔路徑 | 程式碼內寫死，請修改或每次指定 |

## 輸入格式

輸入資料夾內需包含以下檔案：

```
input_dir/
├── items.csv          ← 必要，固定檔名
├── cover.pdf          ← 選用（亦可為 .doc / .docx），自動作為封面
└── （其他佐證資料檔案）
```

**items.csv** 格式範例（UTF-8 或 Big5，**第一列為標頭**）：

```
檔案路徑,描述
小考/quiz1.jpg,第1次小考，高分，95
期中考/midterm.pdf,期中考考卷，中分，78
```

- 檔案路徑為相對於 `input_dir` 的路徑
- 描述文字將顯示於每頁頂端，多頁項目自動加上 `(i/n)` 頁碼標記

**支援的檔案類型**：

| 類型 | 副檔名 |
|---|---|
| 圖檔 | `.jpg` `.jpeg` `.png` `.bmp` `.tif` `.tiff` `.webp` |
| PDF | `.pdf` |
| Word | `.doc` `.docx` |
| PowerPoint | `.ppt` `.pptx` |
| 純文字／程式碼 | 其他副檔名一律嘗試以文字方式讀取 |

## 輸出格式

單一 PDF 檔案。若有封面，封面置於第一頁（維持原始版面，不加描述標頭）；其後每頁對應 `items.csv` 中的一筆資料。

## 注意事項

- **手機拍照旋轉**：程式自動套用 EXIF 方向標籤，不會出現內容橫躺的問題。
- **內容轉為圖片**：PDF、Office 文件的每頁均先轉為圖片再排版，原始文字不再可選取。如需更高畫質，可調高 `--dpi`。
- **投影片網格**：`.pptx` 預設每頁排列 `PPTX_GRID_ROWS × PPTX_GRID_COLS`（預設 2 列 1 欄）張投影片，可修改程式開頭的常數調整。
- **頁數上限**：每份佐證資料最多顯示 `MAX_PAGES_PER_ITEM`（預設 5）頁，超過時印出警告並截斷。
- **字型路徑**：`--font` 的預設值寫死在程式碼的 `parse_args()` 中，換機器使用前請修改，或每次以 `--font` 指定。
