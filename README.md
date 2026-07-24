# ITShortPrinter

최신 IT 뉴스를 수집·선별해 한국어 YouTube Shorts로 제작하고, 검토가 끝난 영상만 안전하게 업로드하는 자동화 프로젝트입니다.

뉴스 수집과 랭킹부터 대본 생성·검수, 세로형 이미지, TTS, 자막, MP4 렌더링, YouTube Data API 업로드와 선택적 멀티 플랫폼 배포까지 한 저장소에서 처리합니다.

> 이 저장소는 [FujiwaraChoki/MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2)를 기반으로 한 AGPL-3.0 포크입니다. 원본 저작권과 라이선스는 [LICENSE](LICENSE)를 확인하세요.

Sponsored by Post Bridge

<a href="https://www.post-bridge.com/?ref=moneyprinter">
  <img src="docs/repo/PostBridgeBanner.png" alt="Post Bridge integration banner" width="720" />
</a>

## 주요 기능

- 국내외 IT 뉴스 소스를 수집하고 중복·오래된 기사·루머를 걸러 Shorts 적합도를 계산합니다.
- 한국어 대본, 제목, 설명, 태그와 이미지 프롬프트를 생성하고 별도 검수 단계를 거칩니다.
- Hermes, Ollama, Gemini 계열 텍스트 생성 경로를 지원합니다.
- Hermes 이미지 큐 또는 CLI, Gemini 이미지 API, 테스트용 플레이스홀더 이미지를 지원합니다.
- Edge TTS를 기본으로 음성을 만들고 Pillow와 MoviePy로 9:16 영상·자막·제목을 합성합니다.
- Top 5 배치, 검토 프레임, 품질 필드와 매니페스트를 생성합니다.
- 공식 YouTube Data API로 OAuth 업로드하며 채널 ID, 검토 상태, 공개 업로드 가드를 확인합니다.
- 업로드 후 Post Bridge를 통한 TikTok·Instagram 교차 게시를 선택적으로 지원합니다.

기본 운영 흐름은 다음과 같습니다.

```text
뉴스 수집·랭킹
  -> 한국어 대본·메타데이터 생성 및 검수
  -> 이미지·TTS·자막 생성
  -> 1080x1920 MP4와 검토 매니페스트 생성
  -> 사람 검토
  -> YouTube 비공개 링크(unlisted) 업로드
  -> 명시적으로 허용한 경우에만 공개·교차 게시
```

## 안전 장치

- 단일·Top 5 생성 명령은 영상을 만들 뿐 자동으로 공개하지 않습니다.
- 이미지 생성 실패로 플레이스홀더가 사용된 영상은 업로드 불가 상태로 표시됩니다.
- 검토되지 않은 영상은 기본적으로 업로드가 거부됩니다.
- 기본 업로드 공개 범위는 `unlisted`입니다.
- 공개 업로드에는 `ALLOW_PUBLIC_UPLOAD=1`과 명시적인 YouTube 채널 ID가 모두 필요합니다.
- 생성물과 계정 토큰은 Git에서 제외되는 `.mp/`, `data/`, `reports/`, `secrets/`에 저장됩니다.

## 요구사항

공통 요구사항:

- Git
- Python 3.12
- FFmpeg: TTS 변환과 MoviePy 영상·오디오 렌더링에 사용
- 인터넷 연결: 뉴스 수집, Edge TTS, 클라우드 공급자와 YouTube API 사용 시 필요

권장 개발 환경은 [mise](https://mise.jdx.dev/getting-started.html)입니다. `mise`가 Python 3.12와 프로젝트의 `venv`를 준비하고 운영 명령을 동일하게 제공합니다.

선택한 공급자에 따라 다음 항목이 추가로 필요합니다.

- 기본 Hermes 텍스트 경로: 설치와 인증이 끝난 `hermes` CLI
- Ollama 경로: 로컬 Ollama 서버와 내려받은 모델
- Gemini 텍스트·이미지 경로: `GOOGLE_API_KEY` 또는 `GEMINI_API_KEY`
- YouTube 업로드: Google Cloud OAuth Desktop 클라이언트
- Post Bridge: API 키와 대상 계정 ID
- 기존 브라우저 기반 소셜 자동화: Firefox 프로필

ImageMagick 설정은 이전 워크플로와의 호환을 위해 남아 있지만, 현재 Shorts 자막과 제목은 Pillow 이미지 레이어로 렌더링하므로 필수 항목이 아닙니다. `faster-whisper`를 포함한 선택 기능 의존성도 현재 `requirements.txt`에서 함께 설치됩니다.

## 빠른 시작

저장소 루트에서 실행하세요.

```bash
git clone https://github.com/hvboq/ITShortPrinter.git
cd ITShortPrinter
```

### mise 사용 권장

`mise`를 설치한 뒤 다음 명령을 실행합니다.

```bash
mise trust
mise install
mise run setup
```

이 과정은 다음 작업을 수행합니다.

- Python 3.12 설치 또는 선택
- `venv` 생성과 자동 활성화
- 누락된 `config.json`, `.env` 로컬 파일 생성
- Python 패키지 설치
- 현재 공급자와 로컬 설정에 대한 사전 점검

공급자 CLI나 API 키가 아직 없으면 setup 마지막 점검에 경고 또는 실패 항목이 표시될 수 있습니다. 의존성 설치는 유지되므로 `config.json`과 `.env`를 설정한 뒤 다시 점검하면 됩니다.

```bash
mise run doctor
mise run app
```

사용 가능한 모든 작업은 다음 명령으로 확인합니다.

```bash
mise tasks
```

### Windows PowerShell 직접 설치

```powershell
Copy-Item config.example.json config.json
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1
```

기존 `venv`의 Python 버전이 다르면 저장소 바로 아래의 가상환경만 다시 만듭니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1 -RecreateVenv
```

수동으로 설치하려면:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe scripts\preflight_local.py
```

### Linux/macOS 직접 설치

```bash
cp config.example.json config.json
cp .env.example .env
bash scripts/setup_local.sh
```

수동으로 설치하려면:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts/preflight_local.py
```

## 환경 설정

설정은 두 파일로 나뉩니다.

- `config.json`: 공급자, 모델, 뉴스 소스, 렌더링, TTS/STT, Post Bridge 등 구조화된 설정
- `.env`: API 키, 채널 ID, 실행별 override와 업로드 안전 플래그

두 파일 모두 예제에서 생성되며 Git에 커밋되지 않습니다. 지원되는 값은 현재 셸 환경변수, `.env`, `config.json` 순으로 적용되고, 환경변수 getter가 없는 항목은 `config.json`에서만 읽습니다.

### 현재 기본 프로필

| 영역 | 기본값 | 비고 |
| --- | --- | --- |
| 텍스트 | Hermes / `openai-codex` / `gpt-5.5` | `hermes` CLI 필요 |
| 대본 검수 | 활성화 / `hermes:gpt-5.5` | 검수 결과는 `.mp/script_reviews/`에 저장 |
| 이미지 | Hermes | 큐 우선, CLI 생성은 명시적으로 활성화 |
| TTS | Edge / `ko-KR-SunHiNeural` | 한국어 음성 |
| 자막 | 생성된 대본 기반 | `SHORTS_USE_STT_SUBTITLES=1`일 때 STT 사용 |
| STT | local Whisper | STT 경로를 선택했을 때 사용 |
| 업로드 | YouTube Data API / `unlisted` | 공개 업로드는 별도 허용 필요 |

Hermes 이미지 큐의 기본 위치는 `.mp/hermes_images/queue/`입니다. 큐가 비었을 때 Hermes CLI로 직접 이미지를 만들려면 `.env`에서 다음 값을 명시합니다.

```dotenv
HERMES_ENABLE_CLI_IMAGE_GENERATION=1
HERMES_CLI=hermes
HERMES_IMAGE_PROVIDER=openai-codex
HERMES_IMAGE_MODEL=gpt-5.5
```

Ollama를 사용할 때는 `config.json`을 다음과 같이 맞춥니다.

```json
{
  "text_provider": "ollama",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_model": "your-installed-model"
}
```

Gemini 텍스트와 이미지를 사용할 때는 모델 이름도 `gemini`로 시작해야 합니다.

```json
{
  "text_provider": "gemini",
  "ollama_model": "gemini-2.5-flash",
  "image_provider": "gemini"
}
```

```dotenv
GOOGLE_API_KEY=your_key_here
# 또는 GEMINI_API_KEY=your_key_here
```

텍스트 라우팅은 `text_provider=hermes`를 우선 처리하고, 그 외에는 선택된 모델 이름이 `gemini...`이면 Gemini, 나머지는 Ollama를 사용합니다. 상세 설정은 [docs/Configuration.md](docs/Configuration.md)를 확인하세요.

## mise 작업

| 명령 | 설명 |
| --- | --- |
| `mise run setup` | 로컬 설정·가상환경·의존성 준비 |
| `mise run deps` | Python 의존성만 갱신 |
| `mise run doctor` | 실제 런타임과 같은 설정 getter로 공급자·환경 점검 |
| `mise run app` | 대화형 CLI 시작 |
| `mise run fetch-news` | IT 뉴스 수집·랭킹 |
| `mise run make-short` | 기사 하나로 Short 생성 |
| `mise run generate-top5` | Top 5 배치 생성 |
| `mise run youtube-auth` | YouTube OAuth 인증 |
| `mise run upload-unlisted` | 검토된 Top 5를 unlisted로 업로드 |
| `mise run two-hour-job` | 생성·검토·업로드 작업 1회 실행 |
| `mise run test` | 전체 단위 테스트 실행 |
| `mise run check` | JSON, Python 컴파일, 전체 테스트 검증 |

## 뉴스와 영상 생성

뉴스 후보만 확인합니다.

```bash
mise run fetch-news
mise run make-short -- --dry-run
```

캐시된 뉴스의 두 번째 기사로 단일 Short를 만듭니다.

```bash
mise run make-short -- --use-cache --article-index 2
```

Top 5 배치를 생성합니다.

```bash
mise run generate-top5
```

Windows PowerShell에서 후보 수와 제외어를 지정하는 예시:

```powershell
$env:NEWS_LIMIT = "30"
$env:EXCLUDE_TERMS = "lawsuit|earnings|rumor"
mise run generate-top5
```

주요 결과물은 다음 위치에 생성됩니다.

```text
.mp/batch_top5/manifest.json       배치 메타데이터와 검토 상태
.mp/batch_top5/frame_rank*.png     사람 검토용 대표 프레임
.mp/script_reviews/                대본 검수 기록
```

## YouTube OAuth와 업로드

1. Google Cloud에서 YouTube Data API를 활성화하고 OAuth Desktop 클라이언트를 만듭니다.
2. 받은 JSON을 `secrets/youtube_oauth_client_secret.json`에 저장합니다.
3. 대상 채널 ID를 `.env`의 `YOUTUBE_CHANNEL_ID`에 설정합니다.
4. 브라우저 인증을 실행합니다.

```bash
mise run youtube-auth
```

토큰은 `secrets/youtube_oauth_token.json`에 저장됩니다. 업로드 전에 `.mp/batch_top5/manifest.json`, MP4와 검토 프레임을 확인한 뒤 unlisted 업로드를 실행합니다.

```bash
mise run upload-unlisted
```

일부 순위만 올리려면 `START_RANK`, `END_RANK`를 설정합니다. 공개 업로드는 의도적인 작업이므로 mise 단축 작업으로 제공하지 않습니다.

```powershell
$env:ALLOW_PUBLIC_UPLOAD = "1"
$env:YOUTUBE_CHANNEL_ID = "UC..."
$env:START_RANK = "2"
$env:END_RANK = "4"
mise exec -- python scripts/upload_top5_public_shorts.py
```

`ALLOW_UNREVIEWED_UPLOADS=1`은 보호 장치를 우회하므로 일반 운영에서는 사용하지 마세요. OAuth 세부 절차는 [docs/youtube-api-oauth-setup.md](docs/youtube-api-oauth-setup.md)를 확인하세요.

## 반복 작업과 Post Bridge

2시간 단위 작업을 실제 업로드 없이 점검하려면:

```powershell
$env:SHORTS_JOB_DRY_RUN = "1"
mise run two-hour-job
```

실행 기본 공개 범위는 `unlisted`입니다. `SHORTS_JOB_VISIBILITY=public`도 공개 업로드 가드를 자동으로 우회하지 않습니다.

Post Bridge 교차 게시는 기본적으로 비활성화되어 있습니다. `config.json`의 `post_bridge`와 `.env`의 `POST_BRIDGE_API_KEY`를 설정한 경우에만 활성화하세요. 자세한 내용은 [docs/PostBridge.md](docs/PostBridge.md)를 확인하세요.

## 테스트와 검증

코드 변경 후 권장 검증:

```bash
mise run check
mise run doctor
```

`check`는 예제 JSON 파싱, `src/`와 `scripts/` 컴파일, 전체 `unittest`를 실행합니다. `doctor`는 외부 CLI, 모델, API 키와 네트워크 상태까지 확인하므로 로컬 공급자 설정에 따라 별도로 실패할 수 있습니다.

mise 없이 실행하려면:

```bash
python -m unittest discover -s tests -v
python scripts/preflight_local.py
```

GitHub Actions도 Python 3.12와 FFmpeg 환경에서 전체 테스트를 실행합니다.

## 프로젝트 구조

```text
src/main.py                         대화형 CLI 진입점
src/config.py                       config.json과 .env 설정 getter
src/news/                           뉴스 수집·정규화·랭킹·중복 방지
src/classes/YouTube.py              Shorts 생성 오케스트레이션
src/classes/youtube_*.py            콘텐츠·시각 요소·자막·합성·검토
src/youtube_api/                    OAuth, 업로드, 성능 데이터
scripts/preflight_local.py          로컬 환경 진단
scripts/make_news_short.py          단일 기사 Short 생성
scripts/generate_top5_shorts.py     Top 5 배치 생성
scripts/run_two_hour_short_job.py   반복 운영 작업
scripts/setup_local_*.{sh,ps1}      OS별 초기 설정
tests/                              unittest 테스트 모음
docs/                               설정과 운영 문서
```

## 로컬 데이터와 Git

- `.mp/`: 영상, 오디오, 이미지, 캐시, 매니페스트, 검토 자료
- `data/news_archive.sqlite3`: 수집 뉴스 아카이브
- `data/upload_history.json`: 업로드 이력
- `reports/`: 뉴스와 YouTube 분석 보고서
- `secrets/`: OAuth 클라이언트와 토큰
- `config.json`, `.env`: 로컬 설정과 비밀값
- `venv/`: Python 가상환경

위 항목은 필요한 예제·고정 데이터만 제외하고 `.gitignore`에서 보호됩니다. 실제 API 키, OAuth JSON, 채널별 ID, 생성 미디어 또는 로컬 브라우저 프로필을 커밋하지 마세요. 개인별 mise override는 `mise.local.toml`에 둘 수 있습니다.

## 문제 해결

### `mise` 또는 Python을 찾지 못함

`mise` 설치 후 새 터미널을 열고 `mise install`을 다시 실행하세요. mise를 쓰지 않는 Windows 환경은 Python 3.12 설치 시 `py -3.12 --version`이 동작하는지 확인합니다.

### setup은 끝났지만 doctor가 실패함

기본 설정은 Hermes를 사용합니다. Hermes CLI를 설치·인증하거나 `config.json`에서 Ollama 또는 Gemini 경로를 선택한 뒤 다시 실행하세요.

```bash
mise run doctor
```

### FFmpeg 오류

`ffmpeg -version`이 동작하는지 확인하고 PATH를 갱신하세요. ImageMagick 설치 여부와는 별개입니다.

### 플레이스홀더 때문에 업로드가 차단됨

`image_provider=placeholder`는 smoke test 전용입니다. Hermes 큐/CLI 또는 Gemini 이미지 설정을 복구한 뒤 영상을 다시 생성하세요.

### 잘못된 채널로 업로드될 위험

`.env`의 `YOUTUBE_CHANNEL_ID`를 실제 대상 채널과 일치시키세요. 업로드 코드는 OAuth 토큰의 채널을 조회해 예상 ID와 다르면 중단합니다.

## 문서

- [설정 레퍼런스](docs/Configuration.md)
- [Windows 설정](docs/WindowsSetup.md)
- [YouTube OAuth 설정](docs/youtube-api-oauth-setup.md)
- [Post Bridge](docs/PostBridge.md)
- [로드맵](docs/Roadmap.md)
- [기여 가이드](CONTRIBUTING.md)

## 라이선스와 면책

이 프로젝트는 GNU Affero General Public License v3.0을 따릅니다. 네트워크 서비스로 수정 버전을 제공하는 경우를 포함해 배포·소스 공개 의무는 [LICENSE](LICENSE)를 확인하세요.

생성된 뉴스 요약, 이미지, 음성, 메타데이터와 업로드 대상 계정은 게시 전에 직접 검토해야 합니다. 뉴스 정확성, 저작권, 플랫폼 정책과 계정 작업에 대한 책임은 운영자에게 있습니다.
