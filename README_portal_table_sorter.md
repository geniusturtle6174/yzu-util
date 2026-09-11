# portal_table_sorter

在元智課務系統的作業繳交記錄頁面，自動將學生列表依下列順序排序，每次進入頁面即生效，不需手動操作：

1. 尚未給分的學生排在前面
2. 同組內依最後一筆上傳時間由早到晚排序
3. 上傳時間相同時，依學號由小到大排序

## 安裝

1. 下載或 clone 此 repo，確認本機有 `portal_table_sorter/` 資料夾（內含 `manifest.json` 與 `content.js`）。
2. 在 Chrome 網址列輸入 `chrome://extensions/` 並按 Enter。
3. 開啟右上角的 **Developer mode**。
4. 點左上角的 **Load unpacked**，選擇 `portal_table_sorter/` 資料夾。
5. 清單中出現「元智課務系統作業排序」即代表安裝成功。

安裝後**不需要重新啟動 Chrome**，直接前往作業繳交記錄頁面即可看到效果。

## 更新

程式碼修改後，回到 `chrome://extensions/`，找到本 extension，按右下角的重新整理圖示（⟳），不需重新 Load unpacked。

## 設定

`manifest.json` 裡的 `matches` 欄位指定此 extension 會在哪些網址生效，預設為：

```json
"matches": ["*://lms.yzu.edu.tw/*"]
```

如果課務系統的網址不同，請修改此欄位後，回到 `chrome://extensions/` 重新整理 extension。

如果不確定正確的網址格式，可以暫時改成：

```json
"matches": ["*://*/*"]
```

這樣會在所有網站上載入 extension，但程式碼本身會先檢查頁面上有沒有對應的表格，沒有的話什麼都不會做，不影響其他網站的正常使用。確認 extension 正常運作後，再改回正確的網址比較好。

## 注意事項

- 此 extension 只裝在當下操作的 Chrome profile，其他 profile 不受影響。
- 「作廢」的上傳記錄不計入排序依據，以最後一筆有效上傳時間為準。
- 尚未上傳檔案的學生，在同一給分狀態的群組內排在最後。
- 排序後，列表的交錯底色（深淺交替）會自動重新套用。
