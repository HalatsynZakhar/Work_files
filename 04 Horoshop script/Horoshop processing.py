import pandas as pd
import re
import os
from bs4 import BeautifulSoup

# =================================================================
# НАСТРОЙКИ ПУТЕЙ
# =================================================================
BASE_DIR = r"C:\Users\ABM\Desktop\Робота\Звіти керівництву\27 Подтягивая цен за мониторингом на Хорошоп"

HTML_INPUT_FILE = "tracker_page.html"  # ВАШ СОХРАНЕННЫЙ HTML
EXCEL_INPUT_FILE = "articles.xlsm"
EXCEL_OUTPUT_FILE = "ИТОГОВЫЙ_ОТЧЕТ.xlsx"


# =================================================================

def parse_tracker_html(html_path):
    """Парсит сохраненную HTML страницу Dashboard и собирает ВСЕ строки"""
    if not os.path.exists(html_path):
        print(f"!!! HTML файл не найден: {html_path}")
        return None

    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    tracker_results = []
    # Ищем все строки таблицы
    rows = soup.find_all('tr', {'class': 'processor-restock_diff'})

    for row in rows:
        # 1. Извлекаем ссылку и артикул
        link_tag = row.find('a', {'class': 'external'})
        if not link_tag: continue

        url = link_tag.get('href', '')
        # Регулярка для артикула из ссылки (.../название-артикул.html)
        article_match = re.search(r'/([^/]+)\.html', url)
        raw_article = article_match.group(1) if article_match else ""
        article = raw_article.split('-')[-1].strip().upper()

        # 2. Извлекаем цену
        price_tag = row.find('span', {'class': 'price'})
        price = None
        if price_tag:
            # Оставляем только цифры и точку
            price_text = re.sub(r'[^\d.]', '', price_tag.text.replace(',', '.'))
            try:
                price = float(price_text)
            except:
                price = None

        # 3. Извлекаем наличие
        # Ищем тег с классом in-stock или not-in-stock
        stock_label = row.find('span', {'class': 'restock-label'})
        is_in_stock = False
        if stock_label:
            classes = stock_label.get('class', [])
            if 'in-stock' in classes:
                is_in_stock = True
            elif 'not-in-stock' in classes:
                is_in_stock = False

        tracker_results.append({
            'Артикул_поиск': article,
            'Полный_код_ссылки': raw_article.upper(),
            'Цена': price,
            'В_наличии': is_in_stock
        })

    return pd.DataFrame(tracker_results)


def main():
    path_html = os.path.join(BASE_DIR, HTML_INPUT_FILE)
    path_xlsx = os.path.join(BASE_DIR, EXCEL_INPUT_FILE)
    path_output = os.path.join(BASE_DIR, EXCEL_OUTPUT_FILE)

    print(f"--- Обработка HTML страницы ---")

    # 1. Парсинг HTML
    df_tracker = parse_tracker_html(path_html)
    if df_tracker is None or df_tracker.empty:
        print("Не удалось извлечь данные из HTML.")
        return

    # 2. Загрузка Excel
    try:
        df_my_list = pd.read_excel(path_xlsx, engine='openpyxl')
    except Exception as e:
        print(f"Ошибка чтения Excel: {e}")
        return

    # Выбор колонки (интерактивно)
    print("\nДоступные колонки:")
    for i, col in enumerate(df_my_list.columns):
        print(f"{i} : {col}")
    user_input = input("\nВведите ИМЯ или НОМЕР колонки с вашими артикулами: ").strip()

    if user_input.isdigit():
        idx = int(user_input)
        art_column = df_my_list.columns[idx]
    else:
        art_column = user_input if user_input in df_my_list.columns else df_my_list.columns[0]

    df_my_list[art_column] = df_my_list[art_column].astype(str).str.strip().str.upper()

    # 3. Сопоставление
    merged = pd.merge(
        df_my_list,
        df_tracker[['Артикул_поиск', 'Цена', 'В_наличии', 'Полный_код_ссылки']],
        left_on=art_column,
        right_on='Артикул_поиск',
        how='left'
    )

    # Доп. поиск (по вхождению в ссылку)
    unmatched = merged['Артикул_поиск'].isna()
    if unmatched.any():
        for idx, row in merged[unmatched].iterrows():
            val = str(row[art_column])
            match = df_tracker[df_tracker['Полный_код_ссылки'].str.contains(val, na=False, regex=False)]
            if not match.empty:
                merged.at[idx, 'Цена'] = match.iloc[0]['Цена']
                merged.at[idx, 'В_наличии'] = match.iloc[0]['В_наличии']
                merged.at[idx, 'Артикул_поиск'] = match.iloc[0]['Артикул_поиск']

    # Создаем статус "Найдено у партнера"
    merged['Найдено у партнера'] = merged['Артикул_поиск'].apply(lambda x: '+' if pd.notna(x) else '')

    # Создаем статус "Наличие у партнера"
    def get_stock_status(row):
        if pd.isna(row['Артикул_поиск']): return ''
        return '+' if row['В_наличии'] else '-'

    merged['Наличие у партнера'] = merged.apply(get_stock_status, axis=1)

    # Чистим технические колонки для Листа 2
    sheet2_full = merged.drop(columns=['Артикул_поиск', 'Полный_код_ссылки', 'В_наличии'], errors='ignore')

    # Лист 1: Только успех (Найдено + В наличии + Цена есть)
    sheet1_ready = sheet2_full[
        (sheet2_full['Найдено у партнера'] == '+') &
        (sheet2_full['Наличие у партнера'] == '+') &
        (sheet2_full['Цена'].notna())
        ].copy()
    sheet1_ready = sheet1_ready.drop(columns=['Найдено у партнера', 'Наличие у партнера'])

    # 4. Сохранение
    try:
        with pd.ExcelWriter(path_output, engine='openpyxl') as writer:
            sheet1_ready.to_excel(writer, sheet_name='Готово к импорту', index=False)
            sheet2_full.to_excel(writer, sheet_name='Полный отчет', index=False)

        print("-" * 30)
        print(f"ГОТОВО!")
        print(f"Файл: {path_output}")
        print(f"Всего товаров в вашем списке: {len(sheet2_full)}")
        print(f"Из них готовы к импорту (в наличии): {len(sheet1_ready)}")
    except Exception as e:
        print(f"Ошибка сохранения: {e}")


if __name__ == "__main__":
    main()