import math
import os
import glob
# Переконайтесь, що Pillow встановлено: pip install Pillow
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError, ImageFile
import traceback # Для детальних помилок
import sys # Для перевірки бібліотек
# Переконайтесь, що natsort встановлено (якщо використовується в run_processing): pip install natsort
from natsort import natsorted

# --- Перевірка Pillow ---
try:
    import PIL
except ImportError:
    print("!!! Помилка: Бібліотека Pillow не знайдена."); sys.exit(1)
# --- ---

ImageFile.LOAD_TRUNCATED_IMAGES = True
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp')

# --- Функція відбілювання (ЗА НАЙТЕМНІШИМ ПІКСЕЛЕМ ПЕРИМЕТРУ) ---
# (Залишається без змін з попередньої версії)
def whiten_image_by_darkest_perimeter(img):
    print("    - Функція відбілювання (за пікселем периметру)...") # Скорочено
    img_copy = img.copy(); original_mode = img_copy.mode
    has_alpha = 'A' in img_copy.getbands(); alpha_channel = None
    if original_mode == 'RGBA' and has_alpha:
        try:
            split_bands = img_copy.split()
            if len(split_bands) == 4: alpha_channel = split_bands[3]; img_rgb = img_copy.convert('RGB')
            else: print(f"      ! Помилка RGBA split. Скасовано."); return img
        except Exception as e: print(f"      ! Помилка RGBA split/convert: {e}. Скасовано."); return img
    elif original_mode != 'RGB':
        try: img_rgb = img_copy.convert('RGB')
        except Exception as e: print(f"      ! Помилка конвертації {original_mode}->RGB: {e}. Скасовано."); return img
    else: img_rgb = img_copy
    width, height = img_rgb.size
    if width <= 1 or height <= 1: print("      ! Зображення замале. Скасовано."); return img
    darkest_pixel_rgb = None; min_sum = float('inf'); pixels = None
    try:
        pixels = img_rgb.load()
        def check_pixel(x, y):
            nonlocal min_sum, darkest_pixel_rgb; pixel = pixels[x, y]
            if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                r, g, b = pixel[:3]
                if all(isinstance(val, int) for val in (r, g, b)):
                    current_sum = r + g + b
                    if current_sum < min_sum: min_sum = current_sum; darkest_pixel_rgb = (r, g, b)
        for x in range(width):
            check_pixel(x, 0)
            if height > 1: check_pixel(x, height - 1)
        for y in range(1, height - 1):
            check_pixel(0, y)
            if width > 1: check_pixel(width - 1, y)
    except Exception as e: print(f"      ! Помилка доступу до пікселів: {e}. Скасовано."); return img
    if darkest_pixel_rgb is None: print("      ! Не знайдено валідних пікселів периметру. Скасовано."); return img
    ref_r, ref_g, ref_b = darkest_pixel_rgb
    print(f"      - Референс: R={ref_r}, G={ref_g}, B={ref_b}")
    if ref_r == 255 and ref_g == 255 and ref_b == 255: print("      - Відбілювання не потрібне."); return img
    scale_r = 255.0 / max(1, ref_r); scale_g = 255.0 / max(1, ref_g); scale_b = 255.0 / max(1, ref_b)
    print(f"      - Множники: R*={scale_r:.3f}, G*={scale_g:.3f}, B*={scale_b:.3f}")
    lut_r = bytes([min(255, int(i * scale_r)) for i in range(256)]); lut_g = bytes([min(255, int(i * scale_g)) for i in range(256)]); lut_b = bytes([min(255, int(i * scale_b)) for i in range(256)])
    try:
        if img_rgb is None: raise ValueError("img_rgb is None"); r_ch, g_ch, b_ch = img_rgb.split(); out_r = r_ch.point(lut_r); out_g = g_ch.point(lut_g); out_b = b_ch.point(lut_b)
        img_whitened_rgb = Image.merge('RGB', (out_r, out_g, out_b))
    except Exception as e: print(f"      ! Помилка LUT: {e}. Скасовано."); return img
    if alpha_channel:
        try: img_whitened_rgb.putalpha(alpha_channel); return img_whitened_rgb
        except Exception as e: print(f"      ! Помилка альфа: {e}. RGB."); return img_whitened_rgb
    else: return img_whitened_rgb
# --- ---

# --- Функції перевірки та додавання полів ---
# (Залишаються без змін з попередньої версії)
def check_perimeter_is_white(img, tolerance, margin):
    if margin <= 0: return False
    try:
        if img.mode != 'RGB': img_rgb = img.convert('RGB')
        else: img_rgb = img.copy()
        width, height = img_rgb.size; pixels = img_rgb.load()
    except Exception as e: print(f"  ! Помилка перевірки периметру (init): {e}"); return False
    margin_h = min(margin, height // 2 if height > 1 else 0); margin_w = min(margin, width // 2 if width > 1 else 0)
    if margin_h == 0 and height > 0: margin_h = 1
    if margin_w == 0 and width > 0: margin_w = 1
    if margin_h == 0 or margin_w == 0: return False # Немає чого перевіряти
    cutoff = 255 - tolerance
    try:
        def is_white(x,y): p=pixels[x,y]; return isinstance(p,(tuple,list)) and len(p)>=3 and p[0]>=cutoff and p[1]>=cutoff and p[2]>=cutoff
        for y in range(margin_h):
            for x in range(width):
                if not is_white(x,y): return False
        for y in range(height - margin_h, height):
            for x in range(width):
                if not is_white(x,y): return False
        for x in range(margin_w):
            for y in range(margin_h, height - margin_h):
                 if not is_white(x,y): return False
        for x in range(width - margin_w, width):
            for y in range(margin_h, height - margin_h):
                 if not is_white(x,y): return False
    except Exception as e: print(f"  ! Помилка перевірки периметру (loop): {e}"); return False
    return True

def add_padding(img, percent):
    if img is None or percent <= 0: return img
    width, height = img.size; padding_pixels = int(max(width, height) * (percent / 100.0))
    if width == 0 or height == 0 or padding_pixels == 0: return img
    nw = width + 2*padding_pixels; nh = height + 2*padding_pixels
    if img.mode != 'RGBA':
        try: img_rgba = img.convert('RGBA')
        except Exception as e: print(f"  ! Помилка конвертації в RGBA перед add_padding: {e}"); return img
    else: img_rgba = img
    padded_img = Image.new('RGBA', (nw, nh), (0,0,0,0))
    try: padded_img.paste(img_rgba, (padding_pixels, padding_pixels), img_rgba)
    except Exception as e: print(f"  ! Помилка paste в add_padding: {e}"); return img_rgba
    return padded_img
# --- ---

# --- Функції обробки зображення ---
# (Залишаються без змін з попередньої версії)
def remove_white_background(img, tolerance):
    if img.mode != 'RGBA':
        try: img_rgba = img.convert('RGBA')
        except Exception as e: print(f"  ! Помилка конвертації в RGBA в remove_white_background: {e}"); return img
    else: img_rgba = img.copy()
    datas = img_rgba.getdata(); newData = []; cutoff = 255 - tolerance
    try:
        for item in datas:
            if len(item) == 4 and item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff: newData.append((*item[:3], 0))
            else: newData.append(item)
        if len(newData) == img_rgba.width * img_rgba.height: img_rgba.putdata(newData)
        else: print(f"  ! Помилка розміру даних в remove_white_background"); return img_rgba.copy()
    except Exception as e: print(f"  ! Помилка в putdata в remove_white_background: {e}"); return img_rgba.copy()
    return img_rgba

def crop_transparent_border(img):
    if img.mode != 'RGBA': print("  ! Попередження: crop_transparent_border очікує RGBA."); return img
    try: bbox = img.getbbox() # Спробуємо getbbox() на всьому зображенні (може працювати і для альфа)
    except Exception: bbox = None
    if bbox and bbox[0] < bbox[2] and bbox[1] < bbox[3]:
        try: return img.crop(bbox)
        except Exception as e: print(f"  ! Помилка img.crop({bbox}): {e}"); return img
    return img

# --- ОНОВЛЕНА Функція обробки одного зображення ---
def process_image(image_path, enable_whitening, white_tolerance, perimeter_margin, padding_percent, resize_w, resize_h):
    """
    Завантажує, опціонально відбілює, перевіряє периметр,
    опціонально видаляє фон та обрізає, умовно додає поля,
    опціонально змінює розмір індивідуального зображення.
    Повертає зображення в режимі RGBA.
    """
    img_current = None
    try:
        # 1. Відкриття
        with Image.open(image_path) as img_opened: img_opened.load(); img_current = img_opened.copy()

        # 1.1 Відбілювання (опц.)
        if enable_whitening:
            print("   - [Опція] Відбілювання...")
            try:
                img_whitened = whiten_image_by_darkest_perimeter(img_current)
                if img_whitened is not img_current: img_current = img_whitened
            except Exception as e: print(f"   ! Помилка відбілювання: {e}")

        # 2. Перевірка периметра
        should_add_padding = check_perimeter_is_white(img_current, white_tolerance if white_tolerance is not None else 0, perimeter_margin)

        # 3, 4: Видалення фону та обрізка (опц.)
        img_after_bg_processing = None
        enable_bg_removal = white_tolerance is not None
        if enable_bg_removal:
            print(f"   - Видалення фону (допуск {white_tolerance})...")
            try: img_rgba_for_bg = img_current.convert('RGBA') if img_current.mode != 'RGBA' else img_current
            except Exception as e: print(f"  !! Помилка конвертації в RGBA для фону: {e}"); img_after_bg_processing = img_current
            else:
                img_no_bg = remove_white_background(img_rgba_for_bg, white_tolerance)
                print("   - Обрізка країв...")
                img_cropped = crop_transparent_border(img_no_bg)
                if img_cropped is None or img_cropped.size[0] == 0 or img_cropped.size[1] == 0: print(f"   ! Порожнє після обрізки."); return None
                img_after_bg_processing = img_cropped
        else:
            print("   - Видалення фону/обрізка вимкнені.")
            img_after_bg_processing = img_current

        if img_after_bg_processing is None or img_after_bg_processing.size[0] == 0 or img_after_bg_processing.size[1] == 0: print(f"   ! Помилка після обробки фону."); return None

        # 5. Додавання полів (опц.)
        img_before_resize = None
        if should_add_padding and padding_percent > 0 and perimeter_margin > 0:
            print(f"   - Додавання полів ({padding_percent}%)...")
            try: img_rgba_for_padding = img_after_bg_processing.convert('RGBA') if img_after_bg_processing.mode != 'RGBA' else img_after_bg_processing
            except Exception as e: print(f"  !! Помилка конвертації для полів: {e}"); img_before_resize = img_after_bg_processing
            else:
                img_padded = add_padding(img_rgba_for_padding, padding_percent)
                if img_padded and img_padded.size[0] > 0 and img_padded.size[1] > 0: img_before_resize = img_padded
                else: print("  ! Помилка додавання полів."); img_before_resize = img_after_bg_processing
        else: img_before_resize = img_after_bg_processing

        if img_before_resize is None or img_before_resize.size[0] == 0 or img_before_resize.size[1] == 0: print(f"   ! Помилка перед зміною розміру."); return None

        # --- 6. ЗМІНА РОЗМІРУ ІНДИВІДУАЛЬНОГО ЗОБРАЖЕННЯ (ОПЦ.) ---
        img_final_rgba = None
        perform_individual_resize = resize_w > 0 and resize_h > 0
        if perform_individual_resize and img_before_resize.size != (resize_w, resize_h):
            print(f"   - [Опція] Зміна розміру до {resize_w}x{resize_h}...")
            ow, oh = img_before_resize.size
            ratio = min(resize_w / ow, resize_h / oh)
            nw, nh = max(1, int(ow * ratio)), max(1, int(oh * ratio))
            try:
                resized_img_content = img_before_resize.resize((nw, nh), Image.Resampling.LANCZOS)
                # Створюємо прозорий (RGBA) холст для індивідуальних зображень
                individual_canvas = Image.new('RGBA', (resize_w, resize_h), (255, 255, 255, 0)) # Прозорий фон
                x, y = (resize_w - nw) // 2, (resize_h - nh) // 2
                # Вставляємо вміст (можливо, RGBA) на прозорий холст
                # Якщо вміст RGBA, використовуємо його альфа як маску
                if resized_img_content.mode == 'RGBA':
                     individual_canvas.paste(resized_img_content, (x, y), resized_img_content)
                else: # Якщо RGB або інший, просто вставляємо
                     individual_canvas.paste(resized_img_content, (x, y))
                img_final_rgba = individual_canvas
            except Exception as resize_err:
                 print(f"   ! Помилка індивідуальної зміни розміру: {resize_err}. Використовується попередній розмір.")
                 img_final_rgba = img_before_resize # Використовуємо зображення до зміни розміру
                 # Переконуємось, що воно RGBA
                 if img_final_rgba.mode != 'RGBA':
                      try: img_final_rgba = img_final_rgba.convert('RGBA')
                      except Exception as e: print(f"   !! Помилка конвертації в RGBA після помилки resize: {e}"); return None
        else:
            # Якщо зміна розміру не потрібна, просто переконуємось, що результат RGBA
            img_final_rgba = img_before_resize
            if img_final_rgba.mode != 'RGBA':
                 try: img_final_rgba = img_final_rgba.convert('RGBA')
                 except Exception as e: print(f"   !! Помилка конвертації в RGBA: {e}"); return None

        return img_final_rgba

    except FileNotFoundError: print(f"   ! Помилка: Файл не знайдено '{image_path}'"); return None
    except UnidentifiedImageError: print(f"   ! Помилка: Не розпізнано '{os.path.basename(image_path)}'"); return None
    except Exception as e: print(f"   ! Неочікувана помилка обробки {os.path.basename(image_path)}: {e}"); traceback.print_exc(); return None
    finally:
         if img_current:
             try: img_current.close();
             except Exception: pass
# --- ---

# --- ОНОВЛЕНА Функція об'єднання ---
def combine_images(image_paths, output_path,
                   enable_whitening, forced_cols, spacing_percent, white_tolerance, quality,
                   perimeter_margin, padding_percent,
                   individual_resize_w, individual_resize_h, # Нові параметри
                   final_resize_w, final_resize_h):          # Нові параметри
    """Обробляє та об'єднує зображення у сітку, з опціональною зміною розмірів."""
    if not image_paths: print("Немає шляхів до зображень."); return

    processed_images = []
    print("\n--- Обробка зображень для колажу ---")
    output_abs_path = os.path.abspath(output_path) if output_path else None

    for path in image_paths:
        if output_abs_path and os.path.abspath(path).lower() == output_abs_path.lower():
            print(f" - Пропуск: '{os.path.basename(path)}' (вихідний файл).")
            continue

        processed = process_image(
            path, enable_whitening, white_tolerance, perimeter_margin, padding_percent,
            individual_resize_w, individual_resize_h # Передаємо індивідуальні розміри
        )
        if processed:
            processed_images.append(processed)
            print(f"   + Додано: {os.path.basename(path)} (розмір для колажу: {processed.size[0]}x{processed.size[1]})")
        else:
            print(f"   ! Пропущено/Помилка: {os.path.basename(path)}")

    num_images = len(processed_images)
    if num_images == 0: print("\nНемає зображень для об'єднання."); return

    print(f"\n--- Створення колажу ({num_images} зображень) ---")
    grid_cols = forced_cols if forced_cols > 0 else math.ceil(math.sqrt(num_images))
    grid_rows = math.ceil(num_images / grid_cols)
    # Максимальні розміри беремо з *оброблених* (і можливо змінених індивідуально) зображень
    max_w = max((img.size[0] for img in processed_images if img), default=1)
    max_h = max((img.size[1] for img in processed_images if img), default=1)

    h_spacing = int(max_w * (spacing_percent / 100.0)); v_spacing = int(max_h * (spacing_percent / 100.0))
    canvas_width = (grid_cols * max_w) + ((grid_cols + 1) * h_spacing)
    canvas_height = (grid_rows * max_h) + ((grid_rows + 1) * v_spacing)

    canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
    print(f"Холст колажу: {canvas_width}x{canvas_height}px | Макс.комірка: {max_w}x{max_h}px | Сітка: {grid_rows}x{grid_cols}")

    # Розміщення зображень (логіка без змін)
    current_image_index = 0
    for r in range(grid_rows):
        items_in_this_row = min(grid_cols, num_images - (r * grid_cols))
        extra_offset_x = (grid_cols - items_in_this_row) * (max_w + h_spacing) // 2 if r == grid_rows - 1 and items_in_this_row < grid_cols else 0
        for c in range(items_in_this_row):
            if current_image_index >= num_images: break
            img = processed_images[current_image_index]; current_image_index += 1
            if img is None: continue
            cell_x = h_spacing + c * (max_w + h_spacing) + extra_offset_x
            cell_y = v_spacing + r * (max_h + v_spacing)
            paste_offset_x = (max_w - img.width) // 2; paste_offset_y = (max_h - img.height) // 2
            paste_x = cell_x + paste_offset_x; paste_y = cell_y + paste_offset_y
            try:
                # Переконуємось, що RGBA для коректної вставки на білий фон
                if img.mode != 'RGBA': img = img.convert('RGBA')
                canvas.paste(img, (paste_x, paste_y), img)
            except Exception as paste_err: print(f"  ! Помилка вставки {current_image_index-1}: {paste_err}")
        if current_image_index >= num_images: break

    # --- ЗМІНА РОЗМІРУ ФІНАЛЬНОГО КОЛАЖУ (ОПЦ.) ---
    canvas_to_save = canvas
    perform_final_resize = final_resize_w > 0 and final_resize_h > 0
    if perform_final_resize and canvas.size != (final_resize_w, final_resize_h):
        print(f"\n--- [Опція] Зміна розміру фінального колажу до {final_resize_w}x{final_resize_h} ---")
        ow, oh = canvas.size
        ratio = min(final_resize_w / ow, final_resize_h / oh)
        nw, nh = max(1, int(ow * ratio)), max(1, int(oh * ratio))
        try:
            resized_collage_content = canvas.resize((nw, nh), Image.Resampling.LANCZOS)
            # Створюємо білий (RGB) холст для фінального колажу
            final_canvas = Image.new('RGB', (final_resize_w, final_resize_h), (255, 255, 255))
            x, y = (final_resize_w - nw) // 2, (final_resize_h - nh) // 2
            final_canvas.paste(resized_collage_content, (x, y))
            canvas_to_save = final_canvas # Оновлюємо змінну для збереження
            print(f"  - Розмір фінального колажу змінено.")
        except Exception as final_resize_err:
            print(f"  ! Помилка зміни розміру фінального колажу: {final_resize_err}. Зберігається оригінальний розмір.")
            # canvas_to_save залишається оригінальним canvas
    # --- ---

    print(f"\nЗбереження результату у '{output_path}'...")
    try:
        # Переконуємось, що зберігаємо RGB
        if canvas_to_save.mode != 'RGB': canvas_to_save = canvas_to_save.convert('RGB')
        canvas_to_save.save(output_path, 'JPEG', quality=quality, optimize=True, subsampling=0)
        print(f"Зображення успішно збережено.")
    except Exception as e: print(f"Помилка збереження '{output_path}': {e}"); traceback.print_exc()
    finally:
        if canvas:
            try: canvas.close();
            except Exception: pass
        if canvas_to_save and canvas_to_save is not canvas:
            try: canvas_to_save.close();
            except Exception: pass
        for img in processed_images:
             if img:
                 try: img.close();
                 except Exception: pass

# --- ОНОВЛЕНА Основна функція запуску ---
def run_processing(source_dir, output_filename, enable_whitening, forced_cols,
                   perimeter_margin, padding_percent, white_tolerance, spacing_percent, quality,
                   individual_resize_w, individual_resize_h, # Нові параметри
                   final_collage_w, final_collage_h):       # Нові параметри
    """Знаходить файли та запускає об'єднання, використовуючи передані параметри."""
    print(f"--- Запуск обробки ---")
    print(f"Папка джерело: {source_dir}")
    print(f"Налаштування обробки:")
    print(f" - Відбілювання (периметр): {'Увімкнено' if enable_whitening else 'Вимкнено'}")
    if white_tolerance is not None: print(f" - Допуск білого (фон): {white_tolerance}")
    else: print(f" - Допуск білого (фон): None (Вимкнено)")
    print(f" - Перевірка периметра (поля): {perimeter_margin}px")
    print(f" - Відсоток полів (якщо треба): {padding_percent}%")
    # Друк налаштувань індивідуального розміру
    if individual_resize_w > 0 and individual_resize_h > 0:
        print(f" - Індивід. розмір: Так ({individual_resize_w}x{individual_resize_h}px)")
    else:
        print(f" - Індивід. розмір: Ні")
    print(f"Налаштування колажу:")
    print(f" - К-ть стовпців: {'Авто' if forced_cols <= 0 else forced_cols}")
    print(f" - Відступ між зображеннями: {spacing_percent}%")
    # Друк налаштувань фінального розміру
    if final_collage_w > 0 and final_collage_h > 0:
        print(f" - Фінальний розмір: Так ({final_collage_w}x{final_collage_h}px)")
    else:
        print(f" - Фінальний розмір: Ні (Залишиться розрахованим)")
    print(f" - Ім'я вихідного файлу: {output_filename}")
    print(f" - Якість JPG: {quality}")
    print(f" - Розширення: {', '.join(SUPPORTED_EXTENSIONS)}")

    if not os.path.isdir(source_dir): print(f"\n!!! Помилка: Папка '{source_dir}' не знайдена."); return

    input_files = []
    print(f"--- Пошук файлів у '{source_dir}' ---")
    for ext in SUPPORTED_EXTENSIONS:
        search_pattern = os.path.join(source_dir, f"*{ext}")
        try: found_files = glob.glob(search_pattern)
        except Exception as e: print(f"Помилка пошуку {ext}: {e}"); found_files=[]
        input_files.extend(found_files)
    # print(f"--- Знайдено файлів (до фільтрації): {len(input_files)} ---")
    input_files = [f for f in input_files if os.path.isfile(f) and f.lower().endswith(SUPPORTED_EXTENSIONS)]
    # print(f"--- Знайдено файлів (після фільтрації): {len(input_files)} ---")

    if not input_files: print(f"\nУ папці '{source_dir}' не знайдено файлів із підтримуваними розширеннями."); return

    input_files = natsorted(input_files)
    print(f"Знайдено {len(input_files)} підтримуваних зображень (відсортовано).")

    output_file_path = os.path.join(source_dir, output_filename)
    combine_images(
        image_paths=input_files, output_path=output_file_path, enable_whitening=enable_whitening,
        forced_cols=forced_cols, spacing_percent=spacing_percent, white_tolerance=white_tolerance,
        quality=quality, perimeter_margin=perimeter_margin, padding_percent=padding_percent,
        individual_resize_w=individual_resize_w, individual_resize_h=individual_resize_h, # Передача нових параметрів
        final_resize_w=final_collage_w, final_resize_h=final_collage_h                 # Передача нових параметрів
    )

# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":

    # --- Налаштування Користувача ---
    source_directory = r"C:\Users\zakhar\Downloads\test3"  # !!! ВАШ шлях
    output_filename = "collage_result_resized.jpg" # !!! Можна змінити

    # === Опції Обробки Зображень (Перед колажем) ===
    enable_whitening = False              # Відбілювання за периметром: True / False
    white_tolerance = 5                   # Допуск білого для фону: 0-255 або None (вимкнути)
    perimeter_check_margin = 5            # Перевірка периметру для полів: 0 (вимкнути) або більше
    padding_percent_if_white = 5.0        # Відсоток полів (якщо треба): 0.0 (вимкнути) або більше

    # === Зміна Розміру Індивідуальних Зображень (Перед колажем) ===
    # Встановіть > 0, щоб змінити розмір кожного фото ДО розміщення на колажі.
    # Якщо 0, розмір не змінюється.
    individual_resize_width = 750         # !!! Бажана ширина (0 для вимкнення)
    individual_resize_height = 750        # !!! Бажана висота (0 для вимкнення)

    # === Налаштування Колажу ===
    forced_grid_cols = 0                  # К-ть стовпців: 0 (авто) або більше
    spacing_percent = 2.0                 # Відступ між фото: 0.0 або більше

    # === Зміна Розміру Фінального Колажу (Після створення) ===
    # Встановіть > 0, щоб змінити розмір ГОТОВОГО колажу.
    # Якщо 0, розмір залишається таким, як розраховано автоматично.
    final_collage_width = 1500            # !!! Бажана ширина (0 для вимкнення)
    final_collage_height = 1500           # !!! Бажана висота (0 для вимкнення)

    # === Якість Збереження ===
    quality = 95                          # !!! 1-100
    # --- Кінець Налаштувань Користувача ---

    # Виклик основної функції з налаштуваннями
    run_processing(
        source_dir=source_directory, output_filename=output_filename,
        enable_whitening=enable_whitening, forced_cols=forced_grid_cols,
        perimeter_margin=perimeter_check_margin, padding_percent=padding_percent_if_white,
        white_tolerance=white_tolerance, spacing_percent=spacing_percent, quality=quality,
        individual_resize_w=individual_resize_width, individual_resize_h=individual_resize_height, # Передача нових параметрів
        final_collage_w=final_collage_width, final_collage_h=final_collage_height          # Передача нових параметрів
    )

    print("\nРоботу скрипту завершено.")