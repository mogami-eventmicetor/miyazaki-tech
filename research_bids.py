"""
全国47農地中間管理機構のWebサイトをスキャンし、
システム開発関連の入札・調達案件を調査してレポートするスクリプト。

調査フロー:
  1. farmland_organizations.json から47機構のURLを読み込む
  2. 各機構のトップページからリンクを収集
  3. 入札・調達・お知らせ系ページを優先的に取得
  4. 御社強み（農地管理・kintone・クラウド）への関連度をスコアリング
  5. bid_research_report.json に保存 + ターミナルにサマリー表示
"""

import json
import time
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# スコアリング用キーワード定義
# ---------------------------------------------------------------------------

# 入札・調達ページを示すキーワード（リンクテキスト・URL両方で照合）
PROCUREMENT_KEYWORDS = [
    "入札", "調達", "公募", "委託", "発注", "契約", "募集",
    "入札情報", "調達情報", "公告", "競争", "随意",
]

# システム開発関連キーワード（高スコア）
SYSTEM_KEYWORDS = [
    "システム", "クラウド", "kintone", "キントーン", "DX", "デジタル",
    "アプリ", "ソフトウェア", "開発", "構築", "整備", "情報化",
    "IT", "ICT", "SaaS", "ASP", "データ",
]

# 農地業務関連キーワード（高スコア）
FARMLAND_KEYWORDS = [
    "農地", "農地売買", "農地貸借", "農地中間管理", "促進計画",
    "農地バンク", "出し手", "受け手", "合意解約", "売渡", "買入",
    "農業委員会", "利用権", "賃借",
]

# お知らせ・新着ページを示すキーワード
NEWS_KEYWORDS = [
    "お知らせ", "新着", "ニュース", "トピックス", "topics",
    "news", "info", "information", "最新情報", "更新情報",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


# ---------------------------------------------------------------------------
# データ定義
# ---------------------------------------------------------------------------

@dataclass
class BidOpportunity:
    prefecture: str
    org_name: str
    page_title: str
    page_url: str
    matched_keywords: List[str]
    relevance_score: int          # 0〜100
    snippet: str                  # 該当テキストの抜粋
    category: str                 # "入札/調達" | "お知らせ" | "その他"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# サイトスキャナー
# ---------------------------------------------------------------------------

class SiteScanner:
    """
    1機構のWebサイトをスキャンし、入札・調達関連ページを発見する。
    トップページのリンクを収集 → 優先度の高いページを取得 → キーワード照合。
    """

    MAX_PAGES = 6       # 1機構あたり最大取得ページ数
    MAX_LINKS = 40      # トップページから収集するリンク上限

    def scan(self, prefecture: str, org_name: str, base_url: str) -> List[BidOpportunity]:
        links = self._collect_links(base_url)
        if not links:
            return []

        prioritized = self._prioritize(links, base_url)
        opportunities: List[BidOpportunity] = []

        for url, label in prioritized[:self.MAX_PAGES]:
            time.sleep(0.5)
            result = self._analyze_page(prefecture, org_name, url, label)
            if result:
                opportunities.append(result)

        return opportunities

    def _collect_links(self, base_url: str) -> List[Tuple[str, str]]:
        """トップページから内部リンク（URL, テキスト）を収集する。"""
        try:
            res = requests.get(base_url, headers=HEADERS, timeout=TIMEOUT,
                               allow_redirects=True)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, "html.parser")
            base_domain = urlparse(base_url).netloc

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True)
                full_url = urljoin(base_url, href)
                # 同一ドメインの内部リンクのみ
                if urlparse(full_url).netloc == base_domain and full_url != base_url:
                    links.append((full_url, text))

            # 重複除去
            seen = set()
            unique = []
            for url, text in links:
                if url not in seen:
                    seen.add(url)
                    unique.append((url, text))
            return unique[:self.MAX_LINKS]
        except Exception:
            return []

    def _prioritize(self, links: List[Tuple[str, str]], base_url: str) -> List[Tuple[str, str]]:
        """
        入札・調達・お知らせ系のリンクを上位に並べ替える。
        スコアが同じ場合は元の順序を維持。
        """
        def score(item: Tuple[str, str]) -> int:
            url, text = item
            combined = (url + " " + text).lower()
            s = 0
            for kw in PROCUREMENT_KEYWORDS:
                if kw in combined:
                    s += 3
            for kw in NEWS_KEYWORDS:
                if kw in combined:
                    s += 2
            for kw in SYSTEM_KEYWORDS:
                if kw in combined:
                    s += 2
            return s

        return sorted(links, key=score, reverse=True)

    def _analyze_page(self, prefecture: str, org_name: str,
                      url: str, link_text: str) -> Optional[BidOpportunity]:
        """ページを取得してキーワード照合・スコアリングを行う。"""
        try:
            res = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                               allow_redirects=True)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, "html.parser")

            # <script>/<style> を除去してテキスト抽出
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            title = soup.title.string.strip() if soup.title else link_text

            matched, score = self._score_text(text)
            if score == 0:
                return None

            snippet = self._extract_snippet(text, matched)
            category = self._categorize(url, link_text, text)

            return BidOpportunity(
                prefecture=prefecture,
                org_name=org_name,
                page_title=title,
                page_url=url,
                matched_keywords=matched,
                relevance_score=min(score, 100),
                snippet=snippet,
                category=category,
            )
        except Exception:
            return None

    @staticmethod
    def _score_text(text: str) -> Tuple[List[str], int]:
        """テキストからキーワードを照合してスコアを計算する。"""
        matched = []
        score = 0
        for kw in PROCUREMENT_KEYWORDS:
            if kw in text:
                matched.append(kw)
                score += 5
        for kw in SYSTEM_KEYWORDS:
            if kw in text:
                matched.append(kw)
                score += 8
        for kw in FARMLAND_KEYWORDS:
            if kw in text:
                matched.append(kw)
                score += 6
        return list(dict.fromkeys(matched)), score  # 重複除去・順序保持

    @staticmethod
    def _extract_snippet(text: str, keywords: List[str]) -> str:
        """最初にキーワードが出現する前後100文字を抜き出す。"""
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                start = max(0, idx - 60)
                end = min(len(text), idx + 100)
                raw = text[start:end].replace("\n", " ").strip()
                return re.sub(r"\s+", " ", raw)
        return ""

    @staticmethod
    def _categorize(url: str, text: str, body: str) -> str:
        combined = (url + " " + text + " " + body[:200]).lower()
        for kw in PROCUREMENT_KEYWORDS[:6]:  # 入札〜発注
            if kw in combined:
                return "入札/調達"
        for kw in NEWS_KEYWORDS:
            if kw in combined:
                return "お知らせ"
        return "その他"


# ---------------------------------------------------------------------------
# レポートジェネレーター
# ---------------------------------------------------------------------------

class ReportGenerator:
    """調査結果を JSON 保存 + ターミナル表示する。"""

    OUTPUT_PATH = "bid_research_report.json"

    def save(self, opportunities: List[BidOpportunity]) -> None:
        with open(self.OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([o.to_dict() for o in opportunities],
                      f, ensure_ascii=False, indent=2)

    def print_summary(self, opportunities: List[BidOpportunity],
                      scanned: int, total: int) -> None:
        high   = [o for o in opportunities if o.relevance_score >= 50]
        medium = [o for o in opportunities if 20 <= o.relevance_score < 50]
        low    = [o for o in opportunities if o.relevance_score < 20]

        print("\n" + "=" * 68)
        print("  農地中間管理機構 システム開発案件リサーチ結果")
        print("=" * 68)
        print(f"  スキャン: {scanned}/{total} 機構  |  ヒットページ数: {len(opportunities)} 件")
        print(f"  高関連 (50点〜): {len(high)}件  "
              f"中関連 (20〜49点): {len(medium)}件  "
              f"低関連 (~19点): {len(low)}件")

        for label, group in [("★ 高関連 (優先確認)", high),
                              ("◎ 中関連 (要チェック)", medium)]:
            if not group:
                continue
            print(f"\n{'─' * 68}")
            print(f"  {label}")
            print(f"{'─' * 68}")
            for o in sorted(group, key=lambda x: -x.relevance_score):
                print(f"\n  [{o.relevance_score:3d}点] {o.prefecture} / {o.org_name}")
                print(f"         カテゴリ : {o.category}")
                print(f"         ページ   : {o.page_title}")
                print(f"         URL      : {o.page_url}")
                print(f"         キーワード: {', '.join(o.matched_keywords[:8])}")
                print(f"         抜粋     : {o.snippet[:120]}...")

        print("\n" + "=" * 68)
        print(f"  詳細は {self.OUTPUT_PATH} を確認してください")
        print("=" * 68)


# ---------------------------------------------------------------------------
# オーケストレーター
# ---------------------------------------------------------------------------

class BidResearcher:
    """47機構を順番にスキャンしてレポートを生成するメインクラス。"""

    SOURCE_JSON = "farmland_organizations.json"

    def __init__(self) -> None:
        self._scanner = SiteScanner()
        self._reporter = ReportGenerator()

    def run(self) -> None:
        orgs = self._load_orgs()
        all_opportunities: List[BidOpportunity] = []
        scanned = 0

        for org in orgs:
            if not org.get("url"):
                print(f"  [{org['prefecture']}] URL未登録 → スキップ")
                continue

            print(f"\n[{org['prefecture']}] {org['name']} をスキャン中...")
            hits = self._scanner.scan(
                prefecture=org["prefecture"],
                org_name=org["name"],
                base_url=org["url"],
            )
            scanned += 1

            if hits:
                best = max(hits, key=lambda h: h.relevance_score)
                print(f"  → {len(hits)} ページヒット（最高スコア: {best.relevance_score}点）")
                all_opportunities.extend(hits)
            else:
                print(f"  → 関連ページなし")

            time.sleep(0.8)

        self._reporter.save(all_opportunities)
        self._reporter.print_summary(all_opportunities, scanned, len(orgs))

    def _load_orgs(self) -> List[dict]:
        with open(self.SOURCE_JSON, encoding="utf-8") as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    BidResearcher().run()
