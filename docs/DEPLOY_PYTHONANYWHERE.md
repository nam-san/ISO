# 배포 가이드 — GitHub + PythonAnywhere (초보자용)

이 문서는 처음 배포하는 사람을 위해 **한 단계씩** 설명합니다.
전체 흐름: **내 컴퓨터 → GitHub(코드 저장소) → PythonAnywhere(웹 서버)**

---

## 준비물

- 이메일 주소 1개
- 이 프로젝트 폴더 (이미 준비 완료)

---

## PART A. GitHub에 코드 올리기

### A-1. GitHub 계정 만들기
1. https://github.com 접속 → **Sign up**
2. 이메일 / 비밀번호 / 사용자이름(username) 입력 후 가입
   - 예: username을 `nurivoice`로 정했다면 기억해 두세요. 뒤에서 씀.

### A-2. 새 저장소(repository) 만들기
1. 로그인 후 오른쪽 위 **+** → **New repository**
2. 입력:
   - **Repository name**: `iso-ims` (원하는 이름)
   - **Public/Private**: 아래 "⚠️ 공개 여부" 참고
   - **Add a README 등은 체크하지 않음** (이미 파일이 있으므로 비워둠)
3. **Create repository** 클릭
4. 다음 화면에 나오는 주소를 복사해 둡니다:
   `https://github.com/사용자이름/iso-ims.git`

> **⚠️ 공개 여부(Public/Private)**
> - `Public`: 누구나 코드를 볼 수 있음 (가장 간단, 배포 테스트에 적합)
> - `Private`: 나만 볼 수 있음 (회사 코드 보호에 안전, 단 PythonAnywhere 연결 시 토큰 1단계 추가)
> - 실제 회사 데이터/문서는 애초에 업로드되지 않으므로(아래 참고), 테스트라면 Public도 무방합니다.

### A-3. 내 컴퓨터에서 GitHub로 업로드
프로젝트 폴더에서 아래 명령을 순서대로 실행합니다.
(`사용자이름`을 본인 GitHub username으로 바꾸세요.)

```bash
git branch -M main
git remote add origin https://github.com/사용자이름/iso-ims.git
git push -u origin main
```

- 처음 push 하면 GitHub 로그인 창이 뜹니다 → 브라우저에서 **Authorize** 하면 됩니다.
- 완료 후 GitHub 저장소 페이지를 새로고침하면 코드가 올라온 것이 보입니다.

> **업로드되지 않는 것 (자동 제외 — 안전)**
> `.env`(비밀키), `instance/`(데이터베이스·회사 데이터), `static/uploads/`(업로드된 문서),
> `.venv/`(가상환경)는 `.gitignore`에 의해 **GitHub에 올라가지 않습니다.**

---

## PART B. PythonAnywhere에 배포하기

### B-1. 계정 만들기
1. https://www.pythonanywhere.com 접속 → **Pricing & signup** → **Create a Beginner account** (무료)
2. 이메일 인증 후 로그인
3. 로그인하면 나오는 주소가 내 사이트 주소가 됩니다:
   `사용자이름.pythonanywhere.com`

### B-2. 코드 내려받기 (Bash 콘솔)
1. 상단 메뉴 **Consoles** → **Bash** 클릭 → 검은 터미널 창이 열림
2. GitHub에서 코드를 내려받습니다 (본인 주소로 변경):
   ```bash
   git clone https://github.com/사용자이름/iso-ims.git
   ```
3. 폴더로 이동:
   ```bash
   cd iso-ims
   ```

### B-3. 가상환경 만들고 패키지 설치
같은 Bash 콘솔에서:
```bash
mkvirtualenv --python=/usr/bin/python3.10 ims-venv
pip install -r requirements.txt
```
- 설치에 1~2분 걸립니다.
- 설치 후 프롬프트 앞에 `(ims-venv)`가 붙어 있으면 정상입니다.

### B-4. 비밀키(.env) 만들기
운영 서버에서는 SECRET_KEY를 반드시 지정해야 합니다. 아래 명령이 랜덤 키로 `.env`를 자동 생성합니다:
```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
echo "FLASK_DEBUG=0" >> .env
```
확인:
```bash
cat .env
```
`SECRET_KEY=...` 와 `FLASK_DEBUG=0` 두 줄이 보이면 됩니다.

### B-5. 웹앱 등록
1. 상단 메뉴 **Web** → **Add a new web app** 클릭
2. 도메인 확인 화면 → **Next**
3. 프레임워크 선택 → **Manual configuration** 선택 (Flask 아님, 주의!)
4. Python 버전 → **Python 3.10** 선택 → **Next**
5. 완료되면 Web 설정 페이지가 나옵니다.

### B-6. 경로 설정
Web 설정 페이지에서 아래 항목을 채웁니다 (`사용자이름`을 본인 것으로):

| 항목 | 값 |
|------|-----|
| **Source code** | `/home/사용자이름/iso-ims` |
| **Working directory** | `/home/사용자이름/iso-ims` |
| **Virtualenv** | `ims-venv` 입력 (자동으로 전체 경로로 바뀜) |

### B-7. WSGI 파일 수정 (서버가 앱을 찾도록 연결)
1. Web 설정 페이지의 **WSGI configuration file** 링크 클릭
   (예: `/var/www/사용자이름_pythonanywhere_com_wsgi.py`)
2. 편집 화면이 열리면 **기존 내용을 전부 지우고** 아래로 교체
   (`사용자이름` 을 본인 것으로 바꾸세요):
   ```python
   import sys

   project_home = '/home/사용자이름/iso-ims'
   if project_home not in sys.path:
       sys.path.insert(0, project_home)

   from app import app as application
   ```
3. 오른쪽 위 **Save** 클릭

### B-8. 정적 파일(CSS/이미지) 연결
Web 설정 페이지 아래 **Static files** 섹션에서 **Enter URL / Enter path** 로 한 줄 추가:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/사용자이름/iso-ims/static` |

### B-9. 실행!
1. Web 설정 페이지 맨 위 초록색 **Reload** 버튼 클릭
2. 잠시 후 `사용자이름.pythonanywhere.com` 접속
3. 로그인 화면이 나오면 성공 🎉
   - 아이디: `admin`
   - 비밀번호: `nurivoice2024!`
   - **로그인 후 즉시 비밀번호를 변경하세요.**

---

## 문제가 생겼을 때

- **화면에 "Something went wrong" / 500 에러**
  → Web 설정 페이지의 **Error log** 링크를 열어 맨 아래 빨간 오류 메시지 확인.
- **CSS가 깨져 보임(디자인 없음)**
  → B-8 정적 파일 경로를 다시 확인하고 Reload.
- **코드를 수정해서 다시 올리고 싶을 때**
  1. 내 컴퓨터에서: `git add -A && git commit -m "수정" && git push`
  2. PythonAnywhere Bash 콘솔에서: `cd iso-ims && git pull`
  3. Web 설정 페이지에서 **Reload** 클릭

---

## ⚠️ 무료 플랜에서 알아둘 점

- **데이터 유지**: PythonAnywhere는 파일이 유지되므로 입력한 데이터·업로드 문서가 남습니다. (Render와 다름)
- **3개월마다 로그인 필요**: 무료 계정은 3개월에 한 번 "still using" 버튼을 눌러야 앱이 유지됩니다.
- **외부 접속 제한**: 무료 플랜은 외부 인터넷 접속(API 호출)이 제한되지만, 이 앱은 외부 호출이 없어 문제 없습니다.
- **실사용 전환 시**: 자체 도메인·상시 가동·성능이 필요하면 유료 플랜($5/월~) 또는 사내 서버를 고려하세요.
