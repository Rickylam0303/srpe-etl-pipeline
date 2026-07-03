# Excel + Power Query 儀表板設定指南

將 PostgreSQL 入面嘅 SRPE 交易資料接到 Excel，做面試展示用儀表板。

## 事前準備

- PostgreSQL 18 服務已啟動
- `srpe_etl` 資料庫已載入 1,145 筆資料
- 已建立 dashboard views（見下方指令）

### 建立 Views（只需做一次）

```powershell
cd "C:\Users\6c10r\OneDrive\Personal\01_career\03_Portfolio_&_Projects\ETL Pipeline"
.\.venv\Scripts\python run_load.py --init-views
```

會建立三個 view：

| View | 用途 |
|------|------|
| `vw_sales_detail` | 每筆交易明細（Power Query 主表） |
| `vw_monthly_sales` | 按月匯總 |
| `vw_block_summary` | 按座數匯總 |

---

## 第一步：Excel 連接 PostgreSQL

> **常見錯誤：** 如果彈出「此連接器需要安裝一個或多個其他元件才能使用」，代表 Excel 未安裝 **Npgsql** 驅動。

### 安裝 Npgsql（必做）

1. 喺 Excel 錯誤視窗按 **深入了解**，或打開：  
   https://learn.microsoft.com/zh-tw/power-query/connectors/postgresql
2. 下載並安裝 **Npgsql**（Microsoft 官方連結）
3. **完全關閉 Excel 再重新開啟**
4. 重新嘗試：**資料** → **取得資料** → **從 PostgreSQL 資料庫**

### 連線步驟

1. 開新 Excel 活頁簿，另存為 `SRPE_Dashboard.xlsx`（建議放喺 `visualize/` 資料夾）
2. 選單：**資料** → **取得資料** → **從資料庫** → **從 PostgreSQL 資料庫**
3. 填寫連線資料：

   | 欄位 | 值 |
   |------|-----|
   | 伺服器 | `localhost` |
   | 資料庫 | `srpe_etl` |

4. 按 **確定**，選擇 **資料庫** 登入
5. 用戶名：`postgres`
6. 密碼：你 `.env` 入面嘅 `SRPE_DB_PASSWORD`
7. 如果彈出 SSL 提示，選 **不加密** 或 **Prefer** 即可（本機測試）

> 如果搵唔到 PostgreSQL 選項：安裝 [PostgreSQL Unicode ODBC driver](https://www.postgresql.org/ftp/odbc/versions/msi/)，然後改用 **從 ODBC** 連線。

---

## 第二步：載入 `vw_sales_detail`

1. 在 Navigator 展開 `public`
2. 勾選 **`vw_sales_detail`**
3. 按 **載入**

預期：**1145 行**。

### 用 M 代碼載入（進階）

1. **資料** → **取得資料** → **從其他來源** → **空白查詢**
2. **進階編輯器**，貼上 `visualize/power_query_sales_detail.m` 內容
3. 按 **關閉並載入**

---

## 第三步：建議儀表板（3 個 Pivot + KPI）

在空白工作表建立以下內容（全部用 `vw_sales_detail` 做來源）：

### Sheet 1：`Dashboard`

**KPI 區（用公式）**

| 指標 | 公式範例 |
|------|----------|
| 總交易數 | `=COUNTA(vw_sales_detail[natural_key])` |
| 已簽正式合約 | `=COUNTIF(vw_sales_detail[transaction_status],"asp_signed")` |
| 撻訂數 | `=COUNTIF(vw_sales_detail[transaction_status],"terminated")` |
| 撻訂率 | `=撻訂數/總交易數`（設為百分比格式） |
| 平均成交價 | `=AVERAGE(vw_sales_detail[final_price_hkd])`（設為貨幣 HK$） |

**Pivot 1：按月成交量**

- 列：`pasp_month`
- 值：`natural_key`（計數）
- 圖表：折線圖

**Pivot 2：按座數平均成交價**

- 列：`block_name`
- 值：`final_price_hkd`（平均）
- 圖表：橫向長條圖

**Pivot 3：付款方式分佈**

- 列：`payment_category`
- 值：`natural_key`（計數）
- 圖表：圓餅圖

**Pivot 4：交易狀態**

- 列：`transaction_status`
- 值：`natural_key`（計數）

### 建立 Pivot 步驟

1. 選 `vw_sales_detail` 任一儲存格
2. **插入** → **樞紐分析表**
3. 新工作表 → 拖欄位到 列 / 值
4. 選 Pivot → **插入** → 建議圖表類型

---

## 第四步：設定重新整理（面試加分）

1. **資料** → **查詢與連線**
2. 右鍵 `vw_sales_detail` → **內容**
3. 面試時按 **全部重新整理**，儀表板即時更新

講解重點：

> 「ETL pipeline 更新 PostgreSQL 之後，Excel 透過 Power Query 一鍵 refresh，唔使手動 export CSV。」

---

## 第五步（可選）：載入預先匯總 View

額外載入 `vw_monthly_sales`、`vw_block_summary`，直接做趨勢圖同座數比較。

---

## 面試講解腳本（30 秒）

1. **Extract**：從 SRPE 下載 RT PDF，用 pdfplumber 解析
2. **Transform**：Pandas 清洗價錢、日期、付款方式、交易狀態
3. **Load**：UPSERT 入 PostgreSQL star schema
4. **Visualize**：Power Query 連 `vw_sales_detail`，Pivot 展示成交量、撻訂率、均價

---

## 常見問題

| 問題 | 解決 |
|------|------|
| 連線逾時 | 確認 PostgreSQL 服務有開 |
| 密碼錯 | 對照 `.env` 入面 `SRPE_DB_PASSWORD` |
| View 搵唔到 | 先跑 `python run_load.py --init-views` |
| 價錢顯示怪 | 將 `final_price_hkd` 欄設為 **貨幣（HK$）** |
