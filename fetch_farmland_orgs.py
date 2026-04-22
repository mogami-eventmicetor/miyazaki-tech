"""
全国47都道府県の農地中間管理機構の名称とURLを
https://www.nouchi.or.jp/GOURIKA//top/li00.jsp からスクレイピングして
farmland_organizations.json に保存するスクリプト。
"""

import json
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# データ定義
# ---------------------------------------------------------------------------

# スクレイピングで都道府県名が取れない場合の補完マップ
# （機構名に含まれる地名から都道府県を特定できないケース向け）
# 機構名にひらがな・愛称で都道府県名が含まれる場合の補完マップ
PREF_NICKNAME: dict = {
    "あおもり": "青森県", "みやぎ": "宮城県", "やまがた": "山形県",
    "いしかわ": "石川県", "ふくい": "福井県",  "ひょうご": "兵庫県",
    "なら": "奈良県",    "しまね": "島根県",    "やまぐち": "山口県",
    "えひめ": "愛媛県",  "ふくおか": "福岡県",  "かごしま": "鹿児島県",
    "おきなわ": "沖縄県",
}

PREF_ORDER = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


@dataclass
class FarmlandOrg:
    prefecture: str
    name: str
    url: Optional[str] = field(default=None)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# スクレイパー
# ---------------------------------------------------------------------------

class FarmlandOrgScraper:
    """
    nouchi.or.jp の一覧ページから機構名とURLを取得する。
    テーブル行を順番に処理し、都道府県順リストと突合して都道府県名を付与する。
    """

    SOURCE_URL = "https://www.nouchi.or.jp/GOURIKA//top/li00.jsp"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def scrape(self) -> List[FarmlandOrg]:
        print(f"取得中: {self.SOURCE_URL}")
        res = requests.get(self.SOURCE_URL, headers=self.HEADERS, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        entries = self._extract_entries(soup)
        print(f"  → {len(entries)} 件を抽出")
        return entries

    def _extract_entries(self, soup: BeautifulSoup) -> List[FarmlandOrg]:
        results: List[FarmlandOrg] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            name = a.get_text(strip=True)

            # 機構名リンクのみ対象（画像リンク・ページ内リンクを除外）
            if not name:
                continue
            if href.startswith("#") or "nouchi.or.jp" in href:
                continue
            if not (href.startswith("http") or href.startswith("www")):
                continue
            if href.endswith(".pdf") or href.endswith(".PDF"):
                continue

            url = href if href.startswith("http") else "https://" + href
            if not url.endswith("/"):
                url += "/"

            prefecture = self._detect_prefecture(name)
            results.append(FarmlandOrg(prefecture=prefecture, name=name, url=url))

        return results

    @staticmethod
    def _detect_prefecture(name: str) -> str:
        """機構名に含まれる都道府県名を抽出する。見つからなければ空文字を返す。"""
        for pref in PREF_ORDER:
            short = pref.rstrip("都道府県")
            if pref in name or short in name:
                return pref
        # ひらがな・愛称での照合
        for nickname, pref in PREF_NICKNAME.items():
            if nickname in name:
                return pref
        return ""


# ---------------------------------------------------------------------------
# 統計レポート
# ---------------------------------------------------------------------------

class StatisticsReporter:
    """farmland_organizations.json を読み込み統計を表示する。"""

    def report(self, json_path: str) -> None:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        total = len(data)
        found = sum(1 for d in data if d["url"])

        print("\n" + "=" * 60)
        print("  全国 農地中間管理機構 一覧")
        print("=" * 60)
        for entry in data:
            url_disp = entry["url"] or "未取得"
            print(f"  {entry['prefecture']:<5} {entry['name']:<25} {url_disp}")
        print("\n" + "-" * 60)
        print(f"  合計: {total} 機構  (URL取得済み: {found} 件)")
        print("=" * 60)


# ---------------------------------------------------------------------------
# オーケストレーター
# ---------------------------------------------------------------------------

class FarmlandOrgCollector:
    """スクレイピング・保存・統計表示を束ねるメインクラス。"""

    OUTPUT_PATH = "farmland_organizations.json"

    def __init__(self) -> None:
        self._scraper = FarmlandOrgScraper()
        self._reporter = StatisticsReporter()

    def run(self) -> None:
        results = self._scraper.scrape()
        self._save(results)
        print(f"保存先: {self.OUTPUT_PATH}")
        self._reporter.report(self.OUTPUT_PATH)

    def _save(self, results: List[FarmlandOrg]) -> None:
        with open(self.OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in results], f,
                      ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    FarmlandOrgCollector().run()
