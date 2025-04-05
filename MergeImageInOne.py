# -*- coding: utf-8 -*-
import math
import os
import glob
# Переконайтесь, що Pillow встановлено: pip install Pillow
from PIL import Image, UnidentifiedImageError, ImageFile
import traceback # Для детальних помилок
import sys # Для перевірки бібліотек

# Переконайтесь, що natsort встановлено: pip install natsort
try:
    from natsort import natsorted
    print("INFO: Бібліотека natsort знайдена.")
except ImportError:
    print("ПОПЕРЕДЖЕННЯ: Бібліотека natsort не знайдена. Сортування буде стандартним.")
    natsorted = sorted

# --- Перевірка Pillow ---
try:
    import PIL
    print("INFO: Бібліотека Pillow (PIL) знайдена.")
except ImportError:
    print("!!! КРИТИЧНА ПОМИЛКА: Бібліотека Pillow (PIL) не знайдена. Встановіть: pip install Pillow")
    sys.exit(1)
# --- ---

ImageFile.LOAD_TRUNCATED_IMAGES = True
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp', '.tif')

# --- Функція безпечного закриття ---
def safe_close(img_obj):
    """Безпечно закриває об'єкт Image, ігноруючи помилки."""
    if img_obj and isinstance(img_obj, Image.Image):
        try:
            img_obj.close()
        except Exception:
            pass # Ігноруємо помилки при закритті

# --- Функція відбілювання ---
# <<< МОДИФІКАЦІЯ: Додано параметр cancel_threshold_sum >>>
def whiten_image_by_darkest_perimeter(img, cancel_threshold_sum):
    """
    Відбілює зображення за найтемнішим пікселем периметру.
    Перевіряє поріг темності перед відбілюванням.
    """
    print("    - Спроба відбілювання (за пікселем периметру)...")
    img_copy = None
    alpha_channel = None
    img_rgb = None
    img_whitened_rgb = None
    r_ch, g_ch, b_ch = None, None, None
    out_r, out_g, out_b = None, None, None
    final_image = img # Повернемо оригінал за замовчуванням

    try:
        # Завжди працюємо з копією, бажано RGBA для збереження прозорості, якщо вона є
        img_copy = img.convert("RGBA") if img.mode != 'RGBA' else img.copy()
        original_mode = img.mode # Використовуємо мод оригіналу для логіки
        has_alpha = 'A' in img_copy.getbands()

        # Готуємо RGB версію для аналізу пікселів
        if has_alpha:
            split_bands = img_copy.split()
            if len(split_bands) == 4:
                alpha_channel = split_bands[3] # Зберігаємо альфу
                img_rgb = img_copy.convert('RGB') # RGB для аналізу
            else: # Якщо split не дав 4 канали
                img_rgb = img_copy.convert('RGB')
                has_alpha = False # Не змогли виділити альфу
        else:
            # Якщо альфи не було, img_rgb це або копія (якщо оригінал RGB) або конвертована копія
            img_rgb = img_copy if original_mode == 'RGB' else img_copy.convert('RGB')

        width, height = img_rgb.size
        if width <= 1 or height <= 1:
            print("      ! Зображення замале для аналізу периметру. Відбілювання скасовано.")
            final_image = img_copy # Повернемо RGBA/RGB копію
            return final_image # Виходимо раніше

        darkest_pixel_rgb = None
        min_sum = float('inf')
        pixels = img_rgb.load()

        # Оптимізований пошук
        perimeter_pixels = []
        if height > 0: perimeter_pixels.extend([(x, 0) for x in range(width)]) # Верх
        if height > 1: perimeter_pixels.extend([(x, height - 1) for x in range(width)]) # Низ
        if width > 0: perimeter_pixels.extend([(0, y) for y in range(1, height - 1)]) # Лівий (без кутів)
        if width > 1: perimeter_pixels.extend([(width - 1, y) for y in range(1, height - 1)]) # Правий (без кутів)

        for x, y in perimeter_pixels:
            try:
                pixel = pixels[x, y]
                # Перевіряємо, чи це RGB кортеж
                if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                    r, g, b = pixel[:3]
                    # Переконуємось, що це числа
                    if isinstance(r, (int, float)) and isinstance(g, (int, float)) and isinstance(b, (int, float)):
                        current_sum = r + g + b
                        if current_sum < min_sum:
                            min_sum = current_sum
                            darkest_pixel_rgb = (int(r), int(g), int(b)) # Зберігаємо як int
            except Exception: continue # Пропускаємо піксель, якщо помилка читання

        if darkest_pixel_rgb is None:
            print("      ! Не знайдено валідних пікселів периметру. Відбілювання скасовано.")
            final_image = img_copy # Повертаємо копію
            return final_image

        ref_r, ref_g, ref_b = darkest_pixel_rgb
        current_pixel_sum = min_sum # Використовуємо знайдену мінімальну суму
        print(f"      - Знайдений найтемніший піксель: R={ref_r}, G={ref_g}, B={ref_b} (Сума: {current_pixel_sum:.0f})")
        print(f"      - Поріг скасування відбілювання (мін. сума): {cancel_threshold_sum}")

        # <<< НОВА ЛОГІКА: Перевірка порогу скасування >>>
        if current_pixel_sum < cancel_threshold_sum:
            print(f"      ! Найтемніший піксель (сума {current_pixel_sum:.0f}) темніший за поріг ({cancel_threshold_sum}). Відбілювання скасовано.")
            final_image = img_copy # Повертаємо копію (можливо RGBA) без змін
            # Ресурси будуть закриті у finally
            return final_image
        # <<< КІНЕЦЬ НОВОЇ ЛОГІКИ >>>

        # Перевірка, чи референс вже білий
        if ref_r == 255 and ref_g == 255 and ref_b == 255:
            print("      - Відбілювання не потрібне (референс вже білий).")
            final_image = img_copy # Повертаємо копію (з можливою альфою)
            return final_image

        # Продовжуємо відбілювання
        print(f"      - Референс для відбілювання: R={ref_r}, G={ref_g}, B={ref_b}")
        scale_r = 255.0 / max(1, ref_r)
        scale_g = 255.0 / max(1, ref_g)
        scale_b = 255.0 / max(1, ref_b)
        print(f"      - Множники: R*={scale_r:.2f}, G*={scale_g:.2f}, B*={scale_b:.2f}")

        lut_r = bytes([min(255, int(i * scale_r)) for i in range(256)])
        lut_g = bytes([min(255, int(i * scale_g)) for i in range(256)])
        lut_b = bytes([min(255, int(i * scale_b)) for i in range(256)])

        # Розділяємо канали img_rgb (який точно RGB)
        r_ch, g_ch, b_ch = img_rgb.split()
        out_r = r_ch.point(lut_r)
        out_g = g_ch.point(lut_g)
        out_b = b_ch.point(lut_b)
        img_whitened_rgb = Image.merge('RGB', (out_r, out_g, out_b))
        print("      - Відбілене RGB зображення створено.")

        # Відновлюємо альфа-канал, якщо він був
        if alpha_channel:
            print("      - Відновлення альфа-каналу...")
            # Додаємо альфу до нового відбіленого RGB
            img_whitened_rgb.putalpha(alpha_channel)
            final_image = img_whitened_rgb # Результат - відбілений RGBA
            img_whitened_rgb = None # Щоб не закрити його у finally, якщо він став final_image
            print("      - Відбілювання з альфа-каналом завершено.")
        else:
            final_image = img_whitened_rgb # Результат - відбілений RGB
            img_whitened_rgb = None # Щоб не закрити його у finally
            print("      - Відбілювання (без альфа-каналу) завершено.")

    except Exception as e:
        print(f"      ! Помилка під час відбілювання: {e}. Повертається копія.")
        traceback.print_exc(limit=1) # Додамо трохи деталей помилки
        # Повертаємо img_copy, бо це найбільш безпечний варіант (принаймні RGBA або копія)
        final_image = img_copy if img_copy else img
    finally:
        # Закриваємо всі проміжні об'єкти
        safe_close(r_ch)
        safe_close(g_ch)
        safe_close(b_ch)
        safe_close(out_r)
        safe_close(out_g)
        safe_close(out_b)
        safe_close(alpha_channel)
        # Закриваємо img_rgb тільки якщо він був створений окремо від img_copy
        if img_rgb and img_rgb is not img_copy:
            safe_close(img_rgb)
        # Закриваємо img_whitened_rgb тільки якщо він був створений і НЕ є фінальним результатом
        if img_whitened_rgb and img_whitened_rgb is not final_image:
             safe_close(img_whitened_rgb)
         # Закриваємо img_copy тільки якщо він був створений і НЕ є фінальним результатом
        if img_copy and img_copy is not final_image:
            safe_close(img_copy)
        # Оригінальний 'img' не закриваємо тут, це відповідальність викликаючої функції

    # Повертаємо або відбілене зображення (RGB або RGBA), або копію оригіналу (RGBA/RGB)
    return final_image


# --- Функція видалення білого фону ---
# ... (код remove_white_background залишається без змін) ...
def remove_white_background(img, tolerance):
    """Перетворює білі пікселі на прозорі."""
    print(f"    - Спроба видалення білого фону (допуск: {tolerance})...")
    img_rgba = None
    final_image = img
    try:
        # Завжди працюємо з копією RGBA
        img_rgba = img.convert('RGBA') if img.mode != 'RGBA' else img.copy()

        datas = list(img_rgba.getdata())
        newData = []
        cutoff = 255 - tolerance
        transparent_count = 0

        for item in datas:
            # Перевіряємо R, G, B і що піксель непрозорий
            if item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff and item[3] > 0:
                newData.append((*item[:3], 0)) # Робимо прозорим
                transparent_count += 1
            else:
                newData.append(item) # Залишаємо як є

        if transparent_count > 0:
            print(f"      - Зроблено прозорими: {transparent_count} пікселів.")
            img_rgba.putdata(newData)
            final_image = img_rgba # Результат - змінена RGBA копія
            img_rgba = None # Обнуляємо, щоб не закрити у finally
            print("      - Видалення фону завершено.")
        else:
            print("      - Білих пікселів для видалення не знайдено.")
            final_image = img_rgba # Повертаємо RGBA копію без змін
            img_rgba = None # Обнуляємо

    except Exception as e:
        print(f"      ! Помилка під час видалення білого фону: {e}. Повертається оригінал.")
        final_image = img # Повертаємо початковий об'єкт у разі помилки
        # img_rgba буде закрито у finally
    finally:
        # Закриваємо проміжну копію, якщо вона не стала результатом
        if img_rgba and img_rgba is not final_image:
            safe_close(img_rgba)

    return final_image

# --- Функція обрізки ---
# ... (код crop_image залишається без змін) ...
def crop_image(img, symmetric_axes=False, symmetric_absolute=False):
    """Обрізає прозорі краї зображення з опціями симетрії."""
    mode_str = "Стандартний"
    if symmetric_absolute: mode_str = "Абсолютно симетричний"
    elif symmetric_axes: mode_str = "Симетричний по осях"
    print(f"    - Спроба обрізки країв (Режим: {mode_str})...")

    img_rgba = None
    cropped_img = None
    final_image = img

    try:
        # Працюємо з RGBA для getbbox
        img_rgba = img.convert('RGBA') if img.mode != 'RGBA' else img.copy()

        bbox = img_rgba.getbbox()
        if not bbox:
            print("      - Не знайдено непрозорих пікселів. Обрізка не потрібна.")
            final_image = img_rgba # Повертаємо RGBA версію
            img_rgba = None # Обнуляємо
            return final_image

        original_width, original_height = img_rgba.size
        left, upper, right, lower = bbox
        print(f"      - Знайдено bbox: L={left}, T={upper}, R={right}, B={lower}")

        if left >= right or upper >= lower:
             print(f"      ! Невалідний bbox. Обрізка скасована.")
             final_image = img_rgba # Повертаємо RGBA версію
             img_rgba = None
             return final_image

        base_crop_box = bbox
        if symmetric_absolute:
            dist_left = left; dist_top = upper
            dist_right = original_width - right; dist_bottom = original_height - lower
            min_dist = min(dist_left, dist_top, dist_right, dist_bottom)
            new_box = (min_dist, min_dist, original_width - min_dist, original_height - min_dist)
            if new_box[0] < new_box[2] and new_box[1] < new_box[3]: # Перевірка валідності
                 base_crop_box = new_box
                 print(f"      - Абсолютно симетричний bbox: {base_crop_box}")
            else: print("      ! Абсолютно симетричний bbox невалідний, використання стандартного.")
        elif symmetric_axes:
            dist_left = left; dist_top = upper
            dist_right = original_width - right; dist_bottom = original_height - lower
            min_h = min(dist_left, dist_right); min_v = min(dist_top, dist_bottom)
            new_box = (min_h, min_v, original_width - min_h, original_height - min_v)
            if new_box[0] < new_box[2] and new_box[1] < new_box[3]: # Перевірка валідності
                 base_crop_box = new_box
                 print(f"      - Симетричний по осях bbox: {base_crop_box}")
            else: print("      ! Симетричний по осях bbox невалідний, використання стандартного.")

        # Додаємо відступ 1px
        l, u, r, b = base_crop_box
        final_crop_box = (max(0, l - 1), max(0, u - 1),
                          min(original_width, r + 1), min(original_height, b + 1))
        print(f"      - Фінальний crop_box (з відступом 1px): {final_crop_box}")

        # Перевірка, чи обрізка взагалі потрібна
        if final_crop_box == (0, 0, original_width, original_height):
             print("      - Обрізка не потрібна (рамка збігається з розміром зображення).")
             final_image = img_rgba # Повертаємо RGBA версію
             img_rgba = None
        elif final_crop_box[0] < final_crop_box[2] and final_crop_box[1] < final_crop_box[3]:
            cropped_img = img_rgba.crop(final_crop_box)
            print(f"      - Обрізка успішна. Новий розмір: {cropped_img.size}")
            final_image = cropped_img # Результат - нове обрізане зображення
            cropped_img = None # Обнуляємо
        else:
             print("      ! Невалідний фінальний crop_box. Обрізка скасована.")
             final_image = img_rgba # Повертаємо RGBA версію без обрізки
             img_rgba = None

    except Exception as e:
        print(f"      ! Помилка під час обрізки: {e}. Повертається оригінал.")
        final_image = img # Повертаємо початковий об'єкт
        # cropped_img та img_rgba будуть закриті у finally
    finally:
        # Закриваємо img_rgba, якщо він був створений і не є фінальним результатом
        if img_rgba and img_rgba is not final_image:
            safe_close(img_rgba)
        # Закриваємо cropped_img, якщо він був створений і не є фінальним результатом
        if cropped_img and cropped_img is not final_image:
            safe_close(cropped_img)

    return final_image


# --- Функція додавання полів ---
# ... (код add_padding залишається без змін) ...
def add_padding(img, percent):
    """Додає прозорі поля навколо зображення."""
    if percent <= 0:
        return img
    print(f"    - Спроба додавання полів ({percent}%)...")
    img_rgba_src = None
    padded_img = None
    final_image = img

    try:
        w, h = img.size
        if w == 0 or h == 0: return img # Немає чого додавати
        pp = int(max(w, h) * (percent / 100.0))
        if pp <= 0: return img # Поля нульові

        nw, nh = w + 2*pp, h + 2*pp
        print(f"      - Оригінал: {w}x{h}, Поле: {pp}px, Новий розмір: {nw}x{nh}")

        # Переконуємося, що джерело RGBA для коректної вставки
        img_rgba_src = img if img.mode == 'RGBA' else img.convert('RGBA')

        padded_img = Image.new('RGBA', (nw, nh), (0,0,0,0))
        # Використовуємо альфа-канал джерела як маску
        padded_img.paste(img_rgba_src, (pp, pp), mask=img_rgba_src)
        print("      - Поля успішно додано.")
        final_image = padded_img # Результат - нове зображення з полями
        padded_img = None # Обнуляємо

    except Exception as e:
        print(f"      ! Помилка під час додавання полів: {e}. Повертається оригінал.")
        final_image = img
        # padded_img та img_rgba_src будуть закриті у finally
    finally:
        # Закриваємо конвертовану копію, якщо вона була створена
        if img_rgba_src and img_rgba_src is not img:
             safe_close(img_rgba_src)
        # Закриваємо padded_img, якщо сталася помилка і він не результат
        if padded_img and final_image is not padded_img:
             safe_close(padded_img)

    return final_image

# --- Функція перевірки білого периметру (Інформаційна) ---
# ... (код check_perimeter_is_white залишається без змін) ...
def check_perimeter_is_white(img, tolerance, margin):
    """Перевіряє, чи є периметр зображення білим (інформаційно)."""
    if margin <= 0: return False
    print(f"    - Інфо: Перевірка білого периметру (відступ {margin}px, допуск {tolerance})...")
    img_check = None
    mask = None # <<< Додано змінну для маски
    is_white = False
    try:
        # Готуємо RGB копію для перевірки, накладаючи на білий фон, якщо є альфа
        if img.mode == 'RGBA' or 'A' in img.getbands():
             img_check = Image.new("RGB", img.size, (255, 255, 255))
             try:
                 mask = img.getchannel('A')
                 img_check.paste(img, mask=mask)
             except Exception: # Якщо не вдалося отримати/використати маску
                 print("      ! Попередження: не вдалося використати альфа-канал для перевірки периметру.")
                 img_check.paste(img) # Спробуємо просто paste
        else:
            # Якщо немає альфи, просто конвертуємо в RGB або копіюємо
            img_check = img.convert("RGB") if img.mode != 'RGB' else img.copy()

        width, height = img_check.size
        # Розраховуємо межі перевірки
        mh = min(margin, height // 2 if height > 0 else 0)
        mw = min(margin, width // 2 if width > 0 else 0)
        # Якщо margin > 0, але розмір замалий, забезпечимо перевірку хоча б 1 пікселя
        if mh == 0 and height > 0 and margin > 0: mh = 1
        if mw == 0 and width > 0 and margin > 0: mw = 1

        if mh == 0 or mw == 0 or width == 0 or height == 0: # Немає чого перевіряти
             print("      ! Зображення замале для перевірки периметру.")
             return False

        pixels = img_check.load()
        cutoff = 255 - tolerance
        is_perimeter_white = True

        # Оптимізований збір координат
        perimeter_coords = set()
        if mh > 0:
            perimeter_coords.update([(x, y) for y in range(mh) for x in range(width)]) # Верх
            perimeter_coords.update([(x, y) for y in range(height - mh, height) for x in range(width)]) # Низ
        if mw > 0:
            perimeter_coords.update([(x, y) for x in range(mw) for y in range(mh, height - mh)]) # Ліво
            perimeter_coords.update([(x, y) for x in range(width - mw, width) for y in range(mh, height - mh)]) # Право

        # Перевірка пікселів
        for x, y in perimeter_coords:
            try:
                p = pixels[x, y]
                # Перевіряємо, чи всі канали RGB >= cutoff
                if not (p[0] >= cutoff and p[1] >= cutoff and p[2] >= cutoff):
                    is_perimeter_white = False
                    # print(f"      - Знайдено не білий піксель: ({x},{y}) = {p}") # Debug
                    break # Достатньо одного не білого
            except IndexError:
                 print(f"      ! Помилка індексу при доступі до пікселя ({x},{y})")
                 is_perimeter_white = False; break
            except Exception as pixel_err:
                 print(f"      ! Помилка читання пікселя ({x},{y}): {pixel_err}")
                 is_perimeter_white = False; break

        is_white = is_perimeter_white # Результат перевірки
        print(f"      - Результат інфо-перевірки: Периметр {'білий' if is_white else 'НЕ білий'}.")

    except Exception as e:
        print(f"      ! Помилка під час інфо-перевірки периметру: {e}")
        is_white = False
    finally:
        safe_close(img_check)
        safe_close(mask) # <<< Закриваємо маску
    return is_white


# --- Функція обробки одного зображення ---
# <<< МОДИФІКАЦІЯ: Додано параметр whitening_cancel_threshold_sum >>>
def process_image(image_path, enable_whitening, whitening_cancel_threshold_sum,
                  white_tolerance, perimeter_margin,
                  crop_symmetric_axes, crop_symmetric_absolute):
    """Завантажує, обробляє та повертає зображення RGBA або None."""
    print(f"\n--- Обробка файлу: {os.path.basename(image_path)} ---")
    img = None
    processed_img = None # Змінна для результату після всіх кроків

    try:
        # 1. Завантаження
        print("  - Крок 1: Завантаження...")
        img_opened = None # Оголошуємо поза with для finally
        try:
             img_opened = Image.open(image_path)
             img_opened.load()
             # Одразу конвертуємо в RGBA для уніфікації подальших кроків
             img = img_opened.convert('RGBA')
             print(f"    - Завантажено та конвертовано в RGBA. Розмір: {img.size}")
        finally:
             safe_close(img_opened) # Закриваємо файловий дескриптор

        if not img: # Якщо конвертація не вдалась (малоймовірно)
             raise ValueError("Не вдалося створити об'єкт зображення.")

        processed_img = img # Починаємо з RGBA версії
        img = None # Початковий об'єкт більше не потрібен

        # 2. Відбілювання (Опціонально)
        if enable_whitening:
            print("  - Крок 2: Відбілювання...")
            # <<< МОДИФІКАЦІЯ: Передаємо поріг >>>
            whitened = whiten_image_by_darkest_perimeter(processed_img, whitening_cancel_threshold_sum)
            if whitened is not processed_img: # Якщо відбілювання щось змінило/створило новий об'єкт
                safe_close(processed_img) # Закриваємо попередній стан
                processed_img = whitened # Оновлюємо результат
                print(f"    - Результат відбілювання застосовано. Режим: {processed_img.mode}")
            else:
                print(f"    - Відбілювання не змінило зображення (або було скасовано).")
                # processed_img залишається тим самим

        # 3. Перевірка периметру (Інформаційно)
        if perimeter_margin > 0:
             print("  - Крок 3: Інформаційна перевірка периметру...")
             check_tolerance = white_tolerance if white_tolerance is not None and white_tolerance >= 0 else 0
             check_perimeter_is_white(processed_img, check_tolerance, perimeter_margin)

        # 4 & 5. Видалення фону та Обрізка (Якщо white_tolerance задано)
        enable_bg_removal_and_crop = white_tolerance is not None and white_tolerance >= 0
        if enable_bg_removal_and_crop:
            print(f"  - Крок 4: Видалення білого фону (допуск {white_tolerance})...")
            no_bg = remove_white_background(processed_img, white_tolerance)
            if no_bg is not processed_img:
                 safe_close(processed_img)
                 processed_img = no_bg
                 print(f"    - Фон видалено. Режим: {processed_img.mode}")
            else:
                 print(f"    - Видалення фону не змінило зображення.")


            print("  - Крок 5: Обрізка країв...")
            cropped = crop_image(processed_img, crop_symmetric_axes, crop_symmetric_absolute)
            if cropped is not processed_img:
                 safe_close(processed_img)
                 processed_img = cropped
                 print(f"    - Обрізку виконано. Розмір: {processed_img.size}, Режим: {processed_img.mode}")
            else:
                 print(f"    - Обрізка не змінила зображення.")


            # Перевірка на порожнє зображення після обрізки
            if not processed_img or processed_img.size[0] <= 0 or processed_img.size[1] <= 0:
                 print(f"  !! ПОМИЛКА: Зображення стало порожнім після видалення фону/обрізки. Пропуск файлу.")
                 safe_close(processed_img) # Закриємо те, що залишилося
                 return None
        else:
             print("  - Кроки 4 та 5: Видалення фону та обрізка вимкнені.")

        # 6. Фінальна перевірка (має бути RGBA)
        if processed_img.mode != 'RGBA':
             print(f"  ! ПОПЕРЕДЖЕННЯ: Результат чомусь не RGBA ({processed_img.mode}). Спроба фінальної конвертації...")
             final_rgba = None
             try:
                 final_rgba = processed_img.convert("RGBA")
                 safe_close(processed_img) # Закриваємо попередній
                 processed_img = final_rgba
                 final_rgba = None # Обнуляємо
                 print(f"    - Успішна фінальна конвертація в RGBA.")
             except Exception as e:
                 print(f"  !! КРИТИЧНА ПОМИЛКА фінальної конвертації в RGBA: {e}. Пропуск файлу.")
                 safe_close(processed_img) # Закриваємо попередній
                 safe_close(final_rgba)    # Закриваємо результат конвертації, якщо він є
                 return None

        print(f"--- Успішно завершено обробку {os.path.basename(image_path)}. Фінал: {processed_img.size} {processed_img.mode} ---")
        return processed_img # Повертаємо фінальний результат (завжди RGBA на цьому етапі)

    except FileNotFoundError:
        print(f"  !! КРИТИЧНА ПОМИЛКА: Файл не знайдено '{image_path}'")
        return None
    except UnidentifiedImageError:
        print(f"  !! ПОМИЛКА: Не розпізнано формат або файл пошкоджено: '{os.path.basename(image_path)}'")
        return None
    except Exception as e:
        print(f"  !! НЕОЧІКУВАНА ГЛОБАЛЬНА ПОМИЛКА обробки {os.path.basename(image_path)}: {e}")
        traceback.print_exc(limit=2)
    finally:
        # Закриваємо основні змінні, якщо вони ще існують і не є результатом
        safe_close(img)
        # processed_img повертається або стає None, його закривати не треба тут
        pass

    # Якщо дісталися сюди через помилку в try блоці
    safe_close(processed_img) # Закриваємо на випадок помилки
    return None


# --- Функція об'єднання ---
# <<< МОДИФІКАЦІЯ: Додано параметр whitening_cancel_threshold_sum >>>
def combine_images(image_paths, output_path,
                   enable_whitening, whitening_cancel_threshold_sum,
                   forced_cols, spacing_percent, white_tolerance, quality,
                   perimeter_margin, padding_percent,
                   crop_symmetric_axes, crop_symmetric_absolute,
                   force_collage_aspect_ratio, max_collage_width, max_collage_height,
                   final_collage_exact_width, final_collage_exact_height,
                   output_format, jpg_background_color,
                   proportional_placement, placement_ratios):
    """Обробляє, об'єднує та зберігає зображення у вигляді колажу."""

    output_format_lower = output_format.lower()
    if output_format_lower not in ['jpg', 'png']:
        print(f"!! ПОМИЛКА: Непідтримуваний формат виводу '{output_format}'. СКАСОВАНО.")
        return
    if not image_paths:
        print("Немає шляхів до зображень.")
        return

    processed_images = [] # Для результатів process_image (RGBA)
    padded_images = []    # Для зображень з полями
    scaled_images = []    # Для масштабованих зображень
    canvas = None         # Холст колажу
    collage_step_img = None # Проміжний результат трансформації колажу
    final_img_to_save = None # Фінальне зображення для збереження
    temp_img = None       # Для проміжних трансформацій

    try:
        # --- 1. Обробка індивідуальних зображень ---
        print("\n--- КРОК 1: Базова обробка зображень ---")
        output_abs_path = os.path.abspath(output_path) if output_path else None
        for i, path in enumerate(image_paths):
            # Перевірка, щоб не обробляти сам вихідний файл, якщо він у тій же папці
            if output_abs_path and os.path.abspath(path).lower() == output_abs_path.lower():
                print(f"   - Пропуск: '{os.path.basename(path)}' (збігається з вихідним файлом).")
                continue
            # <<< МОДИФІКАЦІЯ: Передаємо поріг >>>
            processed = process_image(path, enable_whitening, whitening_cancel_threshold_sum,
                                     white_tolerance, perimeter_margin,
                                     crop_symmetric_axes, crop_symmetric_absolute)
            if processed:
                processed_images.append(processed)
            # process_image сама друкує помилки

        num_processed = len(processed_images)
        if num_processed == 0:
            print("\nНемає зображень для об'єднання після базової обробки.")
            return
        print(f"\n--- Базова обробка завершена. Готово {num_processed} зображень (Режим RGBA) ---")

        # --- 2. Пропорційне масштабування (опц.) ---
        source_list_scaling = processed_images # Список для цього кроку
        target_list_scaling = scaled_images  # Куди записувати результат
        if proportional_placement and num_processed > 0:
            print("\n--- КРОК 2: Пропорційне масштабування ---")
            # Визначаємо базовий розмір з першого вдало обробленого зображення
            base_w, base_h = source_list_scaling[0].size
            if base_w > 0 and base_h > 0:
                print(f"  - Базовий розмір (з першого зображення): {base_w}x{base_h}px")
                ratios = placement_ratios if placement_ratios else []
                for i, img in enumerate(source_list_scaling):
                    temp_img = None # Скидаємо тимчасову змінну
                    ratio = 1.0
                    # Застосовуємо коефіцієнт, якщо він є для цього індексу
                    if i < len(ratios):
                        try: ratio = float(ratios[i]); ratio = max(0.01, ratio) # Мін. коеф. 0.01
                        except (ValueError, TypeError): ratio = 1.0

                    # Розраховуємо цільові розміри на основі базового та коефіцієнта
                    target_w = int(base_w * ratio); target_h = int(base_h * ratio)
                    current_w, current_h = img.size

                    # Перевіряємо, чи потрібно масштабування і чи розміри валідні
                    if current_w > 0 and current_h > 0 and target_w > 0 and target_h > 0:
                        # Рахуємо коефіцієнт для вписування в цільові розміри
                        scale = min(target_w / current_w, target_h / current_h)
                        nw, nh = max(1, int(current_w * scale)), max(1, int(current_h * scale))

                        # Змінюємо розмір тільки якщо новий розмір відрізняється
                        if nw != current_w or nh != current_h:
                             try:
                                 print(f"  - Зобр.{i+1}: Масштабування {current_w}x{current_h} -> {nw}x{nh} (Ціль: ~{target_w}x{target_h}, Ratio: {ratio:.2f})")
                                 temp_img = img.resize((nw, nh), Image.Resampling.LANCZOS)
                                 target_list_scaling.append(temp_img) # Додаємо нове
                                 safe_close(img) # Закриваємо старе
                             except Exception as e_scale:
                                 print(f"  ! Помилка масштабування зобр.{i+1}: {e_scale}")
                                 target_list_scaling.append(img) # Додаємо незмінене у разі помилки
                        else:
                             print(f"  - Зобр.{i+1}: Масштабування не потрібне ({current_w}x{current_h}).")
                             target_list_scaling.append(img) # Додаємо незмінене
                    else:
                         print(f"  - Зобр.{i+1}: Пропуск масштабування через невалідні розміри.")
                         target_list_scaling.append(img) # Додаємо незмінене
                # processed_images тепер не потрібен, працюємо з scaled_images
                processed_images = []
            else:
                print("  ! Базове зображення має нульовий розмір. Масштабування пропущено.")
                target_list_scaling.extend(source_list_scaling) # Копіюємо без змін
                processed_images = [] # Очищаємо попередній список
        else:
            print("\n--- КРОК 2: Пропорційне масштабування вимкнено ---")
            target_list_scaling.extend(source_list_scaling) # Копіюємо без змін
            processed_images = [] # Очищаємо попередній список

        # --- 3. Додавання полів ---
        source_list_padding = scaled_images # Список для цього кроку
        target_list_padding = padded_images # Куди записувати результат
        if padding_percent > 0:
            print(f"\n--- КРОК 3: Додавання полів ({padding_percent}%) ---")
            for i, img in enumerate(source_list_padding):
                 temp_img = add_padding(img, padding_percent)
                 target_list_padding.append(temp_img)
                 if temp_img is not img: safe_close(img) # Закриваємо попереднє, якщо було створено нове
            scaled_images = [] # Очищаємо попередній список
        else:
             print("\n--- КРОК 3: Додавання полів вимкнено ---")
             target_list_padding.extend(source_list_padding) # Копіюємо без змін
             scaled_images = [] # Очищаємо попередній список

        # Перевірка після перших кроків
        num_final_images = len(padded_images)
        if num_final_images == 0:
            print("\nНемає зображень для об'єднання після кроків обробки/масштабування/полів.")
            return

        # --- 4. Розрахунок розмірів колажу ---
        print(f"\n--- КРОК 4: Створення колажу ({num_final_images} зображень) ---")
        # Визначаємо сітку
        grid_cols = forced_cols if forced_cols > 0 else max(1, math.ceil(math.sqrt(num_final_images)))
        grid_rows = max(1, math.ceil(num_final_images / grid_cols))
        # Знаходимо максимальні розміри комірки (на основі зображень з полями)
        max_w = max((img.size[0] for img in padded_images if img and img.size[0] > 0), default=1)
        max_h = max((img.size[1] for img in padded_images if img and img.size[1] > 0), default=1)

        # Розраховуємо відступи та розмір холсту
        h_spacing = int(max_w * (spacing_percent / 100.0))
        v_spacing = int(max_h * (spacing_percent / 100.0))
        canvas_width = (grid_cols * max_w) + ((grid_cols + 1) * h_spacing)
        canvas_height = (grid_rows * max_h) + ((grid_rows + 1) * v_spacing)

        print(f"  - Сітка: {grid_rows}x{grid_cols}, Макс. комірка: {max_w}x{max_h}, Відступи: H={h_spacing} V={v_spacing}")
        print(f"  - Розрахунковий розмір холсту: {canvas_width}x{canvas_height}")
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        collage_step_img = canvas # Починаємо трансформації з цього холсту
        canvas = None # Обнуляємо

        # --- 5. Розміщення зображень ---
        print("  - Розміщення зображень на холсті...")
        current_idx = 0
        for r in range(grid_rows):
            # Визначаємо кількість елементів у поточному рядку (останній може бути неповним)
            items_in_row = min(grid_cols, num_final_images - (r * grid_cols))
            # Горизонтальне центрування останнього (можливо неповного) рядка
            row_width_content = items_in_row * max_w + (items_in_row -1) * h_spacing if items_in_row > 0 else 0
            start_x_offset = (canvas_width - (row_width_content + 2 * h_spacing)) // 2

            for c in range(items_in_row):
                if current_idx >= num_final_images: break # Перевірка про всяк випадок
                img = padded_images[current_idx]
                if img and img.size[0] > 0 and img.size[1] > 0:
                     # Координати верхнього лівого кута для вставки
                     # px = h_spacing + c * (max_w + h_spacing) # Без центрування рядка
                     px = start_x_offset + h_spacing + c * (max_w + h_spacing) # З центруванням рядка
                     py = v_spacing + r * (max_h + v_spacing)
                     # Центрування зображення всередині його комірки max_w x max_h
                     paste_x = px + (max_w - img.width) // 2
                     paste_y = py + (max_h - img.height) // 2
                     try:
                          # Вставляємо зображення, використовуючи його альфа-канал як маску
                          collage_step_img.paste(img, (paste_x, paste_y), mask=img)
                     except Exception as e_paste:
                          print(f"  ! Помилка вставки зображення {current_idx+1} в ({paste_x},{paste_y}): {e_paste}")
                current_idx += 1
            if current_idx >= num_final_images: break # Виходимо з зовнішнього циклу
        print("  - Розміщення зображень завершено.")

        # Закриваємо зображення з padded_images, вони більше не потрібні
        print("  - Зачистка проміжних зображень (після вставки)...")
        for img in padded_images:
            safe_close(img)
        padded_images = []

        # --- 6. Трансформації Колажу ---
        print("\n--- КРОК 5: Трансформації колажу (Співвідношення, Макс.розмір, Точний холст) ---")
        # 6а. Співвідношення сторін
        valid_ratio = (force_collage_aspect_ratio and isinstance(force_collage_aspect_ratio, (tuple, list)) and len(force_collage_aspect_ratio) == 2 and
                       force_collage_aspect_ratio[0] > 0 and force_collage_aspect_ratio[1] > 0)
        if valid_ratio:
            target_w_r, target_h_r = force_collage_aspect_ratio
            cw, ch = collage_step_img.size
            if cw > 0 and ch > 0 : # Перевірка на нульовий розмір
                current_aspect = cw / ch
                desired_aspect = target_w_r / target_h_r
                # Застосовуємо тільки якщо співвідношення суттєво відрізняється
                if abs(current_aspect - desired_aspect) > 0.01:
                    print(f"  - Застосування співвідношення {target_w_r}:{target_h_r}...")
                    # Визначаємо нові розміри холсту
                    if current_aspect > desired_aspect: # Зображення зашироке -> збільшуємо висоту
                        nw, nh = cw, int(cw / desired_aspect)
                    else: # Зображення зависоке -> збільшуємо ширину
                        nw, nh = int(ch * desired_aspect), ch
                    nw, nh = max(1, nw), max(1, nh) # Захист від нуля
                    temp_img = None
                    try:
                        temp_img = Image.new('RGBA', (nw, nh), (0,0,0,0)) # Новий прозорий холст
                        x, y = (nw - cw) // 2, (nh - ch) // 2 # Координати для центрування
                        temp_img.paste(collage_step_img, (x, y), mask=collage_step_img) # Вставляємо старий колаж
                        safe_close(collage_step_img) # Закриваємо старий
                        collage_step_img = temp_img # Оновлюємо посилання
                        temp_img = None # Обнуляємо
                        print(f"    - Новий розмір після зміни співвідношення: {collage_step_img.size}")
                    except Exception as e_ratio:
                        print(f"  ! Помилка зміни співвідношення сторін: {e_ratio}")
                        safe_close(temp_img) # Закриваємо холст, якщо він створився
                else:
                    print(f"  - Співвідношення сторін вже відповідає цільовому.")
            else: print("  - Пропуск зміни співвідношення через нульовий розмір колажу.")

        # 6б. Максимальний розмір
        max_w_valid = max_collage_width is not None and max_collage_width > 0
        max_h_valid = max_collage_height is not None and max_collage_height > 0
        if max_w_valid or max_h_valid:
             cw, ch = collage_step_img.size
             if cw > 0 and ch > 0: # Перевірка на нульовий розмір
                 scale = 1.0
                 if max_w_valid and cw > max_collage_width: scale = min(scale, max_collage_width / cw)
                 if max_h_valid and ch > max_collage_height: scale = min(scale, max_collage_height / ch)

                 if scale < 1.0:
                     nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
                     print(f"  - Обмеження максимального розміру до {nw}x{nh}...")
                     temp_img = None
                     try:
                         temp_img = collage_step_img.resize((nw, nh), Image.Resampling.LANCZOS)
                         safe_close(collage_step_img) # Закриваємо старий
                         collage_step_img = temp_img # Оновлюємо посилання
                         temp_img = None # Обнуляємо
                         print(f"    - Новий розмір після обмеження: {collage_step_img.size}")
                     except Exception as e_resize:
                         print(f"  ! Помилка resize для обмеження розміру: {e_resize}")
                         safe_close(temp_img)
                 else:
                      print(f"  - Колаж вже в межах максимальних розмірів.")
             else: print("  - Пропуск обмеження розміру через нульовий розмір колажу.")


        # 6в. Точний холст
        use_exact = (final_collage_exact_width is not None and final_collage_exact_width > 0 and
                     final_collage_exact_height is not None and final_collage_exact_height > 0)
        if use_exact:
            cw, ch = collage_step_img.size
            tw, th = final_collage_exact_width, final_collage_exact_height
            if cw > 0 and ch > 0: # Перевірка на нульовий розмір
                if cw != tw or ch != th:
                    print(f"  - Створення фінального холсту {tw}x{th}...")
                    # Визначаємо режим та колір фону
                    mode = 'RGBA' if output_format_lower == 'png' else 'RGB'
                    bg_color = (0,0,0,0) if mode == 'RGBA' else jpg_background_color

                    # Масштабуємо вміст, щоб вписати його
                    scale_fit = min(tw / cw, th / ch)
                    nw, nh = max(1, int(cw * scale_fit)), max(1, int(ch * scale_fit))

                    temp_content = None
                    temp_canvas = None
                    paste_mask = None
                    try:
                        temp_content = collage_step_img.resize((nw, nh), Image.Resampling.LANCZOS)
                        temp_canvas = Image.new(mode, (tw, th), bg_color) # Створюємо фінальний холст

                        x, y = (tw - nw) // 2, (th - nh) // 2 # Координати для центрування

                        # Готуємо маску для вставки, якщо потрібно
                        # Якщо холст RGB, а вміст має прозорість - треба маска
                        # Якщо холст RGBA і вміст має прозорість - теж треба маска
                        if temp_content.mode == 'RGBA':
                             paste_mask = temp_content # Використовуємо альфа-канал RGBA як маску

                        # Виконуємо вставку
                        temp_canvas.paste(temp_content, (x, y), mask=paste_mask)

                        safe_close(collage_step_img) # Закриваємо попередній стан
                        collage_step_img = temp_canvas # Оновлюємо посилання
                        temp_canvas = None # Обнуляємо
                        print(f"    - Новий розмір (точний холст): {collage_step_img.size}, Режим: {collage_step_img.mode}")
                    except Exception as e_exact:
                         print(f"  ! Помилка створення точного холсту: {e_exact}")
                         safe_close(temp_content)
                         safe_close(temp_canvas)
                         # Не змінюємо collage_step_img
                    finally:
                         # paste_mask - це посилання на temp_content, закриється разом з ним
                         safe_close(temp_content) # Закриваємо масштабований вміст
                         # temp_canvas закриється, якщо не став collage_step_img
                         if temp_canvas: safe_close(temp_canvas)
                else:
                     print(f"  - Колаж вже має потрібний точний розмір ({tw}x{th}).")
            else: print("  - Пропуск створення точного холсту через нульовий розмір колажу.")

        # --- 7. Підготовка до збереження ---
        print("\n--- КРОК 6: Підготовка до збереження ---")
        final_img_to_save = collage_step_img # За замовчуванням
        collage_step_img = None # Обнуляємо для зачистки

        # Перевірка розміру перед фінальною конвертацією
        if not final_img_to_save or final_img_to_save.size[0] <= 0 or final_img_to_save.size[1] <= 0:
             print("!! ПОМИЛКА: Колаж має нульовий або некоректний розмір перед збереженням.")
             safe_close(final_img_to_save) # Закриваємо те, що є
             return # Виходимо

        # Конвертація для JPG
        if output_format_lower == 'jpg' and final_img_to_save.mode != 'RGB':
             print(f"  - Конвертація/Накладання {final_img_to_save.mode} -> RGB для JPG (фон: {jpg_background_color})...")
             temp_img = None
             paste_mask = None
             try:
                 temp_img = Image.new("RGB", final_img_to_save.size, jpg_background_color)
                 # Використовуємо альфа-канал для маски, якщо він є
                 if final_img_to_save.mode == 'RGBA':
                     paste_mask = final_img_to_save
                 # Виконуємо paste
                 temp_img.paste(final_img_to_save, (0,0), mask=paste_mask)

                 safe_close(final_img_to_save) # Закриваємо попередній (RGBA)
                 final_img_to_save = temp_img # Оновлюємо посилання
                 temp_img = None # Обнуляємо
                 print(f"    - Готово до збереження: {final_img_to_save.size} {final_img_to_save.mode}")
             except Exception as e_to_rgb:
                 print(f"  ! Помилка підготовки до RGB: {e_to_rgb}. Спроба зберегти як є.")
                 safe_close(temp_img) # Закриваємо невдалий холст
                 # final_img_to_save залишається яким був
        # Конвертація для PNG (якщо потрібно)
        elif output_format_lower == 'png' and final_img_to_save.mode != 'RGBA':
             print(f"  - Конвертація {final_img_to_save.mode} -> RGBA для PNG...")
             temp_img = None
             try:
                 temp_img = final_img_to_save.convert("RGBA")
                 safe_close(final_img_to_save) # Закриваємо попередній
                 final_img_to_save = temp_img # Оновлюємо посилання
                 temp_img = None # Обнуляємо
                 print(f"    - Готово до збереження: {final_img_to_save.size} {final_img_to_save.mode}")
             except Exception as e_to_rgba:
                 print(f"  ! Помилка конвертації в RGBA: {e_to_rgba}. Спроба зберегти як є.")
                 safe_close(temp_img)
                 # final_img_to_save залишається яким був
        else:
             # Режим вже відповідає формату збереження
             print(f"  - Зображення вже в потрібному режимі ({final_img_to_save.mode}).")


        # --- 8. Збереження ---
        if not final_img_to_save:
             print("!! ПОМИЛКА: Немає фінального зображення для збереження.")
             return
        if final_img_to_save.size[0] <= 0 or final_img_to_save.size[1] <= 0:
             print(f"!! ПОМИЛКА: Фінальне зображення має нульовий розмір {final_img_to_save.size}.")
             safe_close(final_img_to_save)
             return

        # Корекція шляху та імені файлу
        output_dir = os.path.dirname(output_path)
        output_base_name = os.path.basename(output_path)
        output_name_no_ext, _ = os.path.splitext(output_base_name)
        output_ext_correct = f".{output_format_lower}"
        corrected_output_path = os.path.join(output_dir, f"{output_name_no_ext}{output_ext_correct}")

        print(f"\n--- КРОК 7: Збереження результату у '{corrected_output_path}' ---")
        save_options = {"optimize": True}
        save_format = "JPEG" if output_format_lower == 'jpg' else "PNG"
        if save_format == "JPEG":
            save_options["quality"] = quality
            save_options["subsampling"] = 0
            print(f"  - Параметри JPEG: quality={quality}, subsampling=0")
        elif save_format == "PNG":
            save_options["compress_level"] = 6 # Рівень стиснення PNG (0-9)
            print(f"  - Параметри PNG: compress_level=6")


        final_img_to_save.save(corrected_output_path, save_format, **save_options)
        print(f"\n--- УСПІХ: Колаж збережено у файл '{os.path.basename(corrected_output_path)}' ---")

    except Exception as e:
        print(f"\n!!! КРИТИЧНА ПОМИЛКА під час створення колажу: {e}")
        traceback.print_exc()
    finally:
        print("\n--- Зачистка ресурсів ---")
        # Закриваємо всі основні змінні, якщо вони ще існують
        safe_close(canvas)
        safe_close(collage_step_img)
        safe_close(final_img_to_save)
        safe_close(temp_img)
        # Закриваємо списки зображень, які могли залишитись
        for lst in [processed_images, scaled_images, padded_images]:
            if isinstance(lst, list):
                for img_obj in lst:
                    safe_close(img_obj)
        print("--- Зачистка завершена ---")


# --- Основна функція запуску ---
# <<< МОДИФІКАЦІЯ: Додано параметр whitening_cancel_threshold_sum >>>
def run_processing(source_dir, output_filename,
                   enable_whitening, whitening_cancel_threshold_sum,
                   forced_cols, perimeter_margin, padding_percent, white_tolerance,
                   spacing_percent, quality,
                   crop_symmetric_axes, crop_symmetric_absolute,
                   force_collage_aspect_ratio, max_collage_width, max_collage_height,
                   final_collage_exact_width, final_collage_exact_height,
                   output_format, jpg_background_color,
                   proportional_placement, placement_ratios):
    """Знаходить файли та запускає об'єднання."""

    # --- Вивід налаштувань ---
    print("=" * 60)
    print("--- ЗАПУСК ОБРОБКИ ТА СТВОРЕННЯ КОЛАЖУ ---")
    print("=" * 60)
    print(f"[*] Папка джерела: '{source_dir}'")
    print(f"[*] Вихідний файл: '{output_filename}' (Формат: {output_format.upper()})")
    print("\n--- Налаштування Обробки Зображень ---")
    print(f"  - Відбілювання: {'Так' if enable_whitening else 'Ні'}")
    # <<< МОДИФІКАЦІЯ: Виводимо новий параметр >>>
    if enable_whitening:
        print(f"    - Поріг скасування відбілювання (мін. сума RGB): {whitening_cancel_threshold_sum}")
    bg_crop_enabled = white_tolerance is not None and white_tolerance >= 0
    print(f"  - Видалення фону/Обрізка: {'Так (Допуск: ' + str(white_tolerance) + ')' if bg_crop_enabled else 'Ні'}")
    if bg_crop_enabled:
        crop_mode = "Стандартний"
        if crop_symmetric_absolute: crop_mode = "Абсолютно симетричний"
        elif crop_symmetric_axes: crop_mode = "Симетричний по осях"
        print(f"    - Режим обрізки: {crop_mode}")
    print(f"  - Додавання полів: {padding_percent}%")
    print(f"  - Інфо-перевірка периметра: {'Так (' + str(perimeter_margin) + 'px)' if perimeter_margin is not None and perimeter_margin > 0 else 'Ні'}")

    print("\n--- Налаштування Колажу ---")
    print(f"  - Пропорційне розміщення: {'Так' if proportional_placement else 'Ні'}")
    if proportional_placement: print(f"    - Коефіцієнти: {placement_ratios}")
    print(f"  - Стовпці: {'Авто' if forced_cols is None or forced_cols <= 0 else forced_cols}")
    print(f"  - Відступ: {spacing_percent}%")
    # Перевірка валідності співвідношення
    ratio_valid = False
    ratio_str = "Ні"
    if force_collage_aspect_ratio and isinstance(force_collage_aspect_ratio, (tuple, list)) and len(force_collage_aspect_ratio) == 2:
         try:
             ar_w, ar_h = float(force_collage_aspect_ratio[0]), float(force_collage_aspect_ratio[1])
             if ar_w > 0 and ar_h > 0:
                  ratio_valid = True
                  ratio_str = f"Так ({ar_w}:{ar_h})"
         except (ValueError, TypeError): pass
    print(f"  - Співвідношення сторін: {ratio_str}")
    max_w_str = str(max_collage_width) if max_collage_width is not None and max_collage_width > 0 else "Немає"
    max_h_str = str(max_collage_height) if max_collage_height is not None and max_collage_height > 0 else "Немає"
    print(f"  - Макс. розмір: Ш={max_w_str}, В={max_h_str}")
    exact_w_valid = final_collage_exact_width is not None and final_collage_exact_width > 0
    exact_h_valid = final_collage_exact_height is not None and final_collage_exact_height > 0
    exact_str = f"Так ({final_collage_exact_width}x{final_collage_exact_height})" if exact_w_valid and exact_h_valid else "Ні"
    print(f"  - Точний холст: {exact_str}")

    print("\n--- Налаштування Збереження ---")
    output_fmt_print = output_format.lower()
    if output_fmt_print == 'jpg':
        # Перевірка кольору фону
        bg_color_print = "(255, 255, 255)" # Default
        if jpg_background_color and isinstance(jpg_background_color, (tuple, list)) and len(jpg_background_color) == 3:
             try: bg_color_print = str(tuple(int(c) for c in jpg_background_color))
             except (ValueError, TypeError): pass
        print(f"  - Формат: JPG, Якість: {quality}, Фон: {bg_color_print}")
    elif output_fmt_print == 'png':
        print(f"  - Формат: PNG, Фон: Прозорий (де можливо)")
    else:
        print(f"  - Формат: {output_format.upper()} (Невідомі параметри)")
    print("-" * 60)

    # Перевірка папки
    source_dir = os.path.abspath(source_dir) # Робимо шлях абсолютним
    if not os.path.isdir(source_dir):
        print(f"\n!!! ПОМИЛКА: Папка '{source_dir}' не знайдена.")
        return

    # Перевірка вихідного файлу (чи не співпадає з папкою)
    output_file_path = os.path.abspath(os.path.join(source_dir, output_filename))
    if os.path.isdir(output_file_path):
        print(f"\n!!! ПОМИЛКА: Вказане ім'я вихідного файлу '{output_filename}' є назвою існуючої папки.")
        return

    # Пошук файлів
    print(f"[*] Пошук файлів у '{source_dir}'...")
    input_files_found = []
    for ext in SUPPORTED_EXTENSIONS:
        try:
            # Використовуємо source_dir напряму, бо він вже абсолютний
            found = glob.glob(os.path.join(source_dir, f'*{ext}'))
            # Додаємо тільки файли, не папки
            input_files_found.extend([f for f in found if os.path.isfile(f)])
        except Exception as e: print(f"! Помилка пошуку файлів з розширенням {ext}: {e}")

    if not input_files_found:
        print(f"\n!!! У папці '{source_dir}' не знайдено файлів з розширеннями: {SUPPORTED_EXTENSIONS}")
        return

    # Сортування знайдених файлів
    try:
        # Сортуємо за повною назвою файлу
        input_files_sorted = natsorted(input_files_found)
    except Exception as sort_err:
        print(f"! Помилка натурального сортування: {sort_err}. Використання стандартного сортування.")
        input_files_sorted = sorted(input_files_found)
    print(f"[*] Знайдено {len(input_files_sorted)} зображень для обробки.")
    # print("\n".join([f"   - {os.path.basename(f)}" for f in input_files_sorted])) # Розкоментувати для перегляду списку

    # --- Санітизація параметрів перед передачею ---
    # Переконуємось, що None передається там, де очікується None або число
    wc_tolerance = white_tolerance if white_tolerance is not None and white_tolerance >= 0 else None
    f_cols = forced_cols if forced_cols is not None and forced_cols > 0 else 0
    p_margin = perimeter_margin if perimeter_margin is not None and perimeter_margin > 0 else 0
    p_percent = padding_percent if padding_percent is not None and padding_percent > 0 else 0.0
    s_percent = spacing_percent if spacing_percent is not None and spacing_percent >= 0 else 0.0
    max_w = max_collage_width if max_collage_width is not None and max_collage_width > 0 else 0
    max_h = max_collage_height if max_collage_height is not None and max_collage_height > 0 else 0
    exact_w = final_collage_exact_width if final_collage_exact_width is not None and final_collage_exact_width > 0 else 0
    exact_h = final_collage_exact_height if final_collage_exact_height is not None and final_collage_exact_height > 0 else 0
    jpg_qual = quality if quality is not None and 1 <= quality <= 100 else 95
    # Перевірка кортежу для співвідношення
    ratio_tuple = None
    if ratio_valid: # Використовуємо прапор, встановлений при друку налаштувань
         try: ratio_tuple = (float(force_collage_aspect_ratio[0]), float(force_collage_aspect_ratio[1]))
         except: pass # Якщо помилка конвертації, залишаємо None

    # Перевірка фону JPG
    jpg_bg = (255, 255, 255) # Default
    if jpg_background_color and isinstance(jpg_background_color, (tuple, list)) and len(jpg_background_color) == 3:
        try: jpg_bg = tuple(max(0, min(255, int(c))) for c in jpg_background_color)
        except (ValueError, TypeError): pass # Залишаємо default

    # Виклик combine_images з перевіреними/санітизованими параметрами
    combine_images(
        image_paths=input_files_sorted, output_path=output_file_path,
        enable_whitening=enable_whitening,
        whitening_cancel_threshold_sum=whitening_cancel_threshold_sum, # <<< Передача порогу
        forced_cols=f_cols, spacing_percent=s_percent,
        white_tolerance=wc_tolerance, quality=jpg_qual, perimeter_margin=p_margin,
        padding_percent=p_percent, crop_symmetric_axes=crop_symmetric_axes,
        crop_symmetric_absolute=crop_symmetric_absolute,
        force_collage_aspect_ratio=ratio_tuple, max_collage_width=max_w,
        max_collage_height=max_h, final_collage_exact_width=exact_w,
        final_collage_exact_height=exact_h, output_format=output_format,
        jpg_background_color=jpg_bg,
        proportional_placement=proportional_placement, placement_ratios=placement_ratios
    )


# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":

    # ==========================================================================
    # ===                    НАЛАШТУВАННЯ КОРИСТУВАЧА                      ===
    # ==========================================================================
    # Змінюйте значення змінних нижче відповідно до ваших потреб.
    # ==========================================================================

    # --------------------------------------------------------------------------
    # |                        ЕТАП 0: Шляхи та Імена                        |
    # --------------------------------------------------------------------------
    source_directory = r"C:\Users\zakhar\Downloads\test3" # !!! ЗАМІНІТЬ НА ВАШ ШЛЯХ !!!
    output_filename = "collage_final_threshold.jpg"

    # --------------------------------------------------------------------------
    # |           ЕТАП 1: ОБРОБКА КОЖНОГО ЗОБРАЖЕННЯ ОКРЕМО                  |
    # --------------------------------------------------------------------------
    enable_whitening = True         # Встановити True, щоб увімкнути відбілювання.

    # <<< НОВЕ НАЛАШТУВАННЯ: Поріг Скасування Відбілювання >>>
    # Якщо сума R+G+B найтемнішого пікселя МЕНША за це значення, відбілювання скасовується.
    # Діапазон: 0 (скасує тільки ідеально чорний) до 765 (ніколи не скасує).
    # Рекомендовані значення: 30-100 для ігнорування темних артефактів.
    whitening_cancel_threshold_sum = 500 # Мін. сума RGB для скасування (0-765)

    # --- Видалення білого фону та Обрізка ---
    white_tolerance = 10              # Допуск білого (0-255 або None для вимкнення).
    crop_absolute_symmetry = False   # True для абсолютної симетрії обрізки.
    crop_axes_symmetry = False      # True для симетрії по осях обрізки (якщо absolute = False).

    # --- Інформаційна перевірка периметру ---
    perimeter_check_margin = 1       # Відступ для перевірки (px), 0 = вимкнено.
    padding_percent = 5.0            # Відсоток полів навколо кожного зобр. (0 = вимкнено).

    # --------------------------------------------------------------------------
    # |              ЕТАП 2: ПІДГОТОВКА ДО КОЛАЖУ                            |
    # --------------------------------------------------------------------------
    proportional_placement_enabled = True # True, щоб увімкнути пропорційне масштабування. При вимкненому йде спввідн. пікселів.
    placement_ratios_list = [1,1]    # Список коефіцієнтів [1.0, 0.8, 1.0]



    # --------------------------------------------------------------------------
    # |                  ЕТАП 3: СТВОРЕННЯ КОЛАЖУ                             |
    # --------------------------------------------------------------------------
    forced_grid_cols = 0             # Кількість стовпців (0 = авто).
    spacing_percent = 2.0            # Відсоток відступу між зображеннями, відсотки від найбільшого

    # --------------------------------------------------------------------------
    # | ЕТАП 4: ТРАНСФОРМАЦІЇ ФІНАЛЬНОГО КОЛАЖУ                             |
    # --------------------------------------------------------------------------
    force_collage_aspect_ratio_tuple = None # None або (ширина, висота), напр., (1, 1).
    max_collage_width = 1500         # Макс. ширина колажу (0 = без обмежень).
    max_collage_height = 1500        # Макс. висота колажу (0 = без обмежень).
    final_collage_exact_width = 0    # Точна фінальна ширина (0 = вимкнено).
    final_collage_exact_height = 0   # Точна фінальна висота (0 = вимкнено).

    # --------------------------------------------------------------------------
    # |                   ЕТАП 5: ЗБЕРЕЖЕННЯ РЕЗУЛЬТАТУ                       |
    # --------------------------------------------------------------------------
    output_save_format = 'jpg'       # 'jpg' або 'png'.
    jpg_collage_background_color_tuple = (255, 255, 255) # Фон для JPG (R, G, B).
    jpeg_save_quality = 95           # Якість JPG (1-100).

    # ==========================================================================
    # ===               КІНЕЦЬ НАЛАШТУВАНЬ КОРИСТУВАЧА                     ===
    # ==========================================================================

    # --- Виклик основної функції обробки з усіма налаштуваннями ---
    run_processing(
        source_dir=source_directory, output_filename=output_filename,
        enable_whitening=enable_whitening,
        whitening_cancel_threshold_sum=whitening_cancel_threshold_sum, # <<< Передача нового параметра
        forced_cols=forced_grid_cols,
        perimeter_margin=perimeter_check_margin, padding_percent=padding_percent,
        white_tolerance=white_tolerance, spacing_percent=spacing_percent, quality=jpeg_save_quality,
        crop_symmetric_axes=crop_axes_symmetry, crop_symmetric_absolute=crop_absolute_symmetry,
        force_collage_aspect_ratio=force_collage_aspect_ratio_tuple, max_collage_width=max_collage_width,
        max_collage_height=max_collage_height, final_collage_exact_width=final_collage_exact_width,
        final_collage_exact_height=final_collage_exact_height, output_format=output_save_format,
        jpg_background_color=jpg_collage_background_color_tuple,
        proportional_placement=proportional_placement_enabled, placement_ratios=placement_ratios_list
    )

    print("\nРоботу скрипту завершено.")