import math
import os
import glob
from PIL import Image, ImageChops, ImageOps
import traceback # Для детальних помилок

# --- Налаштування ---
# !!! ВАЖЛИВО: Вкажіть тут шлях до папки з вашими зображеннями !!!
SOURCE_DIRECTORY = r"C:\Users\zakhar\Downloads\test2"

# --- Нове налаштування: Кількість стовпців ---
FORCED_GRID_COLS = 0 # 0 = авто, >0 = фіксована кількість стовпців

# --- Нові налаштування: Умовні поля ---
# Відступ в пікселях від краю для перевірки периметра на білий колір.
# Якщо 0, перевірка не виконується і поля НЕ додаються автоматично.
PERIMETER_CHECK_MARGIN_PIXELS = 0
# Відсоток полів, що додаються, ЯКЩО периметр білий (і margin > 0).
PADDING_PERCENT_IF_WHITE = 0

# --- Константи ---
DEFAULT_WHITE_TOLERANCE = 40 # Допуск для білого фону/периметра
DEFAULT_SPACING_PERCENT = 5 # Відсоток відступу *між* картинками на колажі
DEFAULT_OUTPUT_FILENAME = "combined_output.jpg"
DEFAULT_OUTPUT_QUALITY = 95
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp') # Додав webp
# --- ---

# --- Функції перевірки та додавання полів (з попередніх рішень) ---
def check_perimeter_is_white(img, tolerance, margin):
    """
    Перевіряє, чи всі пікселі по периметру зображення (з відступом margin)
    є білими (з урахуванням tolerance).

    Args:
        img (PIL.Image.Image): Вхідне зображення (перед обробкою).
        tolerance (int): Допуск для білого (0-255).
        margin (int): Відступ від краю в пікселях для перевірки.

    Returns:
        bool: True, якщо весь периметр в межах відступу білий, False інакше.
    """
    if margin <= 0:
        # print("  - Перевірка периметра: Відступ <= 0, перевірка не потрібна.")
        return False

    try:
        img_rgb = img.convert('RGB')
        width, height = img_rgb.size
        pixels = img_rgb.load()
    except Exception as e:
        print(f"  ! Помилка конвертації в RGB для перевірки периметра: {e}")
        return False

    if width < margin * 2 or height < margin * 2:
        # print(f"  - Перевірка периметра: Зображення ({width}x{height}) менше за подвійний відступ ({margin*2}). Перевірка всього зображення.")
        margin_w = min(width // 2, margin)
        margin_h = min(height // 2, margin)
        if margin_w == 0: margin_w = 1
        if margin_h == 0: margin_h = 1
    else:
        margin_w = margin
        margin_h = margin

    cutoff = 255 - tolerance

    # Перевірка верхніх рядків
    for y in range(margin_h):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff: return False
    # Перевірка нижніх рядків
    for y in range(height - margin_h, height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff: return False
    # Перевірка лівих стовпців
    for x in range(margin_w):
        for y in range(margin_h, height - margin_h):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff: return False
    # Перевірка правих стовпців
    for x in range(width - margin_w, width):
        for y in range(margin_h, height - margin_h):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff: return False

    # print("  - Перевірка периметра: Весь периметр білий.")
    return True

def add_padding(img, percent):
    """Додає прозорі поля навколо RGBA зображення."""
    if img is None or percent <= 0:
        return img

    width, height = img.size
    if width == 0 or height == 0:
        return img

    longest_side = max(width, height)
    padding_pixels = int(longest_side * (percent / 100.0))

    if padding_pixels == 0:
        # print("  - Додавання полів: Розрахований відступ = 0 пікселів.")
        return img

    new_width = width + 2 * padding_pixels
    new_height = height + 2 * padding_pixels
    padded_img = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
    paste_x = padding_pixels
    paste_y = padding_pixels
    padded_img.paste(img, (paste_x, paste_y), img if img.mode == 'RGBA' else None)
    # print(f"  - Додавання полів: Новий розмір {new_width}x{new_height}.")
    return padded_img
# --- ---

# --- Функції обробки зображення (модифіковані) ---
def remove_white_background(img, tolerance=DEFAULT_WHITE_TOLERANCE):
    """Видаляє майже білий фон з зображення RGBA."""
    # Переконуємося, що працюємо з RGBA
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    else:
        # Навіть якщо вже RGBA, краще працювати з копією, щоб putdata не змінила оригінал,
        # якщо він потрібен десь ще (хоча в поточному process_image це не критично)
        img = img.copy()

    datas = img.getdata()
    newData = []
    cutoff = 255 - tolerance
    for item in datas:
        # Перевіряємо RGB канали
        if item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff:
            # Якщо білий (з допуском), робимо прозорим (альфа=0)
            newData.append((item[0], item[1], item[2], 0))
        else:
            # Інакше зберігаємо піксель (з його можливою вихідною прозорістю)
            newData.append(item)

    img.putdata(newData)
    return img

def crop_transparent_border(img):
    """Обрізає порожній (прозорий) простір навколо зображення."""
    if img.mode != 'RGBA':
        # Цього не мало б бути, якщо remove_white_background відпрацював, але для безпеки
        img = img.convert('RGBA')

    try:
        # Використовуємо альфа-канал для визначення меж непрозорого контенту
        alpha = img.split()[-1]
        bbox = alpha.getbbox() # Знаходить (left, upper, right, lower)
    except (ValueError, IndexError):
         # Може статися, якщо альфа-канал порожній або його немає
         bbox = None

    if bbox:
        # Обрізаємо зображення за знайденими межами
        return img.crop(bbox)
    else:
        # print("  ! Попередження: Не вдалося знайти межі об'єкта (getbbox повернув None). Пропуск обрізки.")
        # Повертаємо зображення як є, щоб не втратити його зовсім, якщо воно було не повністю прозоре
        return img

def process_image(image_path, white_tolerance, perimeter_margin, padding_percent):
    """
    Завантажує, перевіряє периметр, видаляє фон, обрізає
    та умовно додає поля для одного зображення.
    """
    try:
        # 1. Відкриваємо оригінал
        img_original = Image.open(image_path)
        print(f"   - Відкрито: {os.path.basename(image_path)} ({img_original.size[0]}x{img_original.size[1]}, {img_original.mode})")

        # 2. Перевіряємо периметр оригіналу
        should_add_padding = False
        if perimeter_margin > 0:
            print(f"   - Перевірка периметра (відступ {perimeter_margin}px)...")
            # Використовуємо копію для перевірки, щоб не змінити оригінал
            is_white = check_perimeter_is_white(img_original.copy(), white_tolerance, perimeter_margin)
            if is_white:
                 should_add_padding = True
                 print("     - Периметр білий.")
            else:
                 print("     - Периметр не білий.")
        else:
             print("   - Перевірка периметра: Пропущено (відступ 0).")


        # 3. Конвертуємо в RGBA для подальшої обробки (якщо ще не так)
        img_rgba = img_original if img_original.mode == 'RGBA' else img_original.convert("RGBA")

        # 4. Видалення білого фону -> прозорий фон
        print(f"   - Видалення білого фону (допуск {white_tolerance})...")
        img_no_bg = remove_white_background(img_rgba, white_tolerance)

        # 5. Обрізка прозорих країв
        print("   - Обрізка прозорих країв...")
        img_cropped = crop_transparent_border(img_no_bg)

        # Перевірка, чи щось залишилось після обрізки
        if img_cropped is None or not img_cropped.getbbox():
             print(f"   ! Попередження: Зображення '{os.path.basename(image_path)}' стало порожнім після обробки.")
             return None
        print(f"     - Розмір після обрізки: {img_cropped.size[0]}x{img_cropped.size[1]}")

        # 6. Умовне додавання полів
        img_final = None
        if should_add_padding and padding_percent > 0:
            print(f"   - Додавання полів ({padding_percent}%)...")
            img_final = add_padding(img_cropped, padding_percent)
            if img_final:
                 print(f"     - Розмір після полів: {img_final.size[0]}x{img_final.size[1]}")
            else: # Якщо add_padding повернуло None (малоймовірно)
                 print(f"   ! Помилка додавання полів.")
                 img_final = img_cropped # Використовуємо обрізане
        else:
            if not should_add_padding:
                 print(f"   - Додавання полів: Пропущено (периметр не був білим або відступ 0).")
            elif padding_percent <= 0:
                 print(f"   - Додавання полів: Пропущено (відсоток полів <= 0).")
            img_final = img_cropped # Поля не потрібні, використовуємо обрізане

        # Переконуємось, що фінальне зображення має режим RGBA для коректної вставки
        if img_final and img_final.mode != 'RGBA':
            img_final = img_final.convert('RGBA')

        return img_final

    except FileNotFoundError:
        print(f"   ! Помилка: Файл не знайдено '{image_path}'")
        return None
    except Exception as e:
        print(f"   ! Помилка обробки файлу {os.path.basename(image_path)}: {e}")
        traceback.print_exc() # Друкуємо деталі помилки
        return None
# --- ---

def combine_images(image_paths, output_path, forced_cols=0, spacing_percent=DEFAULT_SPACING_PERCENT, white_tolerance=DEFAULT_WHITE_TOLERANCE, quality=DEFAULT_OUTPUT_QUALITY, perimeter_margin=0, padding_percent=0):
    """Обробляє (з умовними полями) та об'єднує зображення у сітку."""
    if not image_paths:
        print("У вказаній папці не знайдено підтримуваних зображень.")
        return

    processed_images = []
    print("\n--- Обробка зображень ---")
    for path in image_paths:
        # Запобігаємо обробці попереднього результату
        if os.path.abspath(path).lower() == os.path.abspath(output_path).lower():
            print(f" - Пропуск файлу '{os.path.basename(path)}' (збігається з іменем вихідного файлу).")
            continue

        print(f" - Обробка: {os.path.basename(path)}")
        # Передаємо нові параметри в process_image
        processed = process_image(path, white_tolerance, perimeter_margin, padding_percent)
        if processed:
            processed_images.append(processed)
            print(f"   - Додано до колажу (фінальний розмір: {processed.size[0]}x{processed.size[1]})")
        else:
            print(f"   ! Пропущено або не вдалося обробити.")
        print("-" * 10) # Розділювач між файлами

    num_images = len(processed_images)
    if num_images == 0:
        print("\nНемає успішно оброблених зображень для об'єднання.")
        return

    print(f"\n--- Створення колажу ---")
    print(f"Успішно оброблено та готово до колажу: {num_images} зображень.")

    # --- Логіка визначення розмірів сітки ---
    if forced_cols > 0:
        grid_cols = forced_cols
        grid_rows = math.ceil(num_images / grid_cols)
        print(f"Використання фіксованої кількості стовпців: {grid_cols}")
    else:
        grid_cols = math.ceil(math.sqrt(num_images))
        grid_rows = math.ceil(num_images / grid_cols)
        print("Автоматичний розрахунок розмірів сітки.")
    # --- ---

    # Знаходимо максимальні розміри *після* обробки (включаючи можливі поля)
    max_w = 0
    max_h = 0
    for img in processed_images:
        # Перевірка потрібна, хоча None вже мали відфільтруватися
        if img and hasattr(img, 'size') and len(img.size) == 2:
            max_w = max(max_w, img.size[0])
            max_h = max(max_h, img.size[1])

    if max_w == 0 or max_h == 0:
        print("Помилка: Не вдалося визначити максимальні розміри оброблених зображень.")
        return

    # Розраховуємо відступи між картинками на основі максимальних розмірів
    h_spacing = int(max_w * (spacing_percent / 100.0))
    v_spacing = int(max_h * (spacing_percent / 100.0))

    # Розраховуємо розміри фінального холста
    canvas_width = (grid_cols * max_w) + ((grid_cols + 1) * h_spacing)
    canvas_height = (grid_rows * max_h) + ((grid_rows + 1) * v_spacing)

    # Створюємо білий холст RGB
    canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
    print(f"Створено холст: {canvas_width}x{canvas_height}px")
    print(f"Макс. розмір комірки (з полями): {max_w}x{max_h}px")
    print(f"Відступи між комірками: Горизонтальний={h_spacing}px, Вертикальний={v_spacing}px")
    print(f"Сітка: {grid_rows} рядків x {grid_cols} стовпців")

    current_image_index = 0
    for r in range(grid_rows):
        # Визначаємо, скільки елементів реально буде в цьому ряду
        start_index_in_row = r * grid_cols
        items_in_this_row = min(grid_cols, num_images - start_index_in_row)

        # Розраховуємо зміщення для центрування неповного останнього ряду
        extra_offset_x_for_last_row = 0
        if r == grid_rows - 1 and items_in_this_row < grid_cols:
            empty_slots = grid_cols - items_in_this_row
            # Додатковий відступ = половина ширини порожніх слотів (включаючи їх відступи)
            extra_offset_x_for_last_row = (empty_slots * (max_w + h_spacing)) // 2

        for c in range(items_in_this_row):
            if current_image_index < num_images:
                img = processed_images[current_image_index]
                if img is None: # На випадок, якщо None якось просочився
                     current_image_index += 1
                     continue

                # Верхній лівий кут поточної *комірки* (включаючи відступ зліва/зверху)
                cell_x = h_spacing + c * (max_w + h_spacing) + extra_offset_x_for_last_row
                cell_y = v_spacing + r * (max_h + v_spacing)

                # Розраховуємо зсув для центрування *зображення* всередині *комірки*
                paste_offset_x = (max_w - img.width) // 2
                paste_offset_y = (max_h - img.height) // 2

                # Фінальні координати для вставки (верхній лівий кут зображення)
                paste_x = cell_x + paste_offset_x
                paste_y = cell_y + paste_offset_y

                # Переконуємося, що зображення RGBA для правильної вставки з прозорістю
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                # Вставляємо зображення на холст, використовуючи його альфа-канал як маску
                try:
                    # print(f"  - Вставка {os.path.basename(image_paths[current_image_index])} у ({paste_x},{paste_y})")
                    canvas.paste(img, (paste_x, paste_y), img)
                except Exception as paste_err:
                    print(f"  ! Помилка вставки зображення {current_image_index}: {paste_err}")

                current_image_index += 1
            else:
                 break # Вийшли за межі доступних зображень

    print(f"\nЗбереження результату у '{output_path}'...")
    try:
        # Переконуємося, що зберігаємо як RGB (холст вже RGB, але для надійності)
        if canvas.mode != 'RGB':
             rgb_canvas = Image.new("RGB", canvas.size, (255, 255, 255))
             if canvas.mode == 'RGBA' and len(canvas.split()) == 4:
                 rgb_canvas.paste(canvas, mask=canvas.split()[3])
             else: # P, L, etc.
                 rgb_canvas.paste(canvas)
             canvas_to_save = rgb_canvas
        else:
             canvas_to_save = canvas

        canvas_to_save.save(output_path, 'JPEG', quality=quality, optimize=True, subsampling=0) # Додав subsampling=0 для кращої якості
        print(f"Зображення успішно збережено в: {output_path}")
    except Exception as e:
        print(f"Помилка збереження файлу '{output_path}': {e}")
        traceback.print_exc()

def run_processing():
    """Основна функція: знаходить файли, запускає об'єднання."""
    print(f"Пошук зображень у папці: {SOURCE_DIRECTORY}")
    print(f"Налаштування:")
    print(f" - К-ть стовпців: {'Авто' if FORCED_GRID_COLS <= 0 else FORCED_GRID_COLS}")
    print(f" - Допуск білого: {DEFAULT_WHITE_TOLERANCE}")
    print(f" - Відступ перевірки периметра: {PERIMETER_CHECK_MARGIN_PIXELS}px")
    print(f" - Поля якщо периметр білий: {PADDING_PERCENT_IF_WHITE}%")
    print(f" - Відступ між зображеннями: {DEFAULT_SPACING_PERCENT}%")
    print(f" - Ім'я вихідного файлу: {DEFAULT_OUTPUT_FILENAME}")
    print(f" - Якість JPG: {DEFAULT_OUTPUT_QUALITY}")
    print(f" - Підтримувані розширення: {', '.join(SUPPORTED_EXTENSIONS)}")


    if not os.path.isdir(SOURCE_DIRECTORY):
        print(f"\n!!! Помилка: Папка '{SOURCE_DIRECTORY}' не знайдена.")
        print("Будь ласка, перевірте шлях у змінній SOURCE_DIRECTORY у скрипті.")
        return

    input_files = []
    for ext in SUPPORTED_EXTENSIONS:
        # Використовуємо рекурсивний пошук, якщо потрібно (**)
        # search_pattern = os.path.join(SOURCE_DIRECTORY, '**', f"*{ext}")
        # found_files = glob.glob(search_pattern, recursive=True)
        search_pattern = os.path.join(SOURCE_DIRECTORY, f"*{ext}")
        # Ігноруємо регістр символів для розширень
        found_files = [f for f in glob.glob(search_pattern) if f.lower().endswith(ext)]
        input_files.extend(found_files)

    if not input_files:
        print(f"\nУ папці '{SOURCE_DIRECTORY}' не знайдено файлів із розширеннями: {', '.join(SUPPORTED_EXTENSIONS)}")
        return

    # Сортуємо знайдені файли за іменем для послідовного порядку
    input_files.sort()
    print(f"\nЗнайдено {len(input_files)} потенційних зображень (відсортовано).")

    output_file_path = os.path.join(SOURCE_DIRECTORY, DEFAULT_OUTPUT_FILENAME)

    combine_images(
        image_paths=input_files,
        output_path=output_file_path,
        forced_cols=FORCED_GRID_COLS,
        spacing_percent=DEFAULT_SPACING_PERCENT,
        white_tolerance=DEFAULT_WHITE_TOLERANCE,
        quality=DEFAULT_OUTPUT_QUALITY,
        # Передаємо нові параметри
        perimeter_margin=PERIMETER_CHECK_MARGIN_PIXELS,
        padding_percent=PADDING_PERCENT_IF_WHITE
    )

if __name__ == "__main__":
    # Перевірка Pillow винесена сюди, щоб не імпортувати її глобально до перевірки
    try:
        import PIL
        # print(f"Pillow version: {PIL.__version__}") # Для діагностики
    except ImportError:
        print("!!! Помилка: Бібліотека Pillow не знайдена.")
        print("Будь ласка, встановіть її, виконавши команду в терміналі:")
        print("pip install Pillow")
        exit()

    run_processing()
    print("\nРоботу скрипту завершено.")