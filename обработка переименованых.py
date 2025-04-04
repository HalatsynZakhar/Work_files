import os
import math
from PIL import Image, ImageChops
from natsort import natsorted
import traceback # Для детальних помилок

# --- Константи ---
# Допуск для білого, відсоток полів та відступ для перевірки периметра
# визначаються внизу, у налаштуваннях
# --- ---

# --- Функції обробки зображення ---
def remove_white_background(img, tolerance):
    """Видаляє майже білий фон з зображення RGBA."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    datas = img.getdata()
    newData = []
    cutoff = 255 - tolerance
    for item in datas:
        # Перевіряємо перші три канали (RGB)
        if item[0] >= cutoff and item[1] >= cutoff and item[2] >= cutoff:
            # Якщо піксель білий (з допуском), робимо його прозорим
            newData.append((item[0], item[1], item[2], 0))
        else:
            # Інакше зберігаємо піксель як є
            newData.append(item)
    img.putdata(newData)
    return img

def crop_transparent_border(img):
    """Обрізає прозорий простір навколо зображення (потребує RGBA)."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    try:
        # Використовуємо альфа-канал для визначення меж об'єкта
        alpha = img.split()[-1]
        bbox = alpha.getbbox() # Знаходить прямокутник, що містить непрозорі пікселі
    except (ValueError, IndexError):
        bbox = None # Може статися, якщо альфа-каналу немає або він порожній
    if bbox:
        return img.crop(bbox) # Обрізаємо зображення за знайденими межами
    else:
        # Якщо межі не знайдено (зображення повністю прозоре або помилка),
        # повертаємо зображення як є
        return img

def add_padding(img, percent):
    """Додає прозорі поля навколо RGBA зображення."""
    if img is None:
        print("  ! Помилка: Немає зображення для додавання полів.")
        return None
    if percent <= 0:
        return img # Поля нульові або від'ємні - нічого не робимо

    width, height = img.size
    if width == 0 or height == 0:
        print("  ! Попередження: Розмір зображення нульовий, неможливо додати поля.")
        return img # Немає сенсу додавати поля до порожнього зображення

    # Визначаємо довший бік для розрахунку відступу
    longest_side = max(width, height)
    # Розраховуємо відступ у пікселях
    padding_pixels = int(longest_side * (percent / 100.0))

    # Якщо відступ виявився нульовим (наприклад, через малий розмір і малий відсоток)
    if padding_pixels == 0:
        return img

    new_width = width + 2 * padding_pixels
    new_height = height + 2 * padding_pixels

    # Створюємо нове прозоре зображення більшого розміру
    padded_img = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
    # Визначаємо координати для вставки вихідного зображення
    paste_x = padding_pixels
    paste_y = padding_pixels
    # Вставляємо вихідне зображення в центр нового (використовуючи його маску)
    padded_img.paste(img, (paste_x, paste_y), img if img.mode == 'RGBA' else None)
    return padded_img

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
        print("  - Перевірка периметра: Відступ <= 0, перевірка не потрібна.")
        return False # Якщо відступ 0, вважаємо, що перевірка не пройшла

    try:
        # Конвертуємо до RGB для спрощення перевірки пікселів
        # Робимо копію, щоб не змінити оригінал для наступних кроків
        img_rgb = img.convert('RGB')
        width, height = img_rgb.size
        pixels = img_rgb.load() # Швидший доступ до пікселів
    except Exception as e:
        print(f"  ! Помилка конвертації в RGB для перевірки периметра: {e}")
        return False # Не можемо перевірити, вважаємо, що не білий

    # Перевіряємо, чи зображення достатньо велике для заданого відступу
    if width < margin * 2 or height < margin * 2:
        # Якщо зображення занадто мале для повного периметру з відступом,
        # перевіряємо всі пікселі, які є.
         print(f"  - Перевірка периметра: Зображення ({width}x{height}) менше за подвійний відступ ({margin*2}). Перевірка всього зображення.")
         margin = min(width // 2, height // 2, margin) # Адаптуємо відступ, якщо він завеликий
         if margin == 0: margin = 1 # Треба хоч 1 піксель перевірити

    cutoff = 255 - tolerance

    # Перевірка верхніх рядків (0 до margin-1)
    for y in range(margin):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель зверху ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка нижніх рядків (height-margin до height-1)
    for y in range(height - margin, height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель знизу ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка лівих стовпців (0 до margin-1), уникаючи кутів, вже перевірених
    for x in range(margin):
        for y in range(margin, height - margin):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель зліва ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка правих стовпців (width-margin до width-1), уникаючи кутів
    for x in range(width - margin, width):
        for y in range(margin, height - margin):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель справа ({x},{y}): {r},{g},{b}")
                return False

    # Якщо всі перевірки пройшли
    print("  - Перевірка периметра: Весь периметр в межах відступу білий.")
    return True
# --- Кінець функцій обробки ---


def process_images_without_rename(folder_path, white_tolerance, padding_percent, perimeter_margin):
    print(f"Обробка папки: {folder_path}")
    print(f"Допуск для білого фону: {white_tolerance}")
    print(f"Відсоток полів (якщо додаються): {padding_percent}%")
    print(f"Відступ для перевірки периметра: {perimeter_margin} пікселів")
    print("-" * 20)

    try:
        files = natsorted([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
        print(f"Знайдено файлів для обробки: {len(files)}")
    except FileNotFoundError:
        print(f"Помилка: Папку не знайдено - {folder_path}")
        return
    except Exception as e:
        print(f"Помилка при читанні вмісту папки {folder_path}: {e}")
        return

    processed_files_count = 0
    for file in files:
        file_path = os.path.join(folder_path, file)
        print(f"\nОбробка файлу: {file}")
        try:
            with Image.open(file_path) as img_original:
                original_mode = img_original.mode
                original_size = img_original.size
                print(f"  - Початковий режим: {original_mode}, Розмір: {original_size}")

                # Визначаємо нове ім'я файлу (завжди .jpg)
                base_name = os.path.splitext(file)[0]
                new_filename = f"{base_name}.jpg"
                new_file_path = os.path.join(folder_path, new_filename)

                # --- Інтегрована обробка ---

                # * ПЕРЕВІРКА ПЕРИМЕТРА (на оригінальному зображенні) *
                print(f"  - Крок 0: Перевірка периметра (відступ {perimeter_margin}px, допуск {white_tolerance})...")
                # Робимо копію перед перевіркою, щоб оригінал залишився недоторканим для подальшої обробки
                should_add_padding = check_perimeter_is_white(img_original.copy(), white_tolerance, perimeter_margin)

                # 0. Завжди конвертуємо в RGBA для видалення фону та обрізки
                print(f"  - Крок 1: Конвертація в RGBA...")
                img_rgba = img_original.convert("RGBA")

                # 1. Видалення білого фону
                print(f"  - Крок 2: Видалення білого фону (допуск {white_tolerance})...")
                img_no_bg = remove_white_background(img_rgba, white_tolerance)

                # 2. Обрізка прозорих країв
                print("  - Крок 3: Обрізка прозорих країв...")
                img_cropped = crop_transparent_border(img_no_bg)

                if img_cropped is None or not img_cropped.getbbox():
                    print("  ! Попередження: Зображення стало порожнім після видалення фону/обрізки. Пропуск.")
                    continue
                print(f"  - Розмір після обрізки: {img_cropped.size}")

                # 3. Додавання полів (Padding) - УМОВНО
                img_processed_before_resize = None # Змінна для результату цього кроку
                if should_add_padding and padding_percent > 0:
                    print(f"  - Крок 4: Додавання полів ({padding_percent}%)... (Периметр був білим)")
                    img_padded = add_padding(img_cropped, padding_percent)
                    if img_padded is None:
                         print("  ! Помилка при додаванні полів. Пропуск.")
                         continue
                    print(f"  - Розмір після додавання полів: {img_padded.size}")
                    img_processed_before_resize = img_padded
                else:
                    if not should_add_padding:
                         print(f"  - Крок 4: Поля не додаються (периметр не був білим або відступ 0).")
                    elif padding_percent <= 0:
                         print(f"  - Крок 4: Поля не додаються (відсоток полів <= 0).")
                    img_processed_before_resize = img_cropped # Використовуємо обрізане зображення без полів

                # 4. Конвертація в RGB з білим фоном
                print("  - Крок 5: Конвертація в RGB (заміна прозорості на білий)...")
                # Створюємо біле тло потрібного розміру
                final_rgb_img = Image.new("RGB", img_processed_before_resize.size, (255, 255, 255))
                try:
                     # Перевіряємо, чи є альфа-канал для використання як маски
                     if 'A' in img_processed_before_resize.getbands():
                          mask = img_processed_before_resize.split()[3]
                          final_rgb_img.paste(img_processed_before_resize, (0, 0), mask)
                     else:
                          # Якщо альфа-каналу немає (малоймовірно після попередніх кроків, але можливо)
                          final_rgb_img.paste(img_processed_before_resize, (0, 0))
                except IndexError:
                     # Аварійний варіант, якщо .split() не спрацював
                     print("  ! Помилка при отриманні альфа-каналу для paste. Спроба прямої конвертації.")
                     try:
                         final_rgb_img = img_processed_before_resize.convert("RGB")
                     except Exception as conv_err:
                          print(f"  !! Остаточна конвертація в RGB не вдалася: {conv_err}")
                          continue # Пропускаємо цей файл

                img = final_rgb_img # img тепер RGB з полями (якщо були додані) або без них
                print(f"  - Розмір перед масштабуванням: {img.size}")

                # 5. Зміна розміру до 1500x1500 з центровкою
                print("  - Крок 6: Масштабування до 1500x1500 з центровкою...")
                target_size = 1500
                if img.size != (target_size, target_size):
                    original_width, original_height = img.size

                    # Перевірка на нульовий розмір перед розрахунком
                    if original_width == 0 or original_height == 0:
                        print("  ! Попередження: Розмір зображення нульовий перед масштабуванням. Спроба створити порожній квадрат.")
                        # Створюємо порожній білий квадрат, оскільки зображення порожнє
                        img = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                    else:
                        # Розраховуємо коефіцієнт масштабування
                        ratio = min(target_size / original_width, target_size / original_height)
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)

                        # Перевірка, чи розраховані розміри коректні
                        if new_width > 0 and new_height > 0:
                            try:
                                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            except ValueError:
                                print(f"  ! Помилка при зміні розміру до {new_width}x{new_height}. Можливо, розмір занадто малий.")
                                resized_img = img # Пробуємо продовжити з поточним
                                new_width, new_height = img.size # Оновлюємо розміри
                        else:
                             print(f"  ! Попередження: Новий розрахований розмір ({new_width}x{new_height}) некоректний. Пропуск масштабування.")
                             resized_img = img # Залишаємо як є
                             new_width, new_height = img.size # Оновлюємо розміри

                        # Створюємо білий квадрат 1500x1500
                        canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                        # Рахуємо координати для центрування
                        x = (target_size - new_width) // 2
                        y = (target_size - new_height) // 2
                        # Вставляємо відмасштабоване зображення на білий квадрат
                        canvas.paste(resized_img, (x, y))
                        img = canvas # Тепер img - це центроване зображення 1500x1500
                else:
                     print("  - Зображення вже має розмір 1500x1500.")

                # 6. Збереження як JPG
                print(f"  - Крок 7: Збереження як {new_filename}...")
                img.save(new_file_path, "JPEG", quality=95, optimize=True)
                processed_files_count += 1

                # 7. Видалення вихідного файлу, якщо він не був JPG з тим самим іменем
                if file_path.lower() != new_file_path.lower() and not file.lower().endswith('.jpg'):
                    try:
                        print(f"  - Видалення оригінального файлу: {file}")
                        os.remove(file_path)
                    except Exception as remove_error:
                        print(f"  ! Помилка при видаленні {file}: {remove_error}")
                elif file_path.lower() == new_file_path.lower():
                    print("  - Оригінальний файл був JPG і був перезаписаний.")
                elif file_path.lower() != new_file_path.lower() and file.lower().endswith('.jpg'):
                     # Випадок, коли ім'я файлу (без розширення) було таке саме,
                     # але оригінал був JPG (наприклад, інший регістр).
                     # Перезапис вже відбувся.
                     print(f"  - Оригінальний файл {file} перезаписаний як {new_filename}.")


        except Exception as e:
            print(f"!!! Помилка обробки файлу {file}: {e}")
            traceback.print_exc() # Друкуємо детальний traceback помилки
            continue # Переходимо до наступного файлу

    print(f"\nОбробка завершена. Успішно оброблено файлів: {processed_files_count}")

# --- Приклад використання ---
if __name__ == "__main__":
    try:
        import PIL
    except ImportError:
        print("Помилка: Бібліотека Pillow не знайдена.\nВстановіть її: pip install Pillow")
        exit()
    try:
        import natsort
    except ImportError:
        print("Помилка: Бібліотека natsort не знайдена.\nВстановіть її: pip install natsort")
        exit()

    # --- Налаштування користувача ---
    folder_to_process = r"C:\Users\zakhar\Downloads\test2" # !!! ВАШ шлях до папки
    tolerance_for_white = 0              # !!! Допуск для білого (0-255), використовується і для фону, і для перевірки периметра
    padding_percentage = 5                # !!! Відсоток полів (наприклад, 5 для 5%), застосовується ТІЛЬКИ якщо периметр білий
    perimeter_check_margin_pixels = 1     # !!! ВІДСТУП в пікселях від краю для перевірки на білий колір. Якщо 0, поля НЕ додаються автоматично.
    # --- ---

    if not os.path.isdir(folder_to_process):
         print(f"Помилка: Вказана папка не існує або недоступна: {folder_to_process}")
    else:
         process_images_without_rename(
             folder_to_process,
             tolerance_for_white,
             padding_percentage,
             perimeter_check_margin_pixels # Передаємо новий параметр
         )
         print("\nРобота скрипту завершена.")