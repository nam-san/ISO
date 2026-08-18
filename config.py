import os
import secrets
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _require_secret_key():
    key = os.environ.get('SECRET_KEY')
    if not key:
        # 개발 환경에서만 임시 키 자동 생성 (경고 출력)
        key = secrets.token_hex(32)
        print("⚠️  경고: SECRET_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


class Config:
    # 보안 비밀키 — .env의 SECRET_KEY 사용 (미설정 시 임시 키 자동 생성)
    SECRET_KEY = _require_secret_key()

    # 데이터베이스 경로
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'ims.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 파일 업로드 설정
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 최대 50MB
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'hwp', 'hwpx', 'png', 'jpg', 'jpeg'}

    # 보안 쿠키 설정
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # SESSION_COOKIE_SECURE = True  # HTTPS 환경에서 활성화

    # CSRF 보호 — 토큰 만료를 세션 수명에 맡김(긴 폼 작성 중 만료 방지)
    WTF_CSRF_TIME_LIMIT = None

    # 회사 정보
    COMPANY_NAME = os.environ.get('COMPANY_NAME', '주식회사 누리보이스')
    SYSTEM_NAME = 'ISO 통합경영시스템 (IMS)'
    SYSTEM_VERSION = 'v1.1'

    # 세션 설정
    PERMANENT_SESSION_LIFETIME = 28800  # 8시간

    # 폐기 알림 임박 기준 (일)
    DISPOSAL_ALERT_DAYS = 30
