#!/usr/bin/env python3
"""
fetch_data.py
=============
GitHub Actions 러너(자유로운 인터넷 접근)에서 실행되는 데이터 수집 스크립트.
CNN Fear&Greed API + yfinance 로 실측 데이터를 모아 build_dashboard.py 가 읽는
data.json 스키마로 저장한다.

로컬/샌드박스가 아니라 GitHub Actions 위에서 실행되는 것을 전제로 한다
(requests/yfinance 같은 일반 아웃바운드 네트워크가 막혀 있는 환경에서는 동작하지 않는다).
"""
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta

import numpy as np
import requests
import yfinance as yf

KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockDashboardBot/1.0)"}


def log(msg):
    print(f"[fetch_data] {msg}", flush=True)


def safe(fn, default=None, label=""):
    try:
        return fn()
    except Exception as e:
        log(f"WARN {label}: {e}")
        return default


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1) CNN Fear & Greed (원본 JSON, 미가공 실측치)
# ---------------------------------------------------------------------------
def fetch_cnn_fear_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    raw = r.json()

    fg = raw["fear_and_greed"]

    label_map = {
        "market_momentum_sp500": "시장 모멘텀 (S&P500 vs 125일 이평)",
        "market_momentum_sp125": "시장 모멘텀 (S&P500 vs 125일 이평, 보조)",
        "stock_price_strength": "주가 강도 (52주 신고가/신저가 비율)",
        "stock_price_breadth": "주가 폭 (상승/하락 거래량)",
        "put_call_options": "풋/콜 옵션 비율",
        "market_volatility_vix_50": "시장 변동성 (VIX vs 50일 이평)",
        "market_volatility_vix_125": "시장 변동성 (VIX vs 125일 이평)",
        "junk_bond_demand": "정크본드 수요",
        "safe_haven_demand": "안전자산 수요",
    }
    components = []
    for key, label in label_map.items():
        node = raw.get(key)
        if not node or not node.get("data"):
            continue
        last = node["data"][-1]
        score = last.get("y")
        rating = node.get("rating", "")
        if score is None:
            continue
        components.append({"name": label, "score": round(float(score), 1), "rating": rating})

    return {
        "score": round(float(fg["score"]), 2),
        "prev_close": round(float(fg.get("previous_close", fg["score"])), 2),
        "rating_en": fg["rating"].title() if isinstance(fg["rating"], str) else fg["rating"],
        "rating_kr": {
            "extreme fear": "극단적 공포", "fear": "공포", "neutral": "중립",
            "greed": "탐욕", "extreme greed": "극단적 탐욕",
        }.get(str(fg["rating"]).lower(), fg["rating"]),
        "asof": datetime.fromisoformat(fg["timestamp"].replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d"),
        "source_url": "https://edition.cnn.com/markets/fear-and-greed",
        "components": components if components else [
            {"name": "데이터 없음", "score": 50.0, "rating": "N/A"}
        ],
        "insight": None,
    }


# ---------------------------------------------------------------------------
# 2) 지수/환율 (yfinance)
# ---------------------------------------------------------------------------
def history_or_none(ticker, period="1y"):
    h = yf.Ticker(ticker).history(period=period)
    return None if h is None or h.empty else h


def index_snapshot(candidates, label):
    """여러 후보 티커 중 첫 번째로 성공하는 것을 사용."""
    for t in candidates:
        h = safe(lambda: history_or_none(t, "1y"), label=f"{label}:{t}")
        if h is not None and len(h) > 5:
            last = h["Close"].iloc[-1]
            prev = h["Close"].iloc[-2]
            chg_pct = (last - prev) / prev * 100
            w52_high = h["Close"].max()
            w52_low = h["Close"].min()
            vol = int(h["Volume"].iloc[-1]) if "Volume" in h else None
            return {
                "value": round(float(last), 2),
                "change_pct": round(float(chg_pct), 2),
                "w52_high": round(float(w52_high), 2),
                "w52_low": round(float(w52_low), 2),
                "volume": vol,
                "asof": h.index[-1].strftime("%Y-%m-%d"),
                "_history": h,  # 내부 계산용, JSON 저장 전에 제거함
                "_ticker": t,
            }
    return None


def realized_vol_score(hist, window=20, baseline_window=250):
    """VKOSPI 실측치가 없어 20일 실현변동성(연율화)을 대체 지표로 사용.
    최근 1년 분포 대비 백분위로 0~100 점수화 (변동성 낮음=평온/탐욕쪽, 높음=공포쪽)."""
    ret = hist["Close"].pct_change().dropna()
    if len(ret) < window + 10:
        return None, None
    rolling_vol = ret.rolling(window).std() * np.sqrt(252) * 100
    rolling_vol = rolling_vol.dropna()
    latest = rolling_vol.iloc[-1]
    pct_rank = (rolling_vol <= latest).mean() * 100  # 낮을수록 평온
    score = clamp(100 - pct_rank)  # 변동성 낮음(백분위 낮음) -> 점수 높음(평온/탐욕)
    return round(float(latest), 2), round(float(score), 1)


# ---------------------------------------------------------------------------
# 3) 종목 (yfinance)
# ---------------------------------------------------------------------------
def fetch_stock(ticker, name):
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = float(info.get("last_price") or info.get("lastPrice"))
        prev_close = float(info.get("previous_close") or info.get("previousClose"))
        w52_high = float(info.get("year_high") or info.get("yearHigh"))
        w52_low = float(info.get("year_low") or info.get("yearLow"))
        change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0.0

        per = None
        market_cap = None
        try:
            slow = t.info
            per = slow.get("trailingPE")
            mc = slow.get("marketCap")
            if mc:
                market_cap = f"{mc/1e12:.2f}조" if mc >= 1e12 else f"{mc/1e8:.0f}억"
        except Exception:
            pass

        return {
            "ticker": ticker, "name": name,
            "price": round(price, 2), "change_pct": round(change_pct, 2),
            "per": round(per, 2) if per else None,
            "w52_high": round(w52_high, 2), "w52_low": round(w52_low, 2),
            "market_cap": market_cap,
        }
    except Exception as e:
        log(f"WARN stock {ticker}: {e}")
        return None


def fetch_universe(list_, limit=None):
    out = []
    total = len(list_[:limit] if limit else list_)
    for i, item in enumerate(list_[:limit] if limit else list_, 1):
        s = fetch_stock(item["ticker"], item["name"])
        if s:
            out.append(s)
        if i % 20 == 0:
            log(f"  진행: {i}/{total}")
        time.sleep(0.2)  # 과도한 연속 호출 방지
    return out


# ---------------------------------------------------------------------------
# 3-1) 거래대금(거래량) 상위 종목 자동 스크리닝
# ---------------------------------------------------------------------------
def fetch_kr_top_by_value(sosok, market_label, max_items=50):
    """네이버금융 '거래대금상위' 페이지에서 종목명/코드를 추출한다.
    sosok=0: 코스피, sosok=1: 코스닥. 50개/페이지이므로 필요한 만큼 페이지를 넘긴다."""
    suffix = ".KS" if sosok == 0 else ".KQ"
    items = []
    seen = set()
    page = 1
    while len(items) < max_items and page <= 4:
        url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}&page={page}"
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        r.encoding = "euc-kr"
        html = r.text
        found_this_page = 0
        for m in re.finditer(r'/item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)</a>', html):
            code, name = m.group(1), m.group(2).strip()
            if code in seen:
                continue
            seen.add(code)
            items.append({"ticker": f"{code}{suffix}", "name": name})
            found_this_page += 1
            if len(items) >= max_items:
                break
        if found_this_page == 0:
            break  # 더 이상 페이지가 없음
        page += 1
    log(f"{market_label} 거래대금 상위 {len(items)}종목 수집 완료")
    return items


def fetch_us_top_by_value(count=100):
    """야후 파이낸스 'most_actives' 스크리너(거래량 상위, 달러 거래대금 상위와 유사)를 사용.
    엔드포인트/스키마가 바뀌면 예외를 던지고 상위 호출부에서 정적 리스트로 대체한다."""
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    params = {"formatted": "false", "lang": "en-US", "region": "US", "scrIds": "most_actives", "count": count}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    quotes = data["finance"]["result"][0]["quotes"]
    items = []
    for q in quotes:
        sym = q.get("symbol")
        name = q.get("shortName") or q.get("longName") or sym
        if sym:
            items.append({"ticker": sym, "name": name})
    log(f"미국 거래대금(거래량) 상위 {len(items)}종목 수집 완료")
    return items


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    now = datetime.now(KST)
    log("CNN Fear & Greed 수집 중...")
    us_fg = safe(fetch_cnn_fear_greed, label="cnn_fg")
    if us_fg is None:
        us_fg = {
            "score": 50.0, "prev_close": 50.0, "rating_en": "Neutral", "rating_kr": "중립",
            "asof": now.strftime("%Y-%m-%d"), "source_url": "https://edition.cnn.com/markets/fear-and-greed",
            "components": [{"name": "데이터 수집 실패", "score": 50.0, "rating": "N/A"}],
            "insight": "CNN API 응답을 가져오지 못해 중립값으로 대체했습니다.",
        }

    log("KOSPI/KOSDAQ/환율 수집 중...")
    kospi = index_snapshot(["^KS11"], "KOSPI")
    kosdaq = index_snapshot(["^KQ11", "229200.KS"], "KOSDAQ")
    usdkrw = index_snapshot(["KRW=X"], "USDKRW")

    if kospi is None:
        log("ERROR: KOSPI 데이터를 가져오지 못했습니다. 중단합니다.")
        sys.exit(1)

    vkospi_val, vol_score = (None, None)
    if kospi.get("_history") is not None:
        vkospi_val, vol_score = realized_vol_score(kospi["_history"])

    for d in (kospi, kosdaq, usdkrw):
        if d:
            d.pop("_history", None)
            d.pop("_ticker", None)

    indices = {
        "kospi": kospi,
        "kosdaq": kosdaq or {"value": None, "change_pct": 0, "asof": "N/A"},
        "usdkrw": usdkrw or {"value": None, "change_pct": 0, "asof": "N/A"},
        "vkospi": {
            "value": vkospi_val if vkospi_val is not None else 0,
            "change": 0,
            "asof": kospi["asof"],
            "note": "V-KOSPI 실측치 대신 20일 실현변동성(연율화, %)을 사용",
        },
    }

    with open("universe.json", encoding="utf-8") as f:
        universe = json.load(f)

    log("한국 거래대금 상위 종목(코스피50+코스닥50) 자동 수집 중...")
    kr_dynamic = (
        safe(lambda: fetch_kr_top_by_value(0, "코스피", 50), default=[], label="kr_top_kospi")
        + safe(lambda: fetch_kr_top_by_value(1, "코스닥", 50), default=[], label="kr_top_kosdaq")
    )
    if len(kr_dynamic) < 20:
        log("WARN: 거래대금 상위 수집 실패/부족 -> universe.json 고정 리스트로 대체")
        kr_list, kr_dynamic_ok = universe["kr"], False
    else:
        kr_list, kr_dynamic_ok = kr_dynamic, True

    log("미국 거래대금(거래량) 상위 100종목 자동 수집 중...")
    us_dynamic = safe(lambda: fetch_us_top_by_value(100), default=[], label="us_top_active")
    if len(us_dynamic) < 20:
        log("WARN: 미국 상위 종목 수집 실패/부족 -> universe.json 고정 리스트로 대체")
        us_list, us_dynamic_ok = universe["us"], False
    else:
        us_list, us_dynamic_ok = us_dynamic, True

    log(f"종목 상세 데이터 수집 중 (KR {len(kr_list)}종목, US {len(us_list)}종목)...")
    kr_stocks = fetch_universe(kr_list)
    us_stocks = fetch_universe(us_list)

    universe_note = (
        f"한국: {'거래대금 상위 (코스피 50 + 코스닥 50, 네이버금융 실시간 랭킹)' if kr_dynamic_ok else '자동 수집 실패로 고정 감시리스트 사용'} · "
        f"미국: {'거래대금(거래량) 상위 100종목 (야후파이낸스 스크리너)' if us_dynamic_ok else '자동 수집 실패로 고정 감시리스트 사용'}"
    )

    data = {
        "generated_at": now.isoformat(),
        "generated_at_label": now.strftime("%Y-%m-%d %H:%M KST"),
        "data_asof_note": "미국 지표는 CNN/야후파이낸스 최신 종가, 한국 지표는 야후파이낸스 최신 데이터 기준입니다. "
                           "V-KOSPI는 실측치가 아닌 실현변동성 대체 지표입니다. 종목 유니버스: " + universe_note,
        "us_fear_greed": us_fg,
        "indices": indices,
        "kr_stocks": kr_stocks,
        "us_stocks": us_stocks,
        "_vol_score_override": vol_score,  # build_dashboard.py 가 참고 (없으면 자체 계산)
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"data.json 저장 완료 (KR {len(kr_stocks)}종목, US {len(us_stocks)}종목)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
