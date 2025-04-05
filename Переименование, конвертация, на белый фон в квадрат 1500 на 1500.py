import os
import math
# Переконайтесь, що Pillow встановлено: pip install Pillow
from PIL import Image, ImageChops, UnidentifiedImageError, ImageFile
# Переконайтесь, що natsort встановлено: pip install natsort
from natsort import natsorted
import traceback # Для детальних помилок
import sys # Для перевірки бібліотек
import shutil # Для копіювання файлів (резервне копіювання)

# --- Перевірка наявності бібліотек ---
try: import PIL;
except ImportError: print("Помилка: Pillow не знайдена."); sys.exit(1)
try: import natsort;
except ImportError: print("Помилка: natsort не знайдена."); sys.exit(1)
# --- ---

ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Функції обробки зображення ---
# (whiten_image_by_darkest_perimeter, remove_white_background,
# crop_transparent_border, add_padding, check_perimeter_is_white -
# залишаються без змін з попередньої версії)

def whiten_image_by_darkest_perimeter(img):
    """
    Відбілює зображення, використовуючи найтемніший піксель ПЕРИМЕТРУ
    (1px рамка) як референс для білого.
    Працює з копією зображення.
    """
    print("    - Функція відбілювання (за пікселем периметру)...")
    img_copy = img.copy(); original_mode = img_copy.mode
    has_alpha = 'A' in img_copy.getbands(); alpha_channel = None; img_rgb = None
    try:
        if original_mode == 'RGBA' and has_alpha:
            split_bands = img_copy.split();
            if len(split_bands) == 4: alpha_channel = split_bands[3]; img_rgb = img_copy.convert('RGB')
            else: raise ValueError(f"Очікувалось 4 канали в RGBA, отримано {len(split_bands)}")
        elif original_mode != 'RGB': img_rgb = img_copy.convert('RGB')
        else: img_rgb = img_copy
    except Exception as e: print(f"      ! Помилка підготовки до відбілювання: {e}. Скасовано."); return img

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
            check_pixel(x, 0);
            if height > 1: check_pixel(x, height - 1)
        for y in range(1, height - 1):
            check_pixel(0, y);
            if width > 1: check_pixel(width - 1, y)
    except Exception as e: print(f"      ! Помилка доступу до пікселів: {e}. Скасовано."); return img

    if darkest_pixel_rgb is None: print("      ! Не знайдено валідних пікселів периметру. Скасовано."); return img
    ref_r, ref_g, ref_b = darkest_pixel_rgb; print(f"      - Референс: R={ref_r}, G={ref_g}, B={ref_b}")
    if ref_r == 255 and ref_g == 255 and ref_b == 255: print("      - Відбілювання не потрібне."); return img

    scale_r = 255.0 / max(1, ref_r); scale_g = 255.0 / max(1, ref_g); scale_b = 255.0 / max(1, ref_b)
    print(f"      - Множники: R*={scale_r:.3f}, G*={scale_g:.3f}, B*={scale_b:.3f}")
    lut_r = bytes([min(255, int(i * scale_r)) for i in range(256)]); lut_g = bytes([min(255, int(i * scale_g)) for i in range(256)]); lut_b = bytes([min(255, int(i * scale_b)) for i in range(256)])

    # --- ВИПРАВЛЕННЯ ПОМИЛКИ UnboundLocalError ---
    img_whitened_rgb = None
    out_r, out_g, out_b = None, None, None # Ініціалізуємо перед try
    try:
        if img_rgb is None: raise ValueError("img_rgb is None")
        r_ch, g_ch, b_ch = img_rgb.split()
        out_r = r_ch.point(lut_r) # Присвоюємо значення
        out_g = g_ch.point(lut_g) # Присвоюємо значення
        out_b = b_ch.point(lut_b) # Присвоюємо значення

        # Злиття відбувається тільки якщо всі попередні кроки успішні
        img_whitened_rgb = Image.merge('RGB', (out_r, out_g, out_b))

    except Exception as e:
        print(f"      ! Помилка застосування LUT/злиття: {e}. Скасовано.")
        # У випадку помилки повертаємо оригінальну копію
        # img_whitened_rgb залишиться None, і функція поверне img (копію оригіналу)
        return img
    # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---

    if alpha_channel:
        try:
            # Перевіряємо, чи img_whitened_rgb було успішно створено
            if img_whitened_rgb:
                 img_whitened_rgb.putalpha(alpha_channel)
                 return img_whitened_rgb
            else: # Якщо відбілювання скасовано через помилку LUT/merge
                 return img # Повертаємо оригінал (копію)
        except Exception as e:
             print(f"      ! Помилка відновлення альфа: {e}. Повернення RGB.")
             return img_whitened_rgb if img_whitened_rgb else img # Повертаємо або результат RGB, або оригінал
    else:
        # Якщо альфи не було, повертаємо результат RGB або оригінал, якщо була помилка
        return img_whitened_rgb if img_whitened_rgb else img

def remove_white_background(img, tolerance):
    if img.mode != 'RGBA':
        try: img_rgba = img.convert('RGBA')
        except Exception as e: print(f"  ! Помилка convert->RGBA в remove_bg: {e}"); return img
    else: img_rgba = img.copy()
    datas = img_rgba.getdata(); newData = []; cutoff = 255 - tolerance
    try:
        for item in datas:
            if len(item) == 4 and item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff: newData.append((*item[:3], 0))
            else: newData.append(item)
        if len(newData) == img_rgba.width * img_rgba.height: img_rgba.putdata(newData)
        else: print(f"  ! Помилка розміру даних в remove_bg"); return img_rgba.copy()
    except Exception as e: print(f"  ! Помилка putdata в remove_bg: {e}"); return img_rgba.copy()
    return img_rgba

def crop_transparent_border(img):
    if img.mode != 'RGBA': print("  ! Попередження: crop очікує RGBA."); return img
    try: bbox = img.getbbox()
    except Exception: bbox = None
    if bbox and bbox[0] < bbox[2] and bbox[1] < bbox[3]:
        try: return img.crop(bbox)
        except Exception as e: print(f"  ! Помилка img.crop({bbox}): {e}"); return img
    return img

def add_padding(img, percent):
    if img is None or percent <= 0: return img
    w, h = img.size; pp = int(max(w, h) * (percent / 100.0))
    if w == 0 or h == 0 or pp == 0: return img
    nw, nh = w + 2*pp, h + 2*pp
    if img.mode != 'RGBA':
        try: img_rgba = img.convert('RGBA')
        except Exception as e: print(f"  ! Помилка convert->RGBA в add_padding: {e}"); return img
    else: img_rgba = img
    padded_img = Image.new('RGBA', (nw, nh), (0,0,0,0))
    try: padded_img.paste(img_rgba, (pp, pp), img_rgba)
    except Exception as e: print(f"  ! Помилка paste в add_padding: {e}"); return img_rgba
    return padded_img

def check_perimeter_is_white(img, tolerance, margin):
    if margin <= 0: return False
    try:
        if img.mode != 'RGB': img_rgb = img.convert('RGB')
        else: img_rgb = img.copy()
        width, height = img_rgb.size; pixels = img_rgb.load()
    except Exception as e: print(f"  ! Помилка підготовки check_perimeter: {e}"); return False
    mh = min(margin, height // 2 if height > 1 else 0); mw = min(margin, width // 2 if width > 1 else 0)
    if mh == 0 and height > 0: mh = 1
    if mw == 0 and width > 0: mw = 1
    if mh == 0 or mw == 0: return False
    cutoff = 255 - tolerance
    try:
        def is_white(x,y): p=pixels[x,y]; return isinstance(p,(tuple,list)) and len(p)>=3 and p[0]>=cutoff and p[1]>=cutoff and p[2]>=cutoff
        for y in range(mh):
            for x in range(width):
                if not is_white(x,y): return False
        for y in range(height - mh, height):
            for x in range(width):
                if not is_white(x,y): return False
        for x in range(mw):
            for y in range(mh, height - mh):
                 if not is_white(x,y): return False
        for x in range(width - mw, width):
            for y in range(mh, height - mh):
                 if not is_white(x,y): return False
    except Exception as e: print(f"  ! Помилка циклу check_perimeter: {e}"); return False
    # print("  - Перевірка периметра: Весь периметр білий.") # Debug
    return True
# --- Кінець функцій обробки ---


# --- ОНОВЛЕНА Основна функція обробки та перейменування ---
def rename_and_convert_images(
        input_path,                 # Папка ДЖЕРЕЛА (тільки читання)
        output_path,                # Папка РЕЗУЛЬТАТІВ (запис/перезапис)
        article_name,               # Артикул (або None для вимкнення перейменування)
        delete_originals,           # Прапорець: True - видаляти оригінали, False - ні
        preresize_width,            # Ширина для попереднього ресайзу (0 = вимк.)
        preresize_height,           # Висота для попереднього ресайзу (0 = вимк.)
        enable_whitening,           # Чи вмикати відбілювання?
        white_tolerance,            # Допуск для білого (або None для вимкнення видалення фону)
        perimeter_margin,           # Відступ для перевірки периметра
        padding_percent,            # Відсоток полів
        final_resize_width,         # Бажана ширина фінальна (0 = вимк.)
        final_resize_height,        # Бажана висота фінальна (0 = вимк.)
        backup_folder_path=None,    # Папка для резервних копій (опціонально)
    ):
    """
    Обробляє зображення з input_path, зберігає в output_path.
    Опціонально: бекапить, пре-ресайзить, відбілює, видаляє фон/обрізає,
    додає поля, фінально ресайзить, перейменовує, видаляє оригінали.
    """
    print(f"--- Параметри обробки ---")
    print(f"Папка ДЖЕРЕЛА: {input_path}")
    print(f"Папка РЕЗУЛЬТАТІВ: {output_path}")

    if not os.path.isdir(output_path):
        try: os.makedirs(output_path); print(f"  - Створено папку результатів.")
        except Exception as e: print(f"!! ПОМИЛКА створення папки '{output_path}': {e}. СКАСОВАНО."); return
    elif not os.path.exists(output_path): print(f"!! ПОМИЛКА: Шлях '{output_path}' існує, але не є папкою. СКАСОВАНО."); return

    enable_renaming_actual = bool(article_name and article_name.strip())
    if enable_renaming_actual: print(f"Артикул (для перейменування): {article_name}")
    else: print(f"Перейменування за артикулом: Вимкнено")
    print(f"Видалення оригіналів з '{input_path}': {'Так' if delete_originals else 'Ні'}")
    perform_preresize = preresize_width > 0 and preresize_height > 0
    if perform_preresize: print(f"Попередній ресайз: Так ({preresize_width}x{preresize_height}px)")
    else: print(f"Попередній ресайз: Ні")
    print(f"Відбілювання (периметр): {'Увімкнено' if enable_whitening else 'Вимкнено'}")
    enable_bg_removal = white_tolerance is not None
    if enable_bg_removal: print(f"Видалення білого фону: Так (допуск {white_tolerance})")
    else: print(f"Видалення білого фону: Ні")
    print(f"Перевірка периметра (поля): {perimeter_margin}px")
    print(f"Відсоток полів (якщо треба): {padding_percent}%")
    perform_final_resize = final_resize_width > 0 and final_resize_height > 0
    if perform_final_resize: print(f"Фінальний ресайз: Так ({final_resize_width}x{final_resize_height}px)")
    else: print(f"Фінальний ресайз: Ні")
    if backup_folder_path:
        print(f"Резервне копіювання: Увімкнено ({backup_folder_path})")
        if not os.path.exists(backup_folder_path):
            try: os.makedirs(backup_folder_path); print(f"  - Створено папку бекапів.")
            except Exception as e: print(f"!! Помилка створення папки бекапів: {e}")
    else: print(f"Резервне копіювання: Вимкнено")
    print("-" * 25)

    try:
        all_entries = os.listdir(input_path)
        files = natsorted([f for f in all_entries if os.path.isfile(os.path.join(input_path, f)) and not f.startswith("__temp_")])
        print(f"Знайдено файлів для аналізу в '{input_path}': {len(files)}")
    except FileNotFoundError: print(f"Помилка: Папку ДЖЕРЕЛА не знайдено - {input_path}"); return
    except Exception as e: print(f"Помилка читання папки {input_path}: {e}"); return

    processed_files_count = 0; skipped_files_count = 0; error_files_count = 0
    source_files_to_potentially_delete = [] # Шляхи до ОРИГІНАЛІВ
    processed_output_file_map = {}          # Словник: шлях_до_обробленого_файлу -> оригінальне_ім'я_без_розширення
    SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp')

    for file in files:
        source_file_path = os.path.join(input_path, file) # Шлях до оригіналу
        if not file.lower().endswith(SUPPORTED_EXTENSIONS):
             skipped_files_count += 1; continue

        print(f"\nОбробка файлу: {file}")
        img_current = None; img_to_save = None; success_flag = False
        try:
            # 1. Бекап
            if backup_folder_path:
                backup_file_path = os.path.join(backup_folder_path, file)
                try: shutil.copy2(source_file_path, backup_file_path);
                except Exception as backup_err: print(f"  !! Помилка бекапу: {backup_err}")

            # 2. Відкриття
            with Image.open(source_file_path) as img_original_loaded: img_original_loaded.load(); img_current = img_original_loaded.copy()
            print(f"  - Ориг. розмір: {img_current.size}")

            # 2.1 Перед. ресайз (опц.)
            if perform_preresize and img_current.size != (preresize_width, preresize_height):
                print(f"  - Крок 0: Перед. ресайз до {preresize_width}x{preresize_height}...")
                ow, oh = img_current.size
                if ow > 0 and oh > 0:
                    ratio = min(preresize_width / ow, preresize_height / oh); nw, nh = max(1, int(ow * ratio)), max(1, int(oh * ratio))
                    try:
                        resized_content = img_current.resize((nw, nh), Image.Resampling.LANCZOS)
                        pr_canvas = Image.new('RGB', (preresize_width, preresize_height), (255, 255, 255))
                        x, y = (preresize_width - nw)//2, (preresize_height - nh)//2
                        if resized_content.mode == 'RGBA': pr_canvas.paste(resized_content, (x, y), resized_content)
                        else: pr_canvas.paste(resized_content, (x, y))
                        img_current = pr_canvas; print(f"    - Новий розмір: {img_current.size}")
                    except Exception as pr_err: print(f"   ! Помилка перед. ресайзу: {pr_err}")

            # 3. Відбілювання (опц.)
            if enable_whitening:
                print("  - Крок 1: Відбілювання...")
                try: img_whitened = whiten_image_by_darkest_perimeter(img_current); img_current = img_whitened
                except Exception as wh_err: print(f"  !! Помилка відбілювання: {wh_err}")

            # 4. Перевірка периметра
            # print("  - Крок 2: Перевірка периметра...") # Менше логування
            should_add_padding = check_perimeter_is_white(img_current, white_tolerance if enable_bg_removal else 0, perimeter_margin)

            # 5, 6: Видалення фону та обрізка (опц.)
            img_after_bg_processing = None
            if enable_bg_removal:
                # print(f"  - Крок 3: Видалення фону...") # Менше логування
                try: img_rgba = img_current.convert('RGBA') if img_current.mode!='RGBA' else img_current
                except Exception as e: print(f"  !! Помилка convert->RGBA для фону: {e}"); img_after_bg_processing = img_current
                else:
                    img_no_bg = remove_white_background(img_rgba, white_tolerance)
                    # print("  - Крок 4: Обрізка країв...") # Менше логування
                    img_cropped = crop_transparent_border(img_no_bg)
                    if img_cropped is None or img_cropped.size[0]==0: print(f"   ! Порожнє після обрізки."); skipped_files_count += 1; continue
                    img_after_bg_processing = img_cropped
            else: # print("  - Кроки 3, 4: Видалення фону/обрізка вимкнені."); # Менше логування
                  img_after_bg_processing = img_current
            if img_after_bg_processing is None or img_after_bg_processing.size[0]==0: print(f"   ! Помилка після обробки фону."); skipped_files_count += 1; continue

            # 7. Додавання полів (опц.)
            img_before_final_resize = None
            if should_add_padding and padding_percent > 0 and perimeter_margin > 0:
                 # print(f"  - Крок 5: Додавання полів...") # Менше логування
                 try: img_rgba_pad = img_after_bg_processing.convert('RGBA') if img_after_bg_processing.mode!='RGBA' else img_after_bg_processing
                 except Exception as e: print(f"  !! Помилка convert->RGBA для полів: {e}"); img_before_final_resize = img_after_bg_processing
                 else:
                      img_padded = add_padding(img_rgba_pad, padding_percent)
                      if img_padded and img_padded.size[0]>0: img_before_final_resize = img_padded
                      else: print("  ! Помилка додавання полів."); img_before_final_resize = img_after_bg_processing
            else: img_before_final_resize = img_after_bg_processing
            if img_before_final_resize.size[0]==0: print("   ! Нульовий розмір перед фіналізацією."); skipped_files_count += 1; continue

            # 8. Фіналізація в RGB
            img_ready_for_final_resize = None
            # print("  - Крок 6: Фіналізація в RGB...") # Менше логування
            try:
                if img_before_final_resize.mode == 'RGBA':
                     img_final_rgb = Image.new("RGB", img_before_final_resize.size, (255, 255, 255))
                     img_final_rgb.paste(img_before_final_resize, (0, 0), img_before_final_resize)
                elif img_before_final_resize.mode != 'RGB': img_final_rgb = img_before_final_resize.convert('RGB')
                else: img_final_rgb = img_before_final_resize
                img_ready_for_final_resize = img_final_rgb
            except Exception as conv_err: print(f"  !! Помилка фіналізації в RGB: {conv_err}"); raise

            # 9. Фінальний ресайз (опц.)
            img_to_save = None
            if perform_final_resize and img_ready_for_final_resize.size != (final_resize_width, final_resize_height):
                print(f"  - Крок 7: Фінальний ресайз до {final_resize_width}x{final_resize_height}...")
                ow, oh = img_ready_for_final_resize.size
                if ow > 0 and oh > 0:
                    ratio = min(final_resize_width / ow, final_resize_height / oh)
                    nw, nh = max(1, int(ow * ratio)), max(1, int(oh * ratio))
                    try:
                        resized_img = img_ready_for_final_resize.resize((nw, nh), Image.Resampling.LANCZOS)
                        canvas = Image.new('RGB', (final_resize_width, final_resize_height), (255, 255, 255))
                        x, y = (final_resize_width - nw) // 2, (final_resize_height - nh) // 2
                        canvas.paste(resized_img, (x, y))
                        img_to_save = canvas
                    except Exception as resize_err: print(f"  ! Помилка фінального ресайзу: {resize_err}"); img_to_save = img_ready_for_final_resize
                else: img_to_save = img_ready_for_final_resize
            else: img_to_save = img_ready_for_final_resize

            # 10. Збереження РЕЗУЛЬТАТУ в output_path
            base_name = os.path.splitext(file)[0]
            output_filename = f"{base_name}.jpg" # ЗАВЖДИ зберігаємо як .jpg на цьому етапі
            final_output_path = os.path.join(output_path, output_filename) # Повний шлях для збереження
            print(f"  - Крок 8: Збереження обробленого JPG: {final_output_path}...")
            try:
                if img_to_save.mode != 'RGB': img_to_save = img_to_save.convert('RGB')
                # Перезаписуємо файл у папці output, якщо він вже існує
                img_to_save.save(final_output_path, "JPEG", quality=95, optimize=True, subsampling=0)
                processed_files_count += 1
                success_flag = True
                # Зберігаємо шлях до результату та оригінальне ім'я для перейменування
                processed_output_file_map[final_output_path] = base_name
                # Додаємо ОРИГІНАЛ до списку на можливе видалення
                if os.path.exists(source_file_path) and source_file_path not in source_files_to_potentially_delete:
                     source_files_to_potentially_delete.append(source_file_path)
            except Exception as save_err: print(f"  !! Помилка збереження JPG: {save_err}"); error_files_count += 1; continue

        # --- Обробка помилок ---
        except UnidentifiedImageError: print(f"!!! Помилка: Не розпізнано: {file}"); skipped_files_count += 1
        except FileNotFoundError: print(f"!!! Помилка: Файл не знайдено: {file}"); skipped_files_count += 1
        except OSError as e: print(f"!!! Помилка ОС ({file}): {e}"); error_files_count += 1
        except Exception as e:
            print(f"!!! Неочікувана помилка ({file}): {e}"); traceback.print_exc(); error_files_count += 1
            if not success_flag and source_file_path in source_files_to_potentially_delete:
                 try: source_files_to_potentially_delete.remove(source_file_path);
                 except ValueError: pass
        finally: # Зачистка
            if 'img_current' in locals() and img_current:
                try: img_current.close();
                except Exception: pass
            if 'img_to_save' in locals() and img_to_save:
                try: img_to_save.close();
                except Exception: pass

    print(f"\n--- Статистика обробки ---"); print(f"  - Успішно збережено: {processed_files_count}"); print(f"  - Пропущено/Помилки: {skipped_files_count + error_files_count}")

    # Видалення ОРИГІНАЛІВ з input_path (якщо увімкнено)
    if delete_originals and source_files_to_potentially_delete:
        print(f"\nВидалення {len(source_files_to_potentially_delete)} оригінальних файлів з '{input_path}'...")
        removed_count = 0; remove_errors = 0
        for file_to_remove in source_files_to_potentially_delete:
            try:
                if os.path.exists(file_to_remove): os.remove(file_to_remove); removed_count += 1
            except Exception as remove_error: print(f"  ! Помилка видалення {os.path.basename(file_to_remove)}: {remove_error}"); remove_errors += 1
        print(f"  - Видалено: {removed_count}. Помилок: {remove_errors}.")
    elif not delete_originals: print(f"\nВидалення оригіналів з '{input_path}' вимкнено.")
    else: print(f"\nНемає оригінальних файлів для видалення.")


    # --- ОНОВЛЕНЕ Перейменування (у папці РЕЗУЛЬТАТІВ output_path) ---
    if enable_renaming_actual:
        print(f"\n--- Перейменування файлів у '{output_path}' ---")
        # Використовуємо список успішно збережених файлів
        files_to_rename = list(processed_output_file_map.keys())
        print(f"Файлів для потенційного перейменування: {len(files_to_rename)}")

        if files_to_rename:
            exact_match_filename_final = f"{article_name}.jpg"
            exact_match_temp_path = None # Шлях до файлу, який треба перейменувати в exact_match_filename_final
            files_to_rename_numerically_temp = [] # Список шляхів до файлів для нумерації

            # Розділяємо файли на той, що співпадає з артикулом, і решту
            for temp_output_path in files_to_rename:
                 original_basename = processed_output_file_map.get(temp_output_path)
                 if original_basename and original_basename.lower() == article_name.lower():
                      if exact_match_temp_path is None: # Знайшли перший
                           exact_match_temp_path = temp_output_path
                      else: # Знайшли другий і далі - вони підуть в нумерацію
                           print(f"  ! Попередження: Знайдено дублікат артикулу для '{os.path.basename(temp_output_path)}'. Буде пронумеровано.")
                           files_to_rename_numerically_temp.append(temp_output_path)
                 else:
                      files_to_rename_numerically_temp.append(temp_output_path)

            # Використовуємо двохетапне перейменування для надійності
            temp_rename_map_final = {} # temporary_path -> final_path
            print("  - Крок 1: Перейменування у тимчасові імена...")
            temp_counter = 0; rename_errors_temp = 0
            processed_for_temp_rename_final = set() # Щоб уникнути подвійного перейменування

            all_temp_paths = []
            if exact_match_temp_path: all_temp_paths.append(exact_match_temp_path)
            all_temp_paths.extend(files_to_rename_numerically_temp)

            for current_path in all_temp_paths:
                 if current_path in processed_for_temp_rename_final: continue
                 # Створюємо унікальне тимчасове ім'я в тій же папці output_path
                 temp_filename = f"__temp_{temp_counter}_{os.path.basename(current_path)}"
                 temp_path_stage2 = os.path.join(output_path, temp_filename)
                 try:
                     os.rename(current_path, temp_path_stage2)
                     # Зберігаємо відповідність для наступного кроку
                     temp_rename_map_final[temp_path_stage2] = current_path # Ключ - новий тимчасовий шлях, значення - попередній тимчасовий шлях (__processed_)
                     processed_for_temp_rename_final.add(temp_path_stage2)
                     temp_counter += 1
                 except Exception as rename_error: print(f"  ! Помилка тимч. перейменування '{os.path.basename(current_path)}': {rename_error}"); rename_errors_temp += 1
            if rename_errors_temp > 0: print(f"  ! Помилок тимчасового перейменування: {rename_errors_temp}")


            print("  - Крок 2: Фінальне перейменування...")
            final_rename_counter = 1; rename_errors_final = 0; renamed_final_count = 0

            # Обробляємо файл артикулу
            final_exact_path = os.path.join(output_path, exact_match_filename_final)
            found_temp_exact = None
            # Шукаємо тимчасовий шлях (__temp_...) для файлу артикулу
            for temp_s2_path, temp_s1_path in temp_rename_map_final.items():
                 if exact_match_temp_path and os.path.normcase(temp_s1_path) == os.path.normcase(exact_match_temp_path):
                      found_temp_exact = temp_s2_path
                      break
            if found_temp_exact:
                 try:
                      os.rename(found_temp_exact, final_exact_path); renamed_final_count += 1
                      print(f"    - '{os.path.basename(found_temp_exact)}' -> '{exact_match_filename_final}'")
                      # Видаляємо зі словника, щоб не обробляти його далі
                      del temp_rename_map_final[found_temp_exact]
                 except Exception as rename_error: print(f"  ! Помилка фін. перейм. '{os.path.basename(found_temp_exact)}': {rename_error}"); rename_errors_final += 1
            elif exact_match_temp_path: # Якщо оригінал був, але не вдалося знайти тимчасовий
                 print(f"  ! Не вдалося знайти тимчасовий файл для артикулу: {os.path.basename(exact_match_temp_path)}")


            # Обробляємо решту файлів (нумеровані)
            # Сортуємо за оригінальним іменем, яке заховане в тимчасовому імені __temp_...
            remaining_temp_files = list(temp_rename_map_final.keys())
            try: sorted_remaining_temp = natsorted(remaining_temp_files, key=lambda x: '_'.join(os.path.basename(x).split('_')[3:]))
            except Exception as sort_err: print(f"  ! Помилка сортування: {sort_err}"); sorted_remaining_temp = remaining_temp_files

            for temp_path_s2 in sorted_remaining_temp:
                final_numbered_filename = f"{article_name}_{final_rename_counter}.jpg"
                final_numbered_path = os.path.join(output_path, final_numbered_filename)
                try:
                    os.rename(temp_path_s2, final_numbered_path); renamed_final_count += 1; final_rename_counter += 1
                    print(f"    - '{os.path.basename(temp_path_s2)}' -> '{final_numbered_filename}'")
                except Exception as rename_error: print(f"  ! Помилка фін. перейм. '{os.path.basename(temp_path_s2)}': {rename_error}"); rename_errors_final += 1

            print(f"\n  - Перейменовано файлів: {renamed_final_count}. Помилок: {rename_errors_final}.")
            # Перевірка на залишкові тимчасові файли __temp_...
            remaining_temp_final = [f for f in os.listdir(output_path) if f.startswith("__temp_")];
            if remaining_temp_final: print(f"  ! Увага: Залишилися тимчасові файли в '{output_path}': {remaining_temp_final}")
        else:
            print("Немає успішно оброблених файлів для перейменування.")
    else:
        print("\n--- Перейменування файлів пропущено (вимкнено через налаштування артикулу) ---")
# --- Кінець функції rename_and_convert_images ---


# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":

    # --- Налаштування користувача ---

    # === Шляхи до папок ===
    # Важливо: Використовуйте 'r' перед шляхами у Windows або подвійні '\\'.

    # Папка, де знаходяться ВАШІ ОРИГІНАЛЬНІ зображення.
    # Скрипт буде тільки ЧИТАТИ з цієї папки (крім випадку, коли delete_originals = True).
    input_folder_path = r"C:\Users\zakhar\Downloads\test3"  # !!! ВАШ ШЛЯХ ДО ОРИГІНАЛІВ

    # Папка, куди будуть збережені ОБРОБЛЕНІ зображення у форматі JPG.
    # Якщо папка не існує, скрипт спробує її створити.
    # Якщо встановити None, буде автоматично створена підпапка 'output_processed'
    # всередині папки з оригіналами (input_folder_path).
    output_folder_path = r"C:\Users\zakhar\Downloads\test3" # !!! ВАШ ШЛЯХ або None

    # (Опціонально) Папка для РЕЗЕРВНИХ КОПІЙ оригіналів.
    # Сюди будуть скопійовані ваші вихідні файли ПЕРЕД обробкою.
    # Якщо встановити None, резервне копіювання не виконується.
    backup_folder_path = r"C:\Users\zakhar\Downloads\test_py_bak" # !!! ВАШ ШЛЯХ або None

    # === Налаштування Перейменування та Видалення ===

    # Вкажіть артикул (базове ім'я) для перейменування оброблених файлів у папці результатів.
    # - Якщо вказати рядок (напр., "MyProduct123"), то:
    #   - Файл, оригінальне ім'я якого (без розширення) співпадає з артикулом,
    #     буде названо "{article}.jpg".
    #   - Решта файлів будуть названі "{article}_1.jpg", "{article}_2.jpg", ...
    # - Якщо встановити None або порожній рядок "", перейменування за артикулом
    #   НЕ БУДЕ виконуватися, і файли в папці результатів залишаться
    #   з іменами '{оригінальне_ім'я}.jpg'.
    article = "X38"                 # !!! ВАШ артикул або None

    # Встановити True, щоб ВИДАЛИТИ оригінальні файли з папки ДЖЕРЕЛА
    # (input_folder_path) ПІСЛЯ їх успішної обробки та збереження результату.
    # Встановити False, щоб НЕ видаляти оригінали.
    # УВАГА: Видалення незворотнє! Рекомендується використовувати разом з резервним копіюванням.
    delete_originals_after_processing = False # !!! True або False

    # === Попередній Ресайз (До основної обробки) ===
    # Зменшує розмір зображення ДО початку обробки (відбілювання, фон і т.д.).
    # Корисно, якщо вихідні файли дуже великі, а фінальний результат все одно
    # буде меншим, щоб прискорити обробку.
    # Зображення вписується в зазначені розміри зі збереженням пропорцій,
    # вільний простір заповнюється білим.
    # Встановіть 0 для ширини АБО висоти, щоб ВИМКНУТИ цей крок.
    preresize_width = 0                     # !!! Бажана ширина (0 для вимкнення)
    preresize_height = 0                    # !!! Бажана висота (0 для вимкнення)

    # === Відбілювання ===
    # Вмикає/вимикає функцію автоматичного відбілювання.
    # Аналізує ПЕРИМЕТР зображення (після попереднього ресайзу, якщо він був),
    # знаходить найтемніший піксель і коригує кольори, щоб він став білим.
    enable_whitening = True                 # !!! True або False

    # === Параметри Обробки Зображень (Після відбілювання) ===

    # Допуск для білого кольору (0-255).
    # Впливає на видалення фону та перевірку периметра.
    # Встановіть None, щоб ПОВНІСТЮ ВИМКНУТИ видалення білого фону
    # та обрізку по прозорості (кроки 3 і 4).
    tolerance_for_white = 15                # !!! Число 0-255 або None

    # Відступ в пікселях від краю для перевірки периметра на білий колір
    # (використовується для умовного додавання полів).
    # Встановіть 0, щоб ВИМКНУТИ цю перевірку (і залежне від неї додавання полів).
    perimeter_check_margin_pixels = 3       # !!! 0 або більше

    # Відсоток полів, що додаються, ЯКЩО perimeter_check_margin > 0 і периметр визнано білим.
    # Встановіть 0.0, щоб ВИМКНУТИ додавання полів, навіть якщо умова виконана.
    padding_percentage = 5.0                # !!! 0.0 або більше

    # === Фінальний Ресайз (Після всіх обробок) ===
    # Змінює розмір ГОТОВОГО зображення (після видалення фону, полів і т.д.)
    # перед збереженням у фінальний JPG.
    # Зображення вписується у зазначені розміри зі збереженням пропорцій,
    # вільний простір заповнюється білим.
    # Встановіть 0 для ширини АБО висоти, щоб ВИМКНУТИ цей крок.
    final_resize_width = 1500               # !!! Бажана ширина (0 для вимкнення)
    final_resize_height = 1500              # !!! Бажана висота (0 для вимкнення)

    # --- Кінець Налаштувань Користувача ---


    # --- Логіка визначення шляху результатів, якщо не вказано ---
    if output_folder_path is None:
        output_folder_path = os.path.join(input_folder_path, "output_processed")
        print(f"* Папку результатів не вказано, буде використано: {output_folder_path}")
    # --- ---

    # --- Запуск Скрипта ---
    print("--- Початок роботи скрипту ---")
    if not os.path.isdir(input_folder_path):
         print(f"\nПомилка: Вказана папка ДЖЕРЕЛА не існує: {input_folder_path}")
    else:
         rename_and_convert_images(
             input_path=input_folder_path,
             output_path=output_folder_path,
             article_name=article,
             delete_originals=delete_originals_after_processing,
             preresize_width=preresize_width,
             preresize_height=preresize_height,
             enable_whitening=enable_whitening,
             white_tolerance=tolerance_for_white,
             perimeter_margin=perimeter_check_margin_pixels,
             padding_percent=padding_percentage,
             final_resize_width=final_resize_width,
             final_resize_height=final_resize_height,
             backup_folder_path=backup_folder_path,
         )
         print("\n--- Робота скрипту завершена ---")