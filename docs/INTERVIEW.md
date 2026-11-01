# 面試說明與展示提綱

## 60 秒介紹

這個專案把香港一手住宅的雙語成交紀錄 PDF，轉成可追溯的 CSV、
PostgreSQL 資料表及 SQL／Excel 報表。最主要的挑戰是來源表格有不同版面，
而且付款條款及價格會修訂，直接擷取或取第一段文字容易得到錯誤結果。

我針對已發現的問題補回 38 筆漏列，按修訂日期選取最新條款，並保留原文、
來源頁碼與檔案 hash。每頁的候選交易數會和擷取數核對，未解決的異常會阻擋成功狀態。
載入則用 natural key 與 UPSERT，驗證重跑不增加筆數，同一筆合約的修訂會更新原列。

目前核對後是 1,183 筆合約，八項測試和六個 SQL 範例通過，也實測了 Excel refresh。
我把分析限制寫清楚，例如合約數不等於完成成交、座數均價不能直接證明定價溢價，
以及仍有 15 項來源或分類警告。

## English opening

This project turns bilingual Hong Kong residential transaction PDFs into
validated contract records, a PostgreSQL star schema, and SQL and Excel reports.
The main challenges were incomplete table extraction and dated amendments to
prices and payment terms. I recovered 38 omitted records, added page-level
reconciliation, and retained the source text and page references. I also tested
repeat loads and same-key amendments using PostgreSQL UPSERT. The reviewed
snapshot contains 1,183 contracts, with eight passing tests and six working SQL
examples. I documented the remaining warnings and kept the conclusions within
what this single-development dataset can support.

## 核心問題與答題重點

| 問題 | 可以怎樣回答 |
|---|---|
| 一列代表甚麼？ | 一筆合約紀錄，不是一個單位。相同單位以不同 PASP 日期再出售，會是另一筆合約。 |
| 為何這樣設計 natural key？ | 使用 development、block、floor、unit、PASP date 識別合約；資料庫另有 surrogate sale key。這讓相同識別欄位的修訂可以更新原列。 |
| 重跑如何不重複？ | natural key 有 UNIQUE 約束，UPSERT 遇到相同 key 就更新。測試比較重載前後筆數，也驗證同 key 修訂保留 sale key。這不代表所有情況都有 exactly-once 保證。 |
| 如果來源更改 PASP 日期？ | 這是識別欄位修正，會形成新 key。目前需要額外核對，沒有自動合併舊列或處理來源刪除。 |
| 38 筆怎樣漏掉？ | 已知頁面缺少表格底線，一般表格辨識沒有取得交易列。針對該版面補足邊界，並用每頁候選交易數核對，不在 parser 硬寫 1,183。 |
| 如何決定最新付款方式？ | 擷取有日期的修訂事件，以日期選最新有效段落，再分類；保留完整原文。不能判斷日期或同日條款衝突時列為錯誤，不猜測。 |
| 缺值和解析失敗有何不同？ | 明確表示沒有進一步簽約的來源敘述可以保留為無 ASP 日期並加警告；非法日期字串則是解析失敗，不能當成正常缺值。 |
| 為何均價只看 ASP signed？ | 這個指標要描述已簽正式合約的紀錄，避免把已終止及未進一步簽約的價格混進同一母體；ASP signed 仍不代表完成交易。 |
| 終止率為何用全部合約？ | 494 / 1,183 = 41.76%，描述這個快照的合約狀態比例。按 PASP 月份分組時是 cohort 比率，不是該月發生終止事件的比率。 |
| 為何月份圖要補零？ | 只顯示有交易月份會壓縮中間的時間；只按月份名稱分組又會把跨年資料合併。SQL 以連續月份產生 calendar，再接回交易數。 |
| 八項測試是否證明資料完全正確？ | 不會。它們涵蓋已知缺陷與一條資料庫整合流程；另外有來源 hash、逐頁核對及付款修訂稽核。並非全部 1,183 筆欄位都經人工核對。 |
| 為何不用 Airflow 或 Spark？ | 目前是單一開發項目的 PDF 與小量結構化資料，三個 CLI 足以重現與定位失敗；先確保正確性與可追溯性。若有穩定排程、多來源依賴或規模需求，再評估工具。 |

## 五分鐘展示順序

1. **用途與結果（約 45 秒）**：開啟 [作品集介紹](PORTFOLIO.md) 及 dashboard，
   說明快照日期、合約粒度和主要數字；不推論整體市場。
2. **資料正確性（約 90 秒）**：展示
   [PDF parser](../extract/pdf_parser.py) 的版面 fallback 與頁面核對，
   再用 [付款修訂稽核](payment_revision_audit.csv) 說明最新條款及原文追溯。
3. **載入與 SQL（約 60 秒）**：展示 [schema](../load/schema.sql)、
   [UPSERT](../load/loader.py) 及 [月份 view](../load/views.sql)，說明唯一鍵與零交易月份。
4. **可重現與證據（約 60 秒）**：展示 [README](../README.md) 的 fixture 流程、
   [測試](../tests/test_pipeline.py) 和 [驗證紀錄](VALIDATION.md)。離線測試不需要網站；
   資料庫測試需明確設定環境及 CREATEDB 權限。
5. **限制與取捨（約 45 秒）**：說明 15 項警告、目前 live SRPE 服務未重驗，
   以及 identity 修正需要人工 reconciliation。若展示本機 Excel，說明月份範圍
   目前固定在這份快照，新版本需延伸或改連動態月份 SQL view。

## 面試前確認

- 依自己的實際經驗調整第一人稱敘述，能逐段解釋工具協助產生及修改的程式；
  若被問及開發方式，如實說明使用過的工具及自己執行的核對。
- 區分「自動逐筆比對付款修訂」與「人工核對所有欄位」。
- 使用 [履歷版本](RESUME.md) 時依職缺選 DA 或 DE，避免同時塞入全部 bullet points。
- 以已驗證快照示範；不承諾 live 網站一定能取得同一歷史版本，也不把產生的
  reference dashboard 圖片說成 Excel 截圖。
