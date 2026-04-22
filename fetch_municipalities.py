"""
宮崎県26市町村の公式HPを収集して municipalities.json に保存するスクリプト。

URL解決の優先順位:
  1. 既知パターン候補（city/town/vill + ローマ字名）をHEADリクエストで確認
  2. 失敗した場合、DuckDuckGo HTMLをスクレイピングして上位URLを取得
  3. それも失敗した場合は null
"""

import json
import time
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# データ定義
# ---------------------------------------------------------------------------

@dataclass
class Municipality:
    name: str
    kana: str
    type: str      # "city" | "town" | "village"
    romaji: str
    url: Optional[str] = field(default=None)
    url_source: Optional[str] = field(default=None)

    TYPE_LABEL: Dict[str, str] = field(default_factory=dict, init=False, repr=False, compare=False)

    @property
    def label(self) -> str:
        return {"city": "市", "town": "町", "village": "村"}.get(self.type, "")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "TYPE_LABEL"}


MUNICIPALITIES: List[Municipality] = [
    # 市 (9)
    Municipality("宮崎市",   "みやざきし",       "city",    "miyazaki"),
    Municipality("都城市",   "みやこのじょうし",  "city",    "miyakonojo"),
    Municipality("延岡市",   "のべおかし",       "city",    "nobeoka"),
    Municipality("日南市",   "にちなんし",       "city",    "nichinan"),
    Municipality("小林市",   "こばやしし",       "city",    "kobayashi"),
    Municipality("日向市",   "ひゅうがし",       "city",    "hyuga"),
    Municipality("串間市",   "くしまし",         "city",    "kushima"),
    Municipality("西都市",   "さいとし",         "city",    "saito"),
    Municipality("えびの市", "えびのし",         "city",    "ebino"),
    # 町 (14)
    Municipality("三股町",   "みまたちょう",     "town",    "mimata"),
    Municipality("高原町",   "たかはるちょう",   "town",    "takaharu"),
    Municipality("国富町",   "くにとみちょう",   "town",    "kunitomi"),
    Municipality("綾町",     "あやちょう",       "town",    "aya"),
    Municipality("高鍋町",   "たかなべちょう",   "town",    "takanabe"),
    Municipality("新富町",   "しんとみちょう",   "town",    "shintomi"),
    Municipality("木城町",   "きじょうちょう",   "town",    "kijo"),
    Municipality("川南町",   "かわみなみちょう", "town",    "kawaminami"),
    Municipality("都農町",   "つのちょう",       "town",    "tsuno"),
    Municipality("門川町",   "かどがわちょう",   "town",    "kadogawa"),
    Municipality("美郷町",   "みさとちょう",     "town",    "misato"),
    Municipality("高千穂町", "たかちほちょう",   "town",    "takachiho"),
    Municipality("日之影町", "ひのかげちょう",   "town",    "hinokage"),
    Municipality("五ヶ瀬町", "ごかせちょう",     "town",    "gokase"),
    # 村 (3)
    Municipality("西米良村", "にしめらそん",     "village", "nishimera"),
    Municipality("諸塚村",   "もろつかそん",     "village", "morotsuka"),
    Municipality("椎葉村",   "しいばそん",       "village", "shiiba"),
]


# ---------------------------------------------------------------------------
# URL解決
# ---------------------------------------------------------------------------

class URLResolver:
    """
    自治体ごとのURL候補を生成・検証し、公式HPのURLを返す。
    パターン検証が全滅した場合は DuckDuckGo HTML検索にフォールバックする。
    """

    _TYPE_PREFIX = {"city": "city", "town": "town", "village": "vill"}
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    _TIMEOUT = 8

    def resolve(self, m: Municipality) -> Municipality:
        print(f"[{m.name}] パターン候補を確認中...")
        for url in self._candidate_urls(m):
            print(f"  試行: {url}")
            if self._verify(url):
                print(f"  ✓ 確認OK: {url}")
                m.url = url
                m.url_source = "pattern_verified"
                return m
            time.sleep(0.3)

        print(f"  → パターン不一致。DuckDuckGoで検索中...")
        found = self._search_duckduckgo(f"{m.name} 宮崎県 公式ホームページ")
        time.sleep(1.0)

        if found:
            print(f"  ✓ DDG取得: {found}")
            m.url = found
            m.url_source = "duckduckgo"
        else:
            print(f"  ✗ URL取得失敗")
            m.url = None
            m.url_source = "not_found"

        return m

    def _candidate_urls(self, m: Municipality) -> List[str]:
        prefix = self._TYPE_PREFIX[m.type]
        r = m.romaji
        return [
            f"https://www.{prefix}.{r}.miyazaki.jp/",
            f"https://www.{prefix}.{r}.lg.jp/",
            f"https://{r}.miyazaki.jp/",
            f"https://www.{r}.miyazaki.jp/",
        ]

    def _verify(self, url: str) -> bool:
        try:
            res = requests.head(url, headers=self._HEADERS, timeout=self._TIMEOUT,
                                allow_redirects=True)
            return res.status_code < 400
        except Exception:
            try:
                res = requests.get(url, headers=self._HEADERS, timeout=self._TIMEOUT,
                                   allow_redirects=True, stream=True)
                res.close()
                return res.status_code < 400
            except Exception:
                return False

    def _search_duckduckgo(self, query: str) -> Optional[str]:
        try:
            res = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=self._HEADERS,
                timeout=self._TIMEOUT,
            )
            soup = BeautifulSoup(res.text, "html.parser")
            links = [self._normalize_href(a.get("href", "")) for a in soup.select("a.result__url")]
            links = [l for l in links if l.startswith("http")]

            # 公式ドメイン優先
            for href in links:
                if "miyazaki.jp" in href or ".lg.jp" in href:
                    return href
            return links[0] if links else None
        except Exception as e:
            print(f"    [DuckDuckGo error] {e}")
            return None

    @staticmethod
    def _normalize_href(href: str) -> str:
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        return href if href.endswith("/") else href + "/"


# ---------------------------------------------------------------------------
# 統計レポート
# ---------------------------------------------------------------------------

class StatisticsReporter:
    """municipalities.json を読み込み、市/町/村の種別統計をターミナルに表示する。"""

    _LABELS = [("city", "市"), ("town", "町"), ("village", "村")]
    _BAR_WIDTH = 20

    def report(self, json_path: str) -> None:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        groups: Dict[str, list] = {"city": [], "town": [], "village": []}
        for entry in data:
            t = entry.get("type", "")
            if t in groups:
                groups[t].append(entry)

        total = len(data)
        print("\n" + "=" * 52)
        print("  宮崎県 市町村 種別統計")
        print("=" * 52)

        for type_key, label in self._LABELS:
            items = groups[type_key]
            count = len(items)
            pct = count / total * 100 if total else 0
            bar_len = round(self._BAR_WIDTH * count / total) if total else 0
            bar = "#" * bar_len + "-" * (self._BAR_WIDTH - bar_len)
            print(f"\n  {label} ({count}件 / {pct:.1f}%)  [{bar}]")
            for entry in items:
                url_disp = entry["url"] or "未取得"
                print(f"    - {entry['name']:<7}  {url_disp}")

        print("\n" + "-" * 52)
        print(f"  合計: {total} 市町村  "
              f"(市 {len(groups['city'])} / "
              f"町 {len(groups['town'])} / "
              f"村 {len(groups['village'])})")
        print("=" * 52)


# ---------------------------------------------------------------------------
# オーケストレーター
# ---------------------------------------------------------------------------

class MunicipalityCollector:
    """URL解決・JSON保存・統計表示を束ねるメインクラス。"""

    OUTPUT_PATH = "municipalities.json"

    def __init__(self) -> None:
        self._resolver = URLResolver()
        self._reporter = StatisticsReporter()

    def run(self) -> None:
        results = [self._resolver.resolve(m) for m in MUNICIPALITIES]
        self._save(results)

        found = sum(1 for r in results if r.url)
        print(f"\n完了: {found}/{len(results)} 件のURLを取得")
        print(f"保存先: {self.OUTPUT_PATH}")
        self._print_fetch_summary(results)
        self._reporter.report(self.OUTPUT_PATH)

    def _save(self, results: List[Municipality]) -> None:
        with open(self.OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([m.to_dict() for m in results], f, ensure_ascii=False, indent=2)

    @staticmethod
    def _print_fetch_summary(results: List[Municipality]) -> None:
        print("\n--- 取得結果サマリー ---")
        for r in results:
            status = r.url or "❌ 未取得"
            src = f"[{r.url_source}]" if r.url else ""
            print(f"  {r.name:<8} {src:<22} {status}")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    MunicipalityCollector().run()
