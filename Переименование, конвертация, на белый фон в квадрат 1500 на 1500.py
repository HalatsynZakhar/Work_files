import os
import math
# Переконайтесь, що Pillow встановлено: pip install Pillow
from PIL import Image, ImageChops, UnidentifiedImageError, ImageFile
# Переконайтесь, що natsort встановлено: pip install natsort
try:
    from natsort import natsorted
except ImportError:
    print("ПОПЕРЕДЖЕННЯ: Бібліотека natsort не знайдена. Сортування буде стандартним.")
    natsorted = sorted # Заміна на стандартну функцію сортування
import traceback # Для детальних помилок
import sys # Для перевірки бібліотек
import shutil # Для копіювання файлів (резервне копіювання)

# --- Перевірка наявності бібліотек ---
try:
    import PIL
except ImportError:
    print("Помилка: Pillow не знайдена.")
    sys.exit(1)
# --- ---

ImageFile.LOAD_TRUNCATED_IMAGES = True # Дозволяє завантажувати "обрізані" або пошкоджені файли

# --- Функції обробки зображення ---

# Функція безпечного закриття (додано для надійності)
def safe_close(img_obj):
    """Безпечно закриває об'єкт Image, ігноруючи помилки."""
    if img_obj and isinstance(img_obj, Image.Image):
        try:
            img_obj.close()
        except Exception:
            pass # Ігноруємо помилки при закритті

def whiten_image_by_darkest_perimeter(img, cancel_threshold_sum):
    """
    Відбілює зображення, використовуючи найтемніший піксель ПЕРИМЕТРУ
    (1px рамка) як референс для білого.
    Перевіряє найтемніший піксель на поріг темряви перед відбілюванням.
    Працює з копією зображення. Повертає нове зображення або оригінал.
    """
    print("    - Функція відбілювання (за пікселем периметру)...")
    img_copy = None; img_rgb = None; alpha_channel = None; img_whitened_rgb = None
    final_image = img # Повернемо оригінал за замовчуванням

    try:
        img_copy = img.copy() # Починаємо з копії
        original_mode = img_copy.mode
        has_alpha = 'A' in img_copy.getbands()

        # Готуємо RGB версію та альфу (якщо є)
        if original_mode == 'RGBA' and has_alpha:
            split_bands = img_copy.split()
            if len(split_bands) == 4:
                img_rgb = Image.merge('RGB', split_bands[:3])
                alpha_channel = split_bands[3]
                for band in split_bands[:3]: safe_close(band) # Закриваємо вихідні RGB канали
            else:
                raise ValueError(f"Очікувалось 4 канали в RGBA, отримано {len(split_bands)}")
        elif original_mode != 'RGB':
            img_rgb = img_copy.convert('RGB') # Конвертуємо з копії
        else:
            img_rgb = img_copy.copy() # Створюємо окрему RGB копію

        width, height = img_rgb.size
        if width <= 1 or height <= 1:
            print("      ! Зображення замале для аналізу периметру. Скасовано.")
            final_image = img_copy # Повернемо початкову копію
            img_copy = None # Щоб не закрити у finally
            safe_close(img_rgb); safe_close(alpha_channel)
            return final_image

        darkest_pixel_rgb = None; min_sum = float('inf')
        pixels = img_rgb.load()
        perimeter_pixels = []
        if height > 0: perimeter_pixels.extend([(x, 0) for x in range(width)])
        if height > 1: perimeter_pixels.extend([(x, height - 1) for x in range(width)])
        if width > 0: perimeter_pixels.extend([(0, y) for y in range(1, height - 1)])
        if width > 1: perimeter_pixels.extend([(width - 1, y) for y in range(1, height - 1)])

        for x, y in perimeter_pixels:
            try:
                pixel = pixels[x, y]
                if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                    r, g, b = pixel[:3]
                    if all(isinstance(val, int) for val in (r, g, b)):
                        current_sum = r + g + b
                        if current_sum < min_sum: min_sum = current_sum; darkest_pixel_rgb = (r, g, b)
                elif isinstance(pixel, int): # Для 'L'
                    current_sum = pixel * 3
                    if current_sum < min_sum: min_sum = current_sum; darkest_pixel_rgb = (pixel, pixel, pixel)
            except Exception: continue # Пропускаємо піксель при помилці

        if darkest_pixel_rgb is None:
            print("      ! Не знайдено валідних пікселів периметру. Скасовано.")
            final_image = img_copy; img_copy = None
            safe_close(img_rgb); safe_close(alpha_channel)
            return final_image

        ref_r, ref_g, ref_b = darkest_pixel_rgb
        current_pixel_sum = ref_r + ref_g + ref_b
        print(f"      - Знайдений найтемніший піксель: R={ref_r}, G={ref_g}, B={ref_b} (Сума: {current_pixel_sum})")
        print(f"      - Поріг скасування відбілювання (мін. сума): {cancel_threshold_sum}")

        if current_pixel_sum < cancel_threshold_sum:
            print(f"      ! Найтемніший піксель (сума {current_pixel_sum}) темніший за поріг ({cancel_threshold_sum}). Відбілювання скасовано.")
            final_image = img_copy; img_copy = None
            safe_close(img_rgb); safe_close(alpha_channel)
            return final_image

        if ref_r == 255 and ref_g == 255 and ref_b == 255:
            print("      - Найтемніший піксель вже білий. Відбілювання не потрібне.")
            final_image = img_copy; img_copy = None
            safe_close(img_rgb); safe_close(alpha_channel)
            return final_image

        print(f"      - Референс для відбілювання: R={ref_r}, G={ref_g}, B={ref_b}")
        scale_r = 255.0 / max(1.0, float(ref_r)); scale_g = 255.0 / max(1.0, float(ref_g)); scale_b = 255.0 / max(1.0, float(ref_b))
        print(f"      - Множники: R*={scale_r:.3f}, G*={scale_g:.3f}, B*={scale_b:.3f}")
        lut_r = bytes([min(255, round(i * scale_r)) for i in range(256)])
        lut_g = bytes([min(255, round(i * scale_g)) for i in range(256)])
        lut_b = bytes([min(255, round(i * scale_b)) for i in range(256)])
        lut = lut_r + lut_g + lut_b

        # Застосовуємо LUT до каналів RGB
        img_whitened_rgb = img_rgb.point(lut * (len(img_rgb.getbands()) // 3))
        print("      - LUT застосовано до RGB частини.")

        if alpha_channel:
            print("      - Відновлення альфа-каналу...")
            if img_whitened_rgb.size == alpha_channel.size:
                 img_whitened_rgb.putalpha(alpha_channel)
                 final_image = img_whitened_rgb # Результат - відбілений RGBA
                 img_whitened_rgb = None # Обнуляємо
                 print("      - Відбілювання з альфа-каналом завершено.")
            else:
                 print(f"      ! Невідповідність розмірів при додаванні альфа ({img_whitened_rgb.size} vs {alpha_channel.size}). Повернення відбіленого RGB.")
                 final_image = img_whitened_rgb # Повертаємо тільки RGB
                 img_whitened_rgb = None
        else:
            final_image = img_whitened_rgb # Результат - відбілений RGB
            img_whitened_rgb = None
            print("      - Відбілювання (без альфа-каналу) завершено.")

    except Exception as e:
        print(f"      ! Помилка під час відбілювання: {e}. Повертається копія.")
        traceback.print_exc(limit=1) # Додамо трохи деталей помилки
        final_image = img_copy if img_copy else img # Повертаємо копію, якщо вона є
        img_copy = None # Не закривати у finally
        # img_rgb та alpha_channel закриються у finally
    finally:
        safe_close(alpha_channel)
        # Закриваємо img_rgb, якщо він не є вихідною копією (img_copy)
        if img_rgb and img_rgb is not img_copy:
             safe_close(img_rgb)
        safe_close(img_whitened_rgb) # Закриваємо, якщо він не став final_image
        safe_close(img_copy) # Закриваємо копію, якщо вона не стала final_image

    return final_image

def remove_white_background(img, tolerance):
    """Перетворює білі пікселі на прозорі."""
    img_rgba = None; original_mode = img.mode; was_converted = False
    final_image = img
    try:
        if original_mode != 'RGBA':
            try: img_rgba = img.convert('RGBA'); was_converted = True; print(f"  - Конвертовано {original_mode} -> RGBA для видалення фону.")
            except Exception as e: print(f"  ! Помилка convert->RGBA в remove_bg: {e}"); return img
        else: img_rgba = img.copy(); print("  - Створено копію RGBA для видалення фону.")

        datas = list(img_rgba.getdata()); newData = []; cutoff = 255 - tolerance; pixels_changed = 0
        if datas and isinstance(datas[0], (tuple, list)) and len(datas[0]) == 4:
            for r, g, b, a in datas:
                if a > 0 and r >= cutoff and g >= cutoff and b >= cutoff: newData.append((r, g, b, 0)); pixels_changed += 1
                else: newData.append((r, g, b, a))
        else: print(f"  ! Неочікуваний формат даних пікселів в remove_bg (перший елемент: {datas[0] if datas else 'None'}). Скасовано."); safe_close(img_rgba); return img
        del datas
        if pixels_changed > 0:
            print(f"  - Пікселів зроблено прозорими: {pixels_changed}")
            if len(newData) == img_rgba.width * img_rgba.height:
                try: img_rgba.putdata(newData); final_image = img_rgba; img_rgba = None
                except Exception as e: print(f"  ! Помилка putdata в remove_bg: {e}"); final_image = img # Помилка, повертаємо оригінал
            else: print(f"  ! Помилка розміру даних в remove_bg (очікувалось {img_rgba.width * img_rgba.height}, отримано {len(newData)})"); final_image = img # Помилка, повертаємо оригінал
        else:
            print("  - Не знайдено білих пікселів для видалення фону (або всі вже прозорі).")
            if was_converted: final_image = img_rgba; img_rgba = None # Повертаємо конвертований RGBA
            else: final_image = img # Повертаємо оригінал, якщо він вже був RGBA

    except Exception as e: print(f"  ! Загальна помилка в remove_bg: {e}"); traceback.print_exc(); final_image = img # Повертаємо оригінал у разі помилки
    finally:
        safe_close(img_rgba) # Закриваємо копію/конвертований, якщо він не став final_image

    return final_image

def crop_image(img, symmetric_axes=False, symmetric_absolute=False):
    """Обрізає зображення з опціями симетрії та відступом 1px."""
    img_rgba = None; cropped_img = None; original_mode = img.mode
    final_image = img
    try:
        # Завжди працюємо з копією RGBA для getbbox, щоб не змінити оригінал
        if original_mode != 'RGBA':
            print("  - Попередження: crop_image конвертує в RGBA для визначення меж.");
            try: img_rgba = img.convert('RGBA')
            except Exception as e: print(f"    ! Не вдалося конвертувати в RGBA: {e}. Обрізку скасовано."); return img
        else: img_rgba = img.copy()

        bbox = img_rgba.getbbox()
        if not bbox: print("  - Не знайдено непрозорих пікселів (bbox is None). Обрізку пропущено."); final_image = img_rgba; img_rgba = None # Повертаємо RGBA версію, бо може бути корисною далі
        else:
            original_width, original_height = img_rgba.size; left, upper, right, lower = bbox
            if left >= right or upper >= lower: print(f"  ! Невалідний bbox: {bbox}. Обрізку скасовано."); final_image = img_rgba; img_rgba = None
            else:
                print(f"  - Знайдений bbox непрозорих пікселів: L={left}, T={upper}, R={right}, B={lower}")
                crop_l, crop_u, crop_r, crop_b = left, upper, right, lower
                if symmetric_absolute:
                    print("  - Режим обрізки: Абсолютно симетричний від країв зображення")
                    dist_left = left; dist_top = upper; dist_right = original_width - right; dist_bottom = original_height - lower
                    min_dist = min(dist_left, dist_top, dist_right, dist_bottom)
                    print(f"    - Відступи: L={dist_left}, T={dist_top}, R={dist_right}, B={dist_bottom} -> Мін. відступ: {min_dist}")
                    new_left = min_dist; new_upper = min_dist; new_right = original_width - min_dist; new_lower = original_height - min_dist
                    if new_left < new_right and new_upper < new_lower: crop_l, crop_u, crop_r, crop_b = new_left, new_upper, new_right, new_lower
                    else: print(f"    ! Розраховані абс. симетричні межі невалідні. Використання bbox.")
                elif symmetric_axes:
                    print("  - Режим обрізки: Симетричний по осях відносно центру bbox")
                    center_x = (left + right) / 2.0; center_y = (upper + lower) / 2.0
                    max_reach_x = max(center_x, original_width - center_x); max_reach_y = max(center_y, original_height - center_y)
                    new_width = 2 * max_reach_x; new_height = 2 * max_reach_y
                    new_left = max(0, center_x - (new_width / 2.0)); new_upper = max(0, center_y - (new_height / 2.0))
                    new_right = min(original_width, center_x + (new_width / 2.0)); new_lower = min(original_height, center_y + (new_height / 2.0))
                    nl_int, nu_int = int(new_left), int(new_upper); nr_int, nb_int = int(math.ceil(new_right)), int(math.ceil(new_lower))
                    if nl_int < nr_int and nu_int < nb_int: crop_l, crop_u, crop_r, crop_b = nl_int, nu_int, nr_int, nb_int; print(f"    - Розраховано осі. симетричні межі: L={crop_l}, T={crop_u}, R={crop_r}, B={crop_b}")
                    else: print(f"    ! Розраховані осі. симетричні межі невалідні. Використання bbox.")
                else: print("  - Режим обрізки: Стандартний (за bbox)")

                final_left = max(0, crop_l - 1); final_upper = max(0, crop_u - 1)
                final_right = min(original_width, crop_r + 1); final_lower = min(original_height, crop_b + 1)
                final_crop_box = (final_left, final_upper, final_right, final_lower)

                if final_crop_box == (0, 0, original_width, original_height): print("  - Фінальний crop_box відповідає розміру зображення. Обрізка не потрібна."); final_image = img_rgba; img_rgba = None
                else:
                     print(f"  - Фінальний crop_box (з відступом 1px): {final_crop_box}")
                     try:
                          # Робимо обрізку на RGBA копії
                          cropped_img = img_rgba.crop(final_crop_box);
                          print(f"    - Новий розмір після обрізки: {cropped_img.size}")
                          final_image = cropped_img; cropped_img = None # Результат - нове обрізане зображення
                     except Exception as e: print(f"  ! Помилка під час img_rgba.crop({final_crop_box}): {e}. Обрізку скасовано."); final_image = img_rgba; img_rgba = None # Повертаємо RGBA версію без обрізки

    except Exception as general_error: print(f"  ! Загальна помилка в crop_image: {general_error}"); traceback.print_exc(); final_image = img # У разі помилки повертаємо початковий
    finally:
        # Закриваємо проміжні об'єкти, тільки якщо вони не є фінальним результатом
        safe_close(img_rgba if img_rgba is not final_image else None)
        safe_close(cropped_img if cropped_img is not final_image else None)

    return final_image

def add_padding(img, percent):
    """Додає прозорі поля навколо зображення."""
    if img is None or percent <= 0: return img
    w, h = img.size
    if w == 0 or h == 0: print("  ! Попередження в add_padding: Вхідне зображення має нульовий розмір."); return img
    pp = int(round(max(w, h) * (percent / 100.0)))
    if pp <= 0: return img
    nw, nh = w + 2*pp, h + 2*pp
    # print(f"  - Додавання полів: {percent}% ({pp}px). Новий розмір: {nw}x{nh}") # Повідомлення перенесено вище
    padded_img = None; img_rgba_src = None; final_image = img
    try:
        img_rgba_src = img if img.mode == 'RGBA' else img.convert('RGBA') # Переконуємось, що RGBA
        padded_img = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
        padded_img.paste(img_rgba_src, (pp, pp), img_rgba_src if img_rgba_src.mode == 'RGBA' else None)
        # print(f"    - Зображення вставлено на новий холст.") # Повідомлення перенесено
        final_image = padded_img; padded_img = None
    except Exception as e: print(f"  ! Помилка paste або інша в add_padding: {e}"); traceback.print_exc(); final_image = img
    finally:
        if img_rgba_src is not img: safe_close(img_rgba_src) # Закриваємо конвертовану копію
        safe_close(padded_img) # Закриваємо проміжний, якщо не став результатом

    return final_image

def check_perimeter_is_white(img, tolerance, margin):
    """Перевіряє, чи є периметр зображення білим (з допуском)."""
    if img is None or margin <= 0: return False
    img_to_check = None; created_new_object = False; mask = None
    is_white = False # За замовчуванням - не білий
    try:
        # Готуємо RGB копію, накладаючи на білий фон, якщо є альфа
        if img.mode == 'RGBA' or 'A' in img.getbands():
            img_to_check = Image.new("RGB", img.size, (255, 255, 255)); created_new_object = True
            try:
                if img.mode == 'RGBA': mask = img.split()[-1]
                else:
                    with img.convert('RGBA') as temp_rgba: mask = temp_rgba.split()[-1]
                img_to_check.paste(img, mask=mask)
            except Exception as mask_err:
                # print(f"      ! Попередження: не вдалося використати альфа-канал для перевірки периметру ({mask_err}).") # Debug
                try:
                     with img.convert('RGB') as rgb_ver: img_to_check.paste(rgb_ver)
                except Exception as paste_err: print(f"      ! Не вдалося навіть вставити RGB версію: {paste_err}"); return False # Не можемо перевірити
        elif img.mode != 'RGB':
             try: img_to_check = img.convert('RGB'); created_new_object = True
             except Exception as conv_e: print(f"  ! Помилка convert({img.mode}->RGB) в check_perimeter: {conv_e}"); return False
        else: img_to_check = img # Використовуємо оригінал, якщо він RGB

        width, height = img_to_check.size
        if width <= 0 or height <= 0: print(f"  ! Зображення має нульовий розмір ({width}x{height})."); return False
        mh = min(margin, height // 2 if height > 0 else 0); mw = min(margin, width // 2 if width > 0 else 0)
        if mh == 0 and height > 0 and margin > 0: mh = 1
        if mw == 0 and width > 0 and margin > 0: mw = 1
        if mh == 0 or mw == 0: print(f"  ! Неможливо перевірити периметр з відступом {margin}px на зображенні {width}x{height}."); return False

        pixels = img_to_check.load(); cutoff = 255 - tolerance; is_perimeter_white = True
        perimeter_coords = set()
        if mh > 0:
            perimeter_coords.update([(x, y) for y in range(mh) for x in range(width)]) # Top
            perimeter_coords.update([(x, y) for y in range(height - mh, height) for x in range(width)]) # Bottom
        if mw > 0:
            perimeter_coords.update([(x, y) for x in range(mw) for y in range(mh, height - mh)]) # Left
            perimeter_coords.update([(x, y) for x in range(width - mw, width) for y in range(mh, height - mh)]) # Right

        for x, y in perimeter_coords:
            try:
                pixel_data = pixels[x, y]
                if isinstance(pixel_data, (tuple, list)) and len(pixel_data) >= 3: r, g, b = pixel_data[:3]
                elif isinstance(pixel_data, int): r, g, b = pixel_data, pixel_data, pixel_data
                else: is_perimeter_white = False; break
                if not (r >= cutoff and g >= cutoff and b >= cutoff): is_perimeter_white = False; break
            except (IndexError, TypeError, Exception): is_perimeter_white = False; break

        is_white = is_perimeter_white # Зберігаємо результат
        print(f"  - Перевірка периметра ({margin}px, допуск {tolerance}): Периметр визначено як {'білий' if is_white else 'НЕ білий'}.")

    except Exception as e: print(f"  ! Загальна помилка в check_perimeter: {e}"); traceback.print_exc(); is_white = False
    finally:
         safe_close(mask) # Закриваємо альфа-канал, якщо він був виділений
         if created_new_object and img_to_check: safe_close(img_to_check) # Закриваємо створену копію/холст

    return is_white

# --- Кінець функцій обробки ---

# --- Основна функція обробки та перейменування ---
# <<< МОДИФІКАЦІЯ: Додано параметр allow_expansion >>>
def rename_and_convert_images(
        input_path,                 # Папка ДЖЕРЕЛА
        output_path,                # Папка РЕЗУЛЬТАТІВ
        article_name,               # Артикул
        delete_originals,           # Видаляти оригінали?
        preresize_width,            # Перед. ресайз ширина
        preresize_height,           # Перед. ресайз висота
        enable_whitening,           # Відбілювання?
        whitening_cancel_threshold, # Поріг темряви для скасування відбілювання (сума RGB)
        white_tolerance,            # Допуск білого (фон/обрізка)
        perimeter_margin,           # Перевірка периметра (для умовних полів)
        crop_symmetric_axes,        # Обрізка симетр. осі
        crop_symmetric_absolute,    # Обрізка симетр. абс.
        padding_percent,            # Поля %
        allow_expansion,            # <<< НОВИЙ ПАРАМЕТР: Дозволити збільшення розміру полями?
        force_aspect_ratio,         # Примусове співвідношення сторін (напр., (1,1) або None)
        max_output_width,           # Макс. ширина (0 = без обмеження)
        max_output_height,          # Макс. висота (0 = без обмеження)
        final_exact_width,          # Точна ширина фінального холсту (0 = вимкнено)
        final_exact_height,         # Точна висота фінального холсту (0 = вимкнено)
        output_format,              # Формат 'jpg' або 'png'
        jpg_background_color,       # Колір фону для JPG (R, G, B)
        jpeg_quality,               # Якість JPG
        backup_folder_path=None,    # Папка бекапів
    ):
    """
    Обробляє зображення: відбілювання, фон/обрізка, поля, пропорції, макс.розмір,
    фінальний холст, збереження, перейменування.
    """
    # --- Валідація параметрів на початку ---
    output_format_lower = output_format.lower()
    if output_format_lower not in ['jpg', 'png']: print(f"!! ПОМИЛКА: Непідтримуваний формат виводу '{output_format}'. СКАСОВАНО."); return
    abs_input_path = os.path.abspath(input_path); abs_output_path = os.path.abspath(output_path)
    abs_backup_path = os.path.abspath(backup_folder_path) if backup_folder_path and backup_folder_path.strip() else None
    if abs_backup_path:
        if abs_backup_path == abs_input_path: print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою джерела. Бекап вимкнено."); abs_backup_path = None
        elif abs_backup_path == abs_output_path: print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою результатів. Бекап вимкнено."); abs_backup_path = None
    safe_to_delete = abs_input_path != abs_output_path
    if delete_originals and not safe_to_delete: print(f"!! ПОПЕРЕДЖЕННЯ: Видалення оригіналів увімкнено, але папка джерела та результатів однакові ({abs_input_path}). Видалення вимкнено для безпеки."); delete_originals = False
    try:
        preresize_width = int(preresize_width) if preresize_width else 0
        preresize_height = int(preresize_height) if preresize_height else 0
        whitening_cancel_threshold = int(whitening_cancel_threshold) if whitening_cancel_threshold is not None else 0
        white_tolerance = int(white_tolerance) if white_tolerance is not None and white_tolerance >= 0 else None
        perimeter_margin = int(perimeter_margin) if perimeter_margin and perimeter_margin > 0 else 0
        padding_percent = float(padding_percent) if padding_percent and padding_percent > 0 else 0.0
        max_output_width = int(max_output_width) if max_output_width and max_output_width > 0 else 0
        max_output_height = int(max_output_height) if max_output_height and max_output_height > 0 else 0
        final_exact_width = int(final_exact_width) if final_exact_width and final_exact_width > 0 else 0
        final_exact_height = int(final_exact_height) if final_exact_height and final_exact_height > 0 else 0
        jpeg_quality = max(1, min(100, int(jpeg_quality))) if jpeg_quality is not None else 95
    except (ValueError, TypeError) as e: print(f"!! ПОМИЛКА: Неправильний тип даних в числових параметрах ({e}). СКАСОВАНО."); return
    default_bg = (255, 255, 255); jpg_bg_color_validated = default_bg
    if output_format_lower == 'jpg':
        if jpg_background_color and isinstance(jpg_background_color, (tuple, list)) and len(jpg_background_color) == 3:
            try: jpg_bg_color_validated = tuple(max(0, min(255, int(c))) for c in jpg_background_color)
            except (ValueError, TypeError): print(f"  ! Неправильний формат кольору фону JPG, використано {default_bg}")
        else: print(f"  ! Колір фону JPG не вказано або неправильний формат, використано {default_bg}")
        jpg_background_color = jpg_bg_color_validated
    use_force_aspect_ratio = False; valid_aspect_ratio = None
    if force_aspect_ratio and isinstance(force_aspect_ratio, (tuple, list)) and len(force_aspect_ratio) == 2:
        try:
             ar_w, ar_h = map(float, force_aspect_ratio)
             if ar_w > 0 and ar_h > 0: use_force_aspect_ratio = True; valid_aspect_ratio = (ar_w, ar_h)
             else: print(f"! Примусове співвідношення сторін: Непозитивні значення ({force_aspect_ratio})")
        except (ValueError, TypeError): print(f"! Примусове співвідношення сторін: Неправильний формат ({force_aspect_ratio})")

    # --- Друк фінальних параметрів ---
    print(f"--- Параметри обробки ---")
    print(f"Папка ДЖЕРЕЛА: {abs_input_path}"); print(f"Папка РЕЗУЛЬТАТІВ: {abs_output_path}")
    enable_renaming_actual = bool(article_name and article_name.strip())
    if enable_renaming_actual: print(f"Артикул: {article_name}")
    else: print(f"Перейменування за артикулом: Вимкнено")
    print(f"Видалення оригіналів: {'Так' if delete_originals else 'Ні'}")
    perform_preresize = (preresize_width > 0 or preresize_height > 0)
    if perform_preresize: print(f"Перед. ресайз (зменшення, якщо більше): Так (Ш: {preresize_width or 'N/A'}, В: {preresize_height or 'N/A'}px)")
    else: print(f"Перед. ресайз: Ні")
    print(f"Відбілювання: {'Так' if enable_whitening else 'Ні'}")
    if enable_whitening: print(f"  - Поріг скасування відбілювання (мін. сума RGB): {whitening_cancel_threshold}")
    enable_bg_removal_and_crop = (white_tolerance is not None)
    if enable_bg_removal_and_crop:
        print(f"Видалення фону/Обрізка: Так (допуск білого {white_tolerance})")
        crop_mode = "Стандартний (асиметричний)"
        if crop_symmetric_absolute: crop_mode = "Абсолютно симетричний"
        elif crop_symmetric_axes: crop_mode = "Симетричний по осях"
        print(f"  - Режим обрізки: {crop_mode}")
    else: print(f"Видалення фону/Обрізка: Ні")
    perform_perimeter_check = perimeter_margin > 0; perform_padding = padding_percent > 0
    print(f"Перевірка периметра для полів: {'Так (' + str(perimeter_margin) + 'px)' if perform_perimeter_check else 'Ні'}")
    padding_logic_desc = "(умовно: якщо периметр білий ТА (розширення дозволено АБО розмір не збільшиться))" if perform_perimeter_check else "(умовно: якщо розширення дозволено АБО розмір не збільшиться)"
    print(f"Відсоток полів: {str(padding_percent) + '%' if perform_padding else 'Ні'} {padding_logic_desc if perform_padding else ''}")
    # <<< Друк нового параметра >>>
    print(f"Дозволити збільшення розміру полями: {'Так' if allow_expansion else 'Ні'}")
    if use_force_aspect_ratio: print(f"Примусове співвідношення сторін: Так ({valid_aspect_ratio[0]}:{valid_aspect_ratio[1]})")
    else: print(f"Примусове співвідношення сторін: Ні")
    use_max_dimensions = max_output_width > 0 or max_output_height > 0
    if use_max_dimensions: print(f"Обмеження макс. розміру: Так (Ш: {max_output_width or 'Немає'}, В: {max_output_height or 'Немає'})")
    else: print(f"Обмеження макс. розміру: Ні")
    perform_final_canvas = final_exact_width > 0 and final_exact_height > 0
    if perform_final_canvas: print(f"Фінальний холст точного розміру: Так ({final_exact_width}x{final_exact_height}px)")
    else: print(f"Фінальний холст точного розміру: Ні")
    print(f"Формат збереження: {output_format_lower.upper()}")
    if output_format_lower == 'jpg': print(f"  - Колір фону JPG: {jpg_background_color}"); print(f"  - Якість JPG: {jpeg_quality}")
    else: print(f"  - Фон PNG: Прозорий")
    backup_enabled = abs_backup_path is not None
    if backup_enabled:
        print(f"Резервне копіювання: Увімкнено ({abs_backup_path})")
        if not os.path.exists(abs_backup_path):
            try: os.makedirs(abs_backup_path); print(f"  - Створено папку бекапів.")
            except Exception as e: print(f"!! Помилка створення папки бекапів: {e}. Бекап вимкнено."); backup_enabled = False
        elif not os.path.isdir(abs_backup_path): print(f"!! ПОМИЛКА: Шлях бекапів не є папкою: {abs_backup_path}. Бекап вимкнено."); backup_enabled = False
    else: print(f"Резервне копіювання: Вимкнено")
    print("-" * 25)

    # --- Створення папки результатів ---
    if not os.path.exists(abs_output_path):
        try: os.makedirs(abs_output_path); print(f"Створено папку результатів: {abs_output_path}")
        except Exception as e: print(f"!! ПОМИЛКА створення папки результатів '{abs_output_path}': {e}. СКАСОВАНО."); return
    elif not os.path.isdir(abs_output_path): print(f"!! ПОМИЛКА: Шлях результатів '{abs_output_path}' існує, але не є папкою. СКАСОВАНО."); return

    # --- Пошук файлів ---
    try:
        all_entries = os.listdir(abs_input_path)
        SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp', '.tif')
        files_unsorted = [f for f in all_entries if os.path.isfile(os.path.join(abs_input_path, f)) and not f.startswith(("__temp_", ".")) and f.lower().endswith(SUPPORTED_EXTENSIONS)]
        files = natsorted(files_unsorted)
        print(f"Знайдено файлів для обробки в '{abs_input_path}': {len(files)}")
        if not files: print("Файлів для обробки не знайдено."); return
    except FileNotFoundError: print(f"Помилка: Папку ДЖЕРЕЛА не знайдено - {abs_input_path}"); return
    except Exception as e: print(f"Помилка читання папки {abs_input_path}: {e}"); return

    # --- Ініціалізація лічильників та списків ---
    processed_files_count = 0; skipped_files_count = 0; error_files_count = 0
    source_files_to_potentially_delete = []
    processed_output_file_map = {}
    output_ext = f".{output_format_lower}"

    # --- Основний цикл обробки ---
    for file_index, file in enumerate(files):
        source_file_path = os.path.join(abs_input_path, file)
        print(f"\n[{file_index+1}/{len(files)}] Обробка файлу: {file}")
        img_current = None; success_flag = False
        pre_crop_width, pre_crop_height = 0, 0
        cropped_image_dimensions = None

        try:
            # 1. Бекап
            if backup_enabled:
                backup_file_path = os.path.join(abs_backup_path, file)
                try: shutil.copy2(source_file_path, backup_file_path);
                except Exception as backup_err: print(f"  !! Помилка бекапу: {backup_err}")

            # 2. Відкриття
            with Image.open(source_file_path) as img_opened:
                img_opened.load()
                img_current = img_opened.copy()
                print(f"  - Відкрито. Ориг. розмір: {img_current.size}, Режим: {img_current.mode}")

            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка: Зображення має нульовий розмір після відкриття або не відкрилося. Пропускаємо.")
                 error_files_count += 1; safe_close(img_current); img_current=None; continue

            # --- Конвеєр обробки ---

            # 3. Перед. ресайз
            if perform_preresize:
                 prw = preresize_width if preresize_width and preresize_width > 0 else float('inf')
                 prh = preresize_height if preresize_height and preresize_height > 0 else float('inf')
                 print(f"  - Крок Pre-Resize (зменшення до макс. {preresize_width or 'N/A'}x{preresize_height or 'N/A'}, якщо більше)...")
                 prev_img = img_current; ow, oh = prev_img.size
                 needs_resizing = (ow > prw or oh > prh) and ow > 0 and oh > 0
                 if needs_resizing:
                     resized_img_pr = None
                     try:
                         ratio = 1.0
                         if ow > prw: ratio = min(ratio, prw / ow)
                         if oh > prh: ratio = min(ratio, prh / oh)
                         if ratio < 1.0:
                             nw = max(1, int(round(ow * ratio))); nh = max(1, int(round(oh * ratio)))
                             print(f"    - Зменшення до {nw}x{nh} (ratio: {ratio:.4f})...")
                             resized_img_pr = prev_img.resize((nw, nh), Image.Resampling.LANCZOS)
                             img_current = resized_img_pr; resized_img_pr = None
                             print(f"    - Новий розмір: {img_current.size}, Режим: {img_current.mode}")
                             safe_close(prev_img)
                         else: print("    - Розрахунок показав, що зменшення не потрібне (ratio=1.0)."); # img_current залишається prev_img
                     except Exception as pr_err: print(f"   ! Помилка під час попереднього ресайзу (зменшення): {pr_err}"); safe_close(resized_img_pr); img_current = prev_img
                 else: print(f"    - Зображення ({ow}x{oh}) вже в межах лімітів. Зменшення не потрібне.")
            else: print("  - Крок Pre-Resize: вимкнено.")
            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0: print(f"  ! Помилка або нульовий розмір після Pre-Resize ({img_current.size if img_current else '(None)'}). Пропускаємо файл."); error_files_count += 1; safe_close(img_current); img_current = None; continue

            # 4. Відбілювання
            if enable_whitening:
                print("  - Крок Whitening...")
                prev_img = img_current
                try:
                    img_whitened = whiten_image_by_darkest_perimeter(prev_img, whitening_cancel_threshold)
                    if img_whitened is not prev_img: print(f"    - Відбілювання застосовано."); img_current = img_whitened; safe_close(prev_img)
                    else: print(f"    - Відбілювання не застосовано."); img_current = prev_img
                    print(f"    - Розмір після відбілювання: {img_current.size}, Режим: {img_current.mode}")
                except Exception as wh_err: print(f"  !! Загальна помилка під час виклику відбілювання: {wh_err}"); img_current = prev_img
            else: print("  - Крок Whitening: вимкнено.")

            # 5. Перевірка периметру (для умовних полів)
            should_add_padding_conditionally = False
            if perform_perimeter_check and perform_padding:
                 print("  - Крок Check Perimeter (для умовних полів)...")
                 current_perimeter_tolerance = white_tolerance if enable_bg_removal_and_crop else 0
                 should_add_padding_conditionally = check_perimeter_is_white(img_current, current_perimeter_tolerance, perimeter_margin)
                 # Повідомлення оновлено в логах параметра `padding_percent`
            elif perform_padding:
                 print("  - Крок Check Perimeter: вимкнено, але Padding увімкнено.")
                 should_add_padding_conditionally = True
            else: print("  - Крок Check Perimeter/Padding: вимкнено або не потрібно.")

            # Зберігаємо розміри перед кроками 6 і 7
            if img_current: pre_crop_width, pre_crop_height = img_current.size; print(f"  - Розмір перед видаленням фону/обрізкою: {pre_crop_width}x{pre_crop_height}")
            else: print("  ! Попередження: Немає зображення перед кроком видалення фону/обрізки."); error_files_count += 1; continue

            # 6. Видалення фону
            if enable_bg_removal_and_crop:
                print(f"  - Крок Background Removal (допуск {white_tolerance})...")
                prev_img = img_current
                try:
                    img_no_bg = remove_white_background(prev_img, white_tolerance)
                    if img_no_bg is not prev_img: print("    - Фон видалено (або створено RGBA копію)."); img_current = img_no_bg; safe_close(prev_img)
                    else: print("    - Фон не видалявся."); img_current = prev_img
                    print(f"    - Розмір після видалення фону: {img_current.size}, Режим: {img_current.mode}")
                except Exception as bg_err: print(f"   !! Загальна помилка виклику remove_white_background: {bg_err}"); img_current = prev_img
            else: print("  - Крок Background Removal: вимкнено.")

            # 7. Обрізка
            if enable_bg_removal_and_crop:
                 print("  - Крок Crop...")
                 prev_img = img_current
                 try:
                     img_cropped = crop_image(prev_img, symmetric_axes=crop_symmetric_axes, symmetric_absolute=crop_symmetric_absolute)
                     if img_cropped is not prev_img: print("    - Обрізку виконано."); img_current = img_cropped; safe_close(prev_img)
                     else: print("    - Обрізка не змінила зображення."); img_current = prev_img
                     print(f"    - Розмір після обрізки: {img_current.size}, Режим: {img_current.mode}")
                     if img_current: cropped_image_dimensions = img_current.size
                 except Exception as crop_err: print(f"   !! Загальна помилка виклику crop_image: {crop_err}"); img_current = prev_img; cropped_image_dimensions = img_current.size if img_current else None
            else: cropped_image_dimensions = img_current.size if img_current else None
            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0: size_info = img_current.size if img_current else "(None)"; print(f"  ! Помилка або нульовий розмір після фон/обрізка ({size_info}). Пропускаємо файл."); safe_close(img_current); img_current = None; error_files_count += 1; continue

            # 8. Додавання полів (З УРАХУВАННЯМ allow_expansion)
            apply_padding_final = False
            if perform_padding and should_add_padding_conditionally:
                 print(f"  - Крок Padding ({padding_percent}%, Дозвіл розширення: {allow_expansion})...")
                 current_w, current_h = img_current.size
                 if current_w > 0 and current_h > 0 and padding_percent > 0 and pre_crop_width > 0 and pre_crop_height > 0: # Додано перевірку pre_crop > 0
                     padding_pixels = int(round(max(current_w, current_h) * (padding_percent / 100.0)))
                     if padding_pixels > 0:
                         potential_padded_w = current_w + 2 * padding_pixels
                         potential_padded_h = current_h + 2 * padding_pixels
                         print(f"    - Перевірка розміру:")
                         print(f"      - До обрізки:        {pre_crop_width}x{pre_crop_height}")
                         print(f"      - Після обрізки:     {cropped_image_dimensions[0] if cropped_image_dimensions else 'N/A'}x{cropped_image_dimensions[1] if cropped_image_dimensions else 'N/A'}")
                         print(f"      - Потенційний з полями:{potential_padded_w}x{potential_padded_h}")

                         # <<< ЗМІНЕНА УМОВА з allow_expansion >>>
                         size_check_passed = (potential_padded_w <= pre_crop_width and potential_padded_h <= pre_crop_height)
                         if allow_expansion or size_check_passed:
                             apply_padding_final = True
                             if allow_expansion and not size_check_passed: print("      - РІШЕННЯ: Розширення дозволено (новий розмір > розміру до обрізки). Поля ДОДАЮТЬСЯ.")
                             elif allow_expansion and size_check_passed: print("      - РІШЕННЯ: Розширення дозволено (новий розмір <= розміру до обрізки). Поля ДОДАЮТЬСЯ.")
                             else: print("      - РІШЕННЯ: Розширення заборонено, АЛЕ новий розмір <= розміру до обрізки. Поля ДОДАЮТЬСЯ.") # allow_expansion == False and size_check_passed == True
                         else: # allow_expansion == False and size_check_passed == False
                             print("      - РІШЕННЯ: Розширення заборонено ТА новий розмір > розміру до обрізки. Поля ПРОПУСКАЮТЬСЯ.")
                             apply_padding_final = False
                     else: print("    - Розрахунок полів дав 0 пікселів. Поля не додаються."); apply_padding_final = False
                 else: print(f"    - Поля не додаються (поточний розмір {current_w}x{current_h}, відсоток {padding_percent}, розмір до обрізки {pre_crop_width}x{pre_crop_height})."); apply_padding_final = False

                 if apply_padding_final:
                     prev_img = img_current
                     try:
                          img_padded = add_padding(prev_img, padding_percent) # Викликаємо функцію
                          if img_padded is not prev_img: img_current = img_padded; safe_close(prev_img); print(f"    - Поля додано. Новий розмір: {img_current.size}, Режим: {img_current.mode}")
                          else: print("    - Додавання полів не змінило зображення."); img_current = prev_img # Залишаємо як було, якщо add_padding повернула оригінал
                     except Exception as pad_err: print(f"   !! Загальна помилка виклику add_padding: {pad_err}"); img_current = prev_img
            elif perform_padding and not should_add_padding_conditionally: print("  - Крок Padding: пропущено (умова перевірки периметру не виконана).")
            else: print("  - Крок Padding: вимкнено.")
            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0: size_info = img_current.size if img_current else "(None)"; print(f"  ! Помилка або нульовий розмір після полів ({size_info}). Пропускаємо."); safe_close(img_current); img_current=None; error_files_count += 1; continue

            # 9. Примусове співвідношення сторін
            if use_force_aspect_ratio and valid_aspect_ratio:
                print(f"  - Крок Aspect Ratio ({valid_aspect_ratio[0]}:{valid_aspect_ratio[1]})...")
                prev_img = img_current; ratio_canvas_inner = None; temp_rgba_ratio = None
                try:
                    target_aspect_w, target_aspect_h = valid_aspect_ratio
                    current_w, current_h = prev_img.size
                    if current_h <= 0 or target_aspect_h <= 0: raise ValueError("Нульова висота в співвідношенні")
                    current_aspect = current_w / current_h; desired_aspect = target_aspect_w / target_aspect_h
                    if abs(current_aspect - desired_aspect) > 0.01:
                        print(f"    - Потрібна зміна ({current_aspect:.3f} -> {desired_aspect:.3f})...")
                        if current_aspect > desired_aspect: target_w = current_w; target_h = int(round(current_w / desired_aspect))
                        else: target_h = current_h; target_w = int(round(current_h * desired_aspect))
                        target_w = max(1, target_w); target_h = max(1, target_h)
                        print(f"    - Створення холсту {target_w}x{target_h}")
                        ratio_canvas_inner = Image.new('RGBA', (target_w, target_h), (0,0,0,0))
                        x = (target_w - current_w) // 2; y = (target_h - current_h) // 2
                        paste_mask = None; image_to_paste = prev_img
                        if prev_img.mode != 'RGBA': temp_rgba_ratio = prev_img.convert('RGBA'); image_to_paste = temp_rgba_ratio; paste_mask = temp_rgba_ratio
                        elif prev_img.mode == 'RGBA': paste_mask = prev_img
                        ratio_canvas_inner.paste(image_to_paste, (x, y), mask=paste_mask)
                        img_current = ratio_canvas_inner; ratio_canvas_inner = None
                        print(f"    - Новий розмір після зміни співвідношення: {img_current.size}")
                        safe_close(prev_img); # temp_rgba_ratio закриється у finally
                    else: print("    - Співвідношення сторін вже відповідає цільовому."); img_current = prev_img
                except Exception as ratio_err: print(f"    !! Помилка зміни співвідношення сторін: {ratio_err}"); img_current = prev_img
                finally: safe_close(ratio_canvas_inner); safe_close(temp_rgba_ratio if temp_rgba_ratio is not prev_img else None)
            else: print("  - Крок Aspect Ratio: вимкнено.")
            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0: size_info = img_current.size if img_current else "(None)"; print(f"  ! Помилка або нульовий розмір після співвідношення ({size_info}). Пропускаємо."); safe_close(img_current); img_current=None; error_files_count += 1; continue

            # 10. Обмеження максимальних розмірів
            if use_max_dimensions:
                 mow = max_output_width if max_output_width and max_output_width > 0 else float('inf')
                 moh = max_output_height if max_output_height and max_output_height > 0 else float('inf')
                 print(f"  - Крок Max Dimensions (Ш: {max_output_width or 'N/A'}, В: {max_output_height or 'N/A'})...")
                 prev_img = img_current; resized_img_max = None
                 try:
                      current_w, current_h = prev_img.size; # print(f"    - Поточний розмір: {current_w}x{current_h}")
                      scale_ratio = 1.0
                      if current_w > mow: scale_ratio = min(scale_ratio, mow / current_w)
                      if current_h > moh: scale_ratio = min(scale_ratio, moh / current_h)
                      if scale_ratio < 1.0:
                           nw = max(1, int(round(current_w * scale_ratio))); nh = max(1, int(round(current_h * scale_ratio)))
                           print(f"    - Зменшення до {nw}x{nh}...")
                           resized_img_max = prev_img.resize((nw, nh), Image.Resampling.LANCZOS)
                           img_current = resized_img_max; resized_img_max = None
                           print(f"    - Розмір після обмеження: {img_current.size}")
                           safe_close(prev_img)
                      else: print("    - Зображення вже в межах максимальних розмірів."); img_current = prev_img
                 except Exception as max_resize_err: print(f"    !! Помилка зменшення розміру: {max_resize_err}"); img_current = prev_img
                 finally: safe_close(resized_img_max)
            else: print("  - Крок Max Dimensions: вимкнено.")
            if not img_current or img_current.size[0] <= 0 or img_current.size[1] <= 0: size_info = img_current.size if img_current else "(None)"; print(f"  ! Помилка або нульовий розмір після обмеження ({size_info}). Пропускаємо."); safe_close(img_current); img_current=None; error_files_count += 1; continue

            # 11. Фінальний холст АБО підготовка режиму/фону
            prev_img = img_current
            final_canvas_inner = None; resized_content_fc = None; paste_mask_fc = None; temp_rgba_fc = None; image_to_paste_fc = None
            temp_converted_prep = None; prep_canvas_inner = None; paste_mask_prep_inner = None; temp_rgba_prep_inner = None; image_to_paste_prep_inner = None
            if perform_final_canvas:
                 print(f"  - Крок Final Canvas ({final_exact_width}x{final_exact_height})...")
                 try:
                     bw, bh = prev_img.size;
                     if bw <= 0 or bh <= 0: raise ValueError("Нульовий розмір перед фінальним холстом")
                     ratio = min(final_exact_width / bw, final_exact_height / bh); nw = max(1, int(round(bw * ratio))); nh = max(1, int(round(bh * ratio)))
                     print(f"    - Масштабування вмісту до {nw}x{nh} для вписування...")
                     resized_content_fc = prev_img.resize((nw, nh), Image.Resampling.LANCZOS); image_to_paste_fc = resized_content_fc
                     if output_format_lower == 'png':
                          print(f"    - Створення фінального RGBA холсту (прозорий)"); final_canvas_inner = Image.new('RGBA', (final_exact_width, final_exact_height), (0,0,0,0)); target_paste_mode = 'RGBA'
                     else:
                          print(f"    - Створення фінального RGB холсту (фон: {jpg_background_color})"); final_canvas_inner = Image.new('RGB', (final_exact_width, final_exact_height), jpg_background_color); target_paste_mode = 'RGB'
                     x = (final_exact_width - nw) // 2; y = (final_exact_height - nh) // 2; print(f"    - Вставка вмісту на холст ({target_paste_mode}) в позицію ({x},{y})...")
                     paste_mask_fc = None
                     if image_to_paste_fc.mode == 'RGBA': paste_mask_fc = image_to_paste_fc
                     elif image_to_paste_fc.mode in ('LA', 'PA'):
                          temp_rgba_fc = image_to_paste_fc.convert('RGBA'); paste_mask_fc = temp_rgba_fc.split()[-1]
                          if target_paste_mode == 'RGB':
                              with temp_rgba_fc.copy() as rgba_copy_for_rgb: image_to_paste_fc = rgba_copy_for_rgb.convert('RGB')
                          else: image_to_paste_fc = temp_rgba_fc
                     elif target_paste_mode == 'RGBA' and image_to_paste_fc.mode != 'RGBA': image_to_paste_fc = image_to_paste_fc.convert('RGBA')
                     elif target_paste_mode == 'RGB' and image_to_paste_fc.mode != 'RGB': image_to_paste_fc = image_to_paste_fc.convert('RGB')
                     final_canvas_inner.paste(image_to_paste_fc, (x,y), paste_mask_fc)
                     img_current = final_canvas_inner; final_canvas_inner = None
                     print(f"    - Вміст вставлено. Фінальний розмір: {img_current.size}, Режим: {img_current.mode}")
                     safe_close(prev_img)
                 except Exception as canvas_err: print(f"    !! Помилка створення/заповнення фінального холсту: {canvas_err}"); traceback.print_exc(); img_current = prev_img
                 finally:
                      safe_close(paste_mask_fc if paste_mask_fc is not image_to_paste_fc and paste_mask_fc is not temp_rgba_fc else None)
                      safe_close(image_to_paste_fc if image_to_paste_fc is not resized_content_fc and image_to_paste_fc is not temp_rgba_fc and image_to_paste_fc is not prev_img else None)
                      safe_close(temp_rgba_fc if temp_rgba_fc is not resized_content_fc and temp_rgba_fc is not prev_img else None)
                      safe_close(resized_content_fc if resized_content_fc is not prev_img else None)
                      safe_close(final_canvas_inner)
            else:
                 print(f"  - Крок Final Canvas: вимкнено. Підготовка зображення до збереження...")
                 target_mode = 'RGBA' if output_format_lower == 'png' else 'RGB'; print(f"    - Цільовий режим для збереження: {target_mode}")
                 if prev_img.mode == target_mode: print(f"    - Зображення вже в цільовому режимі ({target_mode})."); img_current = prev_img
                 elif target_mode == 'RGBA':
                     print(f"    - Конвертація {prev_img.mode} -> RGBA...");
                     try: temp_converted_prep = prev_img.convert('RGBA'); img_current = temp_converted_prep; temp_converted_prep = None; safe_close(prev_img)
                     except Exception as rgba_conv_err: print(f"    !! Помилка конвертації в RGBA: {rgba_conv_err}"); img_current = prev_img
                 else:
                     print(f"    - Підготовка {prev_img.mode} для збереження як RGB (фон: {jpg_background_color})...")
                     try:
                         prep_canvas_inner = Image.new('RGB', prev_img.size, jpg_background_color); paste_mask_prep_inner = None; image_to_paste_prep_inner = prev_img
                         if prev_img.mode in ('RGBA', 'LA'): paste_mask_prep_inner = prev_img.split()[-1]
                         elif prev_img.mode == 'PA': temp_rgba_prep_inner = prev_img.convert('RGBA'); paste_mask_prep_inner = temp_rgba_prep_inner.split()[-1]; image_to_paste_prep_inner = temp_rgba_prep_inner
                         prep_canvas_inner.paste(image_to_paste_prep_inner, (0,0), paste_mask_prep_inner)
                         img_current = prep_canvas_inner; prep_canvas_inner = None; safe_close(prev_img)
                     except Exception as prep_err:
                          print(f"    !! Помилка підготовки фону для JPG: {prep_err}. Спроба простої конвертації...")
                          try: temp_converted_prep = prev_img.convert('RGB'); img_current = temp_converted_prep; temp_converted_prep = None; safe_close(prev_img)
                          except Exception as rgb_conv_err: print(f"    !!! Помилка конвертації в RGB: {rgb_conv_err}"); img_current = prev_img
                     finally:
                          safe_close(paste_mask_prep_inner if paste_mask_prep_inner is not prev_img and paste_mask_prep_inner is not temp_rgba_prep_inner else None)
                          safe_close(image_to_paste_prep_inner if image_to_paste_prep_inner is not prev_img and image_to_paste_prep_inner is not temp_rgba_prep_inner else None)
                          safe_close(temp_rgba_prep_inner if temp_rgba_prep_inner is not prev_img else None)
                          safe_close(prep_canvas_inner); safe_close(temp_converted_prep)

            # 12. Збереження
            if not img_current: print("  !! Помилка: Немає зображення для збереження після всіх кроків. Пропускаємо."); error_files_count += 1; continue
            if img_current.size[0] <= 0 or img_current.size[1] <= 0: print(f"  !! Помилка: Зображення для збереження має нульовий розмір {img_current.size}. Пропускаємо."); error_files_count += 1; safe_close(img_current); img_current = None; continue
            base_name = os.path.splitext(file)[0]; output_filename = f"{base_name}{output_ext}"; final_output_path = os.path.join(abs_output_path, output_filename)
            print(f"  - Крок Save: Підготовка до збереження у {final_output_path}..."); print(f"      - Режим: {img_current.mode}, Розмір: {img_current.size}")
            try:
                save_options = {"optimize": True}; img_to_save = None; must_close_img_to_save = False
                if output_format_lower == 'jpg':
                    save_format_name = "JPEG"
                    if img_current.mode != 'RGB': print(f"     ! Попередження: Режим не RGB ({img_current.mode}). Спроба конвертації..."); img_to_save = img_current.convert('RGB'); must_close_img_to_save = True
                    else: img_to_save = img_current
                    try: save_options["quality"] = jpeg_quality; save_options["subsampling"] = 0; save_options["progressive"] = True; img_to_save.save(final_output_path, save_format_name, **save_options)
                    finally: safe_close(img_to_save if must_close_img_to_save else None)
                else:
                    save_format_name = "PNG"
                    if img_current.mode != 'RGBA': print(f"     ! Попередження: Режим не RGBA ({img_current.mode}). Спроба конвертації..."); img_to_save = img_current.convert('RGBA'); must_close_img_to_save = True
                    else: img_to_save = img_current
                    try: save_options["compress_level"] = 6; img_to_save.save(final_output_path, save_format_name, **save_options)
                    finally: safe_close(img_to_save if must_close_img_to_save else None)

                processed_files_count += 1; success_flag = True; print(f"    - Успішно збережено: {final_output_path}")
                processed_output_file_map[final_output_path] = base_name
                if os.path.exists(source_file_path) and source_file_path not in source_files_to_potentially_delete: source_files_to_potentially_delete.append(source_file_path)
            except Exception as save_err:
                print(f"  !! Помилка збереження {save_format_name}: {save_err}"); traceback.print_exc(); error_files_count += 1; success_flag = False
                if os.path.exists(final_output_path):
                    try: os.remove(final_output_path); print(f"    - Видалено частково збережений файл: {final_output_path}")
                    except Exception as del_err: print(f"    ! Не вдалося видалити частковий файл: {del_err}")

        # --- Обробка помилок файлу ---
        except UnidentifiedImageError: print(f"!!! Помилка: Не розпізнано формат файлу або файл пошкоджено: {file}"); skipped_files_count += 1; success_flag = False
        except FileNotFoundError: print(f"!!! Помилка: Файл не знайдено під час обробки: {file}"); skipped_files_count += 1; success_flag = False
        except OSError as e: print(f"!!! Помилка ОС ({file}): {e}"); error_files_count += 1; success_flag = False
        except MemoryError as e: print(f"!!! Помилка ПАМ'ЯТІ ({file}): {e}."); error_files_count += 1; success_flag = False; import gc; gc.collect()
        except Exception as e: print(f"!!! Неочікувана ГЛОБАЛЬНА помилка обробки ({file}): {e}"); traceback.print_exc(); error_files_count += 1; success_flag = False
        finally:
            safe_close(img_current)
            if not success_flag and source_file_path in source_files_to_potentially_delete:
                 try: source_files_to_potentially_delete.remove(source_file_path); print(f"    - Видалено {os.path.basename(source_file_path)} зі списку на видалення через помилку.")
                 except ValueError: pass

    # --- Статистика, Видалення, Перейменування (поза циклом обробки файлів) ---
    print(f"\n--- Статистика обробки ---"); print(f"  - Успішно збережено: {processed_files_count}"); print(f"  - Пропущено (не формат/не знайдено/пошкоджено): {skipped_files_count}"); print(f"  - Файлів з помилками обробки/збереження: {error_files_count}")
    total_processed = processed_files_count + skipped_files_count + error_files_count; print(f"  - Всього проаналізовано файлів: {total_processed} (з {len(files)} знайдених)")
    if delete_originals and source_files_to_potentially_delete:
        print(f"\nВидалення {len(source_files_to_potentially_delete)} оригінальних файлів з '{abs_input_path}'...")
        removed_count = 0; remove_errors = 0
        for file_to_remove in source_files_to_potentially_delete:
            try:
                if os.path.exists(file_to_remove): os.remove(file_to_remove); removed_count += 1; print(f"  - Видалено: {os.path.basename(file_to_remove)}")
                else: print(f"  ! Файл для видалення не знайдено: {os.path.basename(file_to_remove)}")
            except Exception as remove_error: print(f"  ! Помилка видалення {os.path.basename(file_to_remove)}: {remove_error}"); remove_errors += 1
        print(f"  - Успішно видалено: {removed_count}. Помилок видалення: {remove_errors}.")
    elif delete_originals: print(f"\nВидалення оригіналів увімкнено, але немає файлів для видалення.")
    else: print(f"\nВидалення оригіналів з '{abs_input_path}' вимкнено.")
    if enable_renaming_actual and processed_output_file_map:
        print(f"\n--- Перейменування файлів у '{abs_output_path}' ---"); successfully_saved_paths = list(processed_output_file_map.keys()); print(f"Файлів для перейменування: {len(successfully_saved_paths)}")
        files_to_process_for_rename = []
        for saved_path in successfully_saved_paths:
            if os.path.exists(saved_path):
                 original_basename = processed_output_file_map.get(saved_path)
                 if original_basename: files_to_process_for_rename.append((saved_path, original_basename))
                 else: print(f"  ! Попередження: Не знайдено оригінальну назву для {saved_path}")
            else: print(f"  ! Попередження: Файл для перейменування більше не існує: {saved_path}")
        if not files_to_process_for_rename: print("Немає файлів для перейменування.")
        else:
            try: sorted_files_for_rename = natsorted(files_to_process_for_rename, key=lambda item: item[1])
            except NameError: sorted_files_for_rename = sorted(files_to_process_for_rename, key=lambda item: item[1])
            except Exception as sort_err: print(f"  ! Помилка сортування файлів: {sort_err}. Використання несортованого списку."); sorted_files_for_rename = files_to_process_for_rename
            temp_rename_map = {}; rename_step1_errors = 0; temp_prefix = f"__temp_{os.getpid()}_"; print("  - Крок 1: Перейменування у тимчасові імена...")
            for i, (current_path, original_basename) in enumerate(sorted_files_for_rename):
                temp_filename = f"{temp_prefix}{i}_{original_basename}{output_ext}"
                temp_path = os.path.join(abs_output_path, temp_filename)
                try: print(f"    '{os.path.basename(current_path)}' -> '{temp_filename}'"); os.rename(current_path, temp_path); temp_rename_map[temp_path] = original_basename
                except Exception as rename_error: print(f"  ! Помилка тимч. перейменування '{os.path.basename(current_path)}': {rename_error}"); rename_step1_errors += 1
            if rename_step1_errors > 0: print(f"  ! Помилок на кроці 1: {rename_step1_errors}")
            print("  - Крок 2: Фінальне перейменування з тимчасових імен..."); rename_step2_errors = 0; renamed_final_count = 0; occupied_final_names = set()
            existing_temp_paths = list(temp_rename_map.keys()); temp_files_to_process_step2 = []
            for temp_p in existing_temp_paths:
                if os.path.exists(temp_p):
                    original_basename = temp_rename_map.get(temp_p)
                    if original_basename: temp_files_to_process_step2.append((temp_p, original_basename))
                    else: print(f"  ! Попередження: Не знайдено оригінальну назву для тимчасового файлу {os.path.basename(temp_p)}")
                else: print(f"  ! Попередження: Тимчасовий файл '{os.path.basename(temp_p)}' зник перед кроком 2.")
            if not temp_files_to_process_step2: print("  ! Немає тимчасових файлів для фінального перейменування.")
            else:
                all_temp_files_sorted = sorted(temp_files_to_process_step2, key=lambda item: os.path.basename(item[0]))
                found_exact_match_in_list = False; exact_match_original_basename = None
                for _, orig_bn in all_temp_files_sorted:
                    if orig_bn.lower() == article_name.lower(): found_exact_match_in_list = True; exact_match_original_basename = orig_bn; print(f"  * Знайдено точний збіг для '{article_name}' (оригінал: '{orig_bn}')."); break
                if not found_exact_match_in_list: print(f"  * Точний збіг для '{article_name}' не знайдено серед оброблених файлів.")
                base_name_assigned = False; numeric_counter = 1
                for temp_path, original_basename in all_temp_files_sorted:
                    target_filename = None; target_path = None; assign_base = False
                    is_exact_match = original_basename.lower() == article_name.lower()
                    if is_exact_match and not base_name_assigned: assign_base = True; print(f"  * Присвоєння базового імені '{article_name}' файлу з точним збігом '{original_basename}'.")
                    elif not found_exact_match_in_list and not base_name_assigned: assign_base = True; print(f"  * Присвоєння базового імені '{article_name}' першому файлу '{original_basename}'.")
                    if assign_base:
                        target_filename = f"{article_name}{output_ext}"; target_path = os.path.join(abs_output_path, target_filename); norm_target_path = os.path.normcase(target_path)
                        if norm_target_path in occupied_final_names or (os.path.exists(target_path) and temp_path != target_path): print(f"  ! Конфлікт: Базове ім'я '{target_filename}' зайняте/існує. Файл '{os.path.basename(temp_path)}' буде пронумеровано."); assign_base = False
                        else: base_name_assigned = True
                    if not assign_base:
                        while True:
                            target_filename = f"{article_name}_{numeric_counter}{output_ext}"; target_path = os.path.join(abs_output_path, target_filename); norm_target_path = os.path.normcase(target_path)
                            if norm_target_path not in occupied_final_names and not (os.path.exists(target_path) and temp_path != target_path): break
                            numeric_counter += 1
                        numeric_counter += 1
                    try: print(f"    '{os.path.basename(temp_path)}' -> '{target_filename}'"); os.rename(temp_path, target_path); renamed_final_count += 1; occupied_final_names.add(os.path.normcase(target_path))
                    except Exception as rename_error: print(f"  ! Помилка фінального перейменування '{os.path.basename(temp_path)}' -> '{target_filename}': {rename_error}"); rename_step2_errors += 1
            print(f"\n  - Перейменовано файлів: {renamed_final_count}. Помилок на кроці 2: {rename_step2_errors}.")
            remaining_temp_final = [f for f in os.listdir(abs_output_path) if f.startswith(temp_prefix) and os.path.isfile(os.path.join(abs_output_path, f))];
            if remaining_temp_final: print(f"  ! Увага: Залишилися тимчасові файли в '{abs_output_path}': {remaining_temp_final}")
    elif enable_renaming_actual and not processed_output_file_map: print("\n--- Перейменування файлів пропущено: Немає успішно оброблених файлів ---")
    elif not enable_renaming_actual: print("\n--- Перейменування файлів пропущено (вимкнено) ---")
# --- Кінець функції rename_and_convert_images ---


# --- Блок виконання та Налаштування Користувача ---
# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":
    # Цей блок виконується тільки тоді, коли скрипт запускається напряму
    # (а не імпортується як модуль в інший скрипт).
    # Тут знаходяться всі налаштування, які користувач може змінювати.

    # ==========================================================================
    # ===                    НАЛАШТУВАННЯ КОРИСТУВАЧА                      ===
    # ==========================================================================
    # Змінюйте значення змінних нижче відповідно до ваших потреб.
    # Використовуйте одинарні (' ') або подвійні (" ") лапки для шляхів та рядків.
    # Використовуйте префікс r перед шляхами Windows (напр., r"C:\Папка"),
    # або використовуйте прямі слеші (напр., "C:/Папка").
    # ==========================================================================

    # --------------------------------------------------------------------------
    # |                        ЕТАП 0: Шляхи та Імена                        |
    # --------------------------------------------------------------------------

    # Шлях до папки, звідки будуть братися зображення для обробки.
    input_folder_path = r"C:\Users\zakhar\Downloads\test3"

    # Шлях до папки, куди будуть зберігатися оброблені зображення.
    # Може бути тією ж папкою, що й input_folder_path.
    output_folder_path = r"C:\Users\zakhar\Downloads\test3"

    # Шлях до папки для створення резервних копій ОРИГІНАЛЬНИХ файлів перед обробкою.
    # Якщо вказано None або порожній рядок (""), резервне копіювання вимкнено.
    # ВАЖЛИВО: Ця папка не повинна співпадати з input_folder_path або output_folder_path.
    backup_folder_path = r"C:\Users\zakhar\Downloads\test_py_bak"

    # --------------------------------------------------------------------------
    # |          ЕТАП 0.5: Перейменування та Видалення Оригіналів            |
    # --------------------------------------------------------------------------

    # Базове ім'я (артикул) для перейменування оброблених файлів.
    # - Якщо вказано рядок (напр., "ART123"), файли будуть перейменовані у форматі:
    #   "ART123.jpg", "ART123_1.jpg", "ART123_2.jpg" і т.д.
    #   Файл, чия оригінальна назва (без розширення) точно співпадає з артикулом (без урахування регістру),
    #   отримає базове ім'я без суфікса "_N". Якщо такого файлу немає, перший оброблений файл
    #   (після сортування) отримає базове ім'я.
    # - Якщо вказано None або порожній рядок (""), перейменування вимкнено,
    #   файли зберігаються з оригінальними іменами (але з новим розширенням).
    article = "L811"

    # Видаляти оригінальні файли з папки `input_folder_path` ПІСЛЯ успішної обробки?
    # - True: Видаляти.
    # - False: Не видаляти.
    # ВАЖЛИВО: Видалення працює ТІЛЬКИ якщо `input_folder_path` та `output_folder_path` РІЗНІ!
    # Це запобіжний захід від випадкового видалення файлів, які ще не були збережені.
    delete_originals_after_processing = False

    # --------------------------------------------------------------------------
    # |         ЕТАП 1: Попередній Ресайз (До основної обробки)             |
    # --------------------------------------------------------------------------
    # Цей крок ЗМЕНШУЄ зображення, ЯКЩО воно перевищує вказані розміри,
    # зберігаючи пропорції. Він НЕ збільшує зображення і НЕ додає поля на цьому етапі.
    # Використовується для оптимізації перед ресурсоємними операціями.

    # Максимальна ширина зображення після попереднього ресайзу (в пікселях).
    # 0 або None - не обмежувати ширину.
    preresize_width = 2500

    # Максимальна висота зображення після попереднього ресайзу (в пікселях).
    # 0 або None - не обмежувати висоту.
    preresize_height = 2500

    # --------------------------------------------------------------------------
    # |                ЕТАП 2: Відбілювання Фону                             |
    # --------------------------------------------------------------------------
    # Спроба зробити фон світлішим, базуючись на найтемнішому пікселі периметру.
    # Корисно для фото на сірому або неоднорідному світлому фоні.

    # Увімкнути функцію відбілювання?
    # - True: Увімкнути.
    # - False: Вимкнути.
    enable_whitening = True

    # Поріг скасування відбілювання (мінімальна сума R+G+B найтемнішого пікселя периметру).
    # Якщо найтемніший піксель периметру темніший за цей поріг (його сума R+G+B < поріг),
    # відбілювання НЕ буде застосовано, щоб уникнути пересвічування темних об'єктів.
    # - Діапазон: 0 - 765 (0 = чорний, 765 = білий).
    # - Рекомендовані значення: 500-650 (залежить від типового фону).
    # - 0: Відбілювання буде скасовано майже завжди (крім випадків, коли периметр вже ідеально білий).
    # - 765: Відбілювання НЕ буде скасовано ніколи (крім випадків, коли периметр вже білий).
    whitening_cancel_threshold_sum = 550

    # --------------------------------------------------------------------------
    # |           ЕТАП 3: Видалення фону та Обрізка                           |
    # --------------------------------------------------------------------------
    # Ці кроки працюють разом. Якщо `white_tolerance` встановлено (не None),
    # спочатку білі/майже білі пікселі робляться прозорими, а потім
    # прозорі краї обрізаються.

    # Допуск білого кольору для видалення фону.
    # Значення від 0 до 255.
    # - 0: Видаляється тільки ідеально білий колір (255, 255, 255).
    # - 10: Видаляються пікселі, де КОЖЕН канал (R, G, B) >= 245.
    # - 255: Видаляються всі непрозорі пікселі (не рекомендується).
    # - None: Видалення фону та обрізка ВИМКНЕНІ.
    white_tolerance = 0

    # --- Налаштування Обрізки (діють тільки якщо white_tolerance НЕ None) ---

    # Абсолютна симетрія обрізки?
    # - True: Обрізка буде симетричною відносно країв ВИХІДНОГО зображення.
    #   Знаходиться мінімальний відступ від об'єкта до краю, і цей відступ
    #   застосовується з усіх боків. Може обрізати частину об'єкта, якщо він
    #   не по центру вихідного зображення.
    # - False: Використовується наступний параметр (crop_axes_symmetry) або стандартна обрізка.
    crop_absolute_symmetry = True

    # Симетрія обрізки по осях? (Діє, тільки якщо crop_absolute_symmetry = False)
    # - True: Обрізка буде симетричною відносно центру знайденого об'єкта (bbox).
    #   Межі розширюються симетрично від центру bbox до найближчих країв вихідного зображення.
    #   Зберігає об'єкт по центру.
    # - False: Стандартна асиметрична обрізка точно за межами знайденого об'єкта (bbox)
    #   (з невеликим відступом 1px).
    crop_axes_symmetry = False

    # --------------------------------------------------------------------------
    # |                ЕТАП 4: Додавання Полів                               |
    # --------------------------------------------------------------------------
    # Додає прозорі поля навколо зображення ПІСЛЯ обрізки.

    # Ширина рамки (в пікселях) для перевірки білизни периметру ПЕРЕД обрізкою.
    # Якщо цей параметр > 0, то поля будуть додаватися ТІЛЬКИ ЯКЩО периметр
    # зображення (до обрізки) був визначений як білий (з урахуванням white_tolerance).
    # Це допомагає додавати поля тільки фотографіям, які були зняті на білому фоні.
    # - 0: Перевірка периметру вимкнена. Поля додаються за умовою нижче (allow_expansion).
    # - 1 або більше: Увімкнути перевірку периметра з вказаним відступом.
    perimeter_check_margin_pixels = 1

    # Відсоток полів, що додаються з кожного боку.
    # Розраховується від максимального розміру (ширини або висоти) зображення ПІСЛЯ обрізки.
    # - 0.0: Поля не додаються.
    # - 2.0: Додає поля, що дорівнюють 2% від більшої сторони зображення.
    padding_percentage = 5

    # Дозволити полям збільшувати кінцевий розмір зображення?
    # - True: Поля додаються завжди (якщо padding_percentage > 0 і, можливо,
    #   пройдена перевірка perimeter_check_margin_pixels). Розмір зображення
    #   може стати більшим, ніж був до обрізки.
    # - False: Поля додаються тільки якщо кінцевий розмір зображення З ПОЛЯМИ
    #   буде НЕ більшим (по ширині І висоті), ніж розмір зображення ДО ОБРІЗКИ.
    #   Це запобігає візуальному зменшенню об'єкта, якщо обрізка була незначною.
    allow_image_expansion = True

    # --------------------------------------------------------------------------
    # |          ЕТАП 5: Примусове Співвідношення Сторін                    |
    # --------------------------------------------------------------------------
    # Додає прозорі (для PNG) або фонові (для JPG) поля, щоб досягти
    # заданого співвідношення сторін, розміщуючи поточне зображення по центру.
    # Виконується ПІСЛЯ додавання полів (padding_percentage).

    # Вкажіть бажане співвідношення сторін як кортеж (ширина, висота) або None.
    # - None: Функція вимкнена.
    # - (1, 1): Квадратне зображення.
    # - (16, 9): Широкоформатне зображення.
    # - (3, 4): Портретне зображення.
    force_aspect_ratio_tuple = None

    # --------------------------------------------------------------------------
    # |          ЕТАП 6: Обмеження Максимального Розміру                    |
    # --------------------------------------------------------------------------
    # Зменшує зображення (зберігаючи пропорції), якщо воно перевищує
    # вказані максимальні розміри. НЕ збільшує зображення.
    # Виконується ПІСЛЯ зміни співвідношення сторін.

    # Максимальна ширина кінцевого зображення (в пікселях).
    # 0 або None - без обмеження.
    max_output_width = 1500

    # Максимальна висота кінцевого зображення (в пікселях).
    # 0 або None - без обмеження.
    max_output_height = 1500

    # --------------------------------------------------------------------------
    # |          ЕТАП 7: Фінальний Холст Точного Розміру                    |
    # --------------------------------------------------------------------------
    # Створює холст точно заданого розміру і розміщує на ньому поточне
    # зображення по центру, масштабуючи його (зберігаючи пропорції) так,
    # щоб воно вписалося в холст.
    # Виконується ПІСЛЯ обмеження максимального розміру.
    # УВАГА: Якщо співвідношення сторін зображення не збігається з
    # співвідношенням сторін холсту, будуть додані поля (прозорі для PNG,
    # кольору `jpg_background_color_tuple` для JPG).

    # Точна ширина фінального холсту (в пікселях).
    # 0 або None - функція вимкнена.
    final_exact_width = 0

    # Точна висота фінального холсту (в пікселях).
    # 0 або None - функція вимкнена (навіть якщо ширина вказана).
    final_exact_height = 0

    # --------------------------------------------------------------------------
    # |          ЕТАП 8: Формат Збереження, Фон та Якість                   |
    # --------------------------------------------------------------------------

    # Формат збереження кінцевого файлу.
    # - 'jpg': Формат JPEG. Прозорість буде замінена кольором фону.
    # - 'png': Формат PNG. Прозорість буде збережена.
    output_save_format = 'jpg'

    # --- Налаштування для JPG (ігноруються, якщо output_save_format = 'png') ---

    # Колір фону для JPG у форматі (R, G, B).
    # Використовується для заповнення прозорих ділянок при конвертації в JPG
    # та для полів, що додаються на етапах force_aspect_ratio та final_exact_width/height.
    # (255, 255, 255) - білий. (0, 0, 0) - чорний.
    jpg_background_color_tuple = (255, 255, 255)

    # Якість збереження JPG (від 1 до 100).
    # Вищі значення = краща якість, більший розмір файлу.
    # 95 - зазвичай хороший компроміс.
    jpeg_save_quality = 95

    # --- Налаштування для PNG ---
    # Для PNG фон завжди прозорий (де це можливо). Якість контролюється
    # рівнем стиснення (в коді встановлено 6 - стандартний).

    # ==========================================================================
    # ===               КІНЕЦЬ НАЛАШТУВАНЬ КОРИСТУВАЧА                     ===
    # ==========================================================================


    # --- Запуск Скрипта ---
    print("\n--- Початок роботи скрипту ---")
    if not os.path.isdir(input_folder_path):
         print(f"\n!! ПОМИЛКА: Вказана папка ДЖЕРЕЛА не існує або не є папкою: {input_folder_path}")
    else:
         # Передача всіх налаштувань у головну функцію обробки
         rename_and_convert_images(
             input_path=input_folder_path,
             output_path=output_folder_path,
             article_name=article if article and article.strip() else None, # Передаємо None якщо артикул порожній
             delete_originals=delete_originals_after_processing,
             preresize_width=preresize_width,
             preresize_height=preresize_height,
             enable_whitening=enable_whitening,
             whitening_cancel_threshold=whitening_cancel_threshold_sum,
             white_tolerance=white_tolerance, # Передаємо як є (може бути None)
             perimeter_margin=perimeter_check_margin_pixels,
             crop_symmetric_axes=crop_axes_symmetry,
             crop_symmetric_absolute=crop_absolute_symmetry,
             padding_percent=padding_percentage,
             allow_expansion=allow_image_expansion, # <<< Передаємо новий параметр
             force_aspect_ratio=force_aspect_ratio_tuple, # Передаємо як є (може бути None)
             max_output_width=max_output_width,
             max_output_height=max_output_height,
             final_exact_width=final_exact_width,
             final_exact_height=final_exact_height,
             output_format=output_save_format,
             jpg_background_color=jpg_background_color_tuple,
             jpeg_quality=jpeg_save_quality,
             backup_folder_path=backup_folder_path, # Передаємо як є (може бути None)
         )
         print("\n--- Робота скрипту завершена ---")