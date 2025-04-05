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
    img_copy = img.copy(); original_mode = img_copy.mode
    has_alpha = 'A' in img_copy.getbands(); alpha_channel = None; img_rgb = None
    try:
        if original_mode == 'RGBA' and has_alpha:
            split_bands = img_copy.split();
            if len(split_bands) == 4:
                alpha_channel = split_bands[3];
                img_rgb = img_copy.convert('RGB')
            else:
                raise ValueError(f"Очікувалось 4 канали в RGBA, отримано {len(split_bands)}")
        elif original_mode != 'RGB':
            img_rgb = img_copy.convert('RGB')
        else:
            img_rgb = img_copy # Вже RGB, використовуємо копію
    except Exception as e:
        print(f"      ! Помилка підготовки до відбілювання: {e}. Скасовано.")
        if img_copy:
             try: img_copy.close()
             except Exception: pass
        return img # Повертаємо оригінал

    width, height = img_rgb.size
    if width <= 1 or height <= 1:
        print("      ! Зображення замале для аналізу периметру. Скасовано.")
        if img_rgb is not img_copy:
             try: img_rgb.close()
             except Exception: pass
        if alpha_channel:
             try: alpha_channel.close()
             except Exception: pass
        if img_copy:
             try: img_copy.close()
             except Exception: pass
        return img # Повертаємо оригінальний об'єкт

    darkest_pixel_rgb = None; min_sum = float('inf'); pixels = None
    try:
        pixels = img_rgb.load()
        def check_pixel(x, y):
            nonlocal min_sum, darkest_pixel_rgb;
            pixel = pixels[x, y]
            if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                r, g, b = pixel[:3]
                if all(isinstance(val, int) for val in (r, g, b)):
                    current_sum = r + g + b
                    if current_sum < min_sum:
                        min_sum = current_sum;
                        darkest_pixel_rgb = (r, g, b)
        for x in range(width):
            check_pixel(x, 0)
            if height > 1:
                check_pixel(x, height - 1)
        for y in range(1, height - 1):
            check_pixel(0, y)
            if width > 1:
                check_pixel(width - 1, y)
    except Exception as e:
        print(f"      ! Помилка доступу до пікселів: {e}. Скасовано.")
        if img_rgb is not img_copy:
            try: img_rgb.close()
            except Exception: pass
        if alpha_channel:
            try: alpha_channel.close()
            except Exception: pass
        if img_copy:
            try: img_copy.close()
            except Exception: pass
        return img

    if darkest_pixel_rgb is None:
        print("      ! Не знайдено валідних пікселів периметру. Скасовано.")
        if img_rgb is not img_copy:
            try: img_rgb.close()
            except Exception: pass
        if alpha_channel:
            try: alpha_channel.close()
            except Exception: pass
        if img_copy:
            try: img_copy.close()
            except Exception: pass
        return img

    ref_r, ref_g, ref_b = darkest_pixel_rgb
    current_pixel_sum = ref_r + ref_g + ref_b # Сума RGB найтемнішого пікселя
    print(f"      - Знайдений найтемніший піксель: R={ref_r}, G={ref_g}, B={ref_b} (Сума: {current_pixel_sum})")
    print(f"      - Поріг скасування відбілювання (мін. сума): {cancel_threshold_sum}")

    # <<< МОДИФІКАЦІЯ: Перевірка на поріг темряви >>>
    if current_pixel_sum < cancel_threshold_sum:
        print(f"      ! Найтемніший піксель (сума {current_pixel_sum}) темніший за поріг ({cancel_threshold_sum}). Відбілювання скасовано.")
        # Закриваємо тимчасові ресурси
        if img_rgb is not img_copy:
            try: img_rgb.close()
            except Exception: pass
        if alpha_channel:
            try: alpha_channel.close()
            except Exception: pass
        # Повертаємо ОРИГІНАЛЬНИЙ об'єкт 'img', оскільки модифікація не відбулася
        # img_copy закриється автоматично, бо вона повертається або закривається у всіх шляхах
        return img
    # <<< КІНЕЦЬ МОДИФІКАЦІЇ >>>

    # Перевірка, чи відбілювання взагалі потрібне (піксель вже білий)
    if ref_r == 255 and ref_g == 255 and ref_b == 255:
        print("      - Найтемніший піксель вже білий. Відбілювання не потрібне.")
        if img_rgb is not img_copy:
            try: img_rgb.close()
            except Exception: pass
        if alpha_channel:
             try: alpha_channel.close()
             except Exception: pass
        # Повертаємо ОРИГІНАЛ, якщо був альфа-канал, бо копія не потрібна
        # Повертаємо КОПІЮ, якщо альфи не було (вона ідентична оригіналу)
        return img if alpha_channel else img_copy

    # Продовжуємо з відбілюванням, якщо поріг пройдено і піксель не білий
    print(f"      - Референс для відбілювання: R={ref_r}, G={ref_g}, B={ref_b}")
    scale_r = 255.0 / max(1, ref_r); scale_g = 255.0 / max(1, ref_g); scale_b = 255.0 / max(1, ref_b)
    print(f"      - Множники: R*={scale_r:.3f}, G*={scale_g:.3f}, B*={scale_b:.3f}")
    lut_r = bytes([min(255, int(i * scale_r)) for i in range(256)]); lut_g = bytes([min(255, int(i * scale_g)) for i in range(256)]); lut_b = bytes([min(255, int(i * scale_b)) for i in range(256)])

    img_whitened_rgb = None
    r_ch, g_ch, b_ch = None, None, None
    out_r, out_g, out_b = None, None, None
    try:
        if img_rgb is None: raise ValueError("img_rgb is None для LUT")
        r_ch, g_ch, b_ch = img_rgb.split()
        out_r = r_ch.point(lut_r); out_g = g_ch.point(lut_g); out_b = b_ch.point(lut_b)
        img_whitened_rgb = Image.merge('RGB', (out_r, out_g, out_b))
    except Exception as e:
        print(f"      ! Помилка застосування LUT/злиття: {e}. Скасовано.")
        # Якщо сталася помилка тут, повертаємо оригінал (з альфою якщо була)
        if alpha_channel:
             try:
                 # Намагаємось відновити альфу на КОПІЇ, яку потім повернемо
                 img_copy.putalpha(alpha_channel)
                 alpha_channel.close();
             except Exception: pass
             # Якщо відновити альфу не вдалося, повертаємо копію без альфи
             return img_copy
        else:
             # Якщо альфи не було, повертаємо копію
             return img_copy
    finally:
        # Закриваємо всі проміжні канали, якщо вони створилися
        if r_ch:
            try: r_ch.close();
            except Exception: pass
        if g_ch:
            try: g_ch.close();
            except Exception: pass
        if b_ch:
            try: b_ch.close();
            except Exception: pass
        if out_r:
            try: out_r.close();
            except Exception: pass
        if out_g:
            try: out_g.close();
            except Exception: pass
        if out_b:
            try: out_b.close();
            except Exception: pass
        # Закриваємо img_rgb, якщо він не є вихідною копією
        if img_rgb is not img_copy:
            try: img_rgb.close();
            except Exception: pass

    result_image = None
    if alpha_channel:
        try:
            # Додаємо альфа-канал до ВІДБІЛЕНОГО RGB зображення
            img_whitened_rgb.putalpha(alpha_channel)
            result_image = img_whitened_rgb
        except Exception as e:
             print(f"      ! Помилка відновлення альфа: {e}. Повернення RGB.")
             result_image = img_whitened_rgb # Повертаємо тільки RGB
        finally:
             # Альфа-канал вже використаний або оброблений в помилці, закриваємо
             if alpha_channel:
                 try: alpha_channel.close()
                 except Exception: pass
             # Оригінальна копія більше не потрібна
             if img_copy:
                 try: img_copy.close()
                 except Exception: pass
        # Повертаємо нове відбілене зображення з альфою (або без, якщо була помилка)
        return result_image
    else:
        # Якщо альфи не було, оригінальна копія більше не потрібна
        if img_copy:
            try: img_copy.close()
            except Exception: pass
        # Повертаємо нове відбілене RGB зображення
        return img_whitened_rgb

# --- Функція видалення білого фону ---
# ... (код remove_white_background залишається без змін) ...
def remove_white_background(img, tolerance):
    """Перетворює білі пікселі на прозорі."""
    img_rgba = None
    try:
        if img.mode != 'RGBA':
            try:
                img_rgba = img.convert('RGBA')
            except Exception as e:
                print(f"  ! Помилка convert->RGBA в remove_bg: {e}")
                return img
        else:
            img_rgba = img.copy()

        try:
            datas = list(img_rgba.getdata())
        except Exception as e:
            print(f"  ! Помилка getdata в remove_bg: {e}")
            if img_rgba is not img:
                try:
                    img_rgba.close()
                except Exception:
                    pass
            return img

        newData = []; cutoff = 255 - tolerance
        for item in datas:
            # Перевіряємо, чи піксель видимий (альфа > 0) ПЕРЕД тим, як робити його прозорим
            if len(item) == 4 and item[3] > 0 and item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff:
                newData.append((*item[:3], 0)) # Робимо прозорим
            else:
                newData.append(item) # Залишаємо як є
        del datas

        if len(newData) == img_rgba.width * img_rgba.height:
            try:
                img_rgba.putdata(newData)
                # Якщо вихідний об'єкт був img, то зміни відбулися в копії img_rgba
                # Якщо вихідний об'єкт був img_rgba (копія), то зміни в ньому
                return img_rgba
            except Exception as e:
                 print(f"  ! Помилка putdata в remove_bg: {e}")
                 if img_rgba is not img: # Закриваємо тільки якщо це була створена копія
                     try:
                         img_rgba.close()
                     except Exception:
                         pass
                 return img # Повертаємо оригінал у разі помилки putdata
        else:
            print(f"  ! Помилка розміру даних в remove_bg (очікувалось {img_rgba.width * img_rgba.height}, отримано {len(newData)})")
            if img_rgba is not img:
                try:
                    img_rgba.close()
                except Exception:
                    pass
            return img # Повертаємо оригінал
    except Exception as e:
        print(f"  ! Загальна помилка в remove_bg: {e}")
        # Закриваємо img_rgba, якщо він був створений як копія
        if img_rgba and img_rgba is not img:
            try:
                img_rgba.close()
            except Exception:
                pass
        return img

# --- Функція обрізки ---
# ... (код crop_image залишається без змін) ...
def crop_image(img, symmetric_axes=False, symmetric_absolute=False):
    """Обрізає зображення з опціями симетрії та відступом 1px."""
    img_rgba = None
    cropped_img = None
    try:
        # Перевіряємо чи є альфа-канал для коректного bbox
        if img.mode != 'RGBA':
            print("  ! Попередження: crop_image очікує RGBA для визначення меж.");
            try:
                img_rgba = img.convert('RGBA')
                print("    - Спроба конвертації в RGBA для обрізки...")
            except Exception as e:
                print(f"    ! Не вдалося конвертувати в RGBA: {e}. Обрізку скасовано.");
                return img # Повертаємо оригінал
        else:
            # Якщо вже RGBA, робимо копію, щоб не змінювати оригінал, якщо bbox не знайдено
            img_rgba = img.copy()

        try:
            bbox = img_rgba.getbbox()
        except Exception as e:
            print(f"  ! Помилка отримання bbox: {e}. Обрізку скасовано.");
            if img_rgba is not img: # Закриваємо копію
                try: img_rgba.close()
                except Exception: pass
            return img # Повертаємо оригінал

        if not bbox:
            print("  - Не знайдено непрозорих пікселів або помилка bbox. Обрізку пропущено.")
            if img_rgba is not img: # Закриваємо копію
                try: img_rgba.close()
                except Exception: pass
            # Повертаємо ОРИГІНАЛ, бо змін не було
            return img

        # Якщо bbox знайдено, img_rgba (копія або конвертований) буде обрізано
        original_width, original_height = img_rgba.size
        left, upper, right, lower = bbox

        # Перевірка валідності bbox (хоча getbbox зазвичай повертає None або валідний)
        if left >= right or upper >= lower:
            print(f"  ! Невалідний bbox: {bbox}. Обрізку скасовано.")
            try: img_rgba.close() # Закриваємо img_rgba, бо він більше не потрібен
            except Exception: pass
            return img # Повертаємо оригінал

        print(f"  - Знайдений bbox: L={left}, T={upper}, R={right}, B={lower} (Розмір зображення: {original_width}x{original_height})")

        base_crop_box = None
        if symmetric_absolute:
            print("  - Режим обрізки: Абсолютно симетричний")
            dist_left = left; dist_top = upper; dist_right = original_width - right; dist_bottom = original_height - lower
            min_dist = min(dist_left, dist_top, dist_right, dist_bottom); print(f"    - Відступи: L={dist_left}, T={dist_top}, R={dist_right}, B={dist_bottom}"); print(f"    - Мінімальний відступ: {min_dist}")
            # Перевірка, щоб не обрізати занадто багато
            new_left = min_dist
            new_upper = min_dist
            new_right = original_width - min_dist
            new_lower = original_height - min_dist
            if new_left >= new_right or new_upper >= new_lower:
                 print(f"    ! Розраховані симетричні межі невалідні ({new_left},{new_upper},{new_right},{new_lower}). Використання стандартного bbox.")
                 base_crop_box = bbox
            else:
                 base_crop_box = (new_left, new_upper, new_right, new_lower)

        elif symmetric_axes:
            print("  - Режим обрізки: Симетричний по осях")
            dist_left = left; dist_top = upper; dist_right = original_width - right; dist_bottom = original_height - lower
            min_horizontal = min(dist_left, dist_right); min_vertical = min(dist_top, dist_bottom); print(f"    - Відступи: L={dist_left}, T={dist_top}, R={dist_right}, B={dist_bottom}"); print(f"    - Мін. горизонтальний: {min_horizontal}"); print(f"    - Мін. вертикальний: {min_vertical}")
            # Перевірка, щоб не обрізати занадто багато
            new_left = min_horizontal
            new_upper = min_vertical
            new_right = original_width - min_horizontal
            new_lower = original_height - min_vertical
            if new_left >= new_right or new_upper >= new_lower:
                 print(f"    ! Розраховані симетричні межі невалідні ({new_left},{new_upper},{new_right},{new_lower}). Використання стандартного bbox.")
                 base_crop_box = bbox
            else:
                 base_crop_box = (new_left, new_upper, new_right, new_lower)
        else:
            print("  - Режим обрізки: Стандартний (асиметричний)"); base_crop_box = bbox

        final_crop_box = None
        if base_crop_box:
            l, u, r, b = base_crop_box
            # Додаємо відступ 1px, але не виходимо за межі зображення
            final_left = max(0, l - 1)
            final_upper = max(0, u - 1)
            final_right = min(original_width, r + 1)
            final_lower = min(original_height, b + 1)
            final_crop_box = (final_left, final_upper, final_right, final_lower)
            print(f"  - Базовий crop_box: {base_crop_box}")
            print(f"  - Фінальний crop_box (з відступом 1px): {final_crop_box}")
        else:
            # Це не повинно трапитися, якщо bbox був валідний
            print("  ! Не вдалося розрахувати базовий crop_box.")

        # Перевіряємо валідність фінального crop_box
        if final_crop_box and final_crop_box[0] < final_crop_box[2] and final_crop_box[1] < final_crop_box[3]:
            try:
                cropped_img = img_rgba.crop(final_crop_box)
                print(f"    - Новий розмір після обрізки (з відступом): {cropped_img.size}")
                # Закриваємо img_rgba (копію або конвертований), оскільки створили новий cropped_img
                try: img_rgba.close()
                except Exception: pass
                # Повертаємо НОВЕ обрізане зображення
                return cropped_img
            except Exception as e:
                print(f"  ! Помилка під час img.crop({final_crop_box}): {e}. Обрізку скасовано.")
                if cropped_img: # Якщо crop створився, але щось пішло не так далі
                    try: cropped_img.close()
                    except Exception: pass
                # Закриваємо img_rgba, який намагалися обрізати
                try: img_rgba.close()
                except Exception: pass
                return img # Повертаємо оригінал
        else:
            print(f"  ! Невалідний або нульовий фінальний crop_box: {final_crop_box}. Обрізку скасовано.")
            # Закриваємо img_rgba
            try: img_rgba.close()
            except Exception: pass
            return img # Повертаємо оригінал

    except Exception as general_error:
         print(f"  ! Загальна помилка в crop_image: {general_error}")
         # Закриваємо проміжні об'єкти, якщо вони існують і не є оригіналом
         if img_rgba and img_rgba is not img:
             try: img_rgba.close()
             except Exception: pass
         if cropped_img:
             try: cropped_img.close()
             except Exception: pass
         return img # Повертаємо оригінал у разі непередбаченої помилки

# --- Функція додавання полів ---
# ... (код add_padding залишається без змін) ...
def add_padding(img, percent):
    """Додає прозорі поля навколо зображення."""
    if img is None: return None # Якщо вхідний об'єкт None
    if percent <= 0: return img # Поля не потрібні, повертаємо оригінал

    w, h = img.size
    # Додаємо перевірку на нульовий розмір
    if w == 0 or h == 0:
        print("  ! Попередження в add_padding: Вхідне зображення має нульовий розмір.")
        return img # Повертаємо як є

    # Розрахунок відступу
    pp = int(max(w, h) * (percent / 100.0))
    if pp <= 0: return img # Відступ нульовий або від'ємний

    nw, nh = w + 2*pp, h + 2*pp
    print(f"  - Додавання полів: {percent}% ({pp}px). Новий розмір: {nw}x{nh}")

    img_rgba_src = None # Джерело для вставки (можливо конвертоване)
    padded_img = None   # Новий холст з полями

    try:
        # Переконуємось, що джерело RGBA для прозорих полів
        if img.mode != 'RGBA':
            try:
                img_rgba_src = img.convert('RGBA')
                print(f"    - Конвертовано {img.mode} -> RGBA для додавання полів.")
            except Exception as e:
                print(f"  ! Помилка convert->RGBA в add_padding: {e}")
                return img # Повертаємо оригінал, якщо конвертація невдала
        else:
            img_rgba_src = img # Використовуємо оригінал, якщо він вже RGBA

        # Створюємо новий прозорий холст
        padded_img = Image.new('RGBA', (nw, nh), (0,0,0,0))

        # Вставляємо зображення (img_rgba_src) на новий холст з відступом
        # Використовуємо альфа-канал img_rgba_src як маску для коректної вставки
        padded_img.paste(img_rgba_src, (pp, pp), img_rgba_src)
        print(f"    - Зображення вставлено на новий холст.")

        # Закриваємо конвертоване джерело, якщо воно було створене
        if img_rgba_src is not img:
            try: img_rgba_src.close()
            except Exception: pass

        # Повертаємо НОВЕ зображення з полями
        return padded_img

    except Exception as e:
        print(f"  ! Помилка paste або інша в add_padding: {e}");
        # Закриваємо створені об'єкти у разі помилки
        if padded_img:
             try: padded_img.close()
             except Exception: pass
        if img_rgba_src and img_rgba_src is not img:
             try: img_rgba_src.close()
             except Exception: pass
        # Повертаємо оригінальний об'єкт img
        return img

# --- Функція перевірки білого периметру ---
# ... (код check_perimeter_is_white залишається без змін) ...
def check_perimeter_is_white(img, tolerance, margin):
    """Перевіряє, чи є периметр зображення білим (з допуском)."""
    if img is None or margin <= 0: return False
    img_rgb_check = None; img_copy = None; mask = None; pixels = None
    is_perimeter_white = True # Початкове припущення

    try:
        # Робимо копію, щоб не змінювати оригінал
        img_copy = img.copy()

        # Готуємо зображення для перевірки пікселів (конвертуємо в RGB)
        if img_copy.mode == 'RGBA':
            # Створюємо білий фон і накладаємо зображення з альфа-маскою
            img_rgb_check = Image.new("RGB", img_copy.size, (255, 255, 255))
            try:
                mask = img_copy.split()[3]
                img_rgb_check.paste(img_copy, mask=mask)
                # mask.close() # Закриємо в finally
            except IndexError:
                # Якщо немає альфа-каналу (хоча режим RGBA?), просто пастимо
                 print("  ! Попередження в check_perimeter: Режим RGBA, але не вдалося отримати альфа-канал.")
                 img_rgb_check.paste(img_copy)
            except Exception as e:
                 print(f"  ! Помилка paste при перевірці периметру: {e}")
                 is_perimeter_white = False # Вважаємо, що не білий у разі помилки
        elif img_copy.mode in ('LA', 'PA'):
             try:
                 # Конвертація з прозорістю в RGB може дати неочікувані результати на краях,
                 # Краще створити білий фон і накласти
                 temp_rgb = img_copy.convert('RGB') # Спочатку RGB частина
                 img_rgb_check = Image.new("RGB", img_copy.size, (255, 255, 255))
                 alpha_mask = None
                 try:
                     alpha_mask = img_copy.convert('L') # Спробуємо отримати маску
                     img_rgb_check.paste(temp_rgb, mask=alpha_mask)
                 except Exception:
                      img_rgb_check.paste(temp_rgb) # Якщо не вдалося з маскою
                 finally:
                     if temp_rgb: temp_rgb.close()
                     if alpha_mask: alpha_mask.close()

             except Exception as conv_e:
                 print(f"  ! Помилка convert({img_copy.mode}->RGB) в check_perimeter: {conv_e}")
                 is_perimeter_white = False
        elif img_copy.mode != 'RGB':
             try:
                 img_rgb_check = img_copy.convert('RGB')
             except Exception as conv_e:
                 print(f"  ! Помилка convert({img_copy.mode}->RGB) в check_perimeter: {conv_e}")
                 is_perimeter_white = False
        else: # Вже RGB
             img_rgb_check = img_copy # Використовуємо копію напряму

        # Якщо підготовка пройшла успішно і is_perimeter_white все ще True
        if is_perimeter_white and img_rgb_check:
            width, height = img_rgb_check.size
            # Перевірка на занадто малий розмір
            if width < 2*margin and height < 2*margin and (width < 1 or height < 1):
                 print(f"  ! Зображення ({width}x{height}) замале для перевірки периметру з відступом {margin}px.")
                 is_perimeter_white = False # Не можемо перевірити
            elif width <= 0 or height <= 0:
                 print(f"  ! Зображення має нульовий розмір ({width}x{height}).")
                 is_perimeter_white = False
            else:
                 pixels = img_rgb_check.load()
                 mh = min(margin, height // 2 if height > 0 else 0)
                 mw = min(margin, width // 2 if width > 0 else 0)
                 # Якщо відступ більший за половину розміру, коригуємо його
                 if mh == 0 and height > 0: mh = 1
                 if mw == 0 and width > 0: mw = 1

                 # Якщо після корекції відступи все ще нульові, а розмір ненульовий
                 # (це можливо, якщо margin > 0, але width/height = 1)
                 if (mh == 0 or mw == 0) and (width > 0 and height > 0):
                      print(f"  ! Неможливо перевірити периметр з відступом {margin}px на зображенні {width}x{height}.")
                      is_perimeter_white = False
                 # Якщо все ще готові до перевірки
                 elif mh > 0 and mw > 0:
                     cutoff = 255 - tolerance
                     # Функція перевірки одного пікселя
                     def is_white(x,y):
                         try:
                             p=pixels[x,y]
                             # Перевірка типу пікселя (може бути int для L/P режимів до конвертації)
                             if isinstance(p,(tuple,list)) and len(p)>=3:
                                 # Достатньо перевірити перші 3 канали (R, G, B)
                                 return p[0]>=cutoff and p[1]>=cutoff and p[2]>=cutoff
                             elif isinstance(p, int): # Наприклад, для 'L' режиму
                                 return p >= cutoff
                             else:
                                 print(f"  ! Невідомий тип пікселя в check_perimeter: {type(p)} в ({x},{y})")
                                 return False # Невідомо, вважаємо не білим
                         except IndexError:
                             print(f"  ! Помилка індексу при доступі до пікселя ({x},{y})")
                             return False # Помилка доступу, вважаємо не білим

                     # Перевірка периметру
                     # Верхній край
                     for y in range(mh):
                         for x in range(width):
                             if not is_white(x,y): is_perimeter_white = False; break
                         if not is_perimeter_white: break
                     # Нижній край
                     if is_perimeter_white:
                         for y in range(height - mh, height):
                             for x in range(width):
                                 if not is_white(x,y): is_perimeter_white = False; break
                             if not is_perimeter_white: break
                     # Лівий край (без кутів, вже перевірених)
                     if is_perimeter_white:
                         for x in range(mw):
                             for y in range(mh, height - mh):
                                  if not is_white(x,y): is_perimeter_white = False; break
                             if not is_perimeter_white: break
                     # Правий край (без кутів)
                     if is_perimeter_white:
                         for x in range(width - mw, width):
                             for y in range(mh, height - mh):
                                  if not is_white(x,y): is_perimeter_white = False; break
                             if not is_perimeter_white: break

    except Exception as e:
        print(f"  ! Загальна помилка в check_perimeter: {e}")
        # traceback.print_exc() # Для детальної діагностики, якщо потрібно
        is_perimeter_white = False # Вважаємо, що не білий у разі будь-якої помилки
    finally:
        # Зачистка ресурсів
        if mask:
            try: mask.close()
            except Exception: pass
        # img_rgb_check може бути тим самим об'єктом, що й img_copy, якщо оригінал був RGB
        # Закриваємо img_rgb_check, якщо він був створений окремо
        if img_rgb_check and img_rgb_check is not img_copy:
            try: img_rgb_check.close()
            except Exception: pass
        # Завжди закриваємо img_copy, оскільки це була копія оригіналу
        if img_copy:
            try: img_copy.close()
            except Exception: pass

    if is_perimeter_white:
        print(f"  - Перевірка периметра ({margin}px, допуск {tolerance}): Весь периметр визначено як білий.")
    else:
        print(f"  - Перевірка периметра ({margin}px, допуск {tolerance}): Периметр НЕ є повністю білим або сталася помилка.")

    return is_perimeter_white
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
    output_format_lower = output_format.lower()
    if output_format_lower not in ['jpg', 'png']:
        print(f"!! ПОМИЛКА: Непідтримуваний формат виводу '{output_format}'. СКАСОВАНО.")
        return

    print(f"--- Параметри обробки ---")
    print(f"Папка ДЖЕРЕЛА: {input_path}")
    print(f"Папка РЕЗУЛЬТАТІВ: {output_path}")
    if enable_renaming_actual := bool(article_name and article_name.strip()): print(f"Артикул: {article_name}")
    else: print(f"Перейменування за артикулом: Вимкнено")
    print(f"Видалення оригіналів: {'Так' if delete_originals else 'Ні'}")
    if perform_preresize := (preresize_width > 0 and preresize_height > 0): print(f"Перед. ресайз: Так ({preresize_width}x{preresize_height}px)")
    else: print(f"Перед. ресайз: Ні")
    print(f"Відбілювання: {'Так' if enable_whitening else 'Ні'}")
    if enable_whitening: # <<< ДОДАНО ДРУК ПОРОГУ ВІДБІЛЮВАННЯ
        print(f"  - Поріг скасування відбілювання (мін. сума RGB): {whitening_cancel_threshold}")
    if enable_bg_removal_and_crop := (white_tolerance is not None and white_tolerance >= 0): # Додано перевірку >= 0
        print(f"Видалення фону/Обрізка: Так (допуск білого {white_tolerance})")
        if crop_symmetric_absolute: print("  - Режим обрізки: Абсолютно симетричний")
        elif crop_symmetric_axes: print("  - Режим обрізки: Симетричний по осях")
        else: print("  - Режим обрізки: Стандартний (асиметричний)")
    else: print(f"Видалення фону/Обрізка: Ні")
    # Перевірка perimeter_margin >= 0
    perform_perimeter_check = perimeter_margin is not None and perimeter_margin > 0
    print(f"Перевірка периметра для полів: {'Так (' + str(perimeter_margin) + 'px)' if perform_perimeter_check else 'Ні'}")
    # Перевірка padding_percent >= 0
    perform_padding = padding_percent is not None and padding_percent > 0
    print(f"Відсоток полів: {str(padding_percent) + '%' if perform_padding else 'Ні'} (якщо умова перевірки периметра виконана)")

    # Перевірка force_aspect_ratio
    use_force_aspect_ratio = False
    if force_aspect_ratio and isinstance(force_aspect_ratio, (tuple, list)) and len(force_aspect_ratio) == 2:
        try:
             ar_w, ar_h = map(float, force_aspect_ratio)
             if ar_w > 0 and ar_h > 0:
                 print(f"Примусове співвідношення сторін: Так ({ar_w}:{ar_h})")
                 use_force_aspect_ratio = True
                 force_aspect_ratio = (ar_w, ar_h) # Зберігаємо як float для розрахунків
             else: print(f"Примусове співвідношення сторін: Ні (непозитивні значення)")
        except (ValueError, TypeError): print(f"Примусове співвідношення сторін: Ні (неправильний формат)")
    else: print(f"Примусове співвідношення сторін: Ні")

    # Перевірка max_output_width, max_output_height
    use_max_dimensions = False
    max_w = max(0, int(max_output_width)) if max_output_width is not None else 0
    max_h = max(0, int(max_output_height)) if max_output_height is not None else 0
    if max_w > 0 or max_h > 0:
        print(f"Обмеження макс. розміру: Так (Ш: {max_w or 'Немає'}, В: {max_h or 'Немає'})")
        use_max_dimensions = True
    else: print(f"Обмеження макс. розміру: Ні")

    # Перевірка final_exact_width, final_exact_height
    perform_final_canvas = False
    final_w = max(0, int(final_exact_width)) if final_exact_width is not None else 0
    final_h = max(0, int(final_exact_height)) if final_exact_height is not None else 0
    if final_w > 0 and final_h > 0:
        print(f"Фінальний холст точного розміру: Так ({final_w}x{final_h}px)")
        perform_final_canvas = True
    else: print(f"Фінальний холст точного розміру: Ні")

    print(f"Формат збереження: {output_format_lower.upper()}")
    if output_format_lower == 'jpg':
        # Перевірка jpg_background_color_tuple
        default_bg = (255, 255, 255)
        if jpg_background_color and isinstance(jpg_background_color, (tuple, list)) and len(jpg_background_color) == 3:
            try: jpg_bg_color_validated = tuple(max(0, min(255, int(c))) for c in jpg_background_color)
            except (ValueError, TypeError): jpg_bg_color_validated = default_bg; print(f"  ! Неправильний формат кольору фону JPG, використано {default_bg}")
        else: jpg_bg_color_validated = default_bg; print(f"  ! Колір фону JPG не вказано або неправильний формат, використано {default_bg}")
        print(f"  - Колір фону JPG: {jpg_bg_color_validated}")
        # Перевірка jpeg_quality
        jpeg_quality_validated = max(1, min(100, int(jpeg_quality))) if jpeg_quality is not None else 95
        print(f"  - Якість JPG: {jpeg_quality_validated}")
        # Перепризначаємо перевірені значення
        jpg_background_color = jpg_bg_color_validated
        jpeg_quality = jpeg_quality_validated
    else: print(f"  - Фон PNG: Прозорий")

    # Перевірка папки бекапів
    backup_enabled = False
    if backup_folder_path:
        backup_folder_path = os.path.abspath(backup_folder_path) # Робимо шлях абсолютним
        # Перевіряємо, чи папка бекапів не співпадає з папкою вводу або виводу
        if os.path.abspath(input_path) == backup_folder_path:
            print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою джерела. Бекап вимкнено.")
        elif os.path.abspath(output_path) == backup_folder_path:
            print(f"!! ПОПЕРЕДЖЕННЯ: Папка бекапів співпадає з папкою результатів. Бекап вимкнено.")
        else:
            print(f"Резервне копіювання: Увімкнено ({backup_folder_path})")
            if not os.path.exists(backup_folder_path):
                try:
                    os.makedirs(backup_folder_path); print(f"  - Створено папку бекапів.")
                    backup_enabled = True
                except Exception as e: print(f"!! Помилка створення папки бекапів: {e}. Бекап вимкнено.")
            elif not os.path.isdir(backup_folder_path):
                print(f"!! ПОМИЛКА: Вказаний шлях для бекапів не є папкою: {backup_folder_path}. Бекап вимкнено.")
            else: # Папка існує і є папкою
                backup_enabled = True
    else: print(f"Резервне копіювання: Вимкнено")
    print("-" * 25)

    # Створення папки результатів, якщо її немає
    if not os.path.exists(output_path):
        try: os.makedirs(output_path); print(f"Створено папку результатів: {output_path}")
        except Exception as e: print(f"!! ПОМИЛКА створення папки результатів '{output_path}': {e}. СКАСОВАНО."); return
    elif not os.path.isdir(output_path):
        print(f"!! ПОМИЛКА: Вказаний шлях результатів '{output_path}' існує, але не є папкою. СКАСОВАНО."); return

    # --- Пошук файлів ---
    try:
        all_entries = os.listdir(input_path)
        # Фільтруємо файли за розширенням і ігноруємо тимчасові
        SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp', '.tif')
        files_unsorted = [f for f in all_entries if os.path.isfile(os.path.join(input_path, f)) and not f.startswith("__temp_") and f.lower().endswith(SUPPORTED_EXTENSIONS)]
        files = natsorted(files_unsorted)
        print(f"Знайдено файлів для обробки в '{input_path}': {len(files)}")
        if not files: print("Файлів для обробки не знайдено."); return
    except FileNotFoundError: print(f"Помилка: Папку ДЖЕРЕЛА не знайдено - {input_path}"); return
    except NameError: # Якщо natsort не імпортовано
        print("Попередження: natsort не знайдено, використання стандартного сортування.")
        files = sorted(files_unsorted)
        print(f"Знайдено файлів для обробки в '{input_path}': {len(files)}")
    except Exception as e: print(f"Помилка читання папки {input_path}: {e}"); return

    processed_files_count = 0; skipped_files_count = 0; error_files_count = 0
    source_files_to_potentially_delete = []
    processed_output_file_map = {} # Карта: шлях_вихідного_файлу -> оригінальна_базова_назва
    output_ext = f".{output_format_lower}"

    # --- Основний цикл обробки ---
    for file_index, file in enumerate(files):
        source_file_path = os.path.join(input_path, file)
        print(f"\n[{file_index+1}/{len(files)}] Обробка файлу: {file}")

        # Ініціалізація змінних для зображень на КОЖНІЙ ітерації
        img_opened = None
        img_current = None
        img_whitened = None
        img_no_bg = None
        img_cropped = None
        img_padded = None
        img_ratio_enforced = None
        img_max_limited = None
        img_on_final_canvas = None
        img_prepared_for_save = None
        img_to_save = None # Зазвичай це буде img_prepared_for_save
        # Додаткові тимчасові змінні для проміжних кроків
        pr_canvas = None; resized_content = None
        ratio_canvas = None
        resized_img = None
        final_canvas = None; content_to_paste = None; paste_mask = None; temp_rgba_paste = None
        temp_converted = None; prep_canvas = None; temp_rgba_prep = None; paste_mask_prep = None; image_to_paste_prep = None
        image_to_finally_save = None; temp_save_image = None; paste_mask_save = None; image_to_paste_save = None; temp_rgba_save = None

        success_flag = False # Прапор успішного збереження поточного файлу

        try:
            # 1. Бекап (якщо увімкнено і папка існує)
            if backup_enabled:
                backup_file_path = os.path.join(backup_folder_path, file)
                try:
                    shutil.copy2(source_file_path, backup_file_path);
                except Exception as backup_err:
                    print(f"  !! Помилка бекапу: {backup_err}") # Не зупиняємо процес через помилку бекапу

            # 2. Відкриття
            try:
                img_opened = Image.open(source_file_path)
                img_opened.load() # Завантажуємо дані зображення
                img_current = img_opened.copy() # Працюємо з копією
                print(f"  - Відкрито. Ориг. розмір: {img_current.size}, Режим: {img_current.mode}")
            finally:
                # Закриваємо оригінальний файловий дескриптор
                if img_opened:
                    try: img_opened.close()
                    except Exception: pass

            # Перевірка на нульовий розмір після відкриття
            if img_current.size[0] <= 0 or img_current.size[1] <= 0:
                 print(f"  ! Помилка: Зображення має нульовий розмір після відкриття. Пропускаємо.")
                 error_files_count += 1; continue # Пропустити цей файл

            # 3. Перед. ресайз
            if perform_preresize:
                if img_current.size != (preresize_width, preresize_height):
                    print(f"  - Крок Pre-Resize до {preresize_width}x{preresize_height}...")
                    ow, oh = img_current.size
                    if ow > 0 and oh > 0:
                        # Зберігаємо співвідношення сторін при вписуванні
                        ratio = min(preresize_width / ow, preresize_height / oh)
                        nw, nh = max(1, int(ow * ratio)), max(1, int(oh * ratio))
                        # Використовуємо локальні змінні для проміжних результатів
                        resized_content_pr = None; pr_canvas_inner = None
                        try:
                            print(f"    - Масштабування до {nw}x{nh}...")
                            resized_content_pr = img_current.resize((nw, nh), Image.Resampling.LANCZOS)
                            # Створюємо холст з БІЛИМ фоном для передресайзу
                            pr_canvas_inner = Image.new('RGB', (preresize_width, preresize_height), (255, 255, 255))
                            x, y = (preresize_width - nw)//2, (preresize_height - nh)//2
                            print(f"    - Вставка на холст в позицію ({x},{y})...")
                            # Перевірка режиму перед вставкою (якщо вдруг не RGB)
                            if resized_content_pr.mode == 'RGBA':
                                pr_canvas_inner.paste(resized_content_pr, (x, y), resized_content_pr) # Використовуємо альфа-канал як маску
                            else:
                                pr_canvas_inner.paste(resized_content_pr.convert('RGB'), (x, y)) # Конвертуємо в RGB якщо треба
                            # Замінюємо img_current новим зображенням
                            img_current.close(); img_current = pr_canvas_inner; pr_canvas_inner = None # Перепризначили, обнуляємо локальну
                            print(f"    - Новий розмір: {img_current.size}, Режим: {img_current.mode}")
                        except Exception as pr_err:
                            print(f"   ! Помилка перед. ресайзу: {pr_err}")
                            # Якщо сталася помилка, img_current залишається старим
                        finally: # Закриваємо проміжні об'єкти
                             if resized_content_pr:
                                 try: resized_content_pr.close()
                                 except Exception: pass
                             if pr_canvas_inner: # Якщо він не став img_current
                                 try: pr_canvas_inner.close()
                                 except Exception: pass
                    else: print("   ! Нульовий розмір для перед. ресайзу.")
                else: print("   - Перед. ресайз: розмір вже відповідає цільовому.")
            else: print("  - Крок Pre-Resize: вимкнено.")

            # 4. Відбілювання
            if enable_whitening:
                print("  - Крок Whitening...")
                try:
                    # Передаємо поріг скасування
                    img_whitened = whiten_image_by_darkest_perimeter(img_current, whitening_cancel_threshold)
                    # Функція повертає АБО оригінал img_current (якщо скасовано/не потрібно)
                    # АБО нове відбілене зображення
                    if img_whitened is not img_current:
                         print(f"    - Відбілювання застосовано.")
                         img_current.close() # Закриваємо старий img_current
                         img_current = img_whitened # Тепер img_current - це відбілене зображення
                         img_whitened = None # Обнуляємо тимчасову змінну
                    else:
                         print(f"    - Відбілювання не застосовано (скасовано або не потрібно).")
                         # img_current залишається тим самим
                    print(f"    - Розмір після кроку відбілювання: {img_current.size}, Режим: {img_current.mode}")
                except Exception as wh_err:
                     print(f"  !! Загальна помилка під час виклику відбілювання: {wh_err}")
                     # Продовжуємо з поточним img_current
            else: print("  - Крок Whitening: вимкнено.")

            # 5. Перевірка периметра (виконується ПЕРЕД видаленням фону/обрізкою)
            should_add_padding = False
            if perform_perimeter_check and perform_padding:
                 print("  - Крок Check Perimeter (для умовних полів)...")
                 # Використовуємо white_tolerance, якщо видалення фону увімкнено, інакше 0
                 current_perimeter_tolerance = white_tolerance if enable_bg_removal_and_crop else 0
                 should_add_padding = check_perimeter_is_white(img_current, current_perimeter_tolerance, perimeter_margin)
                 print(f"    - Результат перевірки: Поля {'будуть додані' if should_add_padding else 'не будуть додані'}")
            elif perform_padding:
                 print("  - Крок Check Perimeter: вимкнено, але Padding увімкнено -> Поля будуть додані безумовно.")
                 should_add_padding = True # Додаємо поля, якщо perimeter_check вимкнено, але padding увімкнено
            else: print("  - Крок Check Perimeter/Padding: вимкнено або не потрібно.")

            # 6. Видалення фону (якщо увімкнено)
            img_after_bg_processing = img_current # Починаємо з поточного результату
            if enable_bg_removal_and_crop:
                print(f"  - Крок Background Removal (допуск {white_tolerance})...")
                try:
                    img_no_bg = remove_white_background(img_current, white_tolerance)
                    # Функція повертає або нове зображення з прозорістю, або оригінал/копію
                    if img_no_bg is not img_current:
                        print("    - Фон видалено (або створено копію RGBA).")
                        img_current.close() # Закриваємо попередній стан
                        img_after_bg_processing = img_no_bg
                        img_no_bg = None # Обнуляємо тимчасову
                    else:
                        print("    - Фон не видалявся (не знайдено білих пікселів або помилка).")
                        img_after_bg_processing = img_current # Залишаємо поточний
                    print(f"    - Розмір після видалення фону: {img_after_bg_processing.size}, Режим: {img_after_bg_processing.mode}")
                except Exception as bg_err:
                     print(f"   !! Загальна помилка виклику remove_white_background: {bg_err}")
                     img_after_bg_processing = img_current # Повертаємось до стану перед цим кроком
            else: print("  - Крок Background Removal: вимкнено.")

            # 7. Обрізка (якщо увімкнено видалення фону/обрізка)
            # Використовуємо img_after_bg_processing як вхід для обрізки
            img_after_crop = img_after_bg_processing # Починаємо з результату попереднього кроку
            if enable_bg_removal_and_crop:
                 print("  - Крок Crop...")
                 try:
                     img_cropped = crop_image(img_after_bg_processing, symmetric_axes=crop_symmetric_axes, symmetric_absolute=crop_absolute_symmetry)
                     # Функція повертає або нове обрізане зображення, або оригінал/копію
                     if img_cropped is not img_after_bg_processing:
                          print("    - Обрізку виконано.")
                          img_after_bg_processing.close() # Закриваємо попередній стан
                          img_after_crop = img_cropped
                          img_cropped = None # Обнуляємо тимчасову
                     else:
                          print("    - Обрізка не змінила зображення (не було чого обрізати або помилка).")
                          img_after_crop = img_after_bg_processing # Залишаємо поточний
                     print(f"    - Розмір після обрізки: {img_after_crop.size}, Режим: {img_after_crop.mode}")
                 except Exception as crop_err:
                      print(f"   !! Загальна помилка виклику crop_image: {crop_err}")
                      img_after_crop = img_after_bg_processing # Повертаємось до стану перед обрізкою
            # Якщо обрізка не виконувалась, img_after_crop == img_after_bg_processing

            # Перевірка на нульовий розмір після базової обробки
            if img_after_crop.size[0] <= 0 or img_after_crop.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після базової обробки (фон/обрізка). Пропускаємо файл.")
                 error_files_count += 1; continue # Пропустити цей файл

            # 8. Додавання полів (якщо потрібно)
            img_with_padding = img_after_crop # Починаємо з результату попереднього кроку
            if should_add_padding and perform_padding: # Перевіряємо обидва прапори
                 print(f"  - Крок Padding ({padding_percent}%)...")
                 try:
                      img_padded = add_padding(img_after_crop, padding_percent)
                      # Функція повертає нове зображення з полями або оригінал
                      if img_padded is not img_after_crop:
                           print("    - Поля додано.")
                           img_after_crop.close() # Закриваємо попередній стан
                           img_with_padding = img_padded
                           img_padded = None # Обнуляємо тимчасову
                      else:
                           print("    - Додавання полів не змінило зображення (відсоток=0 або помилка).")
                           img_with_padding = img_after_crop # Залишаємо поточний
                      print(f"    - Розмір після додавання полів: {img_with_padding.size}, Режим: {img_with_padding.mode}")
                 except Exception as pad_err:
                      print(f"   !! Загальна помилка виклику add_padding: {pad_err}")
                      img_with_padding = img_after_crop # Повертаємось до стану перед полями
            else: print("  - Крок Padding: пропущено.")

            # Перевірка на нульовий розмір після полів
            if img_with_padding.size[0] <= 0 or img_with_padding.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після додавання полів. Пропускаємо файл.")
                 error_files_count += 1; continue

            # 9. Примусове співвідношення сторін
            img_ratio_enforced = img_with_padding # Починаємо з поточного
            if use_force_aspect_ratio:
                print(f"  - Крок Aspect Ratio ({force_aspect_ratio[0]}:{force_aspect_ratio[1]})...")
                ratio_canvas_inner = None # Локальна змінна для холсту
                try:
                    target_aspect_w, target_aspect_h = force_aspect_ratio
                    current_w, current_h = img_with_padding.size
                    # Запобігання діленню на нуль
                    if current_h == 0: raise ValueError("Висота зображення нульова")
                    current_aspect = current_w / current_h
                    desired_aspect = target_aspect_w / target_aspect_h

                    # Порівнюємо з невеликим допуском
                    if abs(current_aspect - desired_aspect) > 0.01:
                        print(f"    - Поточне співвідношення: {current_aspect:.3f}, Цільове: {desired_aspect:.3f}. Потрібна зміна.")
                        # Визначаємо розміри нового холсту
                        if current_aspect > desired_aspect: # Зображення зашироке, збільшуємо висоту холсту
                            target_w = current_w; target_h = int(current_w / desired_aspect)
                        else: # Зображення зависоке, збільшуємо ширину холсту
                            target_h = current_h; target_w = int(current_h * desired_aspect)
                        # Переконуємось, що розміри не нульові
                        target_w = max(1, target_w); target_h = max(1, target_h)
                        print(f"    - Створення холсту {target_w}x{target_h} (прозорий)")
                        # Створюємо новий RGBA холст
                        ratio_canvas_inner = Image.new('RGBA', (target_w, target_h), (0,0,0,0))
                        x = (target_w - current_w) // 2; y = (target_h - current_h) // 2
                        # Вставляємо поточне зображення (img_with_padding) на холст
                        # Переконуємось, що вставляємо з маскою, якщо є прозорість
                        if img_with_padding.mode == 'RGBA':
                            ratio_canvas_inner.paste(img_with_padding, (x, y), img_with_padding)
                        else:
                             # Якщо не RGBA, конвертуємо перед вставкою, щоб зберегти прозорість холсту
                             temp_rgba_ratio = None
                             try:
                                 temp_rgba_ratio = img_with_padding.convert('RGBA')
                                 ratio_canvas_inner.paste(temp_rgba_ratio, (x, y), temp_rgba_ratio)
                             except Exception as conv_paste_err:
                                  print(f"     ! Помилка конвертації/вставки для співвідношення: {conv_paste_err}. Спроба без маски.")
                                  # Спробуємо вставити як RGB, якщо конвертація в RGBA не вдалася
                                  try: ratio_canvas_inner.paste(img_with_padding.convert('RGB'), (x, y))
                                  except Exception as rgb_paste_err: print(f"     !! Не вдалося вставити навіть як RGB: {rgb_paste_err}")
                             finally:
                                  if temp_rgba_ratio: temp_rgba_ratio.close()

                        # Замінюємо img_ratio_enforced новим холстом
                        img_with_padding.close(); img_ratio_enforced = ratio_canvas_inner; ratio_canvas_inner = None
                        print(f"    - Новий розмір після зміни співвідношення: {img_ratio_enforced.size}")
                    else:
                         print("    - Співвідношення сторін вже відповідає цільовому (в межах допуску).")
                         # img_ratio_enforced залишається img_with_padding
                except Exception as ratio_err:
                    print(f"    !! Помилка зміни співвідношення сторін: {ratio_err}")
                    # Залишаємо img_ratio_enforced як був (img_with_padding)
                finally:
                    # Закриваємо холст, якщо він був створений, але не став результатом
                    if ratio_canvas_inner:
                        try: ratio_canvas_inner.close()
                        except Exception: pass
            else: print("  - Крок Aspect Ratio: вимкнено.")

            # Перевірка на нульовий розмір
            if img_ratio_enforced.size[0] <= 0 or img_ratio_enforced.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після зміни співвідношення сторін. Пропускаємо файл.")
                 error_files_count += 1; continue

            # 10. Обмеження максимальних розмірів
            img_max_limited = img_ratio_enforced # Починаємо з поточного
            resized_img_max = None # Локальна для результату ресайзу
            if use_max_dimensions:
                 print(f"  - Крок Max Dimensions (Ш: {max_w or 'N/A'}, В: {max_h or 'N/A'})...")
                 current_w, current_h = img_ratio_enforced.size
                 print(f"    - Поточний розмір: {current_w}x{current_h}")
                 scale_ratio = 1.0
                 if max_w > 0 and current_w > max_w: scale_ratio = min(scale_ratio, max_w / current_w)
                 if max_h > 0 and current_h > max_h: scale_ratio = min(scale_ratio, max_h / current_h)

                 if scale_ratio < 1.0:
                      nw = max(1, int(current_w * scale_ratio)); nh = max(1, int(current_h * scale_ratio))
                      print(f"    - Зменшення до {nw}x{nh}...")
                      try:
                          resized_img_max = img_ratio_enforced.resize((nw, nh), Image.Resampling.LANCZOS)
                          img_ratio_enforced.close(); img_max_limited = resized_img_max; resized_img_max = None
                          print(f"    - Розмір після обмеження: {img_max_limited.size}")
                      except Exception as max_resize_err:
                           print(f"    !! Помилка зменшення розміру: {max_resize_err}")
                           # Залишаємо img_max_limited як був (img_ratio_enforced)
                      finally:
                           if resized_img_max: # Закриваємо, якщо створили, але не присвоїли
                                try: resized_img_max.close()
                                except Exception: pass
                 else: print("    - Зображення вже в межах максимальних розмірів.")
            else: print("  - Крок Max Dimensions: вимкнено.")

            # Перевірка на нульовий розмір
            if img_max_limited.size[0] <= 0 or img_max_limited.size[1] <= 0:
                 print(f"  ! Помилка або нульовий розмір після обмеження розмірів. Пропускаємо файл.")
                 error_files_count += 1; continue

            # 11. Фінальний холст точного розміру АБО підготовка режиму/фону
            img_prepared_for_save = None # Тут буде фінальний результат перед збереженням
            # Локальні змінні для цього кроку
            final_canvas_inner = None; content_to_paste_fc = None; resized_content_fc = None; paste_mask_fc = None; temp_rgba_fc = None
            prep_canvas_inner = None; temp_converted_prep = None; temp_rgba_prep_inner = None; paste_mask_prep_inner = None; image_to_paste_prep_inner = None

            if perform_final_canvas:
                 print(f"  - Крок Final Canvas ({final_w}x{final_h})...")
                 try:
                     img_before_canvas = img_max_limited # Вхідне зображення для цього кроку
                     bw, bh = img_before_canvas.size
                     # Розрахунок розміру для вписування в холст зі збереженням пропорцій
                     ratio = 1.0
                     if bw > 0: ratio = min(ratio, final_w / bw)
                     if bh > 0: ratio = min(ratio, final_h / bh)
                     nw = max(1, int(bw * ratio)); nh = max(1, int(bh * ratio))
                     print(f"    - Масштабування вмісту до {nw}x{nh} для вписування...")
                     resized_content_fc = img_before_canvas.resize((nw, nh), Image.Resampling.LANCZOS)
                     content_to_paste_fc = resized_content_fc # Зображення, яке будемо вставляти

                     # Створюємо фінальний холст
                     if output_format_lower == 'png':
                          print(f"    - Створення фінального RGBA холсту (прозорий)")
                          final_canvas_inner = Image.new('RGBA', (final_w, final_h), (0,0,0,0))
                     else: # jpg
                          print(f"    - Створення фінального RGB холсту (фон: {jpg_background_color})")
                          final_canvas_inner = Image.new('RGB', (final_w, final_h), jpg_background_color)

                     # Розрахунок позиції для центрування
                     x = (final_w - nw) // 2; y = (final_h - nh) // 2
                     print(f"    - Вставка вмісту на холст в позицію ({x},{y})...")

                     # Вставка з урахуванням прозорості вмісту
                     paste_mask_fc = None
                     temp_rgba_fc = None
                     image_to_paste_fc = content_to_paste_fc # За замовчуванням

                     if content_to_paste_fc.mode in ('RGBA', 'LA'):
                          try: paste_mask_fc = content_to_paste_fc.split()[-1]
                          except IndexError: pass # Якщо немає альфи, маска не потрібна
                     elif content_to_paste_fc.mode == 'PA':
                          try: # Конвертуємо палітру в RGBA для отримання маски
                               temp_rgba_fc = content_to_paste_fc.convert('RGBA')
                               paste_mask_fc = temp_rgba_fc.split()[-1]
                               image_to_paste_fc = temp_rgba_fc # Вставляти будемо конвертоване
                          except Exception as pa_mask_err: print(f"     ! Помилка конвертації PA->RGBA для маски холсту: {pa_mask_err}")
                     # Якщо цільовий холст RGB, а вміст має альфу, маска все одно потрібна для правильного накладання
                     # Якщо цільовий RGBA, маска потрібна для збереження прозорості вмісту

                     final_canvas_inner.paste(image_to_paste_fc, (x,y), paste_mask_fc)

                     print(f"    - Вміст вставлено. Фінальний розмір: {final_canvas_inner.size}")
                     # Результатом стає новий холст
                     img_prepared_for_save = final_canvas_inner; final_canvas_inner = None # Перепризначили, обнуляємо локальну

                 except Exception as canvas_err:
                      print(f"    !! Помилка створення/заповнення фінального холсту: {canvas_err}")
                      img_prepared_for_save = img_max_limited # Повертаємось до попереднього стану
                 finally: # Закриваємо проміжні об'єкти цього кроку
                      if resized_content_fc:
                          try: resized_content_fc.close()
                          except Exception: pass
                      if temp_rgba_fc:
                          try: temp_rgba_fc.close()
                          except Exception: pass
                      if paste_mask_fc:
                          try: paste_mask_fc.close()
                          except Exception: pass
                      if final_canvas_inner: # Якщо створили, але не присвоїли
                          try: final_canvas_inner.close()
                          except Exception: pass
                      # Закриваємо img_max_limited, якщо він НЕ став результатом
                      if img_prepared_for_save is not img_max_limited:
                           try: img_max_limited.close()
                           except Exception: pass

            else: # Фінальний холст не потрібен, просто готуємо режим/фон
                 print(f"  - Крок Final Canvas: вимкнено. Підготовка зображення до збереження...")
                 img_to_prepare = img_max_limited # Вхідне зображення для підготовки
                 try:
                     if output_format_lower == 'png':
                         # Переконуємось, що результат буде RGBA
                         if img_to_prepare.mode != 'RGBA':
                              print(f"    - Конвертація {img_to_prepare.mode} -> RGBA для PNG...")
                              temp_converted_prep = img_to_prepare.convert('RGBA')
                              img_prepared_for_save = temp_converted_prep; temp_converted_prep = None
                         else:
                              print("    - Зображення вже RGBA.")
                              img_prepared_for_save = img_to_prepare # Використовуємо як є
                     else: # jpg - результат має бути RGB
                         if img_to_prepare.mode == 'RGB':
                              print("    - Зображення вже RGB.")
                              img_prepared_for_save = img_to_prepare
                         else:
                              # Потрібно накласти на фон або конвертувати
                              print(f"    - Підготовка {img_to_prepare.mode} для збереження як JPG (фон: {jpg_background_color})...")
                              # Створюємо RGB холст з потрібним фоном
                              prep_canvas_inner = Image.new('RGB', img_to_prepare.size, jpg_background_color)
                              paste_mask_prep_inner = None
                              temp_rgba_prep_inner = None
                              image_to_paste_prep_inner = img_to_prepare # За замовчуванням

                              # Визначаємо, чи потрібна маска для вставки
                              if img_to_prepare.mode in ('RGBA', 'LA'):
                                   try: paste_mask_prep_inner = img_to_prepare.split()[-1]
                                   except IndexError: pass
                              elif img_to_prepare.mode == 'PA':
                                   try: # Конвертуємо палітру в RGBA для коректної вставки
                                        temp_rgba_prep_inner = img_to_prepare.convert('RGBA')
                                        paste_mask_prep_inner = temp_rgba_prep_inner.split()[-1]
                                        image_to_paste_prep_inner = temp_rgba_prep_inner
                                   except Exception as pa_prep_err: print(f"     ! Помилка PA->RGBA для підготовки JPG: {pa_prep_err}")

                              # Вставляємо на фон з маскою (якщо вона є)
                              prep_canvas_inner.paste(image_to_paste_prep_inner, (0,0), paste_mask_prep_inner)
                              img_prepared_for_save = prep_canvas_inner; prep_canvas_inner = None # Перепризначили
                 except Exception as prep_err:
                      print(f"    !! Помилка підготовки до збереження: {prep_err}")
                      img_prepared_for_save = img_max_limited # Повертаємось до попереднього
                 finally: # Закриваємо проміжні об'єкти цього блоку
                      if temp_converted_prep:
                          try: temp_converted_prep.close();
                          except Exception: pass
                      if prep_canvas_inner:
                          try: prep_canvas_inner.close();
                          except Exception: pass
                      if temp_rgba_prep_inner:
                          try: temp_rgba_prep_inner.close();
                          except Exception: pass
                      if paste_mask_prep_inner:
                          try: paste_mask_prep_inner.close();
                          except Exception: pass
                      # Закриваємо img_max_limited, якщо він НЕ став результатом
                      if img_prepared_for_save is not img_max_limited:
                           try: img_max_limited.close();
                           except Exception: pass


            # 12. Збереження
            if img_prepared_for_save is None:
                 print("  !! Помилка: Немає зображення для збереження після всіх кроків. Пропускаємо.")
                 error_files_count += 1; continue
            if img_prepared_for_save.size[0] <= 0 or img_prepared_for_save.size[1] <= 0:
                 print(f"  !! Помилка: Зображення для збереження має нульовий розмір {img_prepared_for_save.size}. Пропускаємо.")
                 error_files_count += 1; continue

            base_name = os.path.splitext(file)[0]
            output_filename = f"{base_name}{output_ext}" # Поки що зберігаємо з оригінальною назвою
            final_output_path = os.path.join(output_path, output_filename)
            print(f"  - Крок Save: Підготовка до збереження у {output_filename}...")
            print(f"      - Режим зображення перед збереженням: {img_prepared_for_save.mode}")
            print(f"      - Розмір зображення перед збереженням: {img_prepared_for_save.size}")

            image_to_finally_save = None # Об'єкт, який буде збережено
            temp_save_image_final = None # Тимчасовий холст/конвертація для збереження
            paste_mask_save_final = None # Маска для фінальної вставки
            temp_rgba_save_final = None  # Тимчасове RGBA для фінальної вставки

            try:
                save_options = {"optimize": True}
                if output_format_lower == 'jpg':
                    save_format_name = "JPEG"
                    target_mode = "RGB"
                    # Перевіряємо, чи потрібна конвертація або накладання на фон
                    if img_prepared_for_save.mode == target_mode:
                        print(f"      - Зображення вже в {target_mode}, готове для збереження як JPG.")
                        image_to_finally_save = img_prepared_for_save # Зберігаємо як є
                    else:
                        # Потрібно створити RGB холст і накласти зображення
                        print(f"      - Фінальне накладання {img_prepared_for_save.mode} на фон {jpg_background_color} для збереження як JPG...")
                        try:
                            temp_save_image_final = Image.new(target_mode, img_prepared_for_save.size, jpg_background_color)
                            image_to_paste_save = img_prepared_for_save
                            # Отримуємо маску, якщо є прозорість
                            if img_prepared_for_save.mode in ('RGBA', 'LA'):
                                try: paste_mask_save_final = img_prepared_for_save.split()[-1]
                                except IndexError: pass
                            elif img_prepared_for_save.mode == 'PA':
                                try: # Конвертуємо палітру в RGBA
                                    temp_rgba_save_final = img_prepared_for_save.convert('RGBA')
                                    paste_mask_save_final = temp_rgba_save_final.split()[-1]
                                    image_to_paste_save = temp_rgba_save_final # Вставляти будемо RGBA версію
                                except Exception as pa_err_save: print(f"       ! Помилка PA->RGBA для маски при збереженні JPG: {pa_err_save}")

                            # Виконуємо вставку з маскою (якщо вона є)
                            temp_save_image_final.paste(image_to_paste_save, (0, 0), paste_mask_save_final)
                            print(f"      - Зображення успішно накладено на фон.")
                            image_to_finally_save = temp_save_image_final; temp_save_image_final = None # Перепризначили
                        except Exception as prep_err_save:
                            print(f"      !! Помилка підготовки фону для JPG: {prep_err_save}. Спроба простої конвертації...")
                            # Якщо накладання не вдалося, спробуємо просто конвертувати
                            try:
                                temp_save_image_final = img_prepared_for_save.convert(target_mode)
                                image_to_finally_save = temp_save_image_final; temp_save_image_final = None
                                print(f"      - Виконано просту конвертацію в {target_mode}.")
                            except Exception as conv_err_save:
                                print(f"      !!! Помилка навіть простої конвертації в RGB: {conv_err_save}. Збереження неможливе.")
                                # Залишаємо image_to_finally_save як None
                        finally:
                            # Закриваємо тимчасові об'єкти цього блоку
                            if temp_rgba_save_final: temp_rgba_save_final.close()
                            if paste_mask_save_final: paste_mask_save_final.close()
                            if temp_save_image_final: temp_save_image_final.close() # Закриваємо, якщо не стало результатом

                    if image_to_finally_save:
                         save_options["quality"] = jpeg_quality
                         save_options["subsampling"] = 0 # Зазвичай краще для якості
                         save_options["progressive"] = True # Може покращити відображення в вебі

                else: # png
                    save_format_name = "PNG"
                    target_mode = "RGBA"
                    # Переконуємось, що зображення RGBA
                    if img_prepared_for_save.mode == target_mode:
                        print(f"      - Зображення вже в {target_mode}, готове для збереження як PNG.")
                        image_to_finally_save = img_prepared_for_save
                    else:
                        print(f"      - Фінальна конвертація зображення ({img_prepared_for_save.mode}) в {target_mode} для збереження як PNG...")
                        try:
                            temp_save_image_final = img_prepared_for_save.convert(target_mode)
                            image_to_finally_save = temp_save_image_final; temp_save_image_final = None
                        except Exception as conv_err_png:
                            print(f"      !! Помилка конвертації в RGBA: {conv_err_png}.")
                            image_to_finally_save = img_prepared_for_save # Спробуємо зберегти як є, якщо можливо
                        finally:
                             if temp_save_image_final: temp_save_image_final.close()

                    if image_to_finally_save:
                         save_options["compress_level"] = 6 # Рівень стиснення (0-9)

                # --- Виконуємо збереження ---
                if image_to_finally_save:
                     print(f"      - Збереження у форматі {save_format_name} в {final_output_path}...")
                     image_to_finally_save.save(final_output_path, save_format_name, **save_options)
                     processed_files_count += 1
                     success_flag = True # Встановлюємо прапор успіху
                     print(f"    - Успішно збережено: {final_output_path}")
                     # Зберігаємо мапінг для подальшого перейменування
                     processed_output_file_map[final_output_path] = base_name
                     # Додаємо оригінальний файл до списку на потенційне видалення
                     if os.path.exists(source_file_path) and source_file_path not in source_files_to_potentially_delete:
                         source_files_to_potentially_delete.append(source_file_path)
                else:
                     print(f"  !! Не вдалося підготувати фінальне зображення для збереження.")
                     error_files_count += 1; success_flag = False

            except Exception as save_err:
                print(f"  !! Помилка збереження {output_format_lower.upper()}: {save_err}")
                traceback.print_exc() # Друкуємо деталі помилки збереження
                error_files_count += 1; success_flag = False
            finally:
                # Закриваємо image_to_finally_save, якщо він був створений окремо від img_prepared_for_save
                if image_to_finally_save and image_to_finally_save is not img_prepared_for_save:
                    try: image_to_finally_save.close()
                    except Exception: pass
                # img_prepared_for_save закриється в головному finally цього циклу

        # --- Обробка помилок файлу ---
        except UnidentifiedImageError:
            print(f"!!! Помилка: Не розпізнано формат файлу або файл пошкоджено: {file}")
            skipped_files_count += 1
            success_flag = False
        except FileNotFoundError:
            print(f"!!! Помилка: Файл не знайдено під час обробки (можливо, видалено?): {file}")
            skipped_files_count += 1
            success_flag = False
        except OSError as e:
            print(f"!!! Помилка ОС ({file}): {e}")
            error_files_count += 1
            success_flag = False
        except MemoryError as e:
            print(f"!!! Помилка ПАМ'ЯТІ під час обробки ({file}): {e}. Спробуйте обробляти менші файли або збільшити RAM.")
            error_files_count += 1
            success_flag = False
        except Exception as e:
            print(f"!!! Неочікувана ГЛОБАЛЬНА помилка обробки ({file}): {e}")
            traceback.print_exc() # Друкуємо повний traceback для діагностики
            error_files_count += 1
            success_flag = False
        finally: # Зачистка пам'яті для поточного файлу в кінці КОЖНОЇ ітерації
            print(f"  - Зачистка пам'яті для {os.path.basename(file)}...")
            # Збираємо ВСІ змінні, які могли містити об'єкти Image
            local_img_vars = [
                img_opened, img_current, img_whitened, img_no_bg, img_cropped,
                img_padded, img_ratio_enforced, img_max_limited, img_on_final_canvas,
                img_prepared_for_save, img_to_save,
                pr_canvas, resized_content, # З pre-resize
                ratio_canvas, # З aspect ratio
                resized_img, # З max dimensions
                final_canvas, content_to_paste, paste_mask, temp_rgba_paste, # З final canvas
                temp_converted, prep_canvas, temp_rgba_prep, paste_mask_prep, image_to_paste_prep, # З підготовки до збереження
                image_to_finally_save, temp_save_image, paste_mask_save, image_to_paste_save, temp_rgba_save, # З фінального збереження
                # Додаємо змінні з внутрішніх блоків, які могли залишитись
                locals().get('resized_content_pr'), locals().get('pr_canvas_inner'),
                locals().get('img_after_bg_processing'), locals().get('img_after_crop'),
                locals().get('ratio_canvas_inner'), locals().get('temp_rgba_ratio'),
                locals().get('resized_img_max'),
                locals().get('final_canvas_inner'), locals().get('resized_content_fc'), locals().get('content_to_paste_fc'), locals().get('paste_mask_fc'), locals().get('temp_rgba_fc'), locals().get('image_to_paste_fc'),
                locals().get('prep_canvas_inner'), locals().get('temp_converted_prep'), locals().get('temp_rgba_prep_inner'), locals().get('paste_mask_prep_inner'), locals().get('image_to_paste_prep_inner'),
                locals().get('temp_save_image_final'), locals().get('paste_mask_save_final'), locals().get('temp_rgba_save_final'), locals().get('image_to_paste_save')
            ]
            closed_ids = set() # Зберігаємо id вже закритих об'єктів
            for var_name, img_obj in locals().items():
                 # Додатково перевіряємо всі локальні змінні на випадок, якщо щось пропустили
                 if isinstance(img_obj, Image.Image):
                     obj_id = id(img_obj)
                     if obj_id not in closed_ids:
                         try:
                             # print(f"    - Закриття об'єкта з id {obj_id} (змінна {var_name})")
                             img_obj.close()
                             closed_ids.add(obj_id)
                         except Exception as close_err:
                              # Може бути помилка, якщо об'єкт вже закритий або некоректний
                              # print(f"    ! Помилка закриття об'єкта {obj_id}: {close_err}")
                              pass # Ігноруємо помилки закриття

            # Перевірка прапора успіху: якщо була помилка, видаляємо файл зі списку на видалення
            if not success_flag and source_file_path in source_files_to_potentially_delete:
                 try:
                     source_files_to_potentially_delete.remove(source_file_path);
                     print(f"    - Видалено {os.path.basename(source_file_path)} зі списку на видалення через помилку.")
                 except ValueError: pass # Якщо його там чомусь немає

            # Очищення змінних в кінці циклу (може допомогти зі збиранням сміття)
            del img_opened, img_current, img_whitened, img_no_bg, img_cropped, img_padded
            del img_ratio_enforced, img_max_limited, img_on_final_canvas, img_prepared_for_save, img_to_save
            del pr_canvas, resized_content, ratio_canvas, resized_img, final_canvas, content_to_paste, paste_mask, temp_rgba_paste
            del temp_converted, prep_canvas, temp_rgba_prep, paste_mask_prep, image_to_paste_prep
            del image_to_finally_save, temp_save_image, paste_mask_save, image_to_paste_save, temp_rgba_save
            # І інші тимчасові змінні
            # Можливо, gc.collect() тут, але зазвичай не потрібно

    # --- Статистика, Видалення, Перейменування (поза циклом обробки файлів) ---
    print(f"\n--- Статистика обробки ---");
    print(f"  - Успішно збережено: {processed_files_count}");
    print(f"  - Пропущено (не формат/не знайдено/пошкоджено): {skipped_files_count}")
    print(f"  - Файлів з помилками обробки/збереження: {error_files_count}")
    total_processed = processed_files_count + skipped_files_count + error_files_count
    print(f"  - Всього проаналізовано файлів: {total_processed} (з {len(files)} знайдених)")

    # --- Видалення оригіналів ---
    if delete_originals and source_files_to_potentially_delete:
        print(f"\nВидалення {len(source_files_to_potentially_delete)} оригінальних файлів з '{input_path}'...")
        removed_count = 0; remove_errors = 0
        for file_to_remove in source_files_to_potentially_delete:
            try:
                if os.path.exists(file_to_remove):
                    os.remove(file_to_remove); removed_count += 1
                    # print(f"  - Видалено: {os.path.basename(file_to_remove)}") # Розкоментувати для детального логу
                else:
                    print(f"  ! Файл для видалення не знайдено: {os.path.basename(file_to_remove)}")
            except Exception as remove_error:
                print(f"  ! Помилка видалення {os.path.basename(file_to_remove)}: {remove_error}")
                remove_errors += 1
        print(f"  - Успішно видалено: {removed_count}. Помилок видалення: {remove_errors}.")
    elif delete_originals: print(f"\nВидалення оригіналів увімкнено, але немає файлів для видалення (або всі мали помилки).")
    else: print(f"\nВидалення оригіналів з '{input_path}' вимкнено.")

    # --- Перейменування ---
    if enable_renaming_actual and processed_output_file_map:
        print(f"\n--- Перейменування файлів у '{output_path}' ---")
        # Отримуємо список шляхів до успішно збережених файлів
        successfully_saved_paths = list(processed_output_file_map.keys())
        print(f"Файлів для перейменування (успішно збережених): {len(successfully_saved_paths)}")

        # Готуємо список: [ (шлях_до_файлу, оригінальна_базова_назва), ... ]
        files_to_process_for_rename = []
        for saved_path in successfully_saved_paths:
            if os.path.exists(saved_path): # Перевіряємо, чи файл все ще існує
                 original_basename = processed_output_file_map.get(saved_path)
                 if original_basename:
                     files_to_process_for_rename.append((saved_path, original_basename))
                 else: print(f"  ! Попередження: Не знайдено оригінальну назву для {saved_path}")
            else: print(f"  ! Попередження: Файл для перейменування більше не існує: {saved_path}")

        if not files_to_process_for_rename:
             print("Немає файлів для перейменування.")
        else:
            # Сортуємо файли за їх ОРИГІНАЛЬНОЮ назвою (використовуючи natsort, якщо доступно)
            try:
                sorted_files_for_rename = natsorted(files_to_process_for_rename, key=lambda item: item[1])
            except NameError:
                sorted_files_for_rename = sorted(files_to_process_for_rename, key=lambda item: item[1])
            except Exception as sort_err:
                print(f"  ! Помилка сортування файлів для перейменування: {sort_err}. Використання несортованого списку.")
                sorted_files_for_rename = files_to_process_for_rename

            # Шукаємо файл, що точно відповідає артикулу (регістронезалежно)
            exact_match_source_path = None
            exact_match_original_name = None
            files_to_rename_numerically = [] # Сюди потраплять всі інші

            target_article_filename_base = article_name # База для точної відповідності
            exact_match_target_filename = f"{target_article_filename_base}{output_ext}" # Повна цільова назва

            for current_path, original_basename in sorted_files_for_rename:
                if original_basename.lower() == target_article_filename_base.lower():
                    if exact_match_source_path is None:
                        exact_match_source_path = current_path
                        exact_match_original_name = original_basename
                        print(f"  - Знайдено точну відповідність артикулу: '{os.path.basename(current_path)}' -> '{exact_match_target_filename}'")
                    else:
                        # Знайдено другий файл, що відповідає артикулу - він піде в нумерацію
                        print(f"  ! Попередження: Знайдено дублікат артикулу '{original_basename}' у файлі '{os.path.basename(current_path)}'. Буде пронумеровано.")
                        files_to_rename_numerically.append((current_path, original_basename))
                else:
                    # Не точна відповідність - додаємо до списку для нумерації
                    files_to_rename_numerically.append((current_path, original_basename))

            # Тепер files_to_rename_numerically вже відсортовані за оригінальною назвою

            # --- Двоетапне перейменування для уникнення конфліктів ---
            temp_rename_map = {} # Карта: тимчасовий_шлях -> фінальний_шлях (або None для нумерованих)
            rename_step1_errors = 0
            processed_for_temp_rename = set() # Щоб уникнути подвійної обробки
            temp_counter = 0 # Лічильник для унікальних тимчасових імен

            print("  - Крок 1: Перейменування у тимчасові імена...")

            # Спочатку обробляємо точну відповідність (якщо є)
            if exact_match_source_path:
                temp_filename = f"__temp_{temp_counter}_{exact_match_original_name}{output_ext}"
                temp_path = os.path.join(output_path, temp_filename)
                final_target_path = os.path.join(output_path, exact_match_target_filename)
                try:
                    print(f"    '{os.path.basename(exact_match_source_path)}' -> '{temp_filename}' (ціль: '{exact_match_target_filename}')")
                    os.rename(exact_match_source_path, temp_path)
                    temp_rename_map[temp_path] = final_target_path # Зберігаємо цільовий шлях
                    processed_for_temp_rename.add(exact_match_source_path) # Позначаємо оригінальний шлях як оброблений
                    temp_counter += 1
                except Exception as rename_error:
                    print(f"  ! Помилка тимч. перейменування '{os.path.basename(exact_match_source_path)}': {rename_error}")
                    rename_step1_errors += 1

            # Потім обробляємо файли для нумерації
            for current_path, original_basename in files_to_rename_numerically:
                if current_path in processed_for_temp_rename: continue # Пропускаємо, якщо вже оброблено (малоймовірно тут)
                temp_filename = f"__temp_{temp_counter}_{original_basename}{output_ext}"
                temp_path = os.path.join(output_path, temp_filename)
                try:
                    print(f"    '{os.path.basename(current_path)}' -> '{temp_filename}' (ціль: нумерована)")
                    os.rename(current_path, temp_path)
                    temp_rename_map[temp_path] = None # Цільовий шлях буде визначено на кроці 2
                    processed_for_temp_rename.add(current_path)
                    temp_counter += 1
                except Exception as rename_error:
                    print(f"  ! Помилка тимч. перейменування '{os.path.basename(current_path)}': {rename_error}")
                    rename_step1_errors += 1

            if rename_step1_errors > 0: print(f"  ! Помилок на кроці 1 (тимчасове перейменування): {rename_step1_errors}")

            # --- Крок 2: Фінальне перейменування ---
            print("  - Крок 2: Фінальне перейменування з тимчасових імен...")
            final_rename_counter = 1 # Лічильник для нумерованих файлів (_1, _2, ...)
            rename_step2_errors = 0
            renamed_final_count = 0
            occupied_final_names = set() # Зберігаємо імена, які вже зайняті на цьому кроці

            # Спочатку перейменовуємо точну відповідність (якщо вона успішно стала тимчасовою)
            temp_path_for_exact_match = None
            target_path_for_exact_match = os.path.join(output_path, exact_match_target_filename)

            for temp_p, target_p in temp_rename_map.items():
                 if target_p and os.path.normcase(target_p) == os.path.normcase(target_path_for_exact_match):
                     temp_path_for_exact_match = temp_p
                     break

            if temp_path_for_exact_match:
                 try:
                     if os.path.exists(target_path_for_exact_match):
                          print(f"  ! Конфлікт: Цільовий файл '{exact_match_target_filename}' вже існує. Перейменування артикулу скасовано.")
                          rename_step2_errors += 1
                          # Залишаємо тимчасовий файл як є або можна спробувати дати нумероване ім'я
                     else:
                          print(f"    '{os.path.basename(temp_path_for_exact_match)}' -> '{exact_match_target_filename}'")
                          os.rename(temp_path_for_exact_match, target_path_for_exact_match)
                          renamed_final_count += 1
                          occupied_final_names.add(os.path.normcase(target_path_for_exact_match)) # Позначаємо ім'я як зайняте
                          del temp_rename_map[temp_path_for_exact_match] # Видаляємо з мапи для подальшої обробки
                 except Exception as rename_error:
                     print(f"  ! Помилка фін. перейм. артикулу '{os.path.basename(temp_path_for_exact_match)}': {rename_error}")
                     rename_step2_errors += 1
            elif exact_match_source_path: # Якщо шукали точну відповідність, але не знайшли її серед тимчасових
                print(f"  ! Не вдалося знайти відповідний тимчасовий файл для артикулу: {os.path.basename(exact_match_source_path)}")


            # Тепер перейменовуємо решту (нумеровані)
            # Сортуємо тимчасові файли за їх порядковим номером (з __temp_N_...)
            remaining_temp_files_sorted = sorted(
                temp_rename_map.keys(),
                key=lambda p: int(os.path.basename(p).split('_')[2]) if len(os.path.basename(p).split('_')) > 2 and os.path.basename(p).split('_')[2].isdigit() else float('inf')
            )

            for temp_path in remaining_temp_files_sorted:
                 # Генеруємо наступне нумероване ім'я
                 while True:
                     final_numbered_filename = f"{article_name}_{final_rename_counter}{output_ext}"
                     final_numbered_path = os.path.join(output_path, final_numbered_filename)
                     # Перевіряємо, чи ім'я не зайняте (включаючи потенційний конфлікт з іменем артикулу)
                     if os.path.normcase(final_numbered_path) not in occupied_final_names and \
                        not os.path.exists(final_numbered_path): # Додаткова перевірка існування файлу
                         break
                     print(f"    - Ім'я '{final_numbered_filename}' вже зайняте або існує, пробуємо наступне...")
                     final_rename_counter += 1 # Переходимо до наступного номера

                 # Виконуємо перейменування
                 try:
                     print(f"    '{os.path.basename(temp_path)}' -> '{final_numbered_filename}'")
                     os.rename(temp_path, final_numbered_path)
                     renamed_final_count += 1
                     occupied_final_names.add(os.path.normcase(final_numbered_path)) # Позначаємо нове ім'я як зайняте
                     final_rename_counter += 1 # Готуємо наступний номер
                 except Exception as rename_error:
                     print(f"  ! Помилка фін. перейм. нумерованого '{os.path.basename(temp_path)}': {rename_error}")
                     rename_step2_errors += 1

            print(f"\n  - Перейменовано файлів: {renamed_final_count}. Помилок на кроці 2 (фінальне перейменування): {rename_step2_errors}.")

            # Перевірка залишків тимчасових файлів
            remaining_temp_final = [f for f in os.listdir(output_path) if f.startswith("__temp_") and os.path.isfile(os.path.join(output_path, f))];
            if remaining_temp_final:
                 print(f"  ! Увага: Залишилися тимчасові файли в '{output_path}': {remaining_temp_final}")
                 print(f"    Це могло статися через помилки перейменування або конфлікти імен.")

    elif enable_renaming_actual and not processed_output_file_map:
         print("\n--- Перейменування файлів пропущено: Немає успішно оброблених файлів для перейменування ---")
    elif not enable_renaming_actual:
         print("\n--- Перейменування файлів пропущено (вимкнено через налаштування артикулу) ---")
# --- Кінець функції rename_and_convert_images ---


# --- Блок виконання та Налаштування Користувача ---
if __name__ == "__main__":

    # --- Налаштування користувача ---

    # === Шляхи до папок ===
    input_folder_path = r"C:\Users\zakhar\Downloads\test3"  # Шлях до папки з оригінальними зображеннями
    output_folder_path = r"C:\Users\zakhar\Downloads\test3" # Шлях для збереження оброблених зображень (може бути той самий)
    backup_folder_path = r"C:\Users\zakhar\Downloads\test_py_bak" # Шлях для резервних копій (None або "" = вимкнено)

    # === Налаштування Перейменування та Видалення ===
    article = "S39H_test"                 # Базове ім'я для перейменування (None або "" = вимкнено)
    delete_originals_after_processing = False # Видаляти оригінали після УСПІШНОЇ обробки? (True/False)

    # === Попередній Ресайз (До основної обробки, з білим фоном) ===
    preresize_width = 0                     # Бажана ширина (0 або None = вимкнено)
    preresize_height = 0                    # Бажана висота (0 або None = вимкнено)

    # === Відбілювання (за найтемнішим пікселем ПЕРИМЕТРУ) ===
    enable_whitening = True                  # Увімкнути відбілювання? (True/False)
    # <<< НОВЕ НАЛАШТУВАННЯ: Поріг Скасування Відбілювання >>>
    # Якщо сума R+G+B найтемнішого пікселя МЕНША за це значення, відбілювання скасовується.
    # Діапазон: 0 (скасує тільки якщо знайдено ідеально чорний) до 765 (ніколи не скасує).
    # Значення близько 50-100 може бути корисним для ігнорування дуже темних артефактів.
    whitening_cancel_threshold_sum = 500    # Мін. сума RGB для скасування (0-765). 0 - всегда отменит, 765 - никогда.

    # === Видалення фону / Обрізка (Працює тільки якщо увімкнено) ===
    # Допуск білого: 0 = тільки чистий білий, 255 = будь-який колір. None = вимкнути.
    white_tolerance = 0                    # Допуск білого для видалення фону (0-255, None = вимкнено)

    # --- НАЛАШТУВАННЯ ОБРІЗКИ (якщо white_tolerance НЕ None) ---
    # Симетрія обрізки (використовується лише якщо white_tolerance задано)
    crop_absolute_symmetry = False          # Абсолютна симетрія від країв зображення (True/False)
    crop_axes_symmetry = False              # Симетрія по осях відносно центру вмісту (True/False, діє якщо absolute=False)
                                            # Якщо обидва False = звичайна обрізка по контенту.

    # === Додавання Полів (Після обрізки/видалення фону) ===
    # Умовне додавання полів: поля додаються тільки якщо периметр був білим ДО видалення фону/обрізки.
    # 0 або None = вимкнути перевірку периметра (поля додаватимуться завжди, якщо padding_percentage > 0)
    perimeter_check_margin_pixels = 1       # Ширина рамки для перевірки білого периметру (px)
    # Відсоток полів від БІЛЬШОЇ сторони зображення ПІСЛЯ обрізки/видалення фону.
    # 0 або None = вимкнено додавання полів.
    padding_percentage = 5                  # Відсоток полів (0.0 = вимкнено)

    # === Примусове Співвідношення Сторін (Після полів) ===
    # Встановлює точне співвідношення сторін, додаючи прозорі поля (для PNG) або поля кольору фону (для JPG).
    # None = вимкнено. Приклад: (1, 1) для квадрату, (16, 9) для пейзажу.
    force_aspect_ratio_tuple = None         # None або (ширина_пропорції, висота_пропорції)

    # === Обмеження Максимального Розміру (Після зміни співвідношення) ===
    # Зменшує зображення, якщо воно перевищує задані розміри, зберігаючи пропорції.
    # 0 або None = без обмеження для відповідної сторони.
    max_output_width = 1500                 # Макс. ширина (px)
    max_output_height = 1500                # Макс. висота (px)

    # === Фінальний Холст Точного Розміру (Після обмеження макс. розміру) ===
    # Вписує зображення в холст точно заданого розміру з центровкою.
    # 0 або None = вимкнено.
    final_exact_width = 0                   # Точна фінальна ширина (px)
    final_exact_height = 0                  # Точна фінальна висота (px)

    # === Формат Збереження, Фон та Якість ===
    output_save_format = 'jpg'              # Формат: 'jpg' або 'png'.
    # --- Налаштування для JPG ---
    # Колір фону використовується при конвертації з прозорості та для полів final_exact_width/height.
    jpg_background_color_tuple = (255, 255, 255) # Колір фону для JPG (R, G, B)
    jpeg_save_quality = 95                  # Якість JPG (1-100, рекомендується 90-98)
    # --- Налаштування для PNG (немає специфічних, крім прозорості) ---

    # --- Кінець Налаштувань Користувача ---


    # --- Перевірка та підготовка шляхів ---
    input_folder_path = os.path.abspath(input_folder_path)
    if not output_folder_path:
        output_folder_path = os.path.join(input_folder_path, "output_processed")
        print(f"* Папку результатів не вказано, буде використано: {output_folder_path}")
    else:
        output_folder_path = os.path.abspath(output_folder_path)

    if backup_folder_path:
         backup_folder_path = os.path.abspath(backup_folder_path)
         # Додаткова перевірка, щоб папка бекапу не була папкою вводу/виводу
         if backup_folder_path == input_folder_path:
              print("ПОПЕРЕДЖЕННЯ: Папка бекапу не може бути папкою джерела. Бекап вимкнено.")
              backup_folder_path = None
         elif backup_folder_path == output_folder_path:
              print("ПОПЕРЕДЖЕННЯ: Папка бекапу не може бути папкою результатів. Бекап вимкнено.")
              backup_folder_path = None
    else: # Якщо None або ""
        backup_folder_path = None # Гарантуємо None

    # --- Запуск Скрипта ---
    print("\n--- Початок роботи скрипту ---")
    if not os.path.isdir(input_folder_path):
         print(f"\n!! ПОМИЛКА: Вказана папка ДЖЕРЕЛА не існує або не є папкою: {input_folder_path}")
    else:
         # Передача всіх налаштувань у головну функцію обробки
         rename_and_convert_images(
             input_path=input_folder_path,
             output_path=output_folder_path,
             article_name=article if article else None, # Передаємо None, якщо пустий рядок
             delete_originals=delete_originals_after_processing,
             preresize_width=preresize_width if preresize_width and preresize_width > 0 else 0,
             preresize_height=preresize_height if preresize_height and preresize_height > 0 else 0,
             enable_whitening=enable_whitening,
             whitening_cancel_threshold=whitening_cancel_threshold_sum, # <<< ПЕРЕДАЧА НОВОГО ПАРАМЕТРА
             white_tolerance=white_tolerance if white_tolerance is not None and white_tolerance >= 0 else None, # Передаємо None якщо вимкнено
             perimeter_margin=perimeter_check_margin_pixels if perimeter_check_margin_pixels and perimeter_check_margin_pixels > 0 else 0,
             crop_symmetric_axes=crop_axes_symmetry,
             crop_symmetric_absolute=crop_absolute_symmetry,
             padding_percent=padding_percentage if padding_percentage and padding_percentage > 0 else 0,
             force_aspect_ratio=force_aspect_ratio_tuple,
             max_output_width=max_output_width if max_output_width and max_output_width > 0 else 0,
             max_output_height=max_output_height if max_output_height and max_output_height > 0 else 0,
             final_exact_width=final_exact_width if final_exact_width and final_exact_width > 0 else 0,
             final_exact_height=final_exact_height if final_exact_height and final_exact_height > 0 else 0,
             output_format=output_save_format,
             jpg_background_color=jpg_background_color_tuple,
             jpeg_quality=jpeg_save_quality,
             backup_folder_path=backup_folder_path,
         )
         print("\n--- Робота скрипту завершена ---")