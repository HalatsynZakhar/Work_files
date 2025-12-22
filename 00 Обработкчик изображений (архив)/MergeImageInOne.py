import math
import os
import glob
from PIL import Image, ImageChops, ImageOps

# --- Налаштування ---
# !!! ВАЖЛИВО: Вкажіть тут шлях до папки з вашими зображеннями !!!
SOURCE_DIRECTORY = r"C:\Users\ABM\Desktop\MM"

# --- Нове налаштування: Кількість стовпців ---
# Встановіть бажану кількість стовпців.
# Якщо 0, кількість стовпців буде розрахована автоматично (намагаючись зробити квадрат).
# Якщо більше 0 (наприклад, 3), буде використано саме ця кількість стовпців.
FORCED_GRID_COLS = 0

# --- Константи ---
DEFAULT_WHITE_TOLERANCE = 10
DEFAULT_SPACING_PERCENT = 10
DEFAULT_OUTPUT_FILENAME = "combined_output.jpg"
DEFAULT_OUTPUT_QUALITY = 95
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')
# --- ---

def remove_white_background(img, tolerance=DEFAULT_WHITE_TOLERANCE):
    """Видаляє майже білий фон з зображення RGBA."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    datas = img.getdata()
    newData = []
    cutoff = 255 - tolerance
    for item in datas:
        if item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff:
            newData.append((item[0], item[1], item[2], 0))
        else:
            newData.append(item)

    img.putdata(newData)
    return img

def crop_transparent_border(img):
    """Обрізає порожній (прозорий) простір навколо зображення."""
    # Переконуємося, що працюємо з копією для конвертації, якщо потрібно
    temp_img = img if img.mode == 'RGBA' else img.convert('RGBA')
    bg = Image.new('RGBA', temp_img.size, (0,0,0,0))
    try:
        # Використовуємо ImageChops.difference для більш надійного визначення меж
        diff = ImageChops.difference(temp_img, bg)
        # Використовуємо альфа-канал різниці для bbox, якщо він є
        if diff.mode == 'RGBA':
            bbox = diff.split()[-1].getbbox() # Беремо bbox з альфа-каналу
            if not bbox: # Якщо альфа-канал порожній, спробуємо весь diff
                bbox = diff.getbbox()
        else: # Якщо різниця не RGBA (малоймовірно, але можливо)
            bbox = diff.getbbox()

    except ValueError:
        bbox = None # Якщо зображення повністю збігається з фоном

    if bbox:
        # Обрізаємо оригінальне зображення (img), а не тимчасове (temp_img)
        return img.crop(bbox)
    else:
        # print("Попередження: Не вдалося знайти межі об'єкта. Пропуск обрізки.")
        return img # Повертаємо те, що є

def process_image(image_path, white_tolerance):
    """Завантажує, видаляє фон та обрізає одне зображення."""
    try:
        img = Image.open(image_path)
        img = img.convert("RGBA") # Завжди конвертуємо в RGBA на початку

        img_no_bg = remove_white_background(img, white_tolerance)
        img_cropped = crop_transparent_border(img_no_bg)

        # Перевірка, чи щось залишилось після обрізки
        if img_cropped is None or not img_cropped.getbbox():
             # print(f"Попередження: Зображення '{os.path.basename(image_path)}' стало порожнім.")
             return None

        return img_cropped

    except FileNotFoundError:
        print(f"Помилка: Файл не знайдено '{image_path}'")
        return None
    except Exception as e:
        print(f"Помилка обробки файлу {os.path.basename(image_path)}: {e}")
        return None

def combine_images(image_paths, output_path, forced_cols=0, spacing_percent=DEFAULT_SPACING_PERCENT, white_tolerance=DEFAULT_WHITE_TOLERANCE, quality=DEFAULT_OUTPUT_QUALITY):
    """Обробляє та об'єднує зображення у сітку."""
    if not image_paths:
        print("У вказаній папці не знайдено підтримуваних зображень.")
        return

    processed_images = []
    print("Обробка зображень...")
    for path in image_paths:
        if os.path.basename(path) == os.path.basename(output_path):
            #print(f"Пропуск файлу '{os.path.basename(path)}' (схоже на попередній результат).")
            continue

        print(f" - Обробка: {os.path.basename(path)}")
        processed = process_image(path, white_tolerance)
        if processed:
            processed_images.append(processed)
        else:
            print(f"   ! Пропущено або не вдалося обробити.")

    num_images = len(processed_images)
    if num_images == 0:
        print("Немає успішно оброблених зображень для об'єднання.")
        return

    print(f"Успішно оброблено: {num_images} зображень.")

    # --- Логіка визначення розмірів сітки ---
    if forced_cols > 0:
        grid_cols = forced_cols
        grid_rows = math.ceil(num_images / grid_cols)
        print(f"Використання фіксованої кількості стовпців: {grid_cols}")
    else:
        # Автоматичний розрахунок (близько до квадрата)
        grid_cols = math.ceil(math.sqrt(num_images))
        grid_rows = math.ceil(num_images / grid_cols)
        print("Автоматичний розрахунок розмірів сітки.")
    # --- ---

    max_w = 0
    max_h = 0
    for img in processed_images:
        if img and hasattr(img, 'width') and hasattr(img, 'height'):
            max_w = max(max_w, img.width)
            max_h = max(max_h, img.height)

    if max_w == 0 or max_h == 0:
        print("Помилка: Не вдалося визначити розміри оброблених зображень.")
        return

    h_spacing = int(max_w * (spacing_percent / 100.0))
    v_spacing = int(max_h * (spacing_percent / 100.0))

    canvas_width = (grid_cols * max_w) + ((grid_cols + 1) * h_spacing)
    canvas_height = (grid_rows * max_h) + ((grid_rows + 1) * v_spacing)

    canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
    print(f"Створено холст: {canvas_width}x{canvas_height}px")
    print(f"Розмір комірки: {max_w}x{max_h}px, Відступи: H={h_spacing}px, V={v_spacing}px")
    print(f"Сітка: {grid_rows}x{grid_cols}")

    current_image_index = 0
    for r in range(grid_rows):
        # Визначаємо, скільки елементів реально буде в цьому ряду
        start_index_in_row = r * grid_cols
        items_in_this_row = min(grid_cols, num_images - start_index_in_row)

        extra_offset_x_for_last_row = 0
        # Розраховуємо зміщення ТІЛЬКИ якщо це ОСТАННІЙ ряд І він НЕПОВНИЙ
        if r == grid_rows - 1 and items_in_this_row < grid_cols:
            empty_slots = grid_cols - items_in_this_row
            extra_offset_x_for_last_row = (empty_slots * (max_w + h_spacing)) // 2

        for c in range(items_in_this_row): # Ітеруємо тільки по реальних елементах ряду
            if current_image_index < num_images: # Додаткова перевірка
                img = processed_images[current_image_index]
                if img is None:
                     current_image_index += 1
                     continue # Пропускаємо, якщо зображення було None

                # Розраховуємо позицію стовпця `c`
                cell_x = h_spacing + c * (max_w + h_spacing) + extra_offset_x_for_last_row
                cell_y = v_spacing + r * (max_h + v_spacing)

                paste_offset_x = (max_w - img.width) // 2
                paste_offset_y = (max_h - img.height) // 2

                paste_x = cell_x + paste_offset_x
                paste_y = cell_y + paste_offset_y

                if img.mode != 'RGBA': # Малоймовірно після process_image, але про всяк випадок
                    img = img.convert('RGBA')
                # Використовуємо альфа-канал зображення як маску для коректної вставки прозорих пікселів
                canvas.paste(img, (paste_x, paste_y), img)

                current_image_index += 1
            else:
                 # Цього не повинно статись через зовнішню перевірку `items_in_this_row`
                 break

    print(f"Збереження результату у '{output_path}'...")
    try:
        if canvas.mode == 'RGBA':
             rgb_canvas = Image.new("RGB", canvas.size, (255, 255, 255))
             if len(canvas.split()) == 4:
                 rgb_canvas.paste(canvas, mask=canvas.split()[3])
             else:
                 rgb_canvas.paste(canvas)
             canvas_to_save = rgb_canvas
        else:
             canvas_to_save = canvas

        canvas_to_save.save(output_path, 'JPEG', quality=quality, optimize=True)
        print(f"Зображення успішно збережено в: {output_path}")
    except Exception as e:
        print(f"Помилка збереження файлу '{output_path}': {e}")

def run_processing():
    """Основна функція: знаходить файли, запускає об'єднання."""
    print(f"Пошук зображень у папці: {SOURCE_DIRECTORY}")

    if not os.path.isdir(SOURCE_DIRECTORY):
        print(f"Помилка: Папка '{SOURCE_DIRECTORY}' не знайдена.")
        print("Будь ласка, перевірте шлях у змінній SOURCE_DIRECTORY у скрипті.")
        return

    input_files = []
    for ext in SUPPORTED_EXTENSIONS:
        search_pattern = os.path.join(SOURCE_DIRECTORY, f"*{ext}")
        found_files = glob.glob(search_pattern)
        input_files.extend(found_files)

    if not input_files:
        print(f"У папці '{SOURCE_DIRECTORY}' не знайдено файлів із розширеннями: {', '.join(SUPPORTED_EXTENSIONS)}")
        return

    # Сортуємо знайдені файли за іменем для послідовного порядку
    input_files.sort()
    print(f"Знайдено {len(input_files)} потенційних зображень (відсортовано).")

    output_file_path = os.path.join(SOURCE_DIRECTORY, DEFAULT_OUTPUT_FILENAME)

    combine_images(
        image_paths=input_files,
        output_path=output_file_path,
        forced_cols=FORCED_GRID_COLS, # Передаємо нове налаштування
        spacing_percent=DEFAULT_SPACING_PERCENT,
        white_tolerance=DEFAULT_WHITE_TOLERANCE,
        quality=DEFAULT_OUTPUT_QUALITY
    )

if __name__ == "__main__":
    try:
        import PIL
    except ImportError:
        print("Помилка: Бібліотека Pillow не знайдена.")
        print("Будь ласка, встановіть її, виконавши команду:")
        print("pip install Pillow")
        exit()

    run_processing()
    print("Роботу завершено.")