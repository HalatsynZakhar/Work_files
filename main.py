"""
Скрипт автоматического сбора цен и статусов наличия из Docker (Changedetection.io)
и формирования отчетов сопоставления цен для Хорошоп.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

# =================================================================
# НАСТРОЙКИ ПУТЕЙ И ПАРАМЕТРОВ (ЛОКАЛЬНО В ПРОЕКТЕ)
# =================================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Внутренние папки проекта
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

EXCEL_INPUT_FILE = "articles.xlsm"
EXCEL_OUTPUT_FILE = "ИТОГОВЫЙ_ОТЧЕТ.xlsx"
EXCEL_FULL_OUTPUT_FILE = "ПОЛНАЯ_ТАБЛИЦА_МОНИТОРИНГА.xlsx"

# Внешняя папка (для синхронизации копии, если папка существует)
EXTERNAL_BACKUP_DIR = r"C:\Users\ABM\Desktop\Робота\Звіти керівництву\27 Подтягивая цен за мониторингом на Хорошоп"

CONTAINER_NAMES = [
    "changedetectionio-changedetection-1",
    "changedetection",
    "changedetectionio_changedetection_1"
]
REMOTE_JSON_PATH = "/datastore/url-watches.json"
BRAND_NAMES = {'road rippers', 'syma', 'nikko', 'revolt', 'machine maker'}


# =================================================================
# РАБОТА С DOCKER
# =================================================================

def find_running_container():
    """Находит имя активного контейнера changedetection"""
    try:
        cmd = ["docker", "ps", "--filter", "ancestor=dgtlmoon/changedetection.io", "--format", "{{.Names}}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        containers = [c.strip() for c in result.stdout.splitlines() if c.strip()]
        if containers:
            return containers[0]

        cmd = ["docker", "ps", "--filter", "name=changedetection", "--format", "{{.Names}}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        containers = [c.strip() for c in result.stdout.splitlines() if c.strip()]
        if containers:
            filtered = [c for c in containers if "selenium" not in c.lower()]
            if filtered:
                return filtered[0]

        for name in CONTAINER_NAMES:
            check_cmd = ["docker", "inspect", "-f", "{{.State.Running}}", name]
            res = subprocess.run(check_cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip() == "true":
                return name
    except Exception as e:
        print(f"Ошибка при поиске контейнеров Docker: {e}")

    return None


PERSONAL_TAGS = {'личное', 'личные', 'personal', 'private'}


def extract_data_from_docker(container_name):
    """Извлекает и парсит активные watches напрямую из Docker контейнера"""
    print(f"-> Чтение данных из контейнера '{container_name}'...")
    # 1. Приоритет: прямое чтение актуальных /datastore/*/watch.json и tag.json
    try:
        script = """
import os, json, glob
datastore = "/datastore"
watches = {}
for p in glob.glob(os.path.join(datastore, "*", "watch.json")):
    uuid = os.path.basename(os.path.dirname(p))
    try:
        with open(p, "r", encoding="utf-8") as f:
            watches[uuid] = json.load(f)
    except Exception:
        pass
tags = {}
for p in glob.glob(os.path.join(datastore, "*", "tag.json")):
    uuid = os.path.basename(os.path.dirname(p))
    try:
        with open(p, "r", encoding="utf-8") as f:
            tags[uuid] = json.load(f)
    except Exception:
        pass
settings = {}
cd_json = os.path.join(datastore, "changedetection.json")
if os.path.exists(cd_json):
    try:
        with open(cd_json, "r", encoding="utf-8") as f:
            settings = json.load(f).get("settings", {})
    except Exception:
        pass
if "application" not in settings:
    settings["application"] = {}
settings["application"]["tags"] = tags
print(json.dumps({"watching": watches, "settings": settings}, ensure_ascii=False))
"""
        cmd = ["docker", "exec", container_name, "python3", "-c", script]
        result = subprocess.run(cmd, capture_output=True, check=True)
        raw_json = result.stdout.decode('utf-8', errors='ignore')
        data = json.loads(raw_json)
        if data and data.get("watching"):
            return data
    except Exception:
        pass

    # 2. Fallback: legacy url-watches.json
    try:
        cmd = ["docker", "exec", container_name, "cat", REMOTE_JSON_PATH]
        result = subprocess.run(cmd, capture_output=True, check=True)
        raw_json = result.stdout.decode('utf-8', errors='ignore')
        data = json.loads(raw_json)
        return data
    except subprocess.CalledProcessError as e:
        print(f"!!! Ошибка выполнения команды docker exec: {e.stderr.decode('utf-8', errors='ignore')}")
    except json.JSONDecodeError as e:
        print(f"!!! Ошибка парсинга JSON: {e}")
    except Exception as e:
        print(f"!!! Непредвиденная ошибка получения данных из Docker: {e}")
    return None


# =================================================================
# ОБРАБОТКА ДАННЫХ ИЗ CHANGEDETECTION
# =================================================================

def format_timestamp(ts):
    """Преобразует unix timestamp в читаемую строку даты и времени"""
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(ts)


def extract_article_info(url, title=""):
    """Извлекает артикул из URL или названия"""
    article_match = re.search(r'/([^/]+)\.html', url)
    raw_article = article_match.group(1) if article_match else ""
    art_from_url = raw_article.split('-')[-1].strip().upper() if raw_article else ""

    art_from_title = ""
    if title:
        parts = title.strip().split()
        if parts:
            art_from_title = parts[0].upper()

    return raw_article, art_from_url, art_from_title


def parse_watches(data, chosen_tag_id=None):
    """
    Преобразует JSON-данные Changedetection в структурированный список товаров
    с поддержкой фильтрации по выбранному магазину/тегу.
    """
    watching = data.get('watching', {})
    tags_dict = {
        k: v.get('title', k)
        for k, v in data.get('settings', {}).get('application', {}).get('tags', {}).items()
    }

    records = []
    for uuid, w in watching.items():
        processor = w.get('processor')
        restock = w.get('restock') or {}
        if processor != 'restock_diff' and not restock:
            continue

        w_tag_ids = w.get('tags', [])
        if chosen_tag_id and chosen_tag_id not in w_tag_ids:
            continue

        url = w.get('url', '')
        title = (w.get('title') or '').strip()
        price = restock.get('price')
        in_stock = bool(restock.get('in_stock', False))
        currency = restock.get('currency') or 'UAH'

        raw_article, art_from_url, art_from_title = extract_article_info(url, title)

        tag_names = [tags_dict.get(t, t) for t in w_tag_ids]
        stores = [t for t in tag_names if t.lower() not in BRAND_NAMES and t.lower() not in PERSONAL_TAGS]
        brands = [t for t in tag_names if t.lower() in BRAND_NAMES]

        last_checked = format_timestamp(w.get('last_checked'))

        records.append({
            'uuid': uuid,
            'url': url,
            'title': title,
            'title_upper': title.upper(),
            'raw_article': raw_article.upper(),
            'art_from_url': art_from_url,
            'art_from_title': art_from_title,
            'price': price,
            'currency': currency,
            'in_stock': in_stock,
            'store': ", ".join(stores) if stores else "Не указан",
            'brand': ", ".join(brands) if brands else "",
            'last_checked': last_checked,
            'tags': tag_names
        })

    return pd.DataFrame(records)


def extract_full_tracker_dataframe(data):
    """
    Создает полную таблицу ВСЕХ товаров из Changedetection со всеми деталями
    (независимо от того, сопоставлены они с вашим файлом артикулов или нет).
    """
    watching = data.get('watching', {})
    tags_dict = {
        k: v.get('title', k)
        for k, v in data.get('settings', {}).get('application', {}).get('tags', {}).items()
    }

    all_rows = []
    for uuid, w in watching.items():
        if w.get('processor') != 'restock_diff' and not w.get('restock'):
            continue

        url = w.get('url', '')
        title = (w.get('title') or '').strip()
        restock = w.get('restock') or {}
        price = restock.get('price')
        in_stock = bool(restock.get('in_stock', False))
        currency = restock.get('currency') or 'UAH'

        raw_article, art_from_url, art_from_title = extract_article_info(url, title)
        art_display = art_from_url if art_from_url else art_from_title

        tag_names = [tags_dict.get(t, t) for t in w.get('tags', [])]
        stores = [t for t in tag_names if t.lower() not in BRAND_NAMES]
        brands = [t for t in tag_names if t.lower() in BRAND_NAMES]

        last_checked = format_timestamp(w.get('last_checked'))
        status_code = w.get('last_check_status') or 200

        all_rows.append({
            'Артикул': art_display,
            'Название товара': title,
            'Магазин': ", ".join(stores) if stores else "Не указан",
            'Бренд': ", ".join(brands) if brands else "",
            'Цена': price,
            'Валюта': currency,
            'В наличии': 'Да' if in_stock else 'Нет',
            'Ссылка на товар': url,
            'Дата последней проверки': last_checked,
            'Статус ответа': f"Код {status_code}" if status_code else ""
        })

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df.sort_values(by=['Магазин', 'Название товара'])
    return df


def select_store_tag(data):
    """Интерактивное меню выбора магазина/тега для фильтрации"""
    tags_dict = data.get('settings', {}).get('application', {}).get('tags', {})
    watching = data.get('watching', {})

    tag_counts = {}
    for w in watching.values():
        if w.get('processor') == 'restock_diff' or w.get('restock'):
            for t in w.get('tags', []):
                tag_counts[t] = tag_counts.get(t, 0) + 1

    if not tag_counts:
        return None, "Все товары"

    stores_tags = []
    brands_tags = []

    for t, count in tag_counts.items():
        name = tags_dict.get(t, {}).get('title', t)
        if name.lower() in BRAND_NAMES:
            brands_tags.append((t, name, count))
        else:
            stores_tags.append((t, name, count))

    stores_tags.sort(key=lambda x: -x[2])
    brands_tags.sort(key=lambda x: -x[2])

    ordered_tags = stores_tags + brands_tags

    default_idx = 1
    for idx, (t, name, _) in enumerate(ordered_tags, start=1):
        if "будинок" in name.lower():
            default_idx = idx
            break

    print("\n" + "=" * 60)
    print("ВЫБОР ФИЛЬТРА ДЛЯ ВЫГРУЗКИ ЦЕН:")
    print("=" * 60)
    print(" 0 : [Все магазины / Без фильтра]")

    print("\n--- МАГАЗИНЫ-ПАРТНЕРЫ ---")
    tag_list_indexed = []
    current_section = "stores"

    for idx, (t, name, count) in enumerate(ordered_tags, start=1):
        if current_section == "stores" and name.lower() in BRAND_NAMES:
            current_section = "brands"
            print("\n--- БРЕНДЫ (фильтр по марке товара) ---")

        is_def = " (ПО УМОЛЧАНИЮ)" if idx == default_idx else ""
        print(f"{idx:2d} : {name:<25} ({count} товаров){is_def}")
        tag_list_indexed.append((t, name))

    prompt = f"\nВведите номер фильтра [Нажмите Enter для выбора '{tag_list_indexed[default_idx-1][1]}']: "
    user_choice = input(prompt).strip()

    if not user_choice:
        chosen_tag_id, chosen_name = tag_list_indexed[default_idx - 1]
        print(f"-> Выбран магазин: {chosen_name}")
        return chosen_tag_id, chosen_name

    if user_choice == "0":
        print("-> Выгрузка по ВСЕМ магазинам без фильтрации")
        return None, "Все магазины"

    if user_choice.isdigit():
        num = int(user_choice)
        if 1 <= num <= len(tag_list_indexed):
            chosen_tag_id, chosen_name = tag_list_indexed[num - 1]
            print(f"-> Выбран: {chosen_name}")
            return chosen_tag_id, chosen_name

    chosen_tag_id, chosen_name = tag_list_indexed[default_idx - 1]
    print(f"-> Некорректный ввод. Выбран по умолчанию: {chosen_name}")
    return chosen_tag_id, chosen_name


# =================================================================
# ОСНОВНОЙ АЛГОРИТМ СОПОСТАВЛЕНИЯ
# =================================================================

def match_articles(df_my_list, df_watches, art_column):
    """
    Выполняет расширенное сопоставление товаров по артикулу:
    1. Точное совпадение по артикулу из URL (...-20155.html -> 20155)
    2. Поиск артикула в заголовке товара (title), например: 'S107H RED Розетка' -> 'S107H RED'
    3. Поиск подстроки артикула в полном коде/URL
    """
    merged = df_my_list.copy()
    merged['Цена'] = None
    merged['В_наличии'] = False
    merged['Найдено'] = False
    merged['Товар_партнера'] = ""
    merged['Ссылка_партнера'] = ""
    merged['Магазин'] = ""
    merged['Бренд'] = ""
    merged['Валюта'] = ""
    merged['Дата_проверки'] = ""

    if df_watches.empty:
        merged['Найдено у партнера'] = ''
        merged['Наличие у партнера'] = ''
        return merged

    watches_list = df_watches.to_dict('records')

    for idx, row in merged.iterrows():
        my_art = str(row[art_column]).strip().upper()
        if not my_art or my_art == 'NAN':
            continue

        matched_watch = None

        # Шаг 1: Точное совпадение с артикулом из URL
        for w in watches_list:
            if w['art_from_url'] == my_art:
                matched_watch = w
                break

        # Шаг 2: Поиск артикула в заголовке товара (title)
        if not matched_watch:
            pattern = re.compile(r'\b' + re.escape(my_art) + r'\b')
            for w in watches_list:
                if pattern.search(w['title_upper']):
                    matched_watch = w
                    break

        # Шаг 3: Поиск вхождения в название/ссылку (как в исходном скрипте)
        if not matched_watch:
            for w in watches_list:
                if my_art in w['raw_article'] or my_art in w['url'].upper():
                    matched_watch = w
                    break

        if matched_watch:
            merged.at[idx, 'Цена'] = matched_watch['price']
            merged.at[idx, 'В_наличии'] = matched_watch['in_stock']
            merged.at[idx, 'Найдено'] = True
            merged.at[idx, 'Товар_партнера'] = matched_watch['title']
            merged.at[idx, 'Ссылка_партнера'] = matched_watch['url']
            merged.at[idx, 'Магазин'] = matched_watch['store']
            merged.at[idx, 'Бренд'] = matched_watch['brand']
            merged.at[idx, 'Валюта'] = matched_watch['currency']
            merged.at[idx, 'Дата_проверки'] = matched_watch['last_checked']

    # Статусы для Хорошоп
    merged['Найдено у партнера'] = merged['Найдено'].apply(lambda x: '+' if x else '')
    merged['Наличие у партнера'] = merged.apply(
        lambda r: ('+' if r['В_наличии'] else '-') if r['Найдено'] else '',
        axis=1
    )

    return merged


def auto_fit_excel_columns(excel_path):
    """Настраивает авто-ширину колонок для всех листов Excel файла"""
    try:
        wb = openpyxl.load_workbook(excel_path)
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                for cell in col:
                    val = str(cell.value or '')
                    if len(val) > max_len:
                        max_len = len(val)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 65)
        wb.save(excel_path)
    except Exception as e:
        print(f"Примечание: авто-ширина колонок не применена ({e})")


# =================================================================
# ТОЧКА ВХОДА
# =================================================================

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 65)
    print("   СБОР И СОПОСТАВЛЕНИЕ ЦЕН ХОРОШОП ИЗ DOCKER (CHANGEDETECTION)   ")
    print("=" * 65)

    # 1. Поиск Docker контейнера
    container_name = find_running_container()
    if not container_name:
        print("\n[ОШИБКА] Контейнер changedetection.io не найден или не запущен в Docker!")
        print("Пожалуйста, убедитесь, что Docker Desktop запущен, и выполните:")
        print("  cd C:\\projects\\changedetection.io && docker-compose up -d")
        input("\nНажмите Enter для выхода...")
        return

    print(f"✓ Найден активный контейнер: {container_name}")

    # 2. Извлечение url-watches.json
    docker_data = extract_data_from_docker(container_name)
    if not docker_data:
        print("\n[ОШИБКА] Не удалось прочитать данные трекера из Docker.")
        input("\nНажмите Enter для выхода...")
        return

    # 3. Выбор магазина для сопоставления
    chosen_tag_id, store_name = select_store_tag(docker_data)

    # 4. Парсинг товаров из Changedetection
    df_watches = parse_watches(docker_data, chosen_tag_id)
    print(f"✓ Загружено товаров для сопоставления: {len(df_watches)}")

    # 5. Извлечение всей базы трекера для полной таблицы
    df_full_tracker = extract_full_tracker_dataframe(docker_data)
    print(f"✓ Загружено товаров всей базы трекера Docker: {len(df_full_tracker)}")

    # 6. Загрузка Excel файла с вашими артикулами
    path_xlsx = os.path.join(BASE_DIR, EXCEL_INPUT_FILE)
    path_output = os.path.join(BASE_DIR, EXCEL_OUTPUT_FILE)
    path_full_output = os.path.join(BASE_DIR, EXCEL_FULL_OUTPUT_FILE)

    if not os.path.exists(path_xlsx):
        print(f"\n[ОШИБКА] Файл артикулов не найден: {path_xlsx}")
        input("\nНажмите Enter для выхода...")
        return

    try:
        df_my_list = pd.read_excel(path_xlsx, sheet_name=0, engine='openpyxl')
        print(f"✓ Загружен файл с артикулами: {EXCEL_INPUT_FILE} ({len(df_my_list)} позиций)")
    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка чтения Excel: {e}")
        input("\nНажмите Enter для выхода...")
        return

    # Выбор колонки артикулов
    print("\nДоступные колонки в Excel:")
    for i, col in enumerate(df_my_list.columns):
        print(f"{i} : {col}")

    col_prompt = f"\nВведите ИМЯ или НОМЕР колонки с артикулами [Enter для '{df_my_list.columns[0]}']: "
    user_input = input(col_prompt).strip()

    if not user_input:
        art_column = df_my_list.columns[0]
    elif user_input.isdigit() and int(user_input) < len(df_my_list.columns):
        art_column = df_my_list.columns[int(user_input)]
    else:
        art_column = user_input if user_input in df_my_list.columns else df_my_list.columns[0]

    print(f"-> Используется колонка артикула: '{art_column}'")

    # 7. Сопоставление
    print("\n-> Сопоставление артикулов и цен...")
    merged = match_articles(df_my_list, df_watches, art_column)

    # 8. Формирование листов

    # Лист 1: Только готовые к импорту (Найдено + В наличии + Цена есть)
    sheet1_ready = merged[
        (merged['Найдено у партнера'] == '+') &
        (merged['Наличие у партнера'] == '+') &
        (merged['Цена'].notna())
    ].copy()
    sheet1_cols = list(df_my_list.columns) + ['Цена']
    sheet1_ready = sheet1_ready[[c for c in sheet1_cols if c in sheet1_ready.columns]]

    # Лист 2: Полный отчет (базовый, как в старой версии)
    sheet2_cols = list(df_my_list.columns) + ['Цена', 'Найдено у партнера', 'Наличие у партнера']
    sheet2_basic = merged[[c for c in sheet2_cols if c in merged.columns]].copy()

    # Лист 3: Полная информация (Детальное сопоставление со всеми ссылками, названиями, магазинами)
    sheet3_cols = list(df_my_list.columns) + [
        'Цена', 'Валюта', 'Найдено у партнера', 'Наличие у партнера',
        'Товар_партнера', 'Магазин', 'Бренд', 'Ссылка_партнера', 'Дата_проверки'
    ]
    sheet3_detailed = merged[[c for c in sheet3_cols if c in merged.columns]].copy()
    sheet3_detailed.rename(columns={
        'Товар_партнера': 'Название у партнера',
        'Ссылка_партнера': 'Ссылка на товар',
        'Дата_проверки': 'Дата проверки'
    }, inplace=True)

def save_excel_safely(writer_callback, target_path, label):
    """
    Безопасно сохраняет Excel файл. Если файл открыт в Excel (PermissionError),
    автоматически сохраняет копию с временным суффиксом.
    """
    try:
        with pd.ExcelWriter(target_path, engine='openpyxl') as writer:
            writer_callback(writer)
        auto_fit_excel_columns(target_path)
        return target_path, False
    except PermissionError:
        now_str = datetime.datetime.now().strftime("%H%M%S")
        dir_name = os.path.dirname(target_path)
        base_name, ext = os.path.splitext(os.path.basename(target_path))
        fallback_path = os.path.join(dir_name, f"{base_name}_{now_str}{ext}")
        try:
            with pd.ExcelWriter(fallback_path, engine='openpyxl') as writer:
                writer_callback(writer)
            auto_fit_excel_columns(fallback_path)
            print(f"\n⚠️  [ВНИМАНИЕ] Файл '{os.path.basename(target_path)}' сейчас открыт в Excel!")
            print(f"    Чтобы не потерять данные, отчет сохранен в файл: {os.path.basename(fallback_path)}")
            return fallback_path, True
        except Exception as e:
            print(f"\n[ОШИБКА] Не удалось сохранить файл: {e}")
            return None, False
    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка при сохранении {label}: {e}")
        return None, False


# =================================================================
# ТОЧКА ВХОДА
# =================================================================

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 65)
    print("   СБОР И СОПОСТАВЛЕНИЕ ЦЕН ХОРОШОП ИЗ DOCKER (CHANGEDETECTION)   ")
    print("=" * 65)

    # 1. Поиск Docker контейнера
    container_name = find_running_container()
    if not container_name:
        print("\n[ОШИБКА] Контейнер changedetection.io не найден или не запущен в Docker!")
        print("Пожалуйста, убедитесь, что Docker Desktop запущен, и выполните:")
        print("  cd C:\\projects\\changedetection.io && docker-compose up -d")
        input("\nНажмите Enter для выхода...")
        return

    print(f"✓ Найден активный контейнер: {container_name}")

    # 2. Извлечение url-watches.json
    docker_data = extract_data_from_docker(container_name)
    if not docker_data:
        print("\n[ОШИБКА] Не удалось прочитать данные трекера из Docker.")
        input("\nНажмите Enter для выхода...")
        return

    # 3. Выбор магазина для сопоставления
    chosen_tag_id, store_name = select_store_tag(docker_data)

    # 4. Парсинг товаров из Changedetection
    df_watches = parse_watches(docker_data, chosen_tag_id)
    print(f"✓ Загружено товаров для сопоставления: {len(df_watches)}")

    # 5. Извлечение всей базы трекера для полной таблицы
    df_full_tracker = extract_full_tracker_dataframe(docker_data)
    print(f"✓ Загружено товаров всей базы трекера Docker: {len(df_full_tracker)}")

    # 6. Загрузка Excel файла с вашими артикулами
    possible_input_paths = [
        os.path.join(INPUT_DIR, EXCEL_INPUT_FILE),
        os.path.join(PROJECT_ROOT, EXCEL_INPUT_FILE),
        os.path.join(DATA_DIR, EXCEL_INPUT_FILE),
        os.path.join(EXTERNAL_BACKUP_DIR, EXCEL_INPUT_FILE),
    ]

    path_xlsx = None
    for p in possible_input_paths:
        if os.path.exists(p):
            path_xlsx = p
            break

    if not path_xlsx:
        print(f"\n[ОШИБКА] Файл артикулов '{EXCEL_INPUT_FILE}' не найден!")
        print(f"Пожалуйста, положите файл в папку: {INPUT_DIR}")
        input("\nНажмите Enter для выхода...")
        return

    path_output = os.path.join(OUTPUT_DIR, EXCEL_OUTPUT_FILE)
    path_full_output = os.path.join(OUTPUT_DIR, EXCEL_FULL_OUTPUT_FILE)

    try:
        df_my_list = pd.read_excel(path_xlsx, sheet_name=0, engine='openpyxl')
        print(f"✓ Загружен входной файл: {os.path.relpath(path_xlsx, PROJECT_ROOT)} ({len(df_my_list)} позиций)")
    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка чтения Excel: {e}")
        input("\nНажмите Enter для выхода...")
        return

    # Выбор колонки артикулов
    print("\nДоступные колонки в Excel:")
    for i, col in enumerate(df_my_list.columns):
        print(f"{i} : {col}")

    col_prompt = f"\nВведите ИМЯ или НОМЕР колонки с артикулами [Enter для '{df_my_list.columns[0]}']: "
    user_input = input(col_prompt).strip()

    if not user_input:
        art_column = df_my_list.columns[0]
    elif user_input.isdigit() and int(user_input) < len(df_my_list.columns):
        art_column = df_my_list.columns[int(user_input)]
    else:
        art_column = user_input if user_input in df_my_list.columns else df_my_list.columns[0]

    print(f"-> Используется колонка артикула: '{art_column}'")

    # 7. Сопоставление
    print("\n-> Сопоставление артикулов и цен...")
    merged = match_articles(df_my_list, df_watches, art_column)

    # 8. Формирование листов

    # Лист 1: Только готовые к импорту (Найдено + В наличии + Цена есть)
    sheet1_ready = merged[
        (merged['Найдено у партнера'] == '+') &
        (merged['Наличие у партнера'] == '+') &
        (merged['Цена'].notna())
    ].copy()
    sheet1_cols = list(df_my_list.columns) + ['Цена']
    sheet1_ready = sheet1_ready[[c for c in sheet1_cols if c in sheet1_ready.columns]]

    # Лист 2: Полный отчет (базовый, как в старой версии)
    sheet2_cols = list(df_my_list.columns) + ['Цена', 'Найдено у партнера', 'Наличие у партнера']
    sheet2_basic = merged[[c for c in sheet2_cols if c in merged.columns]].copy()

    # Лист 3: Полная информация (Детальное сопоставление со всеми ссылками, названиями, магазинами)
    sheet3_cols = list(df_my_list.columns) + [
        'Цена', 'Валюта', 'Найдено у партнера', 'Наличие у партнера',
        'Товар_партнера', 'Магазин', 'Бренд', 'Ссылка_партнера', 'Дата_проверки'
    ]
    sheet3_detailed = merged[[c for c in sheet3_cols if c in merged.columns]].copy()
    sheet3_detailed.rename(columns={
        'Товар_партнера': 'Название у партнера',
        'Ссылка_партнера': 'Ссылка на товар',
        'Дата_проверки': 'Дата проверки'
    }, inplace=True)

    # 9. Сохранение файла ИТОГОВЫЙ_ОТЧЕТ.xlsx
    def write_main_report(writer):
        sheet1_ready.to_excel(writer, sheet_name='Готово к импорту', index=False)
        sheet2_basic.to_excel(writer, sheet_name='Полный отчет', index=False)
        sheet3_detailed.to_excel(writer, sheet_name='Полная информация', index=False)
        df_full_tracker.to_excel(writer, sheet_name='База трекера (все товары)', index=False)

    saved_path_1, is_fb_1 = save_excel_safely(write_main_report, path_output, "ИТОГОВЫЙ_ОТЧЕТ.xlsx")
    if saved_path_1:
        print("\n" + "=" * 65)
        print("   УСПЕШНО СОХРАНЕН ИТОГОВЫЙ ОТЧЕТ!   ")
        print("=" * 65)
        print(f"Файл: {saved_path_1}")
        print(f"  Лист 1: 'Готово к импорту'         ({len(sheet1_ready)} позиций)")
        print(f"  Лист 2: 'Полный отчет'              ({len(sheet2_basic)} позиций)")
        print(f"  Лист 3: 'Полная информация'         ({len(sheet3_detailed)} позиций, со ссылками и магазинами)")
        print(f"  Лист 4: 'База трекера (все товары)' ({len(df_full_tracker)} позиций из Docker)")

    # 10. Сохранение отдельного файла ПОЛНАЯ_ТАБЛИЦА_МОНИТОРИНГА.xlsx
    def write_full_table(writer):
        sheet3_detailed.to_excel(writer, sheet_name='Детальное сопоставление', index=False)
        df_full_tracker.to_excel(writer, sheet_name='Вся база трекера Docker', index=False)
        sheet1_ready.to_excel(writer, sheet_name='Готово к импорту', index=False)

    saved_path_2, is_fb_2 = save_excel_safely(write_full_table, path_full_output, "ПОЛНАЯ_ТАБЛИЦА_МОНИТОРИНГА.xlsx")
    if saved_path_2:
        print("-" * 65)
        print("   СОХРАНЕНА ДОПОЛНИТЕЛЬНАЯ ПОЛНАЯ ТАБЛИЦА!   ")
        print("-" * 65)
        print(f"Файл: {saved_path_2}")
        print(f"  Лист 1: 'Детальное сопоставление'   (артикулы + ссылки + магазины + наличие)")
        print(f"  Лист 2: 'Вся база трекера Docker'   (все {len(df_full_tracker)} товаров из Docker)")
        print(f"  Лист 3: 'Готово к импорту'         (готовые цены для импорта)")
        print("=" * 65)

    # 11. Синхронизация копии во внешнюю папку (если она существует)
    if os.path.exists(EXTERNAL_BACKUP_DIR):
        try:
            import shutil
            if saved_path_1 and os.path.exists(saved_path_1):
                shutil.copy2(saved_path_1, os.path.join(EXTERNAL_BACKUP_DIR, EXCEL_OUTPUT_FILE))
            if saved_path_2 and os.path.exists(saved_path_2):
                shutil.copy2(saved_path_2, os.path.join(EXTERNAL_BACKUP_DIR, EXCEL_FULL_OUTPUT_FILE))
            print(f"✓ Копия отчетов также синхронизирована в: {EXTERNAL_BACKUP_DIR}")
        except Exception:
            pass

    input("\nНажмите Enter для завершения...")


if __name__ == "__main__":
    main()
