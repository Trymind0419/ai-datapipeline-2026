# ==============================================================================
# 프로그램 명: 당근마켓 키워드 검색 기반 중고매물 스크래핑 및 파이프라인 프로그램
# 파일명: daangn_scrap.py
# 작성 목적: 사용자가 입력한 검색어를 당근마켓 검색창에 자동 입력하고, 
#            결과 매물 데이터(제목, 가격, 지역, 시간, 링크)를 스크래핑하여 
#            Pandas DataFrame 정제 후 CSV 및 PostgreSQL로 적재
# 교육 과정: ai-datapipeline-2026 / chapt05
# 필요 패키지: selenium, pandas, sqlalchemy, psycopg
# ==============================================================================

# 프로그램 실행 경과 및 오류를 파일과 화면에 남기기 위한 logging 모듈 임포트
import logging
# 환경변수 조회 및 시스템 설정을 다루기 위한 os 모듈 임포트
import os
# 인간과 유사한 자연스러운 동작을 모사하기 위한 난수 생성 random 모듈 임포트
import random
# 가격 텍스트 및 숫자 정제를 위한 정규표현식 re 모듈 임포트
import re
# 페이지 렌더링 대기 및 작업 간격을 두기 위한 time 모듈 임포트
import time
# 수집 시점 기록 및 고유한 결과 파일명을 생성하기 위한 datetime 모듈 임포트
from datetime import datetime
# 안전한 OS 독립적 파일/폴더 경로 처리를 위한 Path 클래스 임포트
from pathlib import Path
# 명령줄 인자(sys.argv) 처리를 위한 sys 모듈 임포트
import sys

# 수집된 데이터를 2차원 표 구조로 가공하고 저장하기 위한 pandas 라이브러리 임포트
import pandas as pd
# 크롬 웹 브라우저 자동 제어를 위한 Selenium webdriver 모듈 임포트
from selenium import webdriver
# 웹 스크래핑 중 발생할 수 있는 주요 Selenium 예외 클래스 임포트
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
# 태그명, CSS 선택자, XPath 등으로 HTML 요소를 지정하기 위한 By 클래스 임포트
from selenium.webdriver.common.by import By
# 검색창에 Enter 키나 텍스트를 입력하기 위한 Keys 클래스 임포트
from selenium.webdriver.common.keys import Keys
# 웹 요소가 화면에 나타날 때까지 지정한 조건을 판별하는 expected_conditions 임포트
from selenium.webdriver.support import expected_conditions as EC
# 동적 페이지 로딩을 최대 N초 동안 지능적으로 대기하는 WebDriverWait 클래스 임포트
from selenium.webdriver.support.ui import WebDriverWait
# chapt05에서 학습한 PostgreSQL 데이터베이스 연동용 SQLAlchemy 모듈 임포트
from sqlalchemy import BigInteger, Integer, Text, URL, create_engine


# ------------------------------------------------------------------------------
# 1. 로깅 환경 초기화 함수 (chapt05 패턴)
# ------------------------------------------------------------------------------
def init_logger(log_file_path: Path) -> logging.Logger:
    """화면 콘솔과 로그 파일에 실시간 진행 상황을 기록하는 로거 초기화 함수"""
    # basicConfig를 사용하여 콘솔 및 파일 핸들러 동시 등록
    logging.basicConfig(
        level=logging.INFO,  # INFO 등급 이상의 로그만 기록
        format="%(asctime)s %(levelname)s %(message)s",  # 타임스탬프와 로그 레벨 포맷
        handlers=[
            logging.StreamHandler(),  # 터미널 콘솔 화면 출력
            logging.FileHandler(log_file_path, encoding="utf-8"),  # 한글 깨짐 방지 utf-8 파일 기록
        ],
        force=True,  # 기존 로거 설정 초기화 허용
    )
    # 당근마켓 전용 로거 인스턴스 반환
    return logging.getLogger("DaangnScraper")


# ------------------------------------------------------------------------------
# 2. 크롬 웹드라이버 환경 설정 함수
# ------------------------------------------------------------------------------
def setup_chrome_driver() -> webdriver.Chrome:
    """당근마켓 탐색에 최적화된 크롬 브라우저 옵션을 설정하고 실행하는 함수"""
    # 크롬 구동 옵션 인스턴스 생성
    options = webdriver.ChromeOptions()
    # 데스크톱 해상도(1920x1080)로 화면을 고정하여 반응형 레이아웃 깨짐 방지
    options.add_argument("--window-size=1920,1080")
    # 자동화 봇 탐지 플래그 비활성화
    options.add_argument("--disable-blink-features=AutomationControlled")
    # 일반 사용자 브라우저처럼 보이도록 현실적인 User-Agent 문자열 지정
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # 웹 푸시 알림 팝업 차단
    options.add_argument("--disable-notifications")
    # 설정된 옵션으로 크롬 브라우저 드라이버 인스턴스 반환
    return webdriver.Chrome(options=options)


# ------------------------------------------------------------------------------
# 3. 단일 매물 카드 텍스트 파싱 함수
# ------------------------------------------------------------------------------
def parse_daangn_card(element, search_keyword: str) -> dict:
    """하나의 매물 카드 <a> 태그에서 제목, 가격, 동네, 등록시간을 추출하는 함수"""
    # 카드 내의 전체 텍스트 추출 및 앞뒤 공백 제거
    raw_text = element.text.strip()
    # 상품 상세 페이지 연결 URL 추출
    detail_url = element.get_attribute("href")

    # 줄바꿈(\n) 기준으로 분리하고 'thumbnail' 및 '바로구매' 같은 부가 뱃지 제거
    text_lines = [
        line.strip()
        for line in raw_text.split("\n")
        if line.strip() and line.strip() not in ["thumbnail", "바로구매"]
    ]

    # 첫 번째 줄을 상품 제목으로 지정 (없을 경우 빈 문자열)
    title = text_lines[0] if len(text_lines) > 0 else ""

    # 정규표현식으로 '숫자,숫자원' 형태의 가격 문자열 탐색
    price_val = None
    price_match = re.search(r"([\d,]+)원", raw_text)
    if price_match:
        # 쉼표를 제거하고 순수 숫자로 변환하여 정수형으로 저장
        price_val = int(re.sub(r"[^0-9]", "", price_match.group(1)))
    elif "나눔" in raw_text:
        # 무료 나눔 매물인 경우 0원으로 처리
        price_val = 0

    # 동네명과 등록/끌올 시간 분리
    region = ""
    time_info = ""
    for line in text_lines[1:]:
        # 가격 줄이 아닌 경우에만 지역/시간 정보로 판별
        if "원" not in line:
            # 가운데 점(·) 기호가 포함된 경우 동네와 시간으로 분리
            if "·" in line:
                parts = line.split("·")
                region = parts[0].strip()
                time_info = parts[1].strip() if len(parts) > 1 else ""
                break
            # 행정구역 단위나 '전' 문구가 포함된 경우
            elif any(token in line for token in ["동", "구", "읍", "면", "전"]):
                region = line
                break

    # 파싱된 데이터 딕셔너리 반환
    return {
        "keyword": search_keyword,      # 검색에 사용된 키워드
        "title": title,                 # 매물 제목
        "price": price_val,             # 매물 가격 (정수)
        "region": region,               # 거래 지역 (동네)
        "time_info": time_info,         # 등록 또는 끌올 시간
        "article_url": detail_url,      # 상품 상세 페이지 URL
    }


# ------------------------------------------------------------------------------
# 4. PostgreSQL 데이터베이스 저장 함수 (chapt05 패턴)
# ------------------------------------------------------------------------------
def save_to_postgres(df: pd.DataFrame, table_name: str, logger: logging.Logger) -> None:
    """chapt05에서 학습한 SQLAlchemy create_engine과 to_sql을 이용한 DB 적재 함수"""
    engine = None
    try:
        # PostgreSQL 접속 URL 객체 생성
        db_url = URL.create(
            "postgresql+psycopg",
            username=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", "123456"),
            host=os.getenv("PGHOST", "127.0.0.1"),
            port=int(os.getenv("PGPORT", "5432")),
            database=os.getenv("PGDATABASE", "postgres"),
        )
        # SQLAlchemy 엔진 생성
        engine = create_engine(db_url)
        # 데이터프레임을 PostgreSQL 테이블에 replace 모드로 적재
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="replace",  # 기존 테이블이 있으면 덮어쓰기
            index=False,
            dtype={
                "index": BigInteger(),
                "keyword": Text(),
                "title": Text(),
                "price": Integer(),
                "region": Text(),
                "time_info": Text(),
                "article_url": Text(),
            },
        )
        # DB 저장 성공 로그 기록
        logger.info("PostgreSQL 저장 완료: 테이블명=[%s] (%d건)", table_name, len(df))
    except Exception as db_err:
        # DB 연결 실패 시 경고 로그 기록 후 계속 진행
        logger.warning("PostgreSQL 저장 중 오류 (DB 가동 상태를 확인하세요): %s", db_err)
    finally:
        # DB 엔진 자원 해제
        if engine is not None:
            engine.dispose()


# ------------------------------------------------------------------------------
# 5. 당근마켓 키워드 검색 및 스크래핑 메인 함수
# ------------------------------------------------------------------------------
def scrape_daangn_market(keyword: str, max_items: int = 200, save_db: bool = False) -> pd.DataFrame:
    """사용자가 입력한 검색어로 당근마켓을 탐색하여 정제된 DataFrame을 생성 및 저장하는 함수"""
    # 작업 시작 시간 기록
    now = datetime.now()

    # 데이터 저장 경로: 프로젝트 공용 data/ 폴더 자동 연결
    work_dir = Path.cwd()
    data_dir = (work_dir.parent if work_dir.name.lower() == "chapt05" else work_dir) / "data"
    # data 디렉터리가 없을 경우 생성
    data_dir.mkdir(parents=True, exist_ok=True)

    # 안전한 파일명을 위해 공백을 언더바로 변환
    safe_keyword = re.sub(r"\s+", "_", keyword.strip())
    # 결과 CSV 파일 경로 지정
    csv_file = data_dir / f"daangn_{safe_keyword}_{now:%Y%m%d_%H%M%S}.csv"
    # 실행 로그 파일 경로 지정
    log_file = data_dir / f"daangn_{safe_keyword}_{now:%Y%m%d_%H%M%S}.log"

    # 로거 초기화
    logger = init_logger(log_file)
    logger.info("당근마켓 스크래핑 파이프라인 시작: 키워드=['%s'], 목표 건수=%d건", keyword, max_items)

    # 드라이버 인스턴스 변수 초기화
    driver = None
    # 추출된 원본 레코드들을 담을 리스트 생성
    scraped_rows = []

    try:
        # 크롬 브라우저 구동
        driver = setup_chrome_driver()
        # 동적 로딩을 위한 WebDriverWait 인스턴스 생성 (10초 대기)
        wait = WebDriverWait(driver, 10)

        # -------------------------------------------------------------
        # [Step 1] 당근마켓 메인 접속 후 '중고거래' 탭/메뉴 먼저 클릭
        # -------------------------------------------------------------
        logger.info("당근마켓 메인 페이지 접속 시도...")
        driver.get("https://www.daangn.com")
        logger.info("당근마켓 메인 접속 완료: %s", driver.title)

        try:
            # 검색어가 날아가는 것을 방지하기 위해 상단 메뉴에서 '중고거래' 탭/링크를 먼저 클릭
            used_tab = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), '중고거래')] | //button[contains(text(), '중고거래')]")
                )
            )
            # 중고거래 전용 메뉴 클릭 실행
            used_tab.click()
            logger.info("'중고거래' 전용 화면으로 이동 완료")
            # 중고거래 전용 화면 로딩을 위한 대기
            time.sleep(random.uniform(2.0, 3.0))
        except Exception as tab_err:
            # 탭을 찾지 못할 경우 경고를 남기고 현재 화면에서 계속 진행
            logger.warning("중고거래 탭 클릭 실패 (현재 화면에서 검색 진행): %s", tab_err)

        # -------------------------------------------------------------
        # [Step 2] 중고거래 전용 검색창에 키워드 입력 및 검색 실행
        # -------------------------------------------------------------
        # 상단 검색창 input 요소가 보일 때까지 대기 및 탐색
        search_box = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='search'], input[type='text'], input[placeholder*='검색']")
            )
        )

        # 검색창 클릭 및 기존 내용 초기화
        search_box.clear()
        # 사용자 지정 검색어 타이핑
        search_box.send_keys(keyword)
        # Enter 키를 눌러 검색 실행
        search_box.send_keys(Keys.ENTER)
        logger.info("중고거래 검색창에 키워드 ['%s'] 입력 및 검색 실행 완료", keyword)

        # 검색 결과 렌더링을 위해 잠시 대기
        time.sleep(random.uniform(2.5, 3.5))

        # -------------------------------------------------------------
        # [Step 3] 1페이지부터 목표 수량(200개)까지 페이지 번호(1, 2, 3...) 클릭 순회 (chapt04 다나와 패턴)
        # -------------------------------------------------------------
        # 현재 탐색 중인 페이지 번호 초기화
        current_page = 1
        # 1페이지당 약 32개씩 들어오므로 목표 개수에 따른 최대 탐색 페이지 계산
        max_page_limit = (max_items // 30) + 3

        # 목표 수량을 채우거나 최대 페이지 한도에 도달할 때까지 반복
        while len(scraped_rows) < max_items and current_page <= max_page_limit:
            # 현재 페이지의 매물 카드 요소들이 로딩될 때까지 대기
            current_cards = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[href*="/kr/buy-sell/"]'))
            )
            # 현재 페이지 매물 수 및 누적 수집 건수 로깅
            logger.info("[%d페이지] 매물 %d개 확인 (현재 누적: %d개 / 목표: %d개)", current_page, len(current_cards), len(scraped_rows), max_items)

            # 현재 페이지의 매물 카드들을 하나씩 파싱
            for card in current_cards:
                try:
                    # 단일 카드 파싱 함수 호출
                    item_data = parse_daangn_card(card, keyword)
                    # 수집 순번 부여
                    item_data["index"] = len(scraped_rows)
                    # 레코드 목록에 추가
                    scraped_rows.append(item_data)
                    # 목표 수량에 도달하면 즉시 중단
                    if len(scraped_rows) >= max_items:
                        break
                except Exception as parse_err:
                    # 개별 매물 파싱 실패 시 경고 로그 기록 후 다음으로 진행
                    logger.warning("매물 파싱 중 예외 발생: %s", parse_err)

            # 목표 수량을 채웠으면 다음 페이지로 가지 않고 루프 종료
            if len(scraped_rows) >= max_items:
                logger.info("목표 매물 수량(%d개)에 도달하여 수집을 마칩니다.", max_items)
                break

            # 다음 페이지 번호 계산
            next_page_num = current_page + 1
            try:
                # 다음 페이지 번호 버튼 탐색 (예: button '2', button '3' ...)
                next_btn = driver.find_element(By.XPATH, f"//button[normalize-space()='{next_page_num}']")
                # 버튼 위치로 스크롤 이동
                driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                time.sleep(1.0)
                # 다음 페이지 버튼 클릭 실행
                driver.execute_script("arguments[0].click();", next_btn)
                logger.info("[%d페이지] 이동 버튼 클릭 성공", next_page_num)
                # 현재 페이지 번호 갱신
                current_page = next_page_num
                # 다음 페이지 렌더링을 위한 대기
                time.sleep(random.uniform(2.5, 3.5))
            except Exception as page_err:
                # 다음 페이지 버튼이 없으면(마지막 페이지 도달 등) 루프 탈출
                logger.info("다음 페이지 버튼(%d)을 찾을 수 없거나 끝 페이지입니다: %s", next_page_num, page_err)
                break

        # -------------------------------------------------------------
        # [Step 5] Pandas DataFrame 정제 (chapt02, chapt05)
        # -------------------------------------------------------------
        # 추출된 딕셔너리 리스트를 Pandas DataFrame으로 변환
        df_result = pd.DataFrame(
            scraped_rows,
            columns=["index", "keyword", "title", "price", "region", "time_info", "article_url"],
        )
        logger.info("정제 전 총 수집 데이터 건수: %d건", len(df_result))

        if not df_result.empty:
            # 동일한 article_url을 가진 중복 매물 제거
            df_result = df_result.drop_duplicates(subset=["article_url"]).reset_index(drop=True)
            # 재정렬된 행 순서로 index 컬럼 갱신
            df_result["index"] = df_result.index

        logger.info("중복 제거 후 최종 데이터 건수: %d건", len(df_result))

        # -------------------------------------------------------------
        # [Step 6] CSV 파일 저장 (utf-8-sig)
        # -------------------------------------------------------------
        df_result.to_csv(csv_file, index=False, encoding="utf-8-sig")
        logger.info("CSV 파일 저장 완료: %s", csv_file)

        # -------------------------------------------------------------
        # [Step 7] PostgreSQL DB 저장 (옵션 선택 시)
        # -------------------------------------------------------------
        if save_db and not df_result.empty:
            # 오늘 날짜를 포함한 고유 테이블명 생성
            db_table_name = f"daangn_{safe_keyword}_{now:%y%m%d}"
            save_to_postgres(df_result, db_table_name, logger)

        # 수집 완료 안내 요약 콘솔 출력
        print("\n" + "=" * 55)
        print(f"당근마켓 ['{keyword}'] 스크래핑 성공 완료!")
        print(f"- 최종 수집 건수: {len(df_result)}건")
        print(f"- CSV 파일 위치: {csv_file}")
        print("=" * 55)
        # 상위 5개 데이터 미리보기 출력
        if not df_result.empty:
            print(df_result.head())

        # 최종 데이터프레임 반환
        return df_result

    except TimeoutException:
        # 페이지 로딩 시간 초과 예외 처리
        logger.exception("당근마켓 페이지 로딩 시간이 초과되었습니다 (10초).")
        return pd.DataFrame()
    except Exception as total_err:
        # 기타 모든 예외 상황에 대한 에러 로깅
        logger.exception("스크래핑 작업 진행 중 예외 발생: %s", total_err)
        return pd.DataFrame()
    finally:
        # 브라우저 드라이버 정상 종료 처리
        if driver is not None:
            driver.quit()
            logger.info("크롬 웹 브라우저가 안전하게 종료되었습니다.")


# ==============================================================================
# 프로그램 메인 엔트리포인트 (CLI 인터랙티브 실행)
# ==============================================================================
if __name__ == "__main__":
    # 사용자 타이틀 출력
    print("=" * 65)
    print("   당근마켓 키워드 검색 기반 중고매물 스크래핑 파이프라인")
    print("   (Selenium + Pandas + PostgreSQL / ai-datapipeline-2026)")
    print("=" * 65)

    # 기본 설정값 (배치 파일 및 스케줄러 기본 실행값)
    default_keyword = "맥북 프로"
    default_limit = 200

    # 1. 명령줄 인자(sys.argv)가 전달된 경우 지정한 인자값 사용
    if len(sys.argv) > 1:
        # 첫 번째 명령줄 인자를 검색 키워드로 지정 (비어있으면 기본값 사용)
        user_query = sys.argv[1].strip() or default_keyword
        # 두 번째 명령줄 인자가 숫자로 들어오면 수집 개수로 지정
        user_limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else default_limit
        # 세 번째 명령줄 인자가 'y'이면 PostgreSQL DB 저장 활성화 (기본값: False)
        should_save_db = sys.argv[3].lower() == "y" if len(sys.argv) > 3 else False
    else:
        # 2. 인자 없이 바로 실행할 경우 기본값("맥북 프로", 30건)으로 자동 실행
        user_query = default_keyword
        user_limit = default_limit
        should_save_db = False

    # 스크래핑 실행 정보 콘솔 출력
    print(f"스크래핑 시작: 검색어=['{user_query}'], 목표 수량={user_limit}건, DB저장={should_save_db}")
    # 메인 스크래핑 함수 호출 및 실행
    scrape_daangn_market(keyword=user_query, max_items=user_limit, save_db=should_save_db)

