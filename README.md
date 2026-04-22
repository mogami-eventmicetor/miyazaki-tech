# miyazaki-tech

宮崎県全26市町村の公式HPのURLを自動収集し、`municipalities.json` に保存するPythonスクリプト。

## 機能

- 市区町村のURLパターン（`city/town/vill + ローマ字名`）をHEADリクエストで検証
- パターン不一致の場合は DuckDuckGo HTMLスクレイピングにフォールバック（APIキー不要）
- 収集結果を `municipalities.json` に保存
- 市 / 町 / 村の種別ごとに件数・URLの統計をターミナルに表示

## セットアップ

```bash
# 仮想環境を作成・有効化
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 依存ライブラリをインストール
pip install -r requirements.txt
```

## 使い方

```bash
python3 fetch_municipalities.py
```

実行すると以下の順に処理が進む。

1. 26市町村ごとにURL候補を順番に試行
2. HTTP到達確認（HEAD → GET フォールバック）
3. 全候補が失敗した場合は DuckDuckGo で検索
4. 結果を `municipalities.json` に保存
5. 市 / 町 / 村の種別統計をターミナルに出力

## 出力ファイル

### `municipalities.json`

```json
[
  {
    "name": "宮崎市",
    "kana": "みやざきし",
    "type": "city",
    "romaji": "miyazaki",
    "url": "https://www.city.miyazaki.miyazaki.jp/",
    "url_source": "pattern_verified"
  },
  ...
]
```

| フィールド | 説明 |
|---|---|
| `name` | 自治体名（日本語） |
| `kana` | 読み仮名 |
| `type` | `city` / `town` / `village` |
| `romaji` | URL生成用ローマ字表記 |
| `url` | 公式HP URL（取得失敗時は `null`） |
| `url_source` | `pattern_verified` / `duckduckgo` / `not_found` |

## クラス構成

```
Municipality          # 自治体データ（dataclass）
URLResolver           # URL候補生成・HTTP検証・DDGフォールバック
StatisticsReporter    # JSONを読み込み市/町/村の統計を表示
MunicipalityCollector # 全体オーケストレーション（エントリポイント）
```

## 注意事項

- 実行には外部へのHTTPアクセスが必要
- DuckDuckGo の検索結果は公式HP以外のページを返す場合がある（手動確認を推奨）
- 自治体サイトのURL変更に伴い、定期的な再実行を推奨
