# 크랙(Crack) 캐릭터 데이터 수집 파이프라인

## 1. 프로젝트 개요

본 프로젝트는 AI 채팅 콘텐츠 플랫폼 '크랙'의 캐릭터 정보를 수집하기 위해 구축된 자동화된 데이터 파이프라인입니다.

Airflow를 워크플로우 관리 도구로 사용하여, Selenium 기반의 동적 웹 크롤러를 Docker 컨테이너로 실행하고, 수집된 데이터를 구조화하여 PostgreSQL 데이터베이스에 저장합니다. 이 프로젝트는 데이터 엔지니어링의 핵심 요소인 데이터 수집, 처리, 저장을 자동화하는 것을 목표로 합니다.

## 2. 주요 기능 및 수집 데이터

- **자동화된 데이터 수집**: Airflow DAG를 통해 스케줄에 따라 또는 수동으로 크롤링 작업을 실행합니다
- **동적 웹 크롤링**: Selenium을 사용하여 JavaScript로 렌더링되는 웹사이트의 콘텐츠를 수집합니다
- **구조화된 데이터 저장**: 수집된 데이터를 정규화된 형태의 PostgreSQL 데이터베이스에 저장합니다

#### 수집 항목
- 캐릭터명
- 캐릭터 설명
- 캐릭터 사진 원본 URL
- 캐릭터의 첫 메시지
- 캐릭터의 카테고리 (다중)

## 3. 기술 스택 및 아키텍처

- **언어**: Python 3.10
- **의존성 관리**: Poetry
- **컨테이너화**: Docker, Docker Compose
- **워크플로우 관리 (Orchestration)**: Apache Airflow 2.7.3
- **데이터베이스**: PostgreSQL 16
- **웹 크롤링**: Selenium, BeautifulSoup4
- **아키텍처**:
    - `Docker Compose`가 `Airflow`와 `PostgreSQL` 서비스를 실행합니다.
    - `Airflow`의 `DockerOperator`가 `dockerfile.crawler`로 빌드된 별도의 크롤러 이미지를 실행합니다.
    - 크롤러 컨테이너는 `Selenium`으로 웹사이트 데이터를 수집한 후, `psycopg2`를 이용해 `PostgreSQL` DB에 직접 데이터를 저장합니다.

## 4. 프로젝트 구조

```
crack_pipeline/
├── airflow_home/
│   ├── dags/
│   │   └── crack_pipeline_dag.py     # Airflow DAG 정의 파일
│   ├── logs/
│   └── plugins/
├── scripts/
│   └── crawler.py                    # 실제 크롤링 및 DB 저장 로직
├── .env                              # 환경 변수 파일 (DB 접속 정보 등)
├── .venv/                            # Poetry 가상 환경
├── docker-compose.yml                # 전체 서비스(Airflow, Postgres) 정의
├── dockerfile.airflow                # 커스텀 Airflow 이미지를 위한 Dockerfile
├── dockerfile.crawler                # 크롤러 실행을 위한 Dockerfile
├── poetry.lock                       # 의존성 버전 고정 파일
├── pyproject.toml                    # Poetry 의존성 정의 파일
└── README.md                         # 프로젝트 설명서
```

## 5. 데이터베이스 스키마

데이터는 3개의 테이블로 정규화하여 저장합니다

#### 1. `characters`
캐릭터의 고유 정보를 저장합니다.
| 컬럼명 (Column) | 데이터 타입 (Data Type) | 설명 |
| :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | 캐릭터 고유 ID |
| `name` | `VARCHAR(255)` | 캐릭터 이름 |
| `description`| `TEXT` | 캐릭터 설명 |
| `image_url` | `VARCHAR(2048)` | 캐릭터 이미지 URL |
| `first_message` | `TEXT` | 캐릭터 첫 대사 |
| `source_url` | `VARCHAR(2048)` | 캐릭터 대화창 URL |
| `crawled_at`| `TIMESTAMP WITH TIME ZONE`| 수집 시각 |

#### 2. `categories`
카테고리 정보를 중복 없이 저장합니다.
| 컬럼명 (Column) | 데이터 타입 (Data Type) | 설명 |
| :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | 카테고리 고유 ID |
| `name` | `VARCHAR(255) UNIQUE`| 카테고리 이름 |

#### 3. `character_category_mapping`
캐릭터와 카테고리의 다대다(N:M) 관계를 저장하는 매핑 테이블입니다.
| 컬럼명 (Column) | 데이터 타입 (Data Type) | 설명 |
| :--- | :--- | :--- |
| `character_id` | `INTEGER` | `characters.id` 참조 (FK) |
| `category_id`| `INTEGER` | `categories.id` 참조 (FK) |


## 6. 설치 및 실행 방법

#### 사전 준비
- Docker 및 Docker Compose가 설치되어 있어야 합니다
- poetry가 설치되어 있어야 합니다

#### 1단계: 프로젝트 클론 및 의존성 설치
```bash
# 프로젝트를 원하는 위치에 클론합니다.
# 1. 전달받은 소스 코드 압축을 해제하고 해당 폴더로 이동합니다.
cd crack_pipeline

# 2. Poetry를 사용하여 의존성을 설치합니다.
poetry install
```

#### 2단계: 환경 변수 파일(.env) 생성
프로젝트 루트 위치에 `.env` 파일을 생성하고 아래 내용을 추가합니다. (macOS/Linux 기준)

```bash
# 1. 터미널에서 아래 명령어를 실행하여 GID를 확인합니다 (예: 1)
stat -f '%g' /var/run/docker.sock

# 2. .env 파일에 확인된 GID를 입력합니다 (만약 GID가 1이었다면)
# DOCKER_GID=1
```
> **참고**: `DOCKER_GID`는 Airflow 컨테이너가 호스트의 Docker를 제어할 수 있는 권한을 얻기 위해 필요합니다.

#### 3단계: 파이프라인 실행
아래 명령어를 순서대로 실행합니다

```bash
# 1. 이전 실행 기록이 있다면 깨끗하게 정리합니다.
docker-compose down -v

# 2. 크롤러 이미지를 빌드합니다.
docker build -t crack-crawler-image:latest -f dockerfile.crawler .

# 3. --build 옵션으로 Airflow 이미지를 새로 빌드하며 모든 서비스를 실행합니다.
docker-compose up -d --build
```

#### 4단계: Airflow DAG 실행
1. `docker-compose up` 명령이 성공적으로 완료되고 1~2분 정도 기다립니다.
2. 웹 브라우저에서 `http://localhost:8080` 으로 접속합니다.
3. 아이디(`admin`), 비밀번호(`admin`)로 로그인합니다.
4. `crack_character_pipeline` DAG를 찾아 토글을 켜서 활성화합니다.
5. DAG를 수동으로 실행(Trigger)합니다.

## 7. 데이터 확인 및 산출물 생성

#### 데이터 확인
- **GUI 도구 (DBeaver 등)**: 아래 정보로 `localhost`의 PostgreSQL에 접속하여 데이터를 확인합니다.
  - **Host**: `localhost`
  - **Port**: `8081`
  - **Database/User/Password**: `airflow`
- **CLI**: `docker-compose exec -T postgres psql -U airflow -d airflow` 명령어로 접속하여 쿼리를 실행합니다.

#### 산출물 생성
프로젝트 루트 폴더에서 아래 명령어를 실행하여 과제 요구사항에 맞는 산출물을 생성할 수 있습니다.

```bash
# 1. characters 테이블 상위 10개 CSV 파일 생성
docker-compose exec -T postgres psql -U airflow -c "\copy (SELECT * FROM characters LIMIT 10) TO stdout WITH CSV HEADER" > characters_10_rows.csv

# 2. categories 테이블 상위 10개 CSV 파일 생성
docker-compose exec -T postgres psql -U airflow -c "\copy (SELECT * FROM categories ORDER BY id LIMIT 10) TO stdout WITH CSV HEADER" > categories_10_rows.csv

# 3. DB 전체 Dump 파일 생성
docker-compose exec -T postgres pg_dump -U airflow -d airflow > crack_db_dump.sql
```