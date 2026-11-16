# fundstar（基金白話通）

把台灣公募基金的公開資料翻成一般人看得懂的數字與白話。
**只提供資訊與教育，不提供投資建議。**本站不收費、不放廣告、不導購。

## 原則

- 只使用開放授權資料；沒有合法來源的欄位一律顯示「資料不足」，不用估計值填補。
- 文字只寫描述句（數字與事實），不寫判斷句（推薦、該不該買、像不像）。
- 每個數字標示資料日期與來源。
- 0 元建置：GitHub Actions 每日排程、資料存在 GitHub Releases、靜態網站。

## 資料來源（M1）

| 代號 | 內容 | 提供者 | 開放資料集 |
|---|---|---|---|
| tdcc_offshore_basic | 境外基金基本資料（含風險收益等級、規模） | 臺灣集中保管結算所 | https://data.gov.tw/dataset/11639 |
| tdcc_offshore_nav | 境外基金淨值（API 只提供最近數日，歷史靠每日累積） | 臺灣集中保管結算所 | https://data.gov.tw/dataset/11641 |
| tdcc_offshore_div | 境外基金配息（含「本金／配息」比例） | 臺灣集中保管結算所 | https://data.gov.tw/dataset/11642 |
| fsc_domestic_nav | 境內基金每日淨值 | 金融監督管理委員會證券期貨局 | https://data.gov.tw/dataset/11109 |

顯名聲明：以上資料依政府資料開放授權條款（Open Government Data License）進行公眾釋出，
使用者於遵守本條款各項規定之前提下，得利用之。政府資料開放授權條款：https://data.gov.tw/license

### 已知缺口

- **境內基金配息**：沒有開放授權來源。境內「配息型」級別的含息報酬顯示「資料不足」；累積型級別的淨值本身即含息。
- **持股、產業／國家配置、費用率**：沒有開放授權來源（見 M0 報告）。
- **境外淨值歷史**：從開始排程那天起累積，之前的期間顯示「資料不足」。

## 指令

```bash
pip install -r requirements.txt
python -m pytest -q
python -m fundstar fetch      # 循序抓取所有來源，原始檔存 data/raw/
python -m fundstar build      # 把當天原始檔併入 data/curated/*.parquet
python -m fundstar rebuild    # 從所有原始檔重建
python -m fundstar status     # 寫出 data/STATUS.json
python -m fundstar validate validation/official_returns.csv   # 與官方區間報酬比對（容許 0.05 個百分點）
```

## 含息報酬定義

配息在除息日以當日淨值再投資：`index_t = index_{t-1} × (nav_t + 配息_t) / nav_{t-1}`。
除息日沒有淨值時，套用在之後第一個淨值日並記錄警告。官方區間報酬只用於內部核對，不對外顯示。

## 資料存放

- 原始檔：每月一個 Release（`raw-YYYY-MM`），每日一個檔案。
- 整理後資料：Release `data-latest` 的 Parquet，每日覆蓋。
- repo 只提交 `STATUS.json`（筆數、日期範圍），避免 git 歷史膨脹，也讓排程維持活動狀態。
