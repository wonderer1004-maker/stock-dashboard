# CRYPTO DESK · BTC / ETH / BMNR

비트코인·이더리움 추세 분석, 위험예산 계산, Bitmine Immersion Technologies NAV 시나리오.

별도 정적 페이지: https://wonderer1004-maker.github.io/stock-dashboard/crypto-desk/

의존성 및 API 키 없이 작동합니다. 이 폴더에서 `node --test tests.mjs`로 계산 테스트를 실행할 수 있습니다.

- 시세: Coinbase USD 완성 UTC 일봉. 페이지 열기와 새로고침 시 조회하며 실시간 장중 호가가 아닙니다.
- SMA20/50/200, Wilder RSI14/ATR14, 일봉 누락·지연 감지. 일봉 201개 미만 또는 오류 시 판단 보류.
- 포지션: 양방향 거래 비용과 위험예산·최대 투자 비중 적용. 갭·급락으로 실제 손실은 예상을 초과할 수 있습니다.
- BMNR: 2026-10-25 14:00 ET 기준 회사 발표 스냅샷. 보유량은 자동 갱신하지 않습니다.
- NAV: 사용자 입력 가격, 기타 자산, 부채·우선주 등 선순위 청구액, 희석 주식 수 사용. 스테이킹 ETH 중복 합산 금지.
- ETF·거시·온체인·법안 현황 및 BMNR 주가·주식 수는 자동 수집하지 않습니다. 전략 성과는 미검증입니다.

2026-10-27 원래 Netlify 화면을 검토하고 고정 기술지표, 오래된 BMNR 수치, 근거 불명확한 주가 배수와 고정 자산 배분을 교체했습니다. 원래 Netlify 사이트는 이 GitHub 배포로 변경되지 않습니다.

자료: [Coinbase API](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles), [Bitmine IR](https://www.bitminetech.io/investor-relations), [SEC 8-K](https://www.sec.gov/Archives/edgar/data/1829311/000149315226048429/form8-k.htm).

일반 정보·교육용 분석이며 개인별 투자 권유나 수익 보장이 아닙니다.
