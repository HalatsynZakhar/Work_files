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
         print("  - Поля: Розрахований відступ = 0 пікселів, поля не додаються.")
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
        return False # Якщо відступ 0, вважаємо, що перевірка не пройшла (поля не потрібні)

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
         margin_w = min(width // 2, margin) # Адаптуємо горизонтальний відступ
         margin_h = min(height // 2, margin) # Адаптуємо вертикальний відступ
         if margin_w == 0: margin_w = 1 # Треба хоч 1 піксель по ширині
         if margin_h == 0: margin_h = 1 # Треба хоч 1 піксель по висоті
    else:
         margin_w = margin
         margin_h = margin

    cutoff = 255 - tolerance

    # Перевірка верхніх рядків (0 до margin_h-1)
    for y in range(margin_h):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель зверху ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка нижніх рядків (height-margin_h до height-1)
    for y in range(height - margin_h, height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель знизу ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка лівих стовпців (0 до margin_w-1), уникаючи кутів, вже перевірених
    for x in range(margin_w):
        # Перевіряємо від margin_h до height-margin_h, щоб не чіпати кути двічі
        for y in range(margin_h, height - margin_h):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель зліва ({x},{y}): {r},{g},{b}")
                return False

    # Перевірка правих стовпців (width-margin_w до width-1), уникаючи кутів
    for x in range(width - margin_w, width):
        # Перевіряємо від margin_h до height-margin_h
        for y in range(margin_h, height - margin_h):
            r, g, b = pixels[x, y]
            if r < cutoff or g < cutoff or b < cutoff:
                print(f"  - Перевірка периметра: Знайдено не-білий піксель справа ({x},{y}): {r},{g},{b}")
                return False

    # Якщо всі перевірки пройшли
    print("  - Перевірка периметра: Весь периметр в межах відступу білий.")
    return True
# --- Кінець функцій обробки ---


def rename_and_convert_images(folder_path, article_name, white_tolerance, padding_percent, perimeter_margin):
    print(f"Обробка папки: {folder_path}")
    print(f"Артикул для перейменування: {article_name}")
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
    original_files_to_remove = [] # Список для файлів, які потрібно буде видалити

    for file in files:
        file_path = os.path.join(folder_path, file)
        print(f"\nОбробка файлу: {file}")
        try:
            with Image.open(file_path) as img_original:
                original_mode = img_original.mode
                original_size = img_original.size
                print(f"  - Початковий режим: {original_mode}, Розмір: {original_size}")

                # --- ІНТЕГРОВАНА ОБРОБКА З УМОВНИМИ ПОЛЯМИ ---

                # * ПЕРЕВІРКА ПЕРИМЕТРА (на оригінальному зображенні) *
                print(f"  - Крок 0: Перевірка периметра (відступ {perimeter_margin}px, допуск {white_tolerance})...")
                # Робимо копію перед перевіркою, щоб оригінал залишився недоторканим для подальшої обробки
                should_add_padding = check_perimeter_is_white(img_original.copy(), white_tolerance, perimeter_margin)

                # 1. Завжди конвертуємо в RGBA для видалення фону та обрізки
                print(f"  - Крок 1: Конвертація в RGBA...")
                img_rgba = img_original.convert("RGBA")

                # 2. Видалення білого фону
                print(f"  - Крок 2: Видалення білого фону (допуск {white_tolerance})...")
                img_no_bg = remove_white_background(img_rgba, white_tolerance)

                # 3. Обрізка прозорих країв
                print("  - Крок 3: Обрізка прозорих країв...")
                img_cropped = crop_transparent_border(img_no_bg)

                if img_cropped is None or not img_cropped.getbbox():
                    print("  ! Попередження: Зображення стало порожнім після видалення фону/обрізки. Пропуск.")
                    continue
                print(f"  - Розмір після обрізки: {img_cropped.size}")

                # 4. Додавання полів (Padding) - УМОВНО
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

                # 5. Конвертація в RGB з білим фоном
                print("  - Крок 5: Конвертація в RGB (заміна прозорості на білий)...")
                final_rgb_img = Image.new("RGB", img_processed_before_resize.size, (255, 255, 255))
                try:
                     if 'A' in img_processed_before_resize.getbands():
                          mask = img_processed_before_resize.split()[3]
                          final_rgb_img.paste(img_processed_before_resize, (0, 0), mask)
                     else:
                          final_rgb_img.paste(img_processed_before_resize, (0, 0))
                except IndexError:
                     print("  ! Помилка при отриманні альфа-каналу для paste. Спроба прямої конвертації.")
                     try:
                         final_rgb_img = img_processed_before_resize.convert("RGB")
                     except Exception as conv_err:
                          print(f"  !! Остаточна конвертація в RGB не вдалася: {conv_err}")
                          continue

                img = final_rgb_img
                print(f"  - Розмір перед масштабуванням: {img.size}")

                # 6. Зміна розміру до 1500x1500 з центровкою
                print("  - Крок 6: Масштабування до 1500x1500 з центровкою...")
                target_size = 1500
                if img.size != (target_size, target_size):
                    original_width, original_height = img.size

                    if original_width == 0 or original_height == 0:
                        print("  ! Попередження: Розмір зображення нульовий перед масштабуванням. Створення порожнього квадрата.")
                        img = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                    else:
                        ratio = min(target_size / original_width, target_size / original_height)
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)

                        if new_width > 0 and new_height > 0:
                            try:
                                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            except ValueError:
                                print(f"  ! Помилка при зміні розміру до {new_width}x{new_height}. Можливо, розмір занадто малий.")
                                resized_img = img
                                new_width, new_height = img.size
                        else:
                             print(f"  ! Попередження: Новий розрахований розмір ({new_width}x{new_height}) некоректний. Пропуск масштабування.")
                             resized_img = img
                             new_width, new_height = img.size

                        canvas = Image.new('RGB', (target_size, target_size), (255, 255, 255))
                        x = (target_size - new_width) // 2
                        y = (target_size - new_height) // 2
                        canvas.paste(resized_img, (x, y))
                        img = canvas
                else:
                     print("  - Зображення вже має розмір 1500x1500.")

                # 7. Збереження як JPG (з новим іменем, але без нумерації поки що)
                # Важливо: Ми зберігаємо з оригінальною назвою + .jpg,
                # щоб потім коректно перейменувати *всі* jpg файли
                base_name = os.path.splitext(file)[0]
                new_temp_filename = f"{base_name}.jpg" # Тимчасове ім'я буде як оригінальне + .jpg
                new_temp_path = os.path.join(folder_path, new_temp_filename)

                print(f"  - Крок 7: Збереження як тимчасовий JPG: {new_temp_filename}...")
                img.save(new_temp_path, "JPEG", quality=95, optimize=True)
                processed_files_count += 1

                # Додаємо оригінальний файл у список на видалення,
                # *якщо* це не той самий JPG файл, який ми щойно створили/перезаписали
                if file_path.lower() != new_temp_path.lower():
                    original_files_to_remove.append(file_path)
                elif file_path.lower() == new_temp_path.lower():
                    print(f"  - Оригінальний файл {file} був JPG і був перезаписаний.")


        except Exception as e:
            print(f"!!! Помилка обробки файлу {file}: {e}")
            traceback.print_exc() # Друкуємо детальний traceback помилки
            # Якщо помилка була з файлом, який мав бути видалений, прибираємо його зі списку
            if file_path in original_files_to_remove:
                try:
                    original_files_to_remove.remove(file_path)
                except ValueError:
                    pass # На випадок, якщо його там чомусь немає
            continue # Переходимо до наступного файлу

    print(f"\nПопередня обробка завершена. Успішно оброблено/конвертовано файлів: {processed_files_count}")

    # Видалення оригінальних файлів (які не були JPG з тим самим іменем)
    if original_files_to_remove:
        print(f"\nВидалення {len(original_files_to_remove)} оригінальних файлів...")
        for file_to_remove in original_files_to_remove:
            try:
                os.remove(file_to_remove)
                print(f"  - Видалено: {os.path.basename(file_to_remove)}")
            except Exception as remove_error:
                print(f"  ! Помилка при видаленні {os.path.basename(file_to_remove)}: {remove_error}")

    print("\n---")
    print("Перейменування файлів...")

    # Оновлюємо список файлів ТІЛЬКИ JPG після всіх перетворень
    try:
        current_files = natsorted([f for f in os.listdir(folder_path) if f.lower().endswith('.jpg') and os.path.isfile(os.path.join(folder_path, f))])
        print(f"Файлів для перейменування (JPG): {len(current_files)}")
    except Exception as e:
         print(f"Помилка при отриманні списку JPG файлів для перейменування: {e}")
         return # Немає сенсу продовжувати без списку файлів

    if not current_files:
        print("Папка не містить JPG файлів після обробки. Перейменування неможливе.")
        return

    # Логіка перейменування залишається такою самою, вона працює з фінальними JPG
    exact_match_filename = f"{article_name}.jpg"
    exact_match_temp_name = None
    files_to_rename_temp = [] # Список тимчасових шляхів файлів для нумерованого перейменування
    temp_rename_map = {} # Відстеження оригінал -> тимчасовий

    print("  - Створення тимчасових імен (захист від конфліктів)...")
    temp_counter = 0
    rename_errors = 0
    for filename in current_files:
        original_path = os.path.join(folder_path, filename)
        # Створюємо гарантовано унікальне тимчасове ім'я
        temp_filename = f"__temp_{temp_counter}_{os.path.basename(filename)}"
        temp_path = os.path.join(folder_path, temp_filename)
        try:
            os.rename(original_path, temp_path)
            temp_rename_map[original_path] = temp_path # Зберігаємо відповідність
            # Перевіряємо, чи це був файл, який має стати {article_name}.jpg
            # Порівнюємо ім'я *до* додавання __temp_
            if filename.lower() == exact_match_filename.lower():
                exact_match_temp_name = temp_path
                print(f"    - {filename} -> {temp_filename} (буде {exact_match_filename})")
            else:
                files_to_rename_temp.append(temp_path)
                print(f"    - {filename} -> {temp_filename} (буде нумерований)")
            temp_counter += 1
        except Exception as rename_error:
            print(f"  ! Помилка перейменування '{filename}' у тимчасове ім'я: {rename_error}")
            rename_errors += 1
            # Якщо не вдалося перейменувати, файл залишається зі старим іменем,
            # і ми не можемо його включити в подальше перейменування

    if rename_errors > 0:
        print(f"  ! Були помилки ({rename_errors}) при створенні тимчасових імен. Деякі файли можуть бути не перейменовані.")

    print("  - Призначення фінальних імен...")
    final_rename_counter = 1

    # 1. Перейменовуємо файл, що має стати {article_name}.jpg (якщо він був знайдений)
    if exact_match_temp_name:
        final_exact_path = os.path.join(folder_path, exact_match_filename)
        try:
            # Перевірка, чи файл з таким іменем вже не існує (малоймовірно, але можливо)
            if os.path.exists(final_exact_path):
                 print(f"  ! Попередження: Файл {exact_match_filename} вже існує. Неможливо перейменувати {os.path.basename(exact_match_temp_name)}.")
                 # Додаємо цей тимчасовий файл до списку для нумерації
                 files_to_rename_temp.append(exact_match_temp_name)
            else:
                 os.rename(exact_match_temp_name, final_exact_path)
                 print(f"    - '{os.path.basename(exact_match_temp_name)}' -> '{exact_match_filename}'")
        except Exception as rename_error:
            print(f"  ! Помилка фінального перейменування для {exact_match_filename} з {os.path.basename(exact_match_temp_name)}: {rename_error}")
            # Якщо помилка, додаємо назад у список для нумерації
            files_to_rename_temp.append(exact_match_temp_name)

    # 2. Перейменовуємо решту файлів з нумерацією {article_name}_N.jpg
    # Сортуємо список тимчасових файлів, щоб забезпечити стабільний порядок нумерації
    # Використовуємо natsort для природного сортування імен, з яких вони були створені
    files_to_rename_temp_sorted = natsorted(files_to_rename_temp, key=lambda x: os.path.basename(x).split('_', 2)[-1]) # Сортуємо за оригінальним іменем всередині __temp_..._

    for temp_path in files_to_rename_temp_sorted:
        # Генеруємо нове нумероване ім'я
        final_numbered_filename = f"{article_name}_{final_rename_counter}.jpg"
        final_numbered_path = os.path.join(folder_path, final_numbered_filename)

        # Перевірка на існування файлу перед перейменуванням
        if os.path.exists(final_numbered_path):
             print(f"  ! Попередження: Файл {final_numbered_filename} вже існує. Пропуск перейменування {os.path.basename(temp_path)}.")
             # В теорії, цього не мало б статися через тимчасове перейменування,
             # але перевірка не завадить. Можна додати логіку пошуку наступного вільного номера.
             # Поки що просто пропускаємо.
             continue

        try:
            os.rename(temp_path, final_numbered_path)
            print(f"    - '{os.path.basename(temp_path)}' -> '{final_numbered_filename}'")
            final_rename_counter += 1
        except Exception as rename_error:
             print(f"  ! Помилка фінального перейменування для {os.path.basename(temp_path)} -> {final_numbered_filename}: {rename_error}")

    # Перевірка, чи залишилися тимчасові файли (на випадок помилок)
    remaining_temp_files = [f for f in os.listdir(folder_path) if f.startswith("__temp_") and os.path.isfile(os.path.join(folder_path, f))]
    if remaining_temp_files:
        print("\n  ! Увага: Залишилися тимчасові файли після перейменування (можливо через помилки):")
        for f_temp in remaining_temp_files:
            print(f"    - {f_temp}")

    print("Перейменування завершено.")


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
    folder_to_process = r"C:\Users\zakhar\Downloads\test2"  # !!! ВАШ шлях до папки
    article = "TG1018"               # !!! ВАШ артикул
    tolerance_for_white = 0              # !!! Допуск для білого (0-255), використовується і для фону, і для перевірки периметра
    padding_percentage = 5                # !!! Відсоток полів (наприклад, 5 для 5%), застосовується ТІЛЬКИ якщо периметр білий
    perimeter_check_margin_pixels = 1     # !!! ВІДСТУП в пікселях від краю для перевірки на білий колір. Якщо 0, поля НЕ додаються автоматично.
    # --- ---

    if not os.path.isdir(folder_to_process):
         print(f"Помилка: Вказана папка не існує або недоступна: {folder_to_process}")
    else:
         rename_and_convert_images(
             folder_to_process,
             article,
             tolerance_for_white,
             padding_percentage,
             perimeter_check_margin_pixels # Передаємо новий параметр
         )
         print("\nРобота скрипту завершена.")