import math
import os
import glob # Для пошуку файлів за шаблоном
from PIL import Image, ImageChops, ImageOps

# --- Налаштування ---
# !!! ВАЖЛИВО: Вкажіть тут шлях до папки з вашими зображеннями !!!
SOURCE_DIRECTORY = r"C:\Users\ABM\Desktop\MM"
# Приклади:
# SOURCE_DIRECTORY = r"D:\Фото\ДляОбробки"
# SOURCE_DIRECTORY = r"C:\Users\ABM\Pictures\Unicorns"

# --- Константи ---
DEFAULT_WHITE_TOLERANCE = 10 # Допуск для визначення білого кольору (0-255)
DEFAULT_SPACING_PERCENT = 10 # Процент відступу між елементами (відносно розміру елемента)
DEFAULT_OUTPUT_FILENAME = "combined_output.jpg" # Ім'я файлу результату
DEFAULT_OUTPUT_QUALITY = 95 # Якість збереження JPG (1-95)
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff') # Додано крапку на початку
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
    if img.mode != 'RGBA':
         temp_img = img.convert('RGBA')
         bg = Image.new('RGBA', temp_img.size, (0,0,0,0))
         try:
            bbox = ImageChops.difference(temp_img, bg).getbbox()
         except ValueError:
             bbox = None
    else:
         try:
            bbox = img.getbbox()
         except ValueError:
            bbox = None

    if bbox:
        return img.crop(bbox)
    else:
        #print("Попередження: Не вдалося знайти межі об'єкта. Пропуск обрізки.")
        return img # Повертаємо те, що є, щоб не зламати процес

def process_image(image_path, white_tolerance):
    """Завантажує, видаляє фон та обрізає одне зображення."""
    try:
        # Перевірка розширення вже зроблена при пошуку файлів
        img = Image.open(image_path)
        img = img.convert("RGBA")

        img_no_bg = remove_white_background(img, white_tolerance)
        img_cropped = crop_transparent_border(img_no_bg)

        if img_cropped is None or not img_cropped.getbbox():
             #print(f"Попередження: Зображення '{os.path.basename(image_path)}' стало порожнім після обробки.")
             return None # Якщо зображення стало пустим, не повертаємо його

        return img_cropped

    except FileNotFoundError:
        print(f"Помилка: Файл не знайдено '{image_path}' (це дивно, якщо він був знайдений раніше)")
        return None
    except Exception as e:
        print(f"Помилка обробки файлу {os.path.basename(image_path)}: {e}")
        return None

def combine_images(image_paths, output_path, spacing_percent=DEFAULT_SPACING_PERCENT, white_tolerance=DEFAULT_WHITE_TOLERANCE, quality=DEFAULT_OUTPUT_QUALITY):
    """Обробляє та об'єднує зображення у сітку."""
    if not image_paths:
        print("У вказаній папці не знайдено підтримуваних зображень.")
        return

    processed_images = []
    print("Обробка зображень...")
    for path in image_paths:
        # Не обробляємо сам файл результату, якщо він вже існує в папці
        if os.path.basename(path) == os.path.basename(output_path):
            print(f"Пропуск файлу '{os.path.basename(path)}' (схоже на попередній результат).")
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

    # Визначення розмірів сітки
    grid_cols = math.ceil(math.sqrt(num_images))
    grid_rows = math.ceil(num_images / grid_cols)

    max_w = 0
    max_h = 0
    for img in processed_images:
        if img and hasattr(img, 'width') and hasattr(img, 'height'):
            max_w = max(max_w, img.width)
            max_h = max(max_h, img.height)

    if max_w == 0 or max_h == 0:
        print("Помилка: Не вдалося визначити розміри оброблених зображень.")
        return

    # Розрахунок відступів
    h_spacing = int(max_w * (spacing_percent / 100.0))
    v_spacing = int(max_h * (spacing_percent / 100.0))

    # Розрахунок загального розміру холста
    canvas_width = (grid_cols * max_w) + ((grid_cols + 1) * h_spacing)
    canvas_height = (grid_rows * max_h) + ((grid_rows + 1) * v_spacing)

    # Створення холста (білий фон)
    canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
    print(f"Створено холст: {canvas_width}x{canvas_height}px")
    print(f"Розмір комірки: {max_w}x{max_h}px, Відступи: H={h_spacing}px, V={v_spacing}px")
    print(f"Сітка: {grid_rows}x{grid_cols}")

    # Розміщення зображень
    current_image_index = 0
    for r in range(grid_rows):
        items_in_this_row = 0
        if r < grid_rows - 1:
             items_in_this_row = grid_cols
        else:
             items_in_this_row = num_images - (r * grid_cols)

        extra_offset_x_for_last_row = 0
        if r == grid_rows - 1 and items_in_this_row < grid_cols :
            empty_slots = grid_cols - items_in_this_row
            extra_offset_x_for_last_row = (empty_slots * (max_w + h_spacing)) // 2

        for c in range(grid_cols):
            if current_image_index < num_images:
                img = processed_images[current_image_index]
                if img is None:
                     current_image_index += 1
                     continue

                cell_x = h_spacing + c * (max_w + h_spacing) + extra_offset_x_for_last_row
                cell_y = v_spacing + r * (max_h + v_spacing)

                paste_offset_x = (max_w - img.width) // 2
                paste_offset_y = (max_h - img.height) // 2

                paste_x = cell_x + paste_offset_x
                paste_y = cell_y + paste_offset_y

                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                canvas.paste(img, (paste_x, paste_y), img)

                current_image_index += 1
            else:
                 break

    # Збереження результату
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
    # Шукаємо файли з усіма підтримуваними розширеннями
    for ext in SUPPORTED_EXTENSIONS:
        # glob.glob шукає файли за шаблоном. os.path.join коректно з'єднує шлях
        # '*' означає будь-яку назву файлу
        search_pattern = os.path.join(SOURCE_DIRECTORY, f"*{ext}")
        found_files = glob.glob(search_pattern)
        input_files.extend(found_files) # Додаємо знайдені файли до списку

    if not input_files:
        print(f"У папці '{SOURCE_DIRECTORY}' не знайдено файлів із розширеннями: {', '.join(SUPPORTED_EXTENSIONS)}")
        return

    print(f"Знайдено {len(input_files)} потенційних зображень.")

    # Визначаємо повний шлях для збереження результату
    output_file_path = os.path.join(SOURCE_DIRECTORY, DEFAULT_OUTPUT_FILENAME)

    combine_images(
        image_paths=input_files,
        output_path=output_file_path,
        spacing_percent=DEFAULT_SPACING_PERCENT,
        white_tolerance=DEFAULT_WHITE_TOLERANCE,
        quality=DEFAULT_OUTPUT_QUALITY
    )

if __name__ == "__main__":
    # Перевірка наявності Pillow
    try:
        import PIL
    except ImportError:
        print("Помилка: Бібліотека Pillow не знайдена.")
        print("Будь ласка, встановіть її, виконавши команду:")
        print("pip install Pillow")
        exit()

    # Запуск основного процесу
    run_processing()
    print("Роботу завершено.")