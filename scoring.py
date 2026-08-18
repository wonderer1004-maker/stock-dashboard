"""
scoring.py
==========
대가(버핏/리버모어/달리오) 스타일 스코어링 + 한국형 공포탐욕지수 계산 + 매매전략 산출.
전부 순수 함수(네트워크 접속 없음) -- data.json 을 읽어 build_dashboard.py 에서 호출한다.
"""
from __future__ import annotations


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def classify_fg(score: float):
    """CNN 공포탐욕지수와 동일한 5단계 밴드로 분류."""
    if score >= 76:
        return "Extreme Greed", "극단적 탐욕"
    if score >= 56:
        return "Greed", "탐욕"
    if score >= 45:
        return "Neutral", "중립"
    if score >= 25:
        return "Fear", "공포"
    return "Extreme Fear", "극단적 공포"


def fg_color(rating_en: str) -> str:
    """dataviz 스킬의 status 팔레트를 사용 (fear=critical/serious, greed=good)."""
    return {
        "Extreme Fear": "#d03b3b",   # critical
        "Fear": "#ec835a",           # serious
        "Neutral": "#898781",        # muted
        "Greed": "#0ca30c",          # good
        "Extreme Greed": "#006300",  # deep good (success text)
    }.get(rating_en, "#898781")


def kospi_fear_greed(components: list[dict]) -> dict:
    """
    components: [{"name":str, "score":0-100, "weight":float, "detail":str}, ...]
    CNN의 7개 지표 방법론을 한국 시장에서 구할 수 있는 대체 지표 5개로 재구성:
      1) 모멘텀 (52주 레인지 내 위치 + 최근 등락)
      2) 변동성 (V-KOSPI 또는 일중 변동폭)
      3) 시장 폭 (코스피 vs 코스닥 상대강도 = 대형주/소형주 순환)
      4) 안전자산 수요 (원/달러 환율 변동, 역상관)
      5) 거래심리 (거래대금/거래량 변화)
    """
    total_w = sum(c["weight"] for c in components) or 1
    score = sum(c["score"] * c["weight"] for c in components) / total_w
    score = round(clamp(score), 1)
    rating_en, rating_kr = classify_fg(score)
    return {
        "score": score,
        "rating_en": rating_en,
        "rating_kr": rating_kr,
        "color": fg_color(rating_en),
        "components": components,
    }


def buffett_score(stock: dict) -> float:
    """
    가치/퀄리티 스코어 (0-100).
    - PER 낮을수록 가점 (PER 5 -> 100, PER 30 이상 -> 0)
    - 52주 고점 대비 하락폭(안전마진) 클수록 가점 (33% 이상 하락 -> 100)
    """
    per = stock.get("per")
    pct_from_high = stock.get("pct_from_52w_high")  # 음수(예: -18.4)

    score_per = None
    if per and per > 0:
        score_per = clamp(100 - (per - 5) * 4)

    score_mos = None
    if pct_from_high is not None:
        score_mos = clamp(abs(min(pct_from_high, 0)) * 3)

    parts = [p for p in (score_per, score_mos) if p is not None]
    if not parts:
        return 50.0
    return round(sum(parts) / len(parts), 1)


def livermore_score(stock: dict) -> float:
    """
    모멘텀/돌파 스코어 (0-100).
    - 52주 신고가에 근접할수록 가점 (신고가 -> 100)
    - 최근 등락률(상승 모멘텀)이 강할수록 가점
    """
    pct_from_high = stock.get("pct_from_52w_high")
    change_pct = stock.get("change_pct", 0)

    score_prox = clamp(100 - abs(pct_from_high) * 2) if pct_from_high is not None else 50
    score_chg = clamp(50 + change_pct * 5)

    return round(score_prox * 0.6 + score_chg * 0.4, 1)


def style_tag(buffett: float, livermore: float) -> str:
    if livermore >= 65 and livermore - buffett >= 10:
        return "리버모어형 (모멘텀·돌파)"
    if buffett >= 65 and buffett - livermore >= 10:
        return "버핏형 (가치·안전마진)"
    return "혼합형 (가치+모멘텀)"


def trade_levels(stock: dict, style: str) -> dict:
    """
    스타일별 매수가/목표가/손절가 산출.
    price: 현재가
    """
    price = stock["price"]

    if "리버모어" in style:
        # 돌파매매: 눌림목 진입, R:R 약 1:2, 손절은 리버모어/오닐식 7~8%
        entry_low = round(price * 0.97, 2)
        entry_high = round(price * 1.01, 2)
        target = round(price * 1.18, 2)
        stop = round(price * 0.92, 2)
        note = "52주 고점 부근 돌파 시 거래량 동반 확인 후 분할 매수. 손절 -8% 원칙 엄수(리버모어 손절 규율)."
    elif "버핏" in style:
        # 가치매매: 현재가 이하 지정가, 목표가 없음(장기보유), 가격 기준 손절 없음
        entry_low = round(price * 0.93, 2)
        entry_high = round(price * 1.0, 2)
        target = None
        stop = None
        note = "가격이 아닌 '해자(경쟁우위)·실적' 훼손 여부로 매도 판단. 추가 하락 시 분할 매수(에버리징)로 평단 관리."
    else:
        entry_low = round(price * 0.96, 2)
        entry_high = round(price * 1.0, 2)
        target = round(price * 1.12, 2)
        stop = round(price * 0.93, 2)
        note = "가치 지표와 모멘텀 지표가 혼재 -> 분할 매수, 목표가 도달 시 절반 익절 후 나머지는 추세 추종."

    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "target": target,
        "stop": stop,
        "note": note,
    }


def dalio_allocation(fg_score: float) -> dict:
    """
    올웨더(All Weather) 포트폴리오를 현재 시장 국면(F&G)에 맞춰 소폭 틸트.
    기본: 주식30 / 장기채40 / 중기채15 / 금7.5 / 원자재7.5
    극단적 탐욕 -> 주식 비중 축소, 현금성/금 비중 확대 (과열 리스크 관리)
    극단적 공포 -> 주식 비중 확대 (버핏: "남들이 공포에 떨 때 욕심을 내라")
    """
    tilt = round((50 - fg_score) * 0.3, 1)  # 공포일수록 +, 탐욕일수록 -
    equity = clamp(30 + tilt, 15, 45)
    freed = 30 - equity  # 주식에서 빠진/더해진 만큼 채권+금+현금에서 보정
    long_bond = clamp(40 - freed * 0.5, 20, 50)
    mid_bond = clamp(15 - freed * 0.2, 8, 20)
    gold = clamp(7.5 + freed * 0.4, 5, 15)
    cash_or_commodity = round(100 - equity - long_bond - mid_bond - gold, 1)

    return {
        "주식(국내+해외)": round(equity, 1),
        "장기채권": round(long_bond, 1),
        "중기채권": round(mid_bond, 1),
        "금": round(gold, 1),
        "원자재/현금": max(cash_or_commodity, 0),
        "tilt_note": (
            f"현재 F&G {fg_score}점 국면 기준 기본 올웨더(30/40/15/7.5/7.5) 대비 "
            f"주식 비중을 {tilt:+.1f}%p 틸트했습니다."
        ),
    }
