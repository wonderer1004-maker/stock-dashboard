#!/usr/bin/env python3
"""
build_dashboard.py
===================
data.json -> dashboard.html (완전 독립형 단일 HTML 파일)

사용법:
    python3 build_dashboard.py [data.json] [dashboard.html]
"""
import json
import sys
import html as html_lib
from datetime import datetime, timezone, timedelta

from scoring import (
    kospi_fear_greed, classify_fg, fg_color,
    buffett_score, livermore_score, style_tag, trade_levels, dalio_allocation,
)

KST = timezone(timedelta(hours=9))


def esc(s):
    return html_lib.escape(str(s)) if s is not None else ""


def fmt_num(x, unit=""):
    if x is None:
        return "N/A"
    if isinstance(x, float) and x == int(x):
        x = int(x)
    return f"{x:,.2f}{unit}" if isinstance(x, float) else f"{x:,}{unit}"


def pct_from_high(price, high):
    if not price or not high:
        return None
    return round((price - high) / high * 100, 1)


def gauge_svg(score, color, size=220):
    """반원 게이지 (0~100), 바늘 없이 진행 아크로 표시."""
    import math
    r = size / 2 - 18
    cx, cy = size / 2, size / 2
    start_angle = 180
    end_angle = 0
    frac = max(0, min(1, score / 100))
    angle = start_angle - (start_angle - end_angle) * frac

    def pt(a, radius):
        rad = math.radians(a)
        return cx + radius * math.cos(rad), cy - radius * math.sin(rad)

    x0, y0 = pt(180, r)
    x1, y1 = pt(0, r)
    xa, ya = pt(angle, r)
    large_arc = 1 if (180 - angle) > 180 else 0

    bg_path = f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 1 1 {x1:.1f} {y1:.1f}"
    fg_path = f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large_arc} 1 {xa:.1f} {ya:.1f}"

    return f'''
    <svg viewBox="0 0 {size} {size*0.62:.0f}" class="gauge-svg" role="img" aria-label="공포탐욕지수 {score}점">
      <path d="{bg_path}" fill="none" stroke="var(--gauge-track)" stroke-width="16" stroke-linecap="round"/>
      <path d="{fg_path}" fill="none" stroke="{color}" stroke-width="16" stroke-linecap="round"/>
      <text x="{cx}" y="{cy-6}" text-anchor="middle" class="gauge-num" fill="{color}">{score:g}</text>
    </svg>'''


FG_SCALE = [
    ("#d03b3b", "극단공포"), ("#ec835a", "공포"), ("#898781", "중립"),
    ("#0ca30c", "탐욕"), ("#006300", "극단탐욕"),
]


def fg_scale_legend():
    dots = "".join(f'<span><i style="background:{c}"></i>{esc(l)}</span>' for c, l in FG_SCALE)
    return f'<div class="fg-scale">{dots}</div>'


def render_fg_card(title, subtitle, score, rating_kr, color, components, insight=None, source_note=None):
    comp_rows = ""
    for c in components:
        name = esc(c.get("name") or c.get("detail", ""))
        sc = c.get("score")
        rating = c.get("rating", "")
        comp_rows += f'''
        <div class="comp-row">
          <span class="comp-name">{name}</span>
          <div class="comp-bar-track"><div class="comp-bar-fill" style="width:{max(0,min(100,sc)):.0f}%"></div></div>
          <span class="comp-score">{sc:g}</span>
        </div>'''
    insight_html = f'<p class="fg-insight">💡 {esc(insight)}</p>' if insight else ""
    source_html = f'<p class="fg-source">{esc(source_note)}</p>' if source_note else ""
    return f'''
    <section class="card fg-card">
      <h2>{esc(title)}</h2>
      <p class="card-subtitle">{esc(subtitle)}</p>
      <div class="fg-body">
        <div class="gauge-wrap">
          {gauge_svg(score, color)}
          <div class="gauge-label" style="color:{color}">{esc(rating_kr)}</div>
          {fg_scale_legend()}
        </div>
        <div class="comp-list">{comp_rows}</div>
      </div>
      {insight_html}
      {source_html}
    </section>'''


def market_mood_headline(us_score, us_rating_en, kr_score, kr_rating_en):
    diff = abs(us_score - kr_score)
    us_extreme = "Extreme" in us_rating_en
    kr_extreme = "Extreme" in kr_rating_en
    us_greed = "Greed" in us_rating_en
    kr_greed = "Greed" in kr_rating_en
    same_side = (us_greed == kr_greed) and "Neutral" not in us_rating_en and "Neutral" not in kr_rating_en

    if diff >= 15:
        return "미국과 한국의 투자심리가 뚜렷하게 엇갈리고 있어요 — 지역 분산을 점검해볼 만한 구간입니다."
    if same_side and (us_extreme or kr_extreme):
        return "미국·한국 모두 극단적인 심리 국면에 가까워요 — 되돌림 가능성을 염두에 두고 리스크 관리를 우선하세요."
    if same_side:
        return "미국·한국 투자심리가 비슷한 방향을 가리키고 있어요."
    return "미국과 한국의 심리 온도차가 크지 않아요 — 지표별 세부 내용을 함께 살펴보세요."


def render_hero(us_score, us_rating_en, us_rating_kr, us_color, kr_score, kr_rating_en, kr_rating_kr, kr_color):
    headline = market_mood_headline(us_score, us_rating_en, kr_score, kr_rating_en)
    return f'''
  <section class="hero">
    <div class="eyebrow hero-eyebrow">오늘의 시장 심리</div>
    <div class="hero-row">
      <div class="hero-stat">
        <div class="hero-flagline">🇺🇸 미국</div>
        <div class="hero-num" style="color:{us_color}">{us_score:g}</div>
        <div class="hero-tag" style="color:{us_color}">{esc(us_rating_kr)}</div>
      </div>
      <div class="hero-divider"></div>
      <div class="hero-stat">
        <div class="hero-flagline">🇰🇷 한국</div>
        <div class="hero-num" style="color:{kr_color}">{kr_score:g}</div>
        <div class="hero-tag" style="color:{kr_color}">{esc(kr_rating_kr)}</div>
      </div>
    </div>
    <p class="hero-headline">{esc(headline)}</p>
  </section>'''


def render_stock_row(s, style, levels, b_score, l_score):
    chg = s["change_pct"]
    chg_color = "var(--good)" if chg >= 0 else "var(--critical)"
    chg_sign = "+" if chg >= 0 else ""
    entry = f'{fmt_num(levels["entry_low"])} ~ {fmt_num(levels["entry_high"])}'
    target = fmt_num(levels["target"]) if levels["target"] else "장기보유(목표가 없음)"
    stop = fmt_num(levels["stop"]) if levels["stop"] else "가격기준 손절 없음"
    style_class = "style-momentum" if "리버모어" in style else ("style-value" if "버핏" in style else "style-mixed")
    return f'''
    <tr>
      <td class="t-name"><strong>{esc(s["name"])}</strong><br><span class="t-ticker">{esc(s["ticker"])}</span></td>
      <td class="t-num" data-label="현재가/등락">{fmt_num(s["price"])} <span style="color:{chg_color}">{chg_sign}{chg:.2f}%</span></td>
      <td data-label="매매 스타일"><span class="style-pill {style_class}">{esc(style)}</span></td>
      <td class="t-score" data-label="스코어">버핏 {b_score:g} · 리버모어 {l_score:g}</td>
      <td class="t-num" data-label="매수가">{entry}</td>
      <td class="t-num" data-label="목표가">{target}</td>
      <td class="t-num" data-label="손절가">{stop}</td>
      <td class="t-note" data-label="전략 메모">{esc(levels["note"])}</td>
    </tr>'''


def split_stocks(stocks):
    """레버리지/인버스 상품을 제외하고 개별종목/ETF로 분리."""
    clean = [s for s in stocks if not s.get("is_leveraged_inverse")]
    individual = [s for s in clean if s.get("asset_type", "STOCK") != "ETF"]
    etfs = [s for s in clean if s.get("asset_type", "STOCK") == "ETF"]
    return individual, etfs


def render_stock_table(title, stocks, top_n=5, subtitle=None, empty_note=None):
    rows = ""
    scored = []
    for s in stocks:
        s = dict(s)
        s["pct_from_52w_high"] = pct_from_high(s["price"], s.get("w52_high"))
        b = buffett_score(s)
        l = livermore_score(s)
        style = style_tag(b, l)
        levels = trade_levels(s, style)
        scored.append((s, style, levels, b, l))

    scored.sort(key=lambda t: max(t[3], t[4]), reverse=True)
    total = len(scored)
    shown = scored[:top_n] if top_n else scored
    for s, style, levels, b, l in shown:
        rows += render_stock_row(s, style, levels, b, l)

    subtitle_html = f'<p class="card-subtitle">{esc(subtitle)}</p>' if subtitle else ""

    if not shown:
        body = f'<p class="card-subtitle" style="margin-top:8px">{esc(empty_note or "오늘 스크리닝된 종목이 없습니다.")}</p>'
        return f'''
    <section class="card">
      <h2>{esc(title)}</h2>
      {subtitle_html}
      {body}
    </section>'''

    note = ""
    if total > len(shown):
        note = (f'<p class="card-subtitle" style="margin-top:8px">전체 {total}종목을 버핏·리버모어 스코어로 '
                f'스크리닝한 뒤, 스코어 상위 {len(shown)}종목만 표시합니다.</p>')

    return f'''
    <section class="card">
      <h2>{esc(title)}</h2>
      {subtitle_html}
      <div class="table-wrap">
        <table class="stock-table">
          <thead>
            <tr>
              <th>종목</th><th>현재가/등락</th><th>매매 스타일</th><th>스코어(0~100)</th>
              <th>매수가</th><th>목표가</th><th>손절가</th><th>전략 메모</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {note}
    </section>'''


ALLOC_HUES = ["#2a78d6", "#1baf7a", "#eda100", "#4a3aa7", "#e87ba4"]


def render_allocation(alloc):
    pairs = [(k, v) for k, v in alloc.items() if k != "tilt_note"]
    items = "".join(
        f'<div class="alloc-item">'
        f'<div class="alloc-bar" style="width:{v}%; background:{ALLOC_HUES[i % len(ALLOC_HUES)]}"></div>'
        f'<span class="alloc-label">{esc(k)}</span><span class="alloc-pct">{v:g}%</span></div>'
        for i, (k, v) in enumerate(pairs)
    )
    return f'''
    <section class="card">
      <h2>달리오 스타일 포트폴리오 배분 제안</h2>
      <p class="card-subtitle">올웨더(All Weather) 포트폴리오를 현재 공포탐욕 국면에 맞춰 리밸런싱한 참고안입니다.</p>
      <div class="alloc-list">{items}</div>
      <p class="fg-insight">💡 {esc(alloc["tilt_note"])}</p>
    </section>'''


GURU_PHIL = [
    ("워런 버핏 (가치투자)",
     "좋은 기업을 좋은 가격에 사서 오래 보유합니다. PER·PBR 등으로 '안전마진'을 확인하고, "
     "주가가 아니라 기업의 경쟁우위(해자)와 실적이 훼손됐을 때만 매도합니다. "
     "\"남들이 욕심을 낼 때 두려워하고, 남들이 두려워할 때 욕심을 내라.\""),
    ("제시 리버모어 (추세/모멘텀 매매)",
     "시장의 '피벗 포인트(전환점)'를 포착해 신고가 돌파 시 거래량을 동반한 상승에 올라탑니다. "
     "손실은 짧게(-7~10%), 이익은 길게 끌고 가는 손절 규율을 철저히 지켰습니다. "
     "\"돈은 생각하는 데서 버는 게 아니라 기다리는 데서 번다.\""),
    ("레이 달리오 (매크로/올웨더)",
     "경제는 성장·물가의 4가지 국면(레짐)을 순환한다고 보고, 어떤 국면에서도 견디는 "
     "자산배분(주식·채권·금·원자재 분산)으로 리스크를 관리합니다. 예측보다 분산을 신뢰합니다."),
]


def render_guru_section():
    cards = "".join(
        f'<div class="guru-card"><h3>{esc(name)}</h3><p>{esc(desc)}</p></div>'
        for name, desc in GURU_PHIL
    )
    return f'''
    <section class="card">
      <h2>이 리포트가 참고하는 투자 철학</h2>
      <div class="guru-grid">{cards}</div>
    </section>'''


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>공포탐욕지수 &amp; 대가 매매전략 대시보드</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --gridline: #e1e0d9;
    --border: rgba(11,11,11,0.10);
    --good: #0ca30c;
    --warning: #fab219;
    --serious: #ec835a;
    --critical: #d03b3b;
    --series-blue: #2a78d6;
    --gauge-track: #e1e0d9;
    --shadow: 0 1px 2px rgba(11,11,11,0.04), 0 6px 20px rgba(11,11,11,0.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --gridline: #2c2c2a;
      --border: rgba(255,255,255,0.10);
      --good: #0ca30c;
      --warning: #fab219;
      --serious: #ec835a;
      --critical: #e66767;
      --series-blue: #3987e5;
      --gauge-track: #383835;
      --shadow: 0 1px 2px rgba(0,0,0,0.25), 0 8px 24px rgba(0,0,0,0.35);
    }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  .viz-root {{
    display: block;
    min-height: 100vh;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 16px 64px; }}
  header.top {{ padding: 8px 0 20px; margin-bottom: 4px; }}
  header.top h1 {{ font-size: 24px; font-weight: 800; letter-spacing: -0.01em; margin: 0 0 6px; }}
  header.top p {{ margin: 0; color: var(--text-secondary); font-size: 12.5px; line-height: 1.6; }}
  .eyebrow {{
    font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--text-muted); margin: 0 0 6px;
  }}
  .hero {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow);
    padding: 22px 24px 20px;
    margin-bottom: 20px;
    text-align: center;
  }}
  .hero-eyebrow {{ text-align: center; }}
  .hero-row {{ display: flex; align-items: center; justify-content: center; gap: 28px; flex-wrap: wrap; margin: 6px 0 10px; }}
  .hero-stat {{ min-width: 110px; }}
  .hero-flagline {{ font-size: 13px; color: var(--text-secondary); font-weight: 600; margin-bottom: 2px; }}
  .hero-num {{ font-size: 44px; font-weight: 800; line-height: 1.05; font-variant-numeric: tabular-nums; }}
  .hero-tag {{ font-size: 13px; font-weight: 700; }}
  .hero-divider {{ width: 1px; height: 46px; background: var(--gridline); }}
  .hero-headline {{ font-size: 13.5px; color: var(--text-secondary); margin: 6px auto 0; max-width: 640px; line-height: 1.6; }}
  .card {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 14px;
    box-shadow: var(--shadow);
    padding: 20px 22px;
    margin-bottom: 18px;
  }}
  .card h2 {{ font-size: 16px; font-weight: 700; margin: 0 0 4px; }}
  .card-subtitle {{ color: var(--text-secondary); font-size: 12.5px; margin: 0 0 14px; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  @media (max-width: 760px) {{ .two-col {{ grid-template-columns: 1fr; }} .hero-row {{ gap: 18px; }} .hero-num {{ font-size: 38px; }} }}
  .fg-body {{ display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
  .gauge-wrap {{ text-align: center; min-width: 200px; }}
  .gauge-svg {{ width: 220px; max-width: 100%; }}
  .gauge-num {{ font-size: 40px; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .gauge-label {{ font-size: 15px; font-weight: 700; margin-top: -8px; }}
  .fg-scale {{ display: flex; gap: 9px; justify-content: center; flex-wrap: wrap; font-size: 10px; color: var(--text-muted); margin-top: 10px; }}
  .fg-scale i {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }}
  .comp-list {{ flex: 1; min-width: 220px; }}
  .comp-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .comp-name {{ flex: 0 0 44%; font-size: 12px; color: var(--text-secondary); }}
  .comp-bar-track {{ flex: 1; height: 8px; border-radius: 4px; background: var(--gridline); overflow: hidden; }}
  .comp-bar-fill {{ height: 100%; background: var(--series-blue); border-radius: 4px; }}
  .comp-score {{ flex: 0 0 32px; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }}
  .fg-insight {{ font-size: 12.5px; color: var(--text-secondary); margin: 12px 0 0; padding-top: 10px; border-top: 1px dashed var(--gridline); }}
  .fg-source {{ font-size: 11px; color: var(--text-muted); margin: 6px 0 0; }}
  .idx-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
  @media (max-width: 760px) {{ .idx-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .idx-tile {{ background: var(--page); border: 1px solid var(--border); border-radius: 12px; padding: 13px 15px; }}
  .idx-tile .idx-name {{ font-size: 11.5px; color: var(--text-secondary); font-weight: 600; }}
  .idx-tile .idx-val {{ font-size: 21px; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 3px; }}
  .idx-tile .idx-chg {{ font-size: 12px; font-variant-numeric: tabular-nums; font-weight: 600; margin-top: 1px; }}
  table.stock-table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
  .table-wrap {{ overflow-x: auto; }}
  table.stock-table th {{
    text-align: left; font-weight: 700; color: var(--text-muted); font-size: 11px;
    letter-spacing: 0.02em; text-transform: uppercase;
    border-bottom: 1px solid var(--gridline); padding: 8px 10px; white-space: nowrap;
  }}
  table.stock-table tbody tr:nth-child(odd) {{ background: color-mix(in srgb, var(--page) 55%, transparent); }}
  table.stock-table td {{ padding: 10px; border-bottom: 1px solid var(--gridline); vertical-align: top; }}
  table.stock-table tr:last-child td {{ border-bottom: none; }}
  .t-ticker {{ color: var(--text-muted); font-size: 11px; }}
  .t-num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .t-note {{ color: var(--text-secondary); min-width: 220px; }}
  .style-pill {{
    display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700;
    white-space: nowrap; border: 1px solid var(--border);
  }}
  .style-momentum {{ color: #e34948; background: color-mix(in srgb, #e34948 12%, transparent); }}
  .style-value {{ color: #1c5cab; background: color-mix(in srgb, #1c5cab 12%, transparent); }}
  .style-mixed {{ color: #7a6b1f; background: color-mix(in srgb, #eda100 16%, transparent); }}
  .alloc-list {{ display: flex; flex-direction: column; gap: 10px; }}
  .alloc-item {{ position: relative; background: var(--page); border-radius: 8px; height: 36px; overflow: hidden; border: 1px solid var(--border); }}
  .alloc-bar {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 0 8px 8px 0; opacity: .55; }}
  .alloc-label {{ position: absolute; left: 12px; top: 9px; font-size: 12.5px; font-weight: 700; }}
  .alloc-pct {{ position: absolute; right: 12px; top: 9px; font-size: 12.5px; font-variant-numeric: tabular-nums; font-weight: 800; }}

  @media (max-width: 700px) {{
    table.stock-table thead {{ display: none; }}
    table.stock-table, table.stock-table tbody {{ display: block; width: 100%; }}
    table.stock-table tr {{
      display: block; border: 1px solid var(--border); border-radius: 12px;
      margin-bottom: 10px; padding: 12px 14px; background: var(--page);
    }}
    table.stock-table tr:last-child {{ margin-bottom: 0; }}
    table.stock-table td {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 5px 0; border-bottom: none; }}
    table.stock-table td[data-label]::before {{ content: attr(data-label); font-size: 11px; color: var(--text-muted); font-weight: 600; }}
    table.stock-table td.t-name {{ display: block; padding-bottom: 8px; margin-bottom: 6px; border-bottom: 1px dashed var(--gridline); font-size: 14px; }}
    table.stock-table td.t-note {{ display: block; }}
    table.stock-table td.t-note::before {{ content: "전략 메모"; display: block; font-size: 11px; color: var(--text-muted); font-weight: 600; margin-bottom: 4px; }}
  }}
  .guru-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
  @media (max-width: 760px) {{ .guru-grid {{ grid-template-columns: 1fr; }} }}
  .guru-card {{ background: var(--page); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
  .guru-card h3 {{ font-size: 13.5px; margin: 0 0 8px; }}
  .guru-card p {{ font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; margin: 0; }}
  footer.disclaimer {{
    font-size: 11.5px; color: var(--text-muted); line-height: 1.7;
    border-top: 1px solid var(--gridline); padding-top: 16px; margin-top: 8px;
  }}
</style>
</head>
<body>
<div class="viz-root">
<div class="wrap">
  <header class="top">
    <h1>📊 공포탐욕지수 &amp; 대가 매매전략 대시보드</h1>
    <p>생성 시각: {generated_at_label} · {data_asof_note}</p>
  </header>

  {hero_section}

  <div class="two-col">
    {us_fg_card}
    {kr_fg_card}
  </div>

  <section class="card">
    <h2>핵심 시장 지표</h2>
    <div class="idx-grid">
      {index_tiles}
    </div>
  </section>

  {kr_stock_table}
  {kr_etf_table}
  {us_stock_table}
  {us_etf_table}
  {allocation_section}
  {guru_section}

  <footer class="disclaimer">
    <strong>면책 조항</strong> · 이 대시보드는 공개된 시세/지표를 기반으로 규칙 기반 스코어링을 적용한
    교육·참고용 자료이며, 투자자문업자가 제공하는 개인 맞춤형 투자자문이 아닙니다. 매수가/목표가/손절가는
    변동성과 리스크 성향에 따라 조정이 필요하며, 과거 대가들의 원칙을 현재 데이터에 규칙으로 근사한 것으로
    실제 대가 본인의 판단과 다를 수 있습니다. 모든 투자의 최종 책임은 투자자 본인에게 있으며, 원금 손실이
    발생할 수 있습니다. 데이터는 각 카드에 표기된 시점 기준이며 지연 시세를 포함할 수 있습니다.
  </footer>
</div>
</div>
</body>
</html>
"""


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "index.html"

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    # US F&G 카드 (CNN 원본)
    us = data["us_fear_greed"]
    us_card = render_fg_card(
        "🇺🇸 미국 공포탐욕지수 (CNN)", f"CNN Fear & Greed Index · {us['asof']} 기준",
        us["score"], us["rating_kr"], fg_color(us["rating_en"]), us["components"],
        insight=us.get("insight"),
        source_note=f"출처: {us['source_url']} (전일 종가 {us['prev_close']})",
    )

    # KOSPI F&G 계산
    idx = data["indices"]
    kospi, kosdaq, usdkrw, vkospi = idx["kospi"], idx["kosdaq"], idx["usdkrw"], idx["vkospi"]

    pos = (kospi["value"] - kospi["w52_low"]) / (kospi["w52_high"] - kospi["w52_low"])
    momentum = max(0, min(100, 50 + (pos - 0.5) * 100 * 0.6 + kospi["change_pct"] * 3))

    vol_override = data.get("_vol_score_override")
    if vol_override is not None:
        # fetch_data.py 가 실현변동성 백분위로 이미 0~100 점수를 계산해 넘겨준 경우
        vol_score = max(0, min(100, vol_override))
    else:
        # 수기 입력(make_data.py) 경로: V-KOSPI류 지수값을 스케일링.
        # 상한을 45로 좁게 잡으면 실제 위기 국면(50~80대)에서 전부 0으로 눌려버려
        # 세밀한 구분이 사라지므로, 과거 실제 VKOSPI/VIX 위기 국면(~80)을 반영해 10~80 레인지로 완화.
        vol_score = max(0, min(100, 100 - (vkospi["value"] - 10) / (80 - 10) * 100))
    breadth = max(0, min(100, 50 + (kospi["change_pct"] - kosdaq["change_pct"]) * 5))
    safehaven = max(0, min(100, 50 - usdkrw["change_pct"] * 10))
    sentiment = max(0, min(100, 50 + kospi["change_pct"] * 6))

    kr_components = [
        {"name": "모멘텀 (52주 레인지 위치 + 당일 등락)", "score": round(momentum, 1)},
        {"name": "변동성 (V-KOSPI)", "score": round(vol_score, 1)},
        {"name": "시장 폭 (코스피 vs 코스닥 상대강도)", "score": round(breadth, 1)},
        {"name": "안전자산 수요 (원/달러 환율)", "score": round(safehaven, 1)},
        {"name": "거래심리 (당일 강도)", "score": round(sentiment, 1)},
    ]
    kr_fg = kospi_fear_greed([{**c, "weight": 1} for c in kr_components])

    insight = None
    if vol_score < 20 and momentum > 55:
        insight = ("가격은 상승 모멘텀을 보이지만 V-KOSPI(변동성)가 매우 높은 수준입니다. "
                    "상승장 속에서도 불안정성이 큰 '살얼음판 랠리' 신호로 해석될 수 있습니다.")

    kr_card = render_fg_card(
        "🇰🇷 한국 코스피 공포탐욕지수 (자체 산출)", "CNN 방법론을 한국 시장 데이터로 재구성 (5개 지표)",
        kr_fg["score"], kr_fg["rating_kr"], kr_fg["color"], kr_fg["components"],
        insight=insight,
        source_note="산출: KOSPI/KOSDAQ 지수, V-KOSPI, 원/달러 환율 기반 자체 계산 (CNN 7지표를 한국에서 구할 수 있는 5개 대체지표로 재구성)",
    )

    def tile(name, val_str, chg_str, asof):
        chg_color = "var(--good)" if not chg_str.startswith("-") else "var(--critical)"
        return f'''<div class="idx-tile"><div class="idx-name">{esc(name)} <span style="color:var(--text-muted)">· {esc(asof)}</span></div>
        <div class="idx-val">{val_str}</div><div class="idx-chg" style="color:{chg_color}">{chg_str}</div></div>'''

    vkospi_label = "변동성(20일 실현, 연율%)" if vkospi.get("note") else "V-KOSPI"
    index_tiles = "".join([
        tile("KOSPI", fmt_num(kospi["value"]), f'{kospi["change_pct"]:+.2f}%', kospi["asof"]),
        tile("KOSDAQ", fmt_num(kosdaq["value"]), f'{kosdaq["change_pct"]:+.2f}%', kosdaq["asof"]),
        tile("USD/KRW", fmt_num(usdkrw["value"]), f'{usdkrw["change_pct"]:+.2f}%', usdkrw["asof"]),
        tile(vkospi_label, fmt_num(vkospi["value"]), f'{vkospi["change"]:+.2f}', vkospi["asof"]),
    ])

    kr_individual, kr_etf = split_stocks(data["kr_stocks"])
    us_individual, us_etf = split_stocks(data["us_stocks"])

    stock_subtitle = "거래대금 상위 종목 중 개별주만 버핏·리버모어 스코어로 채점한 TOP 5입니다. 레버리지/인버스 상품은 제외했습니다."
    etf_subtitle = ("거래대금 상위 종목 중 일반 ETF만 채점한 TOP 5입니다. 레버리지/인버스 ETF는 일간 재조정(decay) 구조상 "
                     "가치·모멘텀 분석과 맞지 않아 추천에서 제외했습니다.")
    etf_empty = "오늘 스크리닝된 상위 종목 중 (레버리지/인버스 제외) 일반 ETF가 없습니다."

    kr_stock_table = render_stock_table("🇰🇷 국내 개별종목 매매전략 TOP 5", kr_individual, top_n=5, subtitle=stock_subtitle)
    kr_etf_table = render_stock_table("🇰🇷 국내 ETF 매매전략 TOP 5", kr_etf, top_n=5, subtitle=etf_subtitle, empty_note=etf_empty)
    us_stock_table = render_stock_table("🇺🇸 미국 개별종목 매매전략 TOP 5", us_individual, top_n=5, subtitle=stock_subtitle)
    us_etf_table = render_stock_table("🇺🇸 미국 ETF 매매전략 TOP 5", us_etf, top_n=5, subtitle=etf_subtitle, empty_note=etf_empty)

    alloc = dalio_allocation(kr_fg["score"])
    allocation_section = render_allocation(alloc)
    guru_section = render_guru_section()

    hero_section = render_hero(
        us["score"], us["rating_en"], us["rating_kr"], fg_color(us["rating_en"]),
        kr_fg["score"], kr_fg["rating_en"], kr_fg["rating_kr"], kr_fg["color"],
    )

    html_out = PAGE_TEMPLATE.format(
        generated_at_label=esc(data["generated_at_label"]),
        data_asof_note=esc(data["data_asof_note"]),
        hero_section=hero_section,
        us_fg_card=us_card,
        kr_fg_card=kr_card,
        index_tiles=index_tiles,
        kr_stock_table=kr_stock_table,
        kr_etf_table=kr_etf_table,
        us_stock_table=us_stock_table,
        us_etf_table=us_etf_table,
        allocation_section=allocation_section,
        guru_section=guru_section,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
