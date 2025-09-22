# scripts/crawler.py

import os
import time
import json
import traceback
import psycopg2 # PostgreSQL 접속을 위한 라이브러리
from psycopg2.extras import DictCursor

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# DB 접속
# Airflow를 통해 환경변수로 전달받을 정보들
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "airflow")
DB_USER = os.getenv("DB_USER", "airflow")
DB_PASSWORD = os.getenv("DB_PASSWORD", "airflow")
DB_PORT = os.getenv("DB_PORT", 5432)

def get_db_connection():
    """PostgreSQL 데이터베이스에 연결하고 connection 객체를 반환"""
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    return conn

def setup_database():
    """필요한 테이블이 없는 경우 생성하는 함수"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. characters 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            image_url VARCHAR(2048),
            first_message TEXT,
            source_url VARCHAR(2048),
            crawled_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
    """)
    print("Table 'characters' is ready.")

    # 2. categories 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL
        );
    """)
    print("Table 'categories' is ready.")

    # 3. character_category_mapping 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_category_mapping (
            character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            PRIMARY KEY (character_id, category_id)
        );
    """)
    print("Table 'character_category_mapping' is ready.")
    
    conn.commit()
    cur.close()
    conn.close()

def save_to_db(character_data):
    """스크래핑한 데이터를 DB에 저장"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. characters 테이블에 데이터 삽입하고 새로 생성된 character_id 반환받기
        cur.execute(
            """
            INSERT INTO characters (name, description, image_url, first_message, source_url)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                character_data['name'],
                character_data['description'],
                character_data['image_url'],
                character_data['first_message'],
                character_data['source_url']
            )
        )
        character_id = cur.fetchone()[0]
        print(f"    - Saved character '{character_data['name']}' with ID: {character_id}")

        # 2. categories 테이블 및 매핑 테이블 처리
        for category_name in character_data['categories']:
            # 카테고리가 존재하면 id를, 존재하지 않으면 새로 삽입 후 id를 반환 (UPSERT)
            cur.execute(
                """
                INSERT INTO categories (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id;
                """,
                (category_name,)
            )
            category_id = cur.fetchone()[0]
            
            # 3. character_category_mapping 테이블에 연결 정보 삽입
            # 이미 존재하는 연결이면 에러 없이 무시
            cur.execute(
                """
                INSERT INTO character_category_mapping (character_id, category_id)
                VALUES (%s, %s)
                ON CONFLICT (character_id, category_id) DO NOTHING;
                """,
                (character_id, category_id)
            )
        
        conn.commit()
        print(f"    - Saved {len(character_data['categories'])} categories and mappings.")

    except Exception as e:
        conn.rollback()
        print(f"DB 저장 중 에러 발생: {e}")
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()


def scrape_wrtn_characters():
    """메인 크롤링 및 DB 저장 실행 함수"""
    service = Service(executable_path='/usr/bin/chromedriver')
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=service, options=options)

    URL = "https://crack.wrtn.ai/?pageId=682c89c39d1325983179b65b"
    
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 30) # 대기시간 넉넉하게 30초
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.swiper-slide")))
        num_characters = driver.execute_script("return document.querySelectorAll('div.swiper-slide').length")
        print(f"총 {num_characters}개의 캐릭터를 찾았습니다. 크롤링을 시작합니다.")

        for i in range(num_characters):
            character_data = {}
            try:
                print(f"\n--- [ {i+1} / {num_characters} ] 번째 카드 처리 시작 ---")
                
                cards = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.swiper-slide")))
                if i >= len(cards): continue
                
                card_to_process = cards[i]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", card_to_process)
                time.sleep(1)

                clickable_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, f".swiper-wrapper > .swiper-slide:nth-child({i + 1}) .css-m2oo7f")))
                driver.execute_script("arguments[0].click();", clickable_area)

                modal = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.css-12avfy0")))
                modal_html = modal.get_attribute('outerHTML')
                soup = BeautifulSoup(modal_html, 'html.parser')
                
                name_section = soup.find('div', class_='css-112bf3z')
                if name_section and (name_tag := name_section.find('p', class_='css-132a3j1')):
                    name_in_modal = name_tag.text.strip()
                else:
                    raise ValueError("정상적인 캐릭터 이름 영역/태그를 찾지 못했습니다.")
                
                character_data['title'] = name_in_modal
                print(f"    - 대화방 제목: '{name_in_modal}'")

                character_data['description'] = soup.find('p', class_='css-nybeci').text.strip()
                image_tags = soup.select('div.character_avatar img')
                character_data['image_url'] = image_tags[1]['src'] if len(image_tags) > 1 else (image_tags[0]['src'] if image_tags else "Not Found")
                main_categories = [p.text.strip() for p in soup.select('div.css-rc1aux p')]
                hash_tags = [p.text.strip() for p in soup.select('div.css-uai7m0 p')]
                character_data['categories'] = main_categories + hash_tags
                print(">>> [4] 모달 파싱 완료.")

                chat_button_xpath = "//button[@aria-disabled='false']//div[contains(text(), '대화')]"
                print(">>> [5] '대화' 버튼이 DOM에 나타날 때까지 대기...")
                # '클릭 가능' 대신 '존재' 여부만 먼저 확인하여 안정성 확보
                chat_button = wait.until(EC.presence_of_element_located((By.XPATH, chat_button_xpath)))
                print(">>> [5] 버튼 확인. 자바스크립트로 클릭 실행...")
                
                url_before_click = driver.current_url
                # 다른 요소에 가려져도 클릭할 수 있는 JavaScript 클릭 사용
                driver.execute_script("arguments[0].click();", chat_button)
                
                wait.until(EC.url_changes(url_before_click))
                character_data['source_url'] = driver.current_url

                try:
                    short_wait = WebDriverWait(driver, 5)
                    first_bubble = short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.message-bubble.css-1arcon8")))
                    full_text = first_bubble.text.strip()
                    if '|' in full_text:
                        character_name, first_message = [part.strip() for part in full_text.split('|', 1)]
                        character_data['name'] = character_name
                        character_data['first_message'] = first_message
                    else:
                        character_data['name'] = name_in_modal
                        character_data['first_message'] = full_text
                except TimeoutException:
                    print("    - 첫 메시지를 찾을 수 없음. '첫 메시지 없음'으로 기록합니다.")
                    character_data['name'] = name_in_modal
                    character_data['first_message'] = "N/A"
                
                print(f"    - '{character_data['name']}' 정보 수집 완료. DB 저장 시작...")
                save_to_db(character_data)

            except Exception as e:
                print(f"\n[Loop-{i+1}] ERROR: 처리 중 '{type(e).__name__}' 오류 발생. 건너뜁니다.")
                traceback.print_exc()
            
            finally:
                if driver.current_url != URL:
                    print(f"[Loop-{i+1}] FINALLY: 메인 페이지로 복귀합니다.")
                    driver.get(URL)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.swiper-slide")))
                    time.sleep(2)
                else:
                    print(f"[Loop-{i+1}] FINALLY: 다음 카드를 위해 페이지를 새로고침합니다.")
                    try:
                        close_button = driver.find_element(By.CSS_SELECTOR, "div.css-8x3ale > button")
                        close_button.click()
                        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.css-12avfy0")))
                    except:
                        driver.refresh()
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.swiper-slide")))
                    time.sleep(1)
    finally:
        driver.quit()
        print("\n크롤링 완료! 브라우저를 종료합니다.")

if __name__ == "__main__":
    setup_database()
    scrape_wrtn_characters()