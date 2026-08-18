# 공포탐욕지수 & 대가 매매전략 대시보드

미국 CNN Fear & Greed Index, 한국 코스피 자체 공포탐욕지수, 버핏/리버모어/달리오 스타일
매매전략을 담은 완전 자동 갱신 대시보드입니다. GitHub Pages + GitHub Actions 조합으로
**완전 무료**로 매일 자동 갱신되는 라이브 웹사이트를 운영할 수 있습니다.

## 왜 이 구조인가

- `build_dashboard.py`, `scoring.py` : 데이터 → HTML 렌더링 (순수 계산, 네트워크 불필요)
- `fetch_data.py` : CNN API + `yfinance` 로 실측 데이터 수집. **반드시 GitHub Actions
  같은 일반 인터넷 접근이 가능한 환경에서 실행**해야 합니다 (사내망/샌드박스처럼 아웃바운드가
  막힌 환경에서는 동작하지 않습니다).
- `.github/workflows/daily.yml` : 평일 미국 장마감 이후 자동으로 `fetch_data.py` →
  `build_dashboard.py` 를 실행하고 `index.html`을 저장소에 커밋합니다.
- GitHub Pages가 그 `index.html`을 그대로 공개 웹사이트로 서빙합니다.

## 5분 설정 가이드

1. **GitHub 계정으로 새 저장소 생성** (Public, 아무 이름이나 무관 — 예: `stock-dashboard`)
2. 이 폴더(`deploy/`) 안의 모든 파일을 그 저장소에 업로드합니다.
   - GitHub 웹사이트에서 "Add file → Upload files"로 전체 드래그 앤 드롭해도 되고,
   - 터미널을 쓸 수 있다면:
     ```bash
     cd deploy
     git init
     git add .
     git commit -m "init"
     git branch -M main
     git remote add origin https://github.com/<내계정>/<저장소명>.git
     git push -u origin main
     ```
3. 저장소 **Settings → Pages** 로 이동 → Source를 **"Deploy from a branch"** → Branch를
   **main / (root)** 로 지정 → Save.
   - 몇 분 후 `https://<내계정>.github.io/<저장소명>/` 주소로 접속 가능해집니다.
4. 저장소 **Actions** 탭 → "매일 대시보드 자동 갱신" 워크플로 선택 → **Run workflow** 버튼으로
   1회 수동 실행해 `index.html`이 정상 생성되는지 확인합니다.
   - 성공하면 그 결과가 자동으로 커밋되고, Pages 사이트도 몇 분 내 갱신됩니다.
5. 이후로는 **평일마다 자동으로** 실행됩니다(설정된 시각: UTC 22:00 ≈ 한국시간 오전 7시,
   미국 장마감 이후 / 한국 장 시작 전). 시각을 바꾸려면 `.github/workflows/daily.yml`의
   `cron` 값을 수정하세요.

## 비용

- GitHub Pages: 완전 무료 (Public 저장소)
- GitHub Actions: Public 저장소는 무료 무제한, Private 저장소는 매달 2,000분 무료
  (이 워크플로는 1회 실행에 1~2분 내외 → 평일 매일 돌려도 한 달 약 40~60분 소모)

## 종목 리스트 수정

`universe.json` 의 `kr`/`us` 배열에 원하는 티커를 추가/삭제하면 다음 실행부터 반영됩니다.
한국 종목은 코스피 `.KS`, 코스닥 `.KQ` 접미사를 사용합니다.

## 로컬에서 미리 테스트하기 (인터넷이 열려 있는 PC/노트북 기준)

```bash
pip install -r requirements.txt
python fetch_data.py        # data.json 생성 (CNN + yfinance 실측)
python build_dashboard.py data.json index.html
open index.html             # 또는 더블클릭으로 브라우저에서 확인 (Windows는 start index.html)
```

## 면책 조항

이 대시보드는 공개 데이터를 규칙 기반으로 가공한 교육·참고용 도구이며, 투자자문업자의
개인 맞춤형 투자자문이 아닙니다. 최종 투자 판단과 책임은 이용자 본인에게 있습니다.
