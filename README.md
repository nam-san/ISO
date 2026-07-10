# 누리보이스 ISO 통합경영시스템 (IMS)

주식회사 누리보이스의 ISO 통합경영시스템(IMS) 웹 애플리케이션입니다.
문서관리, 기록관리, 내부심사(CAPA), HSE, 교육, 고객불만, 설계, 경영검토, 위험성평가(RBA),
검사, 고충처리, 조직도, 개선활동, 회의록 등을 관리합니다.

## 기술 스택

- **백엔드**: Python / Flask 3
- **데이터베이스**: SQLite (Flask-SQLAlchemy + Flask-Migrate)
- **인증**: Flask-Login
- **보안**: Flask-WTF (CSRF 보호)

## 로컬 실행 방법 (Windows)

1. Python 3.10 이상 설치 (https://www.python.org)
2. 프로젝트 폴더에서 `run.bat` 더블클릭
   - 최초 실행 시 가상환경 생성 및 패키지 자동 설치
   - 브라우저에서 http://localhost:5000 접속
3. 초기 관리자 계정
   - 아이디: `admin`
   - 비밀번호: `nurivoice2024!`
   - **⚠️ 최초 로그인 후 반드시 비밀번호를 변경하세요.**

## 수동 실행 (참고)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # 이후 .env 안의 SECRET_KEY 값을 변경
.venv\Scripts\python app.py
```

## 환경 변수 (.env)

`.env.example`을 복사하여 `.env`를 만들고 값을 채웁니다. 주요 변수:

| 변수 | 설명 |
|------|------|
| `SECRET_KEY` | Flask 세션·CSRF 보안 키 (**운영 시 반드시 랜덤 값으로 변경**) |
| `DATABASE_URL` | DB 경로 (미설정 시 `instance/ims.db` 사용) |
| `FLASK_DEBUG` | `1`=개발, `0`=운영 |

## 배포

온라인 배포(PythonAnywhere) 방법은 [`docs/DEPLOY_PYTHONANYWHERE.md`](docs/DEPLOY_PYTHONANYWHERE.md)를 참고하세요.
