import os
import re

# Поддерживаемые расширения изображений
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

def extract_numeric_article(filename):
    """Извлекает первую найденную последовательность цифр из имени файла."""
    match = re.search(r'\d+', filename)
    if match:
        return int(match.group())
    return None

def get_articles_from_folder(folder_path):
    """Сканирует папку и возвращает множество числовых артикулов из названий изображений."""
    articles = set()
    for root, _, files in os.walk(folder_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                article = extract_numeric_article(file)
                if article is not None:
                    articles.add(article)
    return articles

def main():
    # Укажите пути к вашим папкам здесь ↓↓↓
    folder1 = r"\\10.10.100.2\Foto\BABY TEAM"
    folder2 = r"\\10.10.100.2\Foto\BRUDER"
    # Указывать пути выше ↑↑↑

    print(f"Анализируем папку: {folder1}")
    set1 = get_articles_from_folder(folder1)

    print(f"Анализируем папку: {folder2}")
    set2 = get_articles_from_folder(folder2)

    # Поиск пересечений
    matches = set1 & set2

    if matches:
        print("\nНайдены совпадающие артикулы:")
        for article in sorted(matches):
            print(article)
    else:
        print("\nСовпадающих артикулов не найдено.")

if __name__ == '__main__':
    main()