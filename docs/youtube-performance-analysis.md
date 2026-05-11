# YouTube 성과 분석 작업 가이드

이 문서는 `IT한 하루` 채널의 YouTube Data API v3 + YouTube Analytics API 기반 성과 분석 작업을 실행하기 위한 최소 절차입니다.

## 목적

- Selenium 업로드 자동화와 별개로, 공식 API를 사용해 안정적으로 채널/영상 성과를 수집합니다.
- 최근 업로드 Shorts의 조회수, 시청 시간, 평균 시청 지속시간, 평균 시청률, 구독자 전환을 한 파일로 정리합니다.
- MoneyPrinterV2의 `data/upload_history.json`과 연결해 어떤 기사/주제가 성과를 냈는지 추적합니다.

## 전제 조건

OAuth 토큰이 아래 경로에 있어야 합니다.

```text
/opt/data/MoneyPrinterV2/secrets/youtube_oauth_token.json
```

현재 승인된 읽기 전용 scope:

```text
https://www.googleapis.com/auth/youtube.readonly
https://www.googleapis.com/auth/yt-analytics.readonly
```

## 실행

```bash
cd /opt/data/MoneyPrinterV2
PYTHONPATH=src venv/bin/python scripts/analyze_youtube_performance.py --days 28 --max-videos 50
```

결과물은 아래 폴더에 생성됩니다.

```text
reports/youtube/youtube_performance_<UTC타임스탬프>.json
reports/youtube/youtube_performance_<UTC타임스탬프>.md
```

## 리포트 구성

- 채널 요약: 채널 ID, 핸들, 전체 조회수/구독자/영상 수
- 분석 기간 총합: 기간 조회수, 시청 시간, 순구독자
- 조회수 상위 영상
- 유지율 상위 영상
- 구독 전환 상위 영상
- 카테고리별 요약
- 현재 운영 범위 이탈 후보: `ai/software` 등

## 해석 기준

1. 조회수와 유지율이 동시에 높은 영상은 재생산 우선 후보입니다.
2. 조회수는 높지만 유지율이 낮으면 제목/첫 프레임이 내용 기대와 어긋났을 수 있습니다.
3. 유지율은 높은데 조회수가 낮으면 제목, 첫 프레임, 업로드 타이밍 문제를 우선 봅니다.
4. `ai/software` 분류는 현재 채널 운영 기준상 제외 후보로 검토합니다.

## 주의

- OAuth 코드, access token, refresh token, client secret은 출력하거나 커밋하지 않습니다.
- 이 분석 스크립트는 업로드/삭제/수정 권한을 사용하지 않습니다.
- Analytics API는 당일 데이터가 지연될 수 있으므로 기본적으로 어제까지의 complete day 기준으로 조회합니다.
