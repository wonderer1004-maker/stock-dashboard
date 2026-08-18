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


def _percentile_ranks(stocks, getter, ascending=True):
    """
    getter(stock) -> 값(없으면 None). ascending=True면 값이 작을수록 좋음(예: PER, 부채비율).
    반환: ({index: percentile 0~100(높을수록 좋음)}, 데이터 커버리지 비율 0~1).

    절대 임계값(예: "PER 5 이하면 100점, 30 이상이면 0점")을 쓰지 않고 같은 유니버스
    안에서의 상대 순위를 쓰는 이유: 시장/업종/시기에 따라 PER·PBR 같은 지표의 절대 수준이
    크게 달라서, 고정 임계값은 성장주를 부당하게 낮게 평가하거나 부실기업을 부당하게
    높게 평가하는 왜곡이 생기기 쉽다. 팩터투자(가치·퀄리티·모멘텀 팩터)에서 표준적으로
    쓰이는 방식이 바로 유니버스 내 상대순위(cross-sectional rank)다.
    """
    pairs = [(i, getter(s)) for i, s in enumerate(stocks)]
    valid = [(i, v) for i, v in pairs if v is not None]
    coverage = len(valid) / len(stocks) if stocks else 0.0
    ranks = {}
    if len(valid) >= 2:
        valid_sorted = sorted(valid, key=lambda t: t[1], reverse=not ascending)
        vn = len(valid_sorted)
        for rank, (i, _v) in enumerate(valid_sorted):
            ranks[i] = 100 * (vn - 1 - rank) / (vn - 1)
    for i, _v in pairs:
        ranks.setdefault(i, 50.0)  # 데이터 없으면 중립(50점) 처리
    return ranks, coverage


def _weighted_avg(parts):
    """parts: [(percentile_value, coverage_weight), ...] -> 커버리지로 가중평균.
    데이터가 없는 지표는 자동으로 가중치 0이 되어 결측치 때문에 부당하게 낮은/높은
    점수를 받지 않는다."""
    total_w = sum(w for _, w in parts)
    if total_w <= 0:
        return 50.0
    return sum(v * w for v, w in parts) / total_w


def score_stock_universe(stocks: list[dict]) -> list[dict]:
    """
    가치(Value)·퀄리티(Quality)·모멘텀(Momentum) 3팩터 방식의 종합 스코어링.
    (팩터투자에서 표준적으로 쓰이는 프레임워크 — 예: MSCI/iShares 멀티팩터 지수,
    Fama-French Value/Momentum 팩터, Novy-Marx Quality 팩터를 단순화해 적용)

    - Value 35% : PER·PBR가 유니버스 내에서 낮을수록 유리 (버핏 스타일 저평가)
    - Quality 35% : ROE·순이익률은 높고 부채비율은 낮을수록 유리 (우량 기업 필터.
      단순히 싼 것만 보면 '가치 함정(value trap)'에 빠지기 쉬워 퀄리티로 보완)
    - Momentum 30% : 52주 가격 레인지 내 위치(추세 강도) + 최근 등락률
      (리버모어/오닐 스타일 추세추종)

    이전 방식(PER<5→100점 같은 고정 임계값 + 두 점수 중 max값 채택)의 문제였던
    "레버리지·인버스 ETF나 하루 급등 종목이 최상위로 튀는" 왜곡을 상대순위 기반
    가중합으로 줄인다. 특정 지표가 없는 종목(예: 일부 한국 종목의 ROE 미제공)은
    남은 지표들로만 재계산되어 결측치 불이익이 없다.
    """
    n = len(stocks)
    if n == 0:
        return []

    per_rank, per_cov = _percentile_ranks(
        stocks, lambda s: s.get("per") if (s.get("per") and s["per"] > 0) else None, ascending=True)
    pbr_rank, pbr_cov = _percentile_ranks(
        stocks, lambda s: s.get("pbr") if (s.get("pbr") and s["pbr"] > 0) else None, ascending=True)
    roe_rank, roe_cov = _percentile_ranks(stocks, lambda s: s.get("roe"), ascending=False)
    margin_rank, margin_cov = _percentile_ranks(stocks, lambda s: s.get("profit_margin"), ascending=False)
    debt_rank, debt_cov = _percentile_ranks(
        stocks,
        lambda s: s.get("debt_to_equity") if (s.get("debt_to_equity") is not None and s["debt_to_equity"] >= 0) else None,
        ascending=True,
    )
    chg_rank, chg_cov = _percentile_ranks(stocks, lambda s: s.get("change_pct"), ascending=False)

    results = []
    for i, s in enumerate(stocks):
        s = dict(s)
        price, w_hi, w_lo = s.get("price"), s.get("w52_high"), s.get("w52_low")
        s["pct_from_52w_high"] = round((price - w_hi) / w_hi * 100, 1) if price and w_hi else None

        if price is not None and w_hi and w_lo and w_hi > w_lo:
            range_pos = clamp((price - w_lo) / (w_hi - w_lo) * 100)
        else:
            range_pos = 50.0

        value = round(_weighted_avg([(per_rank[i], per_cov), (pbr_rank[i], pbr_cov)]), 1)
        quality = round(_weighted_avg(
            [(roe_rank[i], roe_cov), (margin_rank[i], margin_cov), (debt_rank[i], debt_cov)]), 1)
        momentum = round(range_pos * 0.75 + chg_rank[i] * 0.25, 1)
        composite = round(value * 0.35 + quality * 0.35 + momentum * 0.30, 1)

        fundamentals = (value + quality) / 2
        if momentum - fundamentals >= 15:
            style = "리버모어형 (모멘텀·돌파)"
        elif fundamentals - momentum >= 15:
            style = "버핏형 (가치·퀄리티)"
        else:
            style = "혼합형 (가치+모멘텀)"

        s.update({
            "value_score": value,
            "quality_score": quality,
            "momentum_score": momentum,
            "composite_score": composite,
            "style": style,
        })
        results.append(s)

    results.sort(key=lambda s: s["composite_score"], reverse=True)
    return results


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
