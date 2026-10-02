import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

#초기 설정
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)

try:
    #웹페이지 오픈
    driver.get('https://quotes.toscrape.com/')

    #웹페이지 다 오픈될 때까지 대기
    footer = wait.until(
        EC.presence_of_element_located((By.CLASS_NAME, 'footer'))
    )

    #로그인 링크 가져오기
    login_link = wait.until(
    EC.element_to_be_clickable((By.LINK_TEXT, 'Login'))
    )

    login_link.click()

    # 아이디 패스워드 입력
    username_input = wait.until(
        EC.presence_of_element_located((By.ID, 'username'))
    )

    password_input = wait.until(
        EC.presence_of_element_located((By.ID, 'password'))
    )

    username_input.send_keys('admin')
    password_input.send_keys('admin')

    login_btn = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
    login_btn.click()

    #로그인완료 확인 및 대기
    wait.until(
    EC.presence_of_element_located((By.LINK_TEXT, 'Logout'))
    )
    print('로그인 성공')

    #1000건 - 100페이지 반복

    rows = []
    # 페이지 번호
    for page_num, page in enumerate(range(1, 11)):
        wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, 'footer'))
        )
        print(f'{page_num} 페이지수집')

        quotes = driver.find_elements(By.CSS_SELECTOR, '.quote')

        for quote in quotes:
            text = quote.find_element(By.CSS_SELECTOR, '.text').text
            author = quote.find_element(By.CSS_SELECTOR, '.author').text
            link = quote.find_elements(By.CSS_SELECTOR, 'span > a')[1].get_attribute('href')
            tags = quote.find_elements(By.CSS_SELECTOR, '.tags > a')
            tag_text = ','.join(tag.text for tag in tags)

            rows.append({
                'text' : text,
                'author' : author,
                'link' : link,
                'tags' : tag_text
            })

        # 마지막 페이지에 NEXT가 없을 떄 find_element()라고 쓰면 실행중 오류 발생!
        next_button = driver.find_elements(By.CSS_SELECTOR, 'li.next a')
        if not next_button:
            break
        next_button[0].click()

    df_quotes = pd.DataFrame(rows)
    #저장
    df_quotes.to_csv('data/quotes_100.csv', encoding='utf-8')
    print('파일저장완료')

    #로그아웃
    logout_link = driver.find_element(By.LINK_TEXT, 'Logout')
    logout_link.click()
    print('로그아웃 완료')
except Exception:
    print('실행중 오류 발생', Exception.args)
finally:
    #접속 정보 빠져나가기
    driver.quit()