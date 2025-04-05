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

def whiten_image_by_darkest_perimeter(img, cancel_threshold_sum):
    """
    Відбілює зображення, використовуючи найтемніший піксель ПЕРИМЕТРУ
    (1px рамка) як референс для білого.
    Перевіряє найтемніший піксель на поріг темряви перед відбілюванням.
    Працює з копією зображення. Повертає нове зображення або оригінал.
    """
    print("    - Функція відбілювання (за пікселем периметру)...")
    # <<< ВИПРАВЛЕНО: Використовуємо context manager для копій/конвертованих зображень >>>
    # Це гарантує закриття ресурсів навіть при помилках
    with img.copy() as img_copy:
        original_mode = img_copy.mode
        has_alpha = 'A' in img_copy.getbands()
        img_rgb = None
        alpha_channel = None

        try:
            # Готуємо RGB версію для аналізу пікселів і альфа-канал окремо
            if original_mode == 'RGBA' and has_alpha:
                split_bands = img_copy.split()
                if len(split_bands) == 4:
                    img_rgb = Image.merge('RGB', split_bands[:3])
                    alpha_channel = split_bands[3]
                    # Закриваємо використані RGB канали з копії
                    for band in split_bands[:3]:
                        band.close()
                else:
                    raise ValueError(f"Очікувалось 4 канали в RGBA, отримано {len(split_bands)}")
            elif original_mode != 'RGB':
                img_rgb = img_copy.convert('RGB')
            else:
                # Якщо вже RGB, створюємо окрему копію для роботи, щоб не змінити img_copy
                img_rgb = img_copy.copy()

        except Exception as e:
            print(f"      ! Помилка підготовки до відбілювання: {e}. Скасовано.")
            # alpha_channel і img_rgb тут будуть None або закриті
            return img # Повертаємо ОРИГІНАЛЬНИЙ об'єкт img

        # Використовуємо context manager для img_rgb і alpha_channel
        with (img_rgb if img_rgb else Image.new('RGB', (0,0))) as current_img_rgb, \
             (alpha_channel if alpha_channel else Image.new('L', (0,0))) as current_alpha_channel:

            width, height = current_img_rgb.size
            if width <= 1 or height <= 1:
                print("      ! Зображення замале для аналізу периметру. Скасовано.")
                return img

            darkest_pixel_rgb = None
            min_sum = float('inf')
            pixels = None
            try:
                pixels = current_img_rgb.load()
                # --- Оптимізовано перевірку периметру ---
                perimeter_pixels = []
                if height > 0:
                    perimeter_pixels.extend([(x, 0) for x in range(width)]) # Верхній рядок
                    if height > 1:
                         perimeter_pixels.extend([(x, height - 1) for x in range(width)]) # Нижній рядок
                if width > 0:
                    perimeter_pixels.extend([(0, y) for y in range(1, height - 1)]) # Лівий стовпець (без кутів)
                    if width > 1:
                         perimeter_pixels.extend([(width - 1, y) for y in range(1, height - 1)]) # Правий стовпець (без кутів)

                for x, y in perimeter_pixels:
                    pixel = pixels[x, y]
                    # Перевіряємо чи це кортеж/список з 3+ елементами (RGB/RGBA)
                    if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                        r, g, b = pixel[:3]
                        if all(isinstance(val, int) for val in (r, g, b)):
                            current_sum = r + g + b
                            if current_sum < min_sum:
                                min_sum = current_sum
                                darkest_pixel_rgb = (r, g, b)
                    # Додамо обробку для інших можливих режимів (наприклад, 'L')
                    elif isinstance(pixel, int): # Для 'L' або інших одноканальних
                         current_sum = pixel * 3 # Умовно масштабуємо для порівняння
                         if current_sum < min_sum:
                             min_sum = current_sum
                             darkest_pixel_rgb = (pixel, pixel, pixel) # Зберігаємо як RGB

            except Exception as e:
                print(f"      ! Помилка доступу до пікселів: {e}. Скасовано.")
                # Ресурси закриються автоматично завдяки 'with'
                return img

            if darkest_pixel_rgb is None:
                print("      ! Не знайдено валідних пікселів периметру. Скасовано.")
                return img

            ref_r, ref_g, ref_b = darkest_pixel_rgb
            current_pixel_sum = ref_r + ref_g + ref_b
            print(f"      - Знайдений найтемніший піксель: R={ref_r}, G={ref_g}, B={ref_b} (Сума: {current_pixel_sum})")
            print(f"      - Поріг скасування відбілювання (мін. сума): {cancel_threshold_sum}")

            if current_pixel_sum < cancel_threshold_sum:
                print(f"      ! Найтемніший піксель (сума {current_pixel_sum}) темніший за поріг ({cancel_threshold_sum}). Відбілювання скасовано.")
                return img # Повертаємо оригінал

            if ref_r == 255 and ref_g == 255 and ref_b == 255:
                print("      - Найтемніший піксель вже білий. Відбілювання не потрібне.")
                # Якщо відбілювання не потрібне, ми все одно працювали з копіями/конвертованими.
                # Треба повернути щось еквівалентне ОРИГІНАЛУ `img`.
                # Оскільки змін не було, повертаємо сам `img`.
                return img

            print(f"      - Референс для відбілювання: R={ref_r}, G={ref_g}, B={ref_b}")
            # Запобігаємо діленню на нуль більш надійно
            scale_r = 255.0 / max(1.0, float(ref_r))
            scale_g = 255.0 / max(1.0, float(ref_g))
            scale_b = 255.0 / max(1.0, float(ref_b))
            print(f"      - Множники: R*={scale_r:.3f}, G*={scale_g:.3f}, B*={scale_b:.3f}")
            # Створюємо LUT (Lookup Table)
            lut_r = bytes([min(255, round(i * scale_r)) for i in range(256)])
            lut_g = bytes([min(255, round(i * scale_g)) for i in range(256)])
            lut_b = bytes([min(255, round(i * scale_b)) for i in range(256)])
            lut = lut_r + lut_g + lut_b # Конкатенація для point()

            img_whitened_rgb = None
            try:
                # Застосовуємо LUT до каналів RGB
                img_whitened_rgb = current_img_rgb.point(lut * (len(current_img_rgb.getbands()) // 3)) # Множимо LUT якщо є зайві канали (малоймовірно тут)
                print("      - LUT застосовано до RGB частини.")
            except Exception as e:
                print(f"      ! Помилка застосування LUT: {e}. Скасовано.")
                # img_whitened_rgb закриється автоматично, якщо створився
                # Повертаємо оригінал img
                return img

            # Обробка альфа-каналу
            if alpha_channel: # Перевіряємо чи існує об'єкт alpha_channel
                 # Створюємо нове зображення RGBA, об'єднуючи відбілений RGB і оригінальну альфу
                 try:
                      # Переконуємось, що alpha_channel має правильний розмір (має бути)
                      if img_whitened_rgb.size == current_alpha_channel.size:
                           img_whitened_rgb.putalpha(current_alpha_channel)
                           print("      - Альфа-канал додано до відбіленого зображення.")
                           # Тепер img_whitened_rgb - це RGBA
                           # Повертаємо НОВЕ відбілене зображення
                           return img_whitened_rgb
                      else:
                           print(f"      ! Невідповідність розмірів при додаванні альфа ({img_whitened_rgb.size} vs {current_alpha_channel.size}). Повернення RGB.")
                           # Закриємо альфу в with блоці
                           return img_whitened_rgb # Повертаємо тільки відбілений RGB
                 except Exception as e:
                      print(f"      ! Помилка додавання альфа: {e}. Повернення RGB.")
                      # Закриємо альфу в with блоці
                      return img_whitened_rgb # Повертаємо тільки відбілений RGB
            else:
                 # Якщо альфа-каналу не було, повертаємо відбілений RGB
                 return img_whitened_rgb

    # Кінець with img.copy(): img_copy закриється автоматично

# --- Функція видалення білого фону ---
def remove_white_background(img, tolerance):
    """Перетворює білі пікселі на прозорі."""
    img_rgba = None
    original_mode = img.mode
    was_converted = False # Прапорець, чи була конвертація в RGBA

    try:
        if original_mode != 'RGBA':
            try:
                # Конвертуємо в RGBA, працюємо з новим об'єктом
                img_rgba = img.convert('RGBA')
                was_converted = True
                print(f"  - Конвертовано {original_mode} -> RGBA для видалення фону.")
            except Exception as e:
                print(f"  ! Помилка convert->RGBA в remove_bg: {e}")
                return img # Повертаємо оригінал якщо конвертація не вдалася
        else:
            # Якщо вже RGBA, робимо копію, щоб не модифікувати вхідний об'єкт напряму
            img_rgba = img.copy()
            print("  - Створено копію RGBA для видалення фону.")

        datas = list(img_rgba.getdata()) # Отримуємо дані пікселів з копії/конвертованого
        newData = []
        cutoff = 255 - tolerance
        pixels_changed = 0

        # Оптимізований цикл: перевіряємо тип першого елемента один раз
        if datas and isinstance(datas[0], (tuple, list)) and len(datas[0]) == 4:
            for r, g, b, a in datas:
                # Робимо прозорим тільки непрозорі білі пікселі
                if a > 0 and r >= cutoff and g >= cutoff and b >= cutoff:
                    newData.append((r, g, b, 0)) # Новий піксель (зберігаємо колір, але робимо прозорим)
                    pixels_changed += 1
                else:
                    newData.append((r, g, b, a)) # Залишаємо як є
        else:
             # Якщо формат даних не RGBA (мало б бути помилкою вище, але про всяк випадок)
             print(f"  ! Неочікуваний формат даних пікселів в remove_bg (перший елемент: {datas[0] if datas else 'None'}). Скасовано.")
             img_rgba.close() # Закриваємо створену копію/конвертований об'єкт
             return img # Повертаємо оригінал

        del datas # Звільняємо пам'ять

        if pixels_changed > 0:
            print(f"  - Пікселів зроблено прозорими: {pixels_changed}")
            if len(newData) == img_rgba.width * img_rgba.height:
                try:
                    img_rgba.putdata(newData) # Застосовуємо зміни до копії/конвертованого об'єкта
                    # Повертаємо змінений об'єкт img_rgba
                    return img_rgba
                except Exception as e:
                     print(f"  ! Помилка putdata в remove_bg: {e}")
                     img_rgba.close() # Закриваємо об'єкт, де сталася помилка
                     return img # Повертаємо оригінал у разі помилки putdata
            else:
                # Ця помилка малоймовірна, якщо getdata/putdata працюють коректно
                print(f"  ! Помилка розміру даних в remove_bg (очікувалось {img_rgba.width * img_rgba.height}, отримано {len(newData)})")
                img_rgba.close()
                return img
        else:
            print("  - Не знайдено білих пікселів для видалення фону (або всі вже прозорі).")
            # Якщо пікселі не змінились, але ми конвертували в RGBA, повертаємо новий RGBA об'єкт
            if was_converted:
                return img_rgba
            else: # Якщо не конвертували і не змінювали, повертаємо оригінал
                img_rgba.close() # Закриваємо непотрібну копію
                return img

    except Exception as e:
        print(f"  ! Загальна помилка в remove_bg: {e}")
        traceback.print_exc() # Друкуємо деталі помилки
        if img_rgba: # Закриваємо img_rgba, якщо він був створений
            try: img_rgba.close()
            except Exception: pass
        return img # Повертаємо оригінал

# --- Функція обрізки ---
def crop_image(img, symmetric_axes=False, symmetric_absolute=False):
    """Обрізає зображення з опціями симетрії та відступом 1px."""
    img_rgba = None # Для роботи з альфа-каналом
    cropped_img = None # Результат обрізки
    original_mode = img.mode
    was_converted = False # Чи конвертували ми в RGBA

    try:
        # Переконуємось, що маємо RGBA для getbbox
        if original_mode != 'RGBA':
            print("  - Попередження: crop_image конвертує в RGBA для визначення меж.");
            try:
                img_rgba = img.convert('RGBA')
                was_converted = True
            except Exception as e:
                print(f"    ! Не вдалося конвертувати в RGBA: {e}. Обрізку скасовано.");
                return img # Повертаємо оригінал
        else:
            # Якщо вже RGBA, працюємо з копією, щоб getbbox не змінив оригінал
            img_rgba = img.copy()

        # Використовуємо 'with' для img_rgba
        with img_rgba:
            try:
                # bbox визначає прямокутник, що містить всі НЕПРОЗОРІ пікселі
                bbox = img_rgba.getbbox()
            except Exception as e:
                print(f"  ! Помилка отримання bbox: {e}. Обрізку скасовано.");
                return img # Оригінал, бо змін не було

            if not bbox:
                print("  - Не знайдено непрозорих пікселів (bbox is None). Зображення прозоре або помилка. Обрізку пропущено.")
                # Якщо ми конвертували в RGBA, то img_rgba - це новий об'єкт, який треба повернути
                # Якщо не конвертували, то img_rgba - це копія, закриється автоматично, повертаємо оригінал img
                # <<< ВИПРАВЛЕНО ЛОГІКУ ПОВЕРНЕННЯ >>>
                # Якщо bbox не знайдено, це означає, що або зображення повністю прозоре,
                # або сталася помилка. В обох випадках краще повернути ОРИГІНАЛЬНИЙ об'єкт 'img',
                # оскільки операція обрізки не відбулася (або не мала сенсу).
                # Копія/конвертований img_rgba закриється 'with'.
                return img

            original_width, original_height = img_rgba.size
            left, upper, right, lower = bbox

            if left >= right or upper >= lower:
                print(f"  ! Невалідний bbox: {bbox}. Обрізку скасовано.")
                return img # Оригінал

            print(f"  - Знайдений bbox непрозорих пікселів: L={left}, T={upper}, R={right}, B={lower}")

            # --- Розрахунок симетричних меж ---
            crop_l, crop_u, crop_r, crop_b = left, upper, right, lower # За замовчуванням = bbox

            if symmetric_absolute:
                print("  - Режим обрізки: Абсолютно симетричний від країв зображення")
                dist_left = left; dist_top = upper;
                dist_right = original_width - right; dist_bottom = original_height - lower
                min_dist = min(dist_left, dist_top, dist_right, dist_bottom)
                print(f"    - Відступи: L={dist_left}, T={dist_top}, R={dist_right}, B={dist_bottom} -> Мін. відступ: {min_dist}")
                # Нові межі обрізки від країв зображення
                new_left = min_dist
                new_upper = min_dist
                new_right = original_width - min_dist
                new_lower = original_height - min_dist
                if new_left < new_right and new_upper < new_lower:
                     crop_l, crop_u, crop_r, crop_b = new_left, new_upper, new_right, new_lower
                else: print(f"    ! Розраховані абс. симетричні межі невалідні. Використання bbox.")

            elif symmetric_axes:
                print("  - Режим обрізки: Симетричний по осях відносно центру bbox")
                center_x = (left + right) / 2.0
                center_y = (upper + lower) / 2.0
                half_width = (right - left) / 2.0
                half_height = (lower - upper) / 2.0
                # Знаходимо максимальне відхилення від центру до країв зображення
                max_reach_x = max(center_x, original_width - center_x)
                max_reach_y = max(center_y, original_height - center_y)
                # Визначаємо нову ширину/висоту обрізки
                new_width = 2 * max_reach_x
                new_height = 2 * max_reach_y
                # Розраховуємо нові межі, зберігаючи вміст bbox видимим
                new_left = center_x - (new_width / 2.0)
                new_upper = center_y - (new_height / 2.0)
                new_right = center_x + (new_width / 2.0)
                new_lower = center_y + (new_height / 2.0)
                # Обрізаємо до меж зображення
                new_left = max(0, new_left)
                new_upper = max(0, new_upper)
                new_right = min(original_width, new_right)
                new_lower = min(original_height, new_lower)
                # Перевірка на валідність (округлення може спричинити проблеми)
                nl_int, nu_int = int(new_left), int(new_upper)
                nr_int, nb_int = int(math.ceil(new_right)), int(math.ceil(new_lower)) # Округлення вгору для правої/нижньої межі
                if nl_int < nr_int and nu_int < nb_int:
                     crop_l, crop_u, crop_r, crop_b = nl_int, nu_int, nr_int, nb_int
                     print(f"    - Розраховано осі. симетричні межі: L={crop_l}, T={crop_u}, R={crop_r}, B={crop_b}")
                else: print(f"    ! Розраховані осі. симетричні межі невалідні. Використання bbox.")
            else:
                print("  - Режим обрізки: Стандартний (за bbox)")

            # --- Додавання відступу 1px ---
            final_left = max(0, crop_l - 1)
            final_upper = max(0, crop_u - 1)
            final_right = min(original_width, crop_r + 1)
            final_lower = min(original_height, crop_b + 1)
            final_crop_box = (final_left, final_upper, final_right, final_lower)

            # Перевірка, чи обрізка взагалі потрібна
            if final_crop_box == (0, 0, original_width, original_height):
                 print("  - Фінальний crop_box відповідає розміру зображення. Обрізка не потрібна.")
                 # Якщо конвертували в RGBA, повертаємо цей конвертований об'єкт
                 # Якщо не конвертували, повертаємо оригінал img
                 # <<< ВИПРАВЛЕНО: Повертаємо оригінал, якщо змін не було >>>
                 # Копія/конвертований img_rgba закриється автоматично.
                 return img
            else:
                 print(f"  - Фінальний crop_box (з відступом 1px): {final_crop_box}")

            # Виконуємо обрізку на img_rgba (який є копією або конвертованим)
            try:
                cropped_img = img_rgba.crop(final_crop_box)
                print(f"    - Новий розмір після обрізки: {cropped_img.size}")
                # Повертаємо НОВЕ обрізане зображення
                return cropped_img
            except Exception as e:
                print(f"  ! Помилка під час img_rgba.crop({final_crop_box}): {e}. Обрізку скасовано.")
                if cropped_img: cropped_img.close() # Закриваємо, якщо встигло створитись
                return img # Повертаємо оригінал

    except Exception as general_error:
         print(f"  ! Загальна помилка в crop_image: {general_error}")
         traceback.print_exc()
         # Закриваємо проміжні об'єкти, якщо вони існують
         if img_rgba and not img_rgba.fp: img_rgba.close() # Закриваємо, якщо це був створений об'єкт
         if cropped_img and not cropped_img.fp: cropped_img.close()
         return img # Повертаємо оригінал у разі непередбаченої помилки

# --- Функція додавання полів ---
def add_padding(img, percent):
    """Додає прозорі поля навколо зображення."""
    if img is None: return None
    if percent <= 0: return img

    w, h = img.size
    if w == 0 or h == 0:
        print("  ! Попередження в add_padding: Вхідне зображення має нульовий розмір.")
        return img

    pp = int(round(max(w, h) * (percent / 100.0))) # Округлення до цілого
    if pp <= 0: return img

    nw, nh = w + 2*pp, h + 2*pp
    print(f"  - Додавання полів: {percent}% ({pp}px). Новий розмір: {nw}x{nh}")

    padded_img = None
    img_rgba_src = None # Джерело для вставки (може бути копією або конвертованим)

    try:
        # Переконуємось, що джерело RGBA для прозорих полів
        if img.mode != 'RGBA':
            try:
                img_rgba_src = img.convert('RGBA')
                print(f"    - Конвертовано {img.mode} -> RGBA для додавання полів.")
            except Exception as e:
                print(f"  ! Помилка convert->RGBA в add_padding: {e}")
                return img # Повертаємо оригінал
        else:
            # Якщо вже RGBA, копіювати не обов'язково, але безпечніше
            # img_rgba_src = img.copy()
            # <<< Оптимізація: не копіюємо, якщо вже RGBA >>>
            img_rgba_src = img # Використовуємо оригінал, якщо він вже RGBA

        # Створюємо новий прозорий холст
        padded_img = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))

        # Вставляємо зображення на новий холст з відступом, використовуючи альфа-канал як маску
        padded_img.paste(img_rgba_src, (pp, pp), img_rgba_src if img_rgba_src.mode == 'RGBA' else None)
        print(f"    - Зображення вставлено на новий холст.")

        # Закриваємо конвертоване джерело, якщо воно було створене ТА відрізняється від img
        if img_rgba_src is not img:
            try: img_rgba_src.close()
            except Exception: pass

        # Повертаємо НОВЕ зображення з полями
        return padded_img

    except Exception as e:
        print(f"  ! Помилка paste або інша в add_padding: {e}");
        traceback.print_exc()
        if padded_img:
             try: padded_img.close()
             except Exception: pass
        # Закриваємо img_rgba_src, якщо він був створений і відрізняється від img
        if img_rgba_src and img_rgba_src is not img:
             try: img_rgba_src.close()
             except Exception: pass
        return img # Повертаємо оригінальний об'єкт img

# --- Функція перевірки білого периметру ---
def check_perimeter_is_white(img, tolerance, margin):
    """Перевіряє, чи є периметр зображення білим (з допуском)."""
    if img is None or margin <= 0: return False

    # Використовуємо 'with' для керування ресурсами
    # Не копіюємо img одразу, робимо це тільки якщо потрібна конвертація
    img_to_check = None
    created_new_object = False # Чи створили ми новий об'єкт для перевірки

    try:
        # Готуємо зображення для перевірки пікселів (потрібен режим RGB)
        if img.mode == 'RGBA':
            # Створюємо білий фон і накладаємо зображення з альфа-маскою
            img_to_check = Image.new("RGB", img.size, (255, 255, 255))
            created_new_object = True
            with img.split() as bands:
                if len(bands) == 4:
                    img_to_check.paste(img, mask=bands[3])
                else: # Несподівана кількість каналів
                    img_to_check.paste(img) # Пробуємо без маски
            print("    - Створено RGB копію з білим фоном для перевірки периметру (з RGBA).")
        elif img.mode == 'LA': # Grayscale + Alpha
             img_to_check = Image.new("RGB", img.size, (255, 255, 255))
             created_new_object = True
             with img.convert('RGBA') as temp_rgba: # Конвертуємо в RGBA для маски
                  with temp_rgba.split() as bands:
                       if len(bands) == 4:
                            img_to_check.paste(temp_rgba, mask=bands[3])
                       else: img_to_check.paste(temp_rgba)
             print("    - Створено RGB копію з білим фоном для перевірки периметру (з LA).")
        elif img.mode == 'P' or img.mode == 'PA': # Palette based
             # Конвертація в RGB може бути найкращим варіантом тут,
             # хоча накладання на білий фон було б ідеальніше
             try:
                  # Якщо є прозорість в палітрі, convert('RGB') може дати не білий фон
                  # Спробуємо конвертувати в RGBA і потім накласти
                  with img.convert('RGBA') as temp_rgba:
                      img_to_check = Image.new("RGB", img.size, (255, 255, 255))
                      created_new_object = True
                      with temp_rgba.split() as bands:
                           if len(bands) == 4:
                                img_to_check.paste(temp_rgba, mask=bands[3])
                           else: img_to_check.paste(temp_rgba)
                      print("    - Створено RGB копію з білим фоном для перевірки периметру (з P/PA).")
             except Exception as p_conv_err:
                  print(f"    ! Помилка конвертації P/PA -> RGBA для перевірки: {p_conv_err}. Спроба прямої конвертації в RGB.")
                  try:
                       img_to_check = img.convert('RGB')
                       created_new_object = True
                       print("    - Конвертовано P/PA -> RGB для перевірки периметру.")
                  except Exception as rgb_conv_err:
                       print(f"    ! Помилка конвертації P/PA -> RGB: {rgb_conv_err}. Перевірку скасовано.")
                       return False # Не можемо перевірити
        elif img.mode != 'RGB':
             try:
                 img_to_check = img.convert('RGB')
                 created_new_object = True
                 print(f"    - Конвертовано {img.mode} -> RGB для перевірки периметру.")
             except Exception as conv_e:
                 print(f"  ! Помилка convert({img.mode}->RGB) в check_perimeter: {conv_e}")
                 return False # Не можемо перевірити
        else: # Вже RGB
             img_to_check = img # Використовуємо оригінал напряму, копію не робимо
             created_new_object = False

        # Перевірка периметру на img_to_check
        with (img_to_check if created_new_object else Image.new('RGB',(0,0))) as current_img_check:
            # Якщо використовували оригінал (created_new_object is False),
            # current_img_check буде порожнім і блок 'with' нічого не робитиме з оригіналом img.
            # Якщо створили новий об'єкт, він буде автоматично закритий.
            # Тепер працюємо з `img_to_check` безпосередньо.

            width, height = img_to_check.size
            if width < 2*margin and height < 2*margin and (width < 1 or height < 1):
                 print(f"  ! Зображення ({width}x{height}) замале для перевірки периметру з відступом {margin}px.")
                 return False
            elif width <= 0 or height <= 0:
                 print(f"  ! Зображення має нульовий розмір ({width}x{height}).")
                 return False

            pixels = img_to_check.load()
            mh = min(margin, height // 2 if height > 0 else 0)
            mw = min(margin, width // 2 if width > 0 else 0)
            # Гарантуємо мінімум 1px, якщо розмір дозволяє
            if mh == 0 and height > 0: mh = 1
            if mw == 0 and width > 0: mw = 1

            if mh == 0 or mw == 0: # Якщо навіть 1px неможливо взяти
                print(f"  ! Неможливо перевірити периметр з відступом {margin}px на зображенні {width}x{height}.")
                return False

            cutoff = 255 - tolerance
            is_perimeter_white = True # Початкове припущення

            # Оптимізований обхід периметру
            try:
                # Верхні mh рядків
                for y in range(mh):
                    for x in range(width):
                        r, g, b = pixels[x, y][:3]
                        if not (r >= cutoff and g >= cutoff and b >= cutoff):
                            print(f"    - Знайдено не білий піксель (верх): ({x},{y}) = {(r,g,b)}")
                            is_perimeter_white = False; break
                    if not is_perimeter_white: break
                # Нижні mh рядків
                if is_perimeter_white:
                    for y in range(height - mh, height):
                        for x in range(width):
                            r, g, b = pixels[x, y][:3]
                            if not (r >= cutoff and g >= cutoff and b >= cutoff):
                                print(f"    - Знайдено не білий піксель (низ): ({x},{y}) = {(r,g,b)}")
                                is_perimeter_white = False; break
                        if not is_perimeter_white: break
                # Ліві mw стовпці (без кутів, вже перевірених)
                if is_perimeter_white:
                    for x in range(mw):
                        for y in range(mh, height - mh):
                              r, g, b = pixels[x, y][:3]
                              if not (r >= cutoff and g >= cutoff and b >= cutoff):
                                   print(f"    - Знайдено не білий піксель (ліво): ({x},{y}) = {(r,g,b)}")
                                   is_perimeter_white = False; break
                        if not is_perimeter_white: break
                # Праві mw стовпці (без кутів)
                if is_perimeter_white:
                    for x in range(width - mw, width):
                        for y in range(mh, height - mh):
                              r, g, b = pixels[x, y][:3]
                              if not (r >= cutoff and g >= cutoff and b >= cutoff):
                                   print(f"    - Знайдено не білий піксель (право): ({x},{y}) = {(r,g,b)}")
                                   is_perimeter_white = False; break
                        if not is_perimeter_white: break

            except IndexError as e:
                 print(f"    ! Помилка індексу при перевірці пікселя: {e}. Припускаємо, що периметр НЕ білий.")
                 is_perimeter_white = False
            except Exception as e: # Обробка інших помилок доступу до пікселів
                 print(f"    ! Помилка доступу до пікселів при перевірці: {e}. Припускаємо, що периметр НЕ білий.")
                 is_perimeter_white = False

            if is_perimeter_white:
                print(f"  - Перевірка периметра ({margin}px, допуск {tolerance}): Весь периметр визначено як білий.")
            else:
                print(f"  - Перевірка периметра ({margin}px, допуск {tolerance}): Периметр НЕ є повністю білим або сталася помилка.")

            return is_perimeter_white

    except Exception as e:
        print(f"  ! Загальна помилка в check_perimeter: {e}")
        traceback.print_exc()
        return False # Вважаємо, що не білий у разі будь-якої помилки
    finally:
         # Закриваємо img_to_check ТІЛЬКИ якщо ми його створили (created_new_object is True)
         # 'with' блок вище вже мав би це зробити, але для надійності.
         if created_new_object and img_to_check:
              try: img_to_check.close()
              except Exception: pass

# --- Кінець функцій обробки ---

# --- Основна функція обробки та перейменування ---
def rename_and_convert_images(
        input_path,                 # Папка ДЖЕРЕЛА
        output_path,                # Папка РЕЗУЛЬТАТІВ
        article_name,               # Артикул
        delete_originals,           # Видаляти оригінали?
        preresize_width,            # Перед. ресайз ширина
        preresize_height,           # Перед. ресайз висота
        enable_whitening,           # Відбілювання?
        whitening_cancel_threshold, # Поріг темряви для скасування відбілювання (сума RGB) # <<< НОВИЙ ПАРАМЕТР
        white_tolerance,            # Допуск білого (фон/обрізка)
        perimeter_margin,           # Перевірка периметра (для умовних полів)
        crop_symmetric_axes,        # Обрізка симетр. осі
        crop_symmetric_absolute,    # Обрізка симетр. абс.
        padding_percent,            # Поля %
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
    if output_format_lower not in ['jpg', 'png']:
        print(f"!! ПОМИЛКА: Непідтримуваний формат виводу '{output_format}'. СКАСОВАНО.")
        return

    # Перевірка несумісних папок
    abs_input_path = os.path.abspath(input_path)
    abs_output_path = os.path.abspath(output_path)
    abs_backup_path = os.path.abspath(backup_folder_path) if backup_folder_path else None

    if abs_backup_path:
        if abs_backup_path == abs_input_path:
            print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою джерела. Бекап вимкнено.")
            abs_backup_path = None
        elif abs_backup_path == abs_output_path:
            print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою результатів. Бекап вимкнено.")
            abs_backup_path = None

    # Перевірка видалення оригіналів тільки якщо шляхи різні
    safe_to_delete = abs_input_path != abs_output_path
    if delete_originals and not safe_to_delete:
        print(f"!! ПОПЕРЕДЖЕННЯ: Видалення оригіналів увімкнено, але папка джерела та результатів однакові ({abs_input_path}). Видалення вимкнено для безпеки.")
        delete_originals = False

    # Валідація числових параметрів
    try:
        preresize_width = int(preresize_width) if preresize_width else 0
        preresize_height = int(preresize_height) if preresize_height else 0
        whitening_cancel_threshold = int(whitening_cancel_threshold) if whitening_cancel_threshold is not None else 0
        white_tolerance = int(white_tolerance) if white_tolerance is not None and white_tolerance >= 0 else None # None вимикає
        perimeter_margin = int(perimeter_margin) if perimeter_margin and perimeter_margin > 0 else 0
        padding_percent = float(padding_percent) if padding_percent and padding_percent > 0 else 0.0
        max_output_width = int(max_output_width) if max_output_width and max_output_width > 0 else 0
        max_output_height = int(max_output_height) if max_output_height and max_output_height > 0 else 0
        final_exact_width = int(final_exact_width) if final_exact_width and final_exact_width > 0 else 0
        final_exact_height = int(final_exact_height) if final_exact_height and final_exact_height > 0 else 0
        jpeg_quality = int(jpeg_quality) if jpeg_quality is not None else 95
        jpeg_quality = max(1, min(100, jpeg_quality))
    except (ValueError, TypeError) as e:
        print(f"!! ПОМИЛКА: Неправильний тип даних в числових параметрах ({e}). СКАСОВАНО.")
        return

    # Валідація кольору фону
    default_bg = (255, 255, 255)
    if output_format_lower == 'jpg':
        if jpg_background_color and isinstance(jpg_background_color, (tuple, list)) and len(jpg_background_color) == 3:
            try: jpg_bg_color_validated = tuple(max(0, min(255, int(c))) for c in jpg_background_color)
            except (ValueError, TypeError): jpg_bg_color_validated = default_bg; print(f"  ! Неправильний формат кольору фону JPG, використано {default_bg}")
        else: jpg_bg_color_validated = default_bg; print(f"  ! Колір фону JPG не вказано або неправильний формат, використано {default_bg}")
        jpg_background_color = jpg_bg_color_validated # Перепризначаємо перевірене значення
    else:
        jpg_background_color = default_bg # Не використовується, але присвоїмо значення

    # Валідація співвідношення сторін
    use_force_aspect_ratio = False
    valid_aspect_ratio = None
    if force_aspect_ratio and isinstance(force_aspect_ratio, (tuple, list)) and len(force_aspect_ratio) == 2:
        try:
             ar_w, ar_h = map(float, force_aspect_ratio)
             if ar_w > 0 and ar_h > 0:
                 use_force_aspect_ratio = True
                 valid_aspect_ratio = (ar_w, ar_h) # Зберігаємо як float
             else: print(f"! Примусове співвідношення сторін: Непозитивні значення ({force_aspect_ratio})")
        except (ValueError, TypeError): print(f"! Примусове співвідношення сторін: Неправильний формат ({force_aspect_ratio})")

    # --- Друк фінальних параметрів ---
    print(f"--- Параметри обробки ---")
    print(f"Папка ДЖЕРЕЛА: {abs_input_path}")
    print(f"Папка РЕЗУЛЬТАТІВ: {abs_output_path}")
    if enable_renaming_actual := bool(article_name and article_name.strip()): print(f"Артикул: {article_name}")
    else: print(f"Перейменування за артикулом: Вимкнено")
    print(f"Видалення оригіналів: {'Так' if delete_originals else 'Ні'}")
    if perform_preresize := (preresize_width > 0 and preresize_height > 0): print(f"Перед. ресайз: Так ({preresize_width}x{preresize_height}px)")
    else: print(f"Перед. ресайз: Ні")
    print(f"Відбілювання: {'Так' if enable_whitening else 'Ні'}")
    if enable_whitening: print(f"  - Поріг скасування відбілювання (мін. сума RGB): {whitening_cancel_threshold}")
    if enable_bg_removal_and_crop := (white_tolerance is not None): # Допуск 0 теж вмикає
        print(f"Видалення фону/Обрізка: Так (допуск білого {white_tolerance})")
        if crop_symmetric_absolute: print("  - Режим обрізки: Абсолютно симетричний")
        elif crop_symmetric_axes: print("  - Режим обрізки: Симетричний по осях")
        else: print("  - Режим обрізки: Стандартний (асиметричний)")
    else: print(f"Видалення фону/Обрізка: Ні")
    perform_perimeter_check = perimeter_margin > 0
    perform_padding = padding_percent > 0
    print(f"Перевірка периметра для полів: {'Так (' + str(perimeter_margin) + 'px)' if perform_perimeter_check else 'Ні'}")
    print(f"Відсоток полів: {str(padding_percent) + '%' if perform_padding else 'Ні'} (якщо умова перевірки периметра виконана або перевірка вимкнена)")
    if use_force_aspect_ratio: print(f"Примусове співвідношення сторін: Так ({valid_aspect_ratio[0]}:{valid_aspect_ratio[1]})")
    else: print(f"Примусове співвідношення сторін: Ні")
    use_max_dimensions = max_output_width > 0 or max_output_height > 0
    if use_max_dimensions: print(f"Обмеження макс. розміру: Так (Ш: {max_output_width or 'Немає'}, В: {max_output_height or 'Немає'})")
    else: print(f"Обмеження макс. розміру: Ні")
    perform_final_canvas = final_exact_width > 0 and final_exact_height > 0
    if perform_final_canvas: print(f"Фінальний холст точного розміру: Так ({final_exact_width}x{final_exact_height}px)")
    else: print(f"Фінальний холст точного розміру: Ні")
    print(f"Формат збереження: {output_format_lower.upper()}")
    if output_format_lower == 'jpg':
        print(f"  - Колір фону JPG: {jpg_background_color}")
        print(f"  - Якість JPG: {jpeg_quality}")
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
    elif not os.path.isdir(abs_output_path):
        print(f"!! ПОМИЛКА: Шлях результатів '{abs_output_path}' існує, але не є папкою. СКАСОВАНО."); return

    # --- Пошук файлів ---
    try:
        all_entries = os.listdir(abs_input_path)
        SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp', '.tif')
        files_unsorted = [f for f in all_entries if os.path.isfile(os.path.join(abs_input_path, f)) and not f.startswith(("__temp_", ".")) and f.lower().endswith(SUPPORTED_EXTENSIONS)] # Ігноруємо приховані та тимчасові
        files = natsorted(files_unsorted)
        print(f"Знайдено файлів для обробки в '{abs_input_path}': {len(files)}")
        if not files: print("Файлів для обробки не знайдено."); return
    except FileNotFoundError: print(f"Помилка: Папку ДЖЕРЕЛА не знайдено - {abs_input_path}"); return
    except Exception as e: print(f"Помилка читання папки {abs_input_path}: {e}"); return

    # --- Ініціалізація лічильників та списків ---
    processed_files_count = 0; skipped_files_count = 0; error_files_count = 0
    source_files_to_potentially_delete = []
    processed_output_file_map = {} # Карта: шлях_вихідного_файлу -> оригінальна_базова_назва
    output_ext = f".{output_format_lower}"

    # --- Основний цикл обробки ---
    for file_index, file in enumerate(files):
        source_file_path = os.path.join(abs_input_path, file)
        print(f"\n[{file_index+1}/{len(files)}] Обробка файлу: {file}")
        img_current = None # Поточний об'єкт зображення в конвеєрі
        success_flag = False # Прапор успішного збереження поточного файлу

        try:
            # 1. Бекап
            if backup_enabled:
                backup_file_path = os.path.join(abs_backup_path, file)
                try:
                    shutil.copy2(source_file_path, backup_file_path);
                except Exception as backup_err:
                    print(f"  !! Помилка бекапу: {backup_err}")

            # 2. Відкриття
            with Image.open(source_file_path) as img_opened:
                img_opened.load() # Завантажуємо дані зображення
                # Робимо копію ОДРАЗУ, щоб оригінал img_opened закрився 'with'
                img_current = img_opened.copy()
                print(f"  - Відкрито. Ориг. розмір: {img_current.size}, Режим: {img_current.mode}")

            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка: Зображення має нульовий розмір після відкриття. Пропускаємо.")
                 error_files_count += 1; img_current.close(); img_current=None; continue

            # --- Конвеєр обробки ---
            # Кожен крок приймає img_current і повертає НОВИЙ об'єкт або той самий img_current
            # Старий img_current закривається, якщо повертається новий об'єкт

            # 3. Перед. ресайз (ЗМІНЕНА ЛОГІКА: тільки зменшення, без холста)
            if perform_preresize:  # perform_preresize = (preresize_width > 0 and preresize_height > 0)
             print(
                 f"  - Крок Pre-Resize (зменшення до макс. {preresize_width}x{preresize_height}, якщо більше)...")
             prev_img = img_current
             ow, oh = prev_img.size

             # Перевіряємо, чи потрібно взагалі зменшувати
             needs_resizing = (ow > preresize_width or oh > preresize_height) and ow > 0 and oh > 0

             if needs_resizing:
                 resized_img_pr = None  # Для результату ресайзу
                 try:
                     # Розраховуємо коефіцієнт масштабування для зменшення
                     ratio = 1.0
                     # Використовуємо ТІЛЬКИ позитивні значення preresize для розрахунку ratio
                     # Якщо preresize_width=0, ця умова не спрацює, і ширина не впливатиме на ratio
                     if preresize_width > 0 and ow > preresize_width:
                         ratio = min(ratio, preresize_width / ow)
                     # Якщо preresize_height=0, ця умова не спрацює
                     if preresize_height > 0 and oh > preresize_height:
                         ratio = min(ratio, preresize_height / oh)

                     # Переконуємось, що масштабування справді потрібне (ratio < 1.0)
                     if ratio < 1.0:
                         nw = max(1, int(round(ow * ratio)))
                         nh = max(1, int(round(oh * ratio)))
                         print(f"    - Поточний розмір ({ow}x{oh}) перевищує ліміти.")
                         print(f"    - Зменшення до {nw}x{nh} (ratio: {ratio:.4f})...")
                         resized_img_pr = prev_img.resize((nw, nh), Image.Resampling.LANCZOS)

                         # Замінюємо img_current новим зменшеним зображенням
                         img_current = resized_img_pr;
                         resized_img_pr = None  # Перепризначили
                         print(f"    - Новий розмір: {img_current.size}, Режим: {img_current.mode}")
                         prev_img.close()  # Закриваємо попередній стан (який був більшим)
                     else:
                         # Це може статися, якщо ow > width і oh > height, але після розрахунку ratio = 1.0 (рідкісний випадок)
                         print("    - Розрахунок показав, що зменшення не потрібне (ratio=1.0).")
                         img_current = prev_img  # Залишаємо як було
                 except Exception as pr_err:
                     print(f"   ! Помилка під час попереднього ресайзу (зменшення): {pr_err}")
                     if resized_img_pr:  # Якщо помилка після створення об'єкту
                         try:
                             resized_img_pr.close()
                         except Exception:
                             pass
                     img_current = prev_img  # Повертаємо старий стан у разі помилки
                 finally:
                     # Переконуємось, що тимчасовий об'єкт закритий, якщо він не став img_current
                     if resized_img_pr:
                         try:
                             resized_img_pr.close()
                         except Exception:
                             pass
             else:
                 print(f"    - Зображення ({ow}x{oh}) вже в межах лімітів. Зменшення не потрібне.")
                 # img_current залишається без змін
            else:
             print("  - Крок Pre-Resize: вимкнено.")

            # --- Далі йде інша частина конвеєра (Відбілювання і т.д.) ---
            # Перевірка на нульовий розмір після цього кроку (на випадок помилки)
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після Pre-Resize ({img_current.size}). Пропускаємо файл.")
                 error_files_count += 1;
                 img_current.close();
                 img_current = None;
                 continue


            # 4. Відбілювання
            if enable_whitening:
                print("  - Крок Whitening...")
                prev_img = img_current
                try:
                    img_whitened = whiten_image_by_darkest_perimeter(prev_img, whitening_cancel_threshold)
                    if img_whitened is not prev_img:
                         print(f"    - Відбілювання застосовано.")
                         img_current = img_whitened # Новий об'єкт
                         prev_img.close() # Закриваємо старий
                    else:
                         print(f"    - Відбілювання не застосовано (скасовано або не потрібно).")
                         img_current = prev_img # Залишаємо як було
                    print(f"    - Розмір після відбілювання: {img_current.size}, Режим: {img_current.mode}")
                except Exception as wh_err:
                     print(f"  !! Загальна помилка під час виклику відбілювання: {wh_err}")
                     img_current = prev_img # Повертаємо попередній
            else: print("  - Крок Whitening: вимкнено.")


            # 5. Перевірка периметра (виконується ПЕРЕД видаленням фону/обрізкою)
            should_add_padding_conditionally = False
            if perform_perimeter_check and perform_padding:
                 print("  - Крок Check Perimeter (для умовних полів)...")
                 # Використовуємо white_tolerance, якщо видалення фону увімкнено, інакше 0
                 current_perimeter_tolerance = white_tolerance if enable_bg_removal_and_crop else 0
                 should_add_padding_conditionally = check_perimeter_is_white(img_current, current_perimeter_tolerance, perimeter_margin)
                 print(f"    - Результат перевірки: Умовні поля {'будуть додані' if should_add_padding_conditionally else 'не будуть додані'}")
            elif perform_padding:
                 print("  - Крок Check Perimeter: вимкнено, але Padding увімкнено -> Поля будуть додані безумовно.")
                 should_add_padding_conditionally = True # Додаємо поля, якщо padding увімкнено
            else: print("  - Крок Check Perimeter/Padding: вимкнено або не потрібно.")


            # 6. Видалення фону
            if enable_bg_removal_and_crop:
                print(f"  - Крок Background Removal (допуск {white_tolerance})...")
                prev_img = img_current
                try:
                    img_no_bg = remove_white_background(prev_img, white_tolerance)
                    if img_no_bg is not prev_img:
                        print("    - Фон видалено (або створено RGBA копію).")
                        img_current = img_no_bg
                        prev_img.close()
                    else:
                        print("    - Фон не видалявся (не знайдено білих пікселів або помилка).")
                        img_current = prev_img
                    print(f"    - Розмір після видалення фону: {img_current.size}, Режим: {img_current.mode}")
                except Exception as bg_err:
                     print(f"   !! Загальна помилка виклику remove_white_background: {bg_err}")
                     img_current = prev_img
            else: print("  - Крок Background Removal: вимкнено.")


            # 7. Обрізка
            if enable_bg_removal_and_crop:
                 print("  - Крок Crop...")
                 prev_img = img_current
                 try:
                     img_cropped = crop_image(prev_img,
                                              symmetric_axes=crop_symmetric_axes,
                                              symmetric_absolute=crop_symmetric_absolute)
                     if img_cropped is not prev_img:
                          print("    - Обрізку виконано.")
                          img_current = img_cropped
                          prev_img.close()
                     else:
                          print("    - Обрізка не змінила зображення (не було чого обрізати або помилка).")
                          img_current = prev_img
                     print(f"    - Розмір після обрізки: {img_current.size}, Режим: {img_current.mode}")
                 except Exception as crop_err:
                      print(f"   !! Загальна помилка виклику crop_image: {crop_err}")
                      img_current = prev_img
            # Перевірка на нульовий розмір після базової обробки
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після фон/обрізка ({img_current.size}). Пропускаємо файл.")
                 error_files_count += 1; img_current.close(); img_current=None; continue

            # 8. Додавання полів
            # Додаємо поля, якщо прапор `should_add_padding_conditionally` встановлений
            if perform_padding and should_add_padding_conditionally:
                 print(f"  - Крок Padding ({padding_percent}%)...")
                 prev_img = img_current
                 try:
                      img_padded = add_padding(prev_img, padding_percent)
                      if img_padded is not prev_img:
                           print("    - Поля додано.")
                           img_current = img_padded
                           prev_img.close()
                      else:
                           print("    - Додавання полів не змінило зображення (відсоток=0 або помилка).")
                           img_current = prev_img
                      print(f"    - Розмір після додавання полів: {img_current.size}, Режим: {img_current.mode}")
                 except Exception as pad_err:
                      print(f"   !! Загальна помилка виклику add_padding: {pad_err}")
                      img_current = prev_img
            else: print("  - Крок Padding: пропущено (або умова не виконана).")
            # Перевірка на нульовий розмір після полів
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після полів ({img_current.size}). Пропускаємо.")
                 error_files_count += 1; img_current.close(); img_current=None; continue


            # 9. Примусове співвідношення сторін
            if use_force_aspect_ratio and valid_aspect_ratio:
                print(f"  - Крок Aspect Ratio ({valid_aspect_ratio[0]}:{valid_aspect_ratio[1]})...")
                prev_img = img_current
                ratio_canvas_inner = None; temp_rgba_ratio = None
                try:
                    target_aspect_w, target_aspect_h = valid_aspect_ratio
                    current_w, current_h = prev_img.size
                    if current_h == 0: raise ValueError("Висота нульова")
                    current_aspect = current_w / current_h
                    desired_aspect = target_aspect_w / target_aspect_h

                    if abs(current_aspect - desired_aspect) > 0.01:
                        print(f"    - Поточне {current_aspect:.3f}, Цільове: {desired_aspect:.3f}. Потрібна зміна.")
                        if current_aspect > desired_aspect: # Зашироке -> збільшуємо висоту холсту
                            target_w = current_w; target_h = int(round(current_w / desired_aspect))
                        else: # Зависоке -> збільшуємо ширину холсту
                            target_h = current_h; target_w = int(round(current_h * desired_aspect))
                        target_w = max(1, target_w); target_h = max(1, target_h)

                        print(f"    - Створення холсту {target_w}x{target_h}")
                        # Створюємо прозорий холст RGBA
                        ratio_canvas_inner = Image.new('RGBA', (target_w, target_h), (0,0,0,0))
                        x = (target_w - current_w) // 2; y = (target_h - current_h) // 2

                        # Вставляємо поточне зображення (prev_img) на холст
                        paste_mask = None
                        image_to_paste = prev_img
                        if prev_img.mode != 'RGBA': # Конвертуємо в RGBA для коректної вставки на прозорий холст
                             temp_rgba_ratio = prev_img.convert('RGBA')
                             image_to_paste = temp_rgba_ratio
                             paste_mask = temp_rgba_ratio # Використовуємо альфу конвертованого
                        elif prev_img.mode == 'RGBA':
                             paste_mask = prev_img # Використовуємо власну альфу

                        ratio_canvas_inner.paste(image_to_paste, (x, y), paste_mask)
                        img_current = ratio_canvas_inner; ratio_canvas_inner = None # Перепризначили
                        print(f"    - Новий розмір після зміни співвідношення: {img_current.size}")
                        prev_img.close() # Закриваємо попередній стан
                    else:
                         print("    - Співвідношення сторін вже відповідає цільовому.")
                         img_current = prev_img # Залишаємо як було
                except Exception as ratio_err:
                    print(f"    !! Помилка зміни співвідношення сторін: {ratio_err}")
                    img_current = prev_img
                finally:
                    if ratio_canvas_inner: ratio_canvas_inner.close()
                    if temp_rgba_ratio: temp_rgba_ratio.close()
            else: print("  - Крок Aspect Ratio: вимкнено.")
            # Перевірка на нульовий розмір
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після співвідношення ({img_current.size}). Пропускаємо.")
                 error_files_count += 1; img_current.close(); img_current=None; continue


            # 10. Обмеження максимальних розмірів
            if use_max_dimensions:
                 print(f"  - Крок Max Dimensions (Ш: {max_output_width or 'N/A'}, В: {max_output_height or 'N/A'})...")
                 prev_img = img_current
                 resized_img_max = None
                 try:
                      current_w, current_h = prev_img.size
                      print(f"    - Поточний розмір: {current_w}x{current_h}")
                      scale_ratio = 1.0
                      if max_output_width > 0 and current_w > max_output_width: scale_ratio = min(scale_ratio, max_output_width / current_w)
                      if max_output_height > 0 and current_h > max_output_height: scale_ratio = min(scale_ratio, max_output_height / current_h)

                      if scale_ratio < 1.0:
                           nw = max(1, int(round(current_w * scale_ratio))); nh = max(1, int(round(current_h * scale_ratio)))
                           print(f"    - Зменшення до {nw}x{nh}...")
                           resized_img_max = prev_img.resize((nw, nh), Image.Resampling.LANCZOS)
                           img_current = resized_img_max; resized_img_max = None
                           print(f"    - Розмір після обмеження: {img_current.size}")
                           prev_img.close()
                      else:
                           print("    - Зображення вже в межах максимальних розмірів.")
                           img_current = prev_img
                 except Exception as max_resize_err:
                      print(f"    !! Помилка зменшення розміру: {max_resize_err}")
                      img_current = prev_img
                 finally:
                      if resized_img_max: resized_img_max.close()
            else: print("  - Крок Max Dimensions: вимкнено.")
            # Перевірка на нульовий розмір
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після обмеження ({img_current.size}). Пропускаємо.")
                 error_files_count += 1; img_current.close(); img_current=None; continue


            # 11. Фінальний холст АБО підготовка режиму/фону
            prev_img = img_current # Зберігаємо поточний стан
            # Локальні змінні для цього кроку
            final_canvas_inner = None; resized_content_fc = None; paste_mask_fc = None; temp_rgba_fc = None; image_to_paste_fc = None
            temp_converted_prep = None; prep_canvas_inner = None; paste_mask_prep_inner = None; temp_rgba_prep_inner = None; image_to_paste_prep_inner = None

            if perform_final_canvas:
                 print(f"  - Крок Final Canvas ({final_exact_width}x{final_exact_height})...")
                 try:
                     bw, bh = prev_img.size
                     if bw == 0 or bh == 0: raise ValueError("Нульовий розмір перед фінальним холстом")
                     ratio = min(final_exact_width / bw, final_exact_height / bh)
                     nw = max(1, int(round(bw * ratio))); nh = max(1, int(round(bh * ratio)))
                     print(f"    - Масштабування вмісту до {nw}x{nh} для вписування...")
                     resized_content_fc = prev_img.resize((nw, nh), Image.Resampling.LANCZOS)
                     image_to_paste_fc = resized_content_fc # Зображення, яке будемо вставляти

                     # Створюємо фінальний холст з потрібним фоном/прозорістю
                     if output_format_lower == 'png':
                          print(f"    - Створення фінального RGBA холсту (прозорий)")
                          final_canvas_inner = Image.new('RGBA', (final_exact_width, final_exact_height), (0,0,0,0))
                          target_paste_mode = 'RGBA'
                     else: # jpg
                          # <<< ПОТЕНЦІЙНЕ ДЖЕРЕЛО БІЛИХ СМУГ >>>
                          print(f"    - Створення фінального RGB холсту (фон: {jpg_background_color})")
                          final_canvas_inner = Image.new('RGB', (final_exact_width, final_exact_height), jpg_background_color)
                          target_paste_mode = 'RGB' # Вставлятимемо на RGB фон

                     x = (final_exact_width - nw) // 2; y = (final_exact_height - nh) // 2
                     print(f"    - Вставка вмісту на холст ({target_paste_mode}) в позицію ({x},{y})...")

                     # Готуємо зображення для вставки і маску
                     paste_mask_fc = None
                     if image_to_paste_fc.mode == 'RGBA':
                          paste_mask_fc = image_to_paste_fc # Маска з альфи
                     elif image_to_paste_fc.mode in ('LA', 'PA'): # Потребує конвертації для маски
                          temp_rgba_fc = image_to_paste_fc.convert('RGBA')
                          paste_mask_fc = temp_rgba_fc.split()[-1]
                          # Якщо цільовий холст RGB, нам не потрібна RGBA версія для вставки
                          if target_paste_mode == 'RGB':
                              image_to_paste_fc = temp_rgba_fc.convert('RGB') # Конвертуємо RGB частину
                          else: # target_paste_mode == 'RGBA'
                              image_to_paste_fc = temp_rgba_fc # Вставляємо RGBA
                     elif target_paste_mode == 'RGBA' and image_to_paste_fc.mode != 'RGBA':
                         # Якщо холст RGBA, а вміст ні - конвертуємо вміст
                         image_to_paste_fc = image_to_paste_fc.convert('RGBA')
                         # Маска не потрібна, бо вставляємо непрозоре на прозоре
                     elif target_paste_mode == 'RGB' and image_to_paste_fc.mode != 'RGB':
                         # Якщо холст RGB, а вміст ні (і не RGBA/LA/PA) - конвертуємо
                         image_to_paste_fc = image_to_paste_fc.convert('RGB')
                         # Маска не потрібна

                     # Виконуємо вставку
                     final_canvas_inner.paste(image_to_paste_fc, (x,y), paste_mask_fc)

                     img_current = final_canvas_inner; final_canvas_inner = None # Перепризначили
                     print(f"    - Вміст вставлено. Фінальний розмір: {img_current.size}, Режим: {img_current.mode}")
                     prev_img.close() # Закриваємо попередній стан

                 except Exception as canvas_err:
                      print(f"    !! Помилка створення/заповнення фінального холсту: {canvas_err}")
                      traceback.print_exc()
                      img_current = prev_img # Повертаємось до попереднього стану
                 finally: # Закриваємо проміжні об'єкти цього кроку
                      if resized_content_fc: resized_content_fc.close()
                      if temp_rgba_fc: temp_rgba_fc.close()
                      # image_to_paste_fc може бути == resized_content_fc або == temp_rgba_fc, закриються вище
                      if paste_mask_fc and paste_mask_fc is not image_to_paste_fc: paste_mask_fc.close()
                      if final_canvas_inner: final_canvas_inner.close()
                      # Якщо temp_rgba_fc використовувався для image_to_paste_fc, він закриється вище
                      # Але якщо image_to_paste_fc був конвертований з RGB/L і не є temp_rgba_fc
                      if image_to_paste_fc not in [resized_content_fc, temp_rgba_fc, prev_img]:
                           try: image_to_paste_fc.close()
                           except Exception: pass

            else: # Фінальний холст не потрібен, просто готуємо режим/фон
                 print(f"  - Крок Final Canvas: вимкнено. Підготовка зображення до збереження...")
                 target_mode = 'RGBA' if output_format_lower == 'png' else 'RGB'
                 print(f"    - Цільовий режим для збереження: {target_mode}")

                 if prev_img.mode == target_mode:
                     print(f"    - Зображення вже в цільовому режимі ({target_mode}).")
                     img_current = prev_img # Залишаємо як є
                 elif target_mode == 'RGBA': # Потрібно конвертувати в RGBA
                     print(f"    - Конвертація {prev_img.mode} -> RGBA...")
                     try:
                          temp_converted_prep = prev_img.convert('RGBA')
                          img_current = temp_converted_prep; temp_converted_prep = None
                          prev_img.close()
                     except Exception as rgba_conv_err:
                          print(f"    !! Помилка конвертації в RGBA: {rgba_conv_err}")
                          img_current = prev_img # Залишаємо як було
                 else: # target_mode == 'RGB'. Потрібно накласти на фон або конвертувати
                     print(f"    - Підготовка {prev_img.mode} для збереження як RGB (фон: {jpg_background_color})...")
                     try:
                         # Створюємо RGB холст з потрібним фоном
                         prep_canvas_inner = Image.new('RGB', prev_img.size, jpg_background_color)
                         paste_mask_prep_inner = None
                         image_to_paste_prep_inner = prev_img # За замовчуванням

                         # Визначаємо, чи потрібна маска для вставки
                         if prev_img.mode in ('RGBA', 'LA'):
                              paste_mask_prep_inner = prev_img.split()[-1]
                         elif prev_img.mode == 'PA':
                              temp_rgba_prep_inner = prev_img.convert('RGBA')
                              paste_mask_prep_inner = temp_rgba_prep_inner.split()[-1]
                              # Вставляти будемо саму палітру (Pillow впорається) або RGBA?
                              # Краще RGBA для передбачуваності
                              image_to_paste_prep_inner = temp_rgba_prep_inner

                         # Вставляємо на фон з маскою (якщо вона є)
                         prep_canvas_inner.paste(image_to_paste_prep_inner, (0,0), paste_mask_prep_inner)
                         img_current = prep_canvas_inner; prep_canvas_inner = None # Перепризначили
                         prev_img.close()
                     except Exception as prep_err:
                          print(f"    !! Помилка підготовки фону для JPG: {prep_err}. Спроба простої конвертації...")
                          try: # Якщо накладання не вдалося, спробуємо просто конвертувати
                               temp_converted_prep = prev_img.convert('RGB')
                               img_current = temp_converted_prep; temp_converted_prep = None
                               prev_img.close()
                          except Exception as rgb_conv_err:
                               print(f"    !!! Помилка конвертації в RGB: {rgb_conv_err}")
                               img_current = prev_img # Залишаємо як було
                     finally: # Закриваємо проміжні об'єкти цього блоку
                          if prep_canvas_inner: prep_canvas_inner.close()
                          if temp_rgba_prep_inner: temp_rgba_prep_inner.close()
                          if paste_mask_prep_inner and paste_mask_prep_inner is not prev_img and paste_mask_prep_inner is not temp_rgba_prep_inner: paste_mask_prep_inner.close()
                          # image_to_paste_prep_inner = prev_img або temp_rgba_prep_inner, закриються окремо

            # 12. Збереження
            if img_current is None:
                 print("  !! Помилка: Немає зображення для збереження після всіх кроків. Пропускаємо.")
                 error_files_count += 1; continue
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  !! Помилка: Зображення для збереження має нульовий розмір {img_current.size}. Пропускаємо.")
                 error_files_count += 1; img_current.close(); img_current = None; continue

            base_name = os.path.splitext(file)[0]
            output_filename = f"{base_name}{output_ext}" # Поки що зберігаємо з оригінальною назвою
            final_output_path = os.path.join(abs_output_path, output_filename)
            print(f"  - Крок Save: Підготовка до збереження у {final_output_path}...")
            print(f"      - Режим зображення перед збереженням: {img_current.mode}")
            print(f"      - Розмір зображення перед збереженням: {img_current.size}")

            try:
                save_options = {"optimize": True}
                if output_format_lower == 'jpg':
                    save_format_name = "JPEG"
                    # Переконуємось що режим RGB (мало б бути з кроку 11)
                    if img_current.mode != 'RGB':
                        print(f"     ! Попередження: Режим не RGB ({img_current.mode}) перед збереженням JPG. Спроба конвертації...")
                        with img_current.convert('RGB') as img_to_save:
                            save_options["quality"] = jpeg_quality
                            save_options["subsampling"] = 0
                            save_options["progressive"] = True
                            img_to_save.save(final_output_path, save_format_name, **save_options)
                    else:
                        save_options["quality"] = jpeg_quality
                        save_options["subsampling"] = 0
                        save_options["progressive"] = True
                        img_current.save(final_output_path, save_format_name, **save_options)

                else: # png
                    save_format_name = "PNG"
                    # Переконуємось що режим RGBA (мало б бути з кроку 11)
                    if img_current.mode != 'RGBA':
                         print(f"     ! Попередження: Режим не RGBA ({img_current.mode}) перед збереженням PNG. Спроба конвертації...")
                         with img_current.convert('RGBA') as img_to_save:
                             save_options["compress_level"] = 6
                             img_to_save.save(final_output_path, save_format_name, **save_options)
                    else:
                         save_options["compress_level"] = 6
                         img_current.save(final_output_path, save_format_name, **save_options)

                # Якщо збереження пройшло успішно
                processed_files_count += 1
                success_flag = True
                print(f"    - Успішно збережено: {final_output_path}")
                processed_output_file_map[final_output_path] = base_name
                if os.path.exists(source_file_path) and source_file_path not in source_files_to_potentially_delete:
                    source_files_to_potentially_delete.append(source_file_path)

            except Exception as save_err:
                print(f"  !! Помилка збереження {save_format_name}: {save_err}")
                traceback.print_exc()
                error_files_count += 1; success_flag = False
                # Спробувати видалити частково збережений файл, якщо він існує
                if os.path.exists(final_output_path):
                    try: os.remove(final_output_path); print(f"    - Видалено частково збережений файл: {final_output_path}")
                    except Exception as del_err: print(f"    ! Не вдалося видалити частковий файл: {del_err}")

        # --- Обробка помилок файлу ---
        except UnidentifiedImageError:
            print(f"!!! Помилка: Не розпізнано формат файлу або файл пошкоджено: {file}")
            skipped_files_count += 1; success_flag = False
        except FileNotFoundError:
            print(f"!!! Помилка: Файл не знайдено під час обробки (можливо, видалено?): {file}")
            skipped_files_count += 1; success_flag = False
        except OSError as e:
            print(f"!!! Помилка ОС ({file}): {e}")
            error_files_count += 1; success_flag = False
        except MemoryError as e:
            print(f"!!! Помилка ПАМ'ЯТІ під час обробки ({file}): {e}. Спробуйте обробляти менші файли або збільшити RAM.")
            error_files_count += 1; success_flag = False
            # Спробувати звільнити пам'ять перед наступним файлом
            if img_current: img_current.close(); img_current = None
            import gc; gc.collect()
        except Exception as e:
            print(f"!!! Неочікувана ГЛОБАЛЬНА помилка обробки ({file}): {e}")
            traceback.print_exc()
            error_files_count += 1; success_flag = False
        finally: # Зачистка пам'яті для поточного файлу
            if img_current:
                try: img_current.close()
                except Exception: pass
                img_current = None
            # Видаляємо файл зі списку на видалення, якщо була помилка
            if not success_flag and source_file_path in source_files_to_potentially_delete:
                 try:
                     source_files_to_potentially_delete.remove(source_file_path);
                     print(f"    - Видалено {os.path.basename(source_file_path)} зі списку на видалення через помилку.")
                 except ValueError: pass

    # --- Статистика, Видалення, Перейменування (поза циклом обробки файлів) ---
    print(f"\n--- Статистика обробки ---");
    print(f"  - Успішно збережено: {processed_files_count}");
    print(f"  - Пропущено (не формат/не знайдено/пошкоджено): {skipped_files_count}")
    print(f"  - Файлів з помилками обробки/збереження: {error_files_count}")
    total_processed = processed_files_count + skipped_files_count + error_files_count
    print(f"  - Всього проаналізовано файлів: {total_processed} (з {len(files)} знайдених)")

    # --- Видалення оригіналів ---
    if delete_originals and source_files_to_potentially_delete:
        print(f"\nВидалення {len(source_files_to_potentially_delete)} оригінальних файлів з '{abs_input_path}'...")
        removed_count = 0; remove_errors = 0
        for file_to_remove in source_files_to_potentially_delete:
            try:
                if os.path.exists(file_to_remove):
                    os.remove(file_to_remove); removed_count += 1
                else: print(f"  ! Файл для видалення не знайдено: {os.path.basename(file_to_remove)}")
            except Exception as remove_error:
                print(f"  ! Помилка видалення {os.path.basename(file_to_remove)}: {remove_error}")
                remove_errors += 1
        print(f"  - Успішно видалено: {removed_count}. Помилок видалення: {remove_errors}.")
    elif delete_originals: print(f"\nВидалення оригіналів увімкнено, але немає файлів для видалення.")
    else: print(f"\nВидалення оригіналів з '{abs_input_path}' вимкнено.")

    # --- Перейменування ---
    if enable_renaming_actual and processed_output_file_map:
        print(f"\n--- Перейменування файлів у '{abs_output_path}' ---")
        successfully_saved_paths = list(processed_output_file_map.keys())
        print(f"Файлів для перейменування (успішно збережених): {len(successfully_saved_paths)}")

        files_to_process_for_rename = []
        for saved_path in successfully_saved_paths:
            if os.path.exists(saved_path):
                 original_basename = processed_output_file_map.get(saved_path)
                 if original_basename: files_to_process_for_rename.append((saved_path, original_basename))
                 else: print(f"  ! Попередження: Не знайдено оригінальну назву для {saved_path}")
            else: print(f"  ! Попередження: Файл для перейменування більше не існує: {saved_path}")

        if not files_to_process_for_rename: print("Немає файлів для перейменування.")
        else:
            try:
                # Сортуємо за ОРИГІНАЛЬНОЮ назвою (важливо для визначення "першого" файлу)
                sorted_files_for_rename = natsorted(files_to_process_for_rename, key=lambda item: item[1])
            except NameError: sorted_files_for_rename = sorted(files_to_process_for_rename, key=lambda item: item[1])
            except Exception as sort_err:
                print(f"  ! Помилка сортування файлів для перейменування: {sort_err}. Використання несортованого списку.")
                sorted_files_for_rename = files_to_process_for_rename

            # --- Двоетапне перейменування ---
            temp_rename_map = {}
            rename_step1_errors = 0
            temp_prefix = f"__temp_{os.getpid()}_" # Унікальний префікс

            print("  - Крок 1: Перейменування у тимчасові імена...")
            # Перейменовуємо в тимчасові імена, ЗБЕРІГАЮЧИ оригінальну назву
            for i, (current_path, original_basename) in enumerate(sorted_files_for_rename):
                temp_filename = f"{temp_prefix}{i}_{original_basename}{output_ext}" # Додаємо оригінал до тимч. імені
                temp_path = os.path.join(abs_output_path, temp_filename)
                try:
                    print(f"    '{os.path.basename(current_path)}' -> '{temp_filename}'")
                    os.rename(current_path, temp_path)
                    temp_rename_map[temp_path] = original_basename # Зберігаємо оригінальну назву для логіки кроку 2
                except Exception as rename_error:
                    print(f"  ! Помилка тимч. перейменування '{os.path.basename(current_path)}': {rename_error}")
                    rename_step1_errors += 1

            if rename_step1_errors > 0: print(f"  ! Помилок на кроці 1 (тимчасове перейменування): {rename_step1_errors}")

            # --- Крок 2: Фінальне перейменування ---
            print("  - Крок 2: Фінальне перейменування з тимчасових імен...")
            rename_step2_errors = 0
            renamed_final_count = 0
            occupied_final_names = set()

            existing_temp_paths = list(temp_rename_map.keys())
            temp_files_to_process_step2 = []
            for temp_p in existing_temp_paths:
                if os.path.exists(temp_p):
                    original_basename = temp_rename_map.get(temp_p)
                    if original_basename: temp_files_to_process_step2.append((temp_p, original_basename))
                    else: print(f"  ! Попередження: Не знайдено оригінальну назву для тимчасового файлу {os.path.basename(temp_p)}")
                else: print(f"  ! Попередження: Тимчасовий файл '{os.path.basename(temp_p)}' зник перед кроком 2.")

            if not temp_files_to_process_step2: print("  ! Немає тимчасових файлів для фінального перейменування.")
            else:
                # Знову сортуємо тимчасові файли за їх ОРИГІНАЛЬНОЮ назвою (щоб логіка була послідовною)
                try:
                    all_temp_files_sorted = natsorted(temp_files_to_process_step2, key=lambda item: item[1])
                except NameError: all_temp_files_sorted = sorted(temp_files_to_process_step2, key=lambda item: item[1])
                except Exception as sort_err:
                    print(f"  ! Помилка сортування тимчасових файлів: {sort_err}. Використання поточного порядку.")
                    all_temp_files_sorted = temp_files_to_process_step2

                # --- **НОВА ЛОГІКА ПЕРЕЙМЕНУВАННЯ** ---
                # Спочатку перевіряємо, чи існує файл з точною назвою артикулу серед тих, що обробляються
                found_exact_match_in_list = False
                for _, orig_bn in all_temp_files_sorted:
                    if orig_bn.lower() == article_name.lower():
                        found_exact_match_in_list = True
                        print(f"  * Знайдено точний збіг для '{article_name}' (оригінал: '{orig_bn}').")
                        break
                if not found_exact_match_in_list:
                    print(f"  * Точний збіг для '{article_name}' не знайдено серед оброблених файлів.")

                # Виконуємо перейменування
                base_name_assigned = False # Чи було вже присвоєно базове ім'я (article_name)?
                numeric_counter = 1       # Лічильник для _1, _2...

                for temp_path, original_basename in all_temp_files_sorted:
                    target_filename = None
                    target_path = None
                    assign_base = False # Чи присвоювати базове ім'я цьому файлу?

                    # Чи є цей файл точною відповідністю артикулу?
                    is_exact_match = original_basename.lower() == article_name.lower()

                    # Умова 1: Якщо цей файл є точним збігом І базове ім'я ще не присвоєно
                    if is_exact_match and not base_name_assigned:
                        assign_base = True
                    # Умова 2: Якщо точного збігу НЕ було знайдено ВЗАГАЛІ У СПИСКУ,
                    # І базове ім'я ще не присвоєно (тобто це ПЕРШИЙ файл у циклі)
                    elif not found_exact_match_in_list and not base_name_assigned:
                        assign_base = True
                        print(f"  * Перший файл '{original_basename}' отримає базове ім'я '{article_name}', оскільки точного збігу не було.")

                    # Присвоєння імені
                    if assign_base:
                        target_filename = f"{article_name}{output_ext}"
                        target_path = os.path.join(abs_output_path, target_filename)
                        # Перевірка конфлікту перед присвоєнням базового імені
                        if os.path.normcase(target_path) in occupied_final_names or os.path.exists(target_path):
                            print(f"  ! Конфлікт: Базове ім'я '{target_filename}' зайняте/існує. Файл '{os.path.basename(temp_path)}' буде пронумеровано.")
                            assign_base = False # Не вдалося присвоїти базове, переходимо до нумерації
                        else:
                            base_name_assigned = True # Успішно резервуємо базове ім'я
                    # else: # Якщо не базове ім'я - генеруємо нумероване
                    # Цей блок тепер виконується, якщо assign_base = False
                    if not assign_base:
                        # Генеруємо ім'я article_name_counter
                        # Навіть якщо файл був is_exact_match, але base_name_assigned вже True, він отримає номер
                        # Або якщо це не перший файл у випадку відсутності точного збігу
                        while True:
                            target_filename = f"{article_name}_{numeric_counter}{output_ext}"
                            target_path = os.path.join(abs_output_path, target_filename)
                            if os.path.normcase(target_path) not in occupied_final_names and not os.path.exists(target_path):
                                break # Знайшли вільне ім'я
                            numeric_counter += 1
                        numeric_counter += 1 # Готуємо лічильник для наступного файлу

                    # Виконуємо перейменування
                    try:
                        print(f"    '{os.path.basename(temp_path)}' -> '{target_filename}'")
                        os.rename(temp_path, target_path)
                        renamed_final_count += 1
                        occupied_final_names.add(os.path.normcase(target_path)) # Додаємо зайняте ім'я
                    except Exception as rename_error:
                        print(f"  ! Помилка фінального перейменування '{os.path.basename(temp_path)}' -> '{target_filename}': {rename_error}")
                        rename_step2_errors += 1
                        # Якщо була помилка, можливо, варто видалити цей шлях зі списку зайнятих? Але це може бути ризиковано.
                        # Наразі залишаємо як є, але може залишитись "дірка" в нумерації.
            # --- **КІНЕЦЬ НОВОЇ ЛОГІКИ** ---

            print(f"\n  - Перейменовано файлів: {renamed_final_count}. Помилок на кроці 2 (фінальне перейменування): {rename_step2_errors}.")

            # Перевірка залишків тимчасових файлів
            remaining_temp_final = [f for f in os.listdir(abs_output_path) if f.startswith(temp_prefix) and os.path.isfile(os.path.join(abs_output_path, f))];
            if remaining_temp_final:
                 print(f"  ! Увага: Залишилися тимчасові файли в '{abs_output_path}': {remaining_temp_final}")

    elif enable_renaming_actual and not processed_output_file_map:
         print("\n--- Перейменування файлів пропущено: Немає успішно оброблених файлів ---")
    elif not enable_renaming_actual:
         print("\n--- Перейменування файлів пропущено (вимкнено) ---")
# --- Кінець функції rename_and_convert_images ---


# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":

    # --- Налаштування користувача ---

    # === Шляхи до папок ===
    input_folder_path = r"C:\Users\zakhar\Downloads\test3"  # Шлях до папки з оригінальними зображеннями
    output_folder_path = r"C:\Users\zakhar\Downloads\test3" # Шлях для збереження оброблених зображень (може бути той самий)
    backup_folder_path = r"C:\Users\zakhar\Downloads\test_py_bak" # Шлях для резервних копій (None або "" = вимкнено)

    # === Налаштування Перейменування та Видалення ===
    article = "L811"                 # Базове ім'я для перейменування (None або "" = вимкнено)
    delete_originals_after_processing = False # Видаляти оригінали? (Тільки якщо input != output)

    # === Попередній Ресайз (До основної обробки) ===
    preresize_width = 2500                     # Бажана ширина (0 або None = вимкнено)
    preresize_height = 2500                  # Бажана висота (0 або None = вимкнено)

    # === Відбілювання (за найтемнішим пікселем ПЕРИМЕТРУ) ===
    enable_whitening = True                  # Увімкнути відбілювання? (True/False)
    whitening_cancel_threshold_sum = 500    # Мін. сума RGB для скасування (0-765). 0=завжди скасує (крім білого), 765=ніколи не скасує.

    # === Видалення фону / Обрізка (Працює тільки якщо white_tolerance НЕ None) ===
    white_tolerance = 30                    # Допуск білого (0-255, 0=тільки чистий білий, None=вимкнено)
    # --- НАЛАШТУВАННЯ ОБРІЗКИ (якщо white_tolerance НЕ None) ---
    crop_absolute_symmetry = False          # Абсолютна симетрія від країв зображення (True/False)
    crop_axes_symmetry = False              # Симетрія по осях відносно центру вмісту (True/False, діє якщо absolute=False)

    # === Додавання Полів (Після обрізки/видалення фону) ===
    # Умовне додавання: тільки якщо периметр був білим ДО видалення фону/обрізки (якщо perimeter_check > 0)
    perimeter_check_margin_pixels = 1       # Ширина рамки для перевірки білого периметру (px). 0=вимкнути перевірку (поля додаються завжди, якщо padding > 0)
    padding_percentage = 5                  # Відсоток полів (0.0 = вимкнено)

    # === Примусове Співвідношення Сторін (Після полів) ===
    # Додає прозорі (PNG) або фонові (JPG) поля для досягнення пропорції.
    force_aspect_ratio_tuple = None         # None або (ширина_пропорції, висота_пропорції), напр. (1, 1)

    # === Обмеження Максимального Розміру (Після зміни співвідношення) ===
    max_output_width = 1500                 # Макс. ширина (px, 0=без обмеження)
    max_output_height = 1500                # Макс. висота (px, 0=без обмеження)

    # === Фінальний Холст Точного Розміру (Після обмеження макс. розміру) ===
    # <<< УВАГА: Цей крок може додавати білі смуги при збереженні в JPG, якщо співвідношення сторін не збігається >>>
    final_exact_width = 0                   # Точна фінальна ширина (px, 0=вимкнено)
    final_exact_height = 0                  # Точна фінальна висота (px, 0=вимкнено)

    # === Формат Збереження, Фон та Якість ===
    output_save_format = 'jpg'              # Формат: 'jpg' або 'png'.
    # --- Налаштування для JPG ---
    # Колір фону використовується при конвертації з прозорості та для полів final_exact_width/height.
    jpg_background_color_tuple = (255, 255, 255) # Колір фону для JPG (R, G, B)
    jpeg_save_quality = 95                  # Якість JPG (1-100)
    # --- Налаштування для PNG --- (прозорість зберігається)

    # --- Кінець Налаштувань Користувача ---

    # --- Запуск Скрипта ---
    print("\n--- Початок роботи скрипту ---")
    if not os.path.isdir(input_folder_path):
         print(f"\n!! ПОМИЛКА: Вказана папка ДЖЕРЕЛА не існує або не є папкою: {input_folder_path}")
    else:
         # Передача всіх налаштувань у головну функцію обробки
         rename_and_convert_images(
             input_path=input_folder_path,
             output_path=output_folder_path,
             article_name=article if article and article.strip() else None, # None якщо пустий або пробіли
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
             force_aspect_ratio=force_aspect_ratio_tuple,
             max_output_width=max_output_width,
             max_output_height=max_output_height,
             final_exact_width=final_exact_width,
             final_exact_height=final_exact_height,
             output_format=output_save_format,
             jpg_background_color=jpg_background_color_tuple,
             jpeg_quality=jpeg_save_quality,
             backup_folder_path=backup_folder_path,
         )
         print("\n--- Робота скрипту завершена ---")