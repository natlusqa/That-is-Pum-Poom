#!/usr/bin/env python3
"""
Скрипт для проверки детекции лиц: загружает модель InsightFace и тестирует на изображении.
Запуск:
  python test_face_detection.py path/to/photo.jpg
  python test_face_detection.py    # использует встроенный тест (камера или пример)
"""
import sys
import os

# Добавляем backend в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
from face_core import face_engine


def test_from_file(image_path: str) -> None:
    """Проверка детекции по файлу изображения."""
    if not os.path.isfile(image_path):
        print(f"Файл не найден: {image_path}")
        return

    img = cv2.imread(image_path)
    if img is None:
        print(f"Не удалось прочитать изображение: {image_path}")
        return

    print(f"Изображение: {image_path}, размер {img.shape[1]}x{img.shape[0]}")
    print("Загрузка модели InsightFace...")
    face_engine.load()
    print("Детекция лиц...")

    faces = face_engine.get_all_faces(img)
    n = len(faces)

    if n == 0:
        print("Лица не обнаружены.")
        print("Проверьте: лицо хорошо освещено, смотрит в камеру, размер лица не слишком маленький.")
        return

    print(f"Найдено лиц: {n}")
    for i, f in enumerate(faces):
        bbox = f["bbox"]
        score = f.get("det_score", 0)
        print(f"  Лицо {i + 1}: bbox={bbox}, уверенность (det_score)={score:.3f}")

    # Опционально: сохранить изображение с рамками
    out_path = image_path.rsplit(".", 1)[0] + "_detected.jpg"
    img_out = img.copy()
    for f in faces:
        x1, y1, x2, y2 = f["bbox"]
        cv2.rectangle(img_out, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.imwrite(out_path, img_out)
    print(f"Результат с рамками сохранён: {out_path}")


def test_from_camera(skip_frames: int = 5) -> None:
    """Краткая проверка с веб-камеры (несколько кадров)."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Не удалось открыть камеру (индекс 0).")
        return

    print("Загрузка модели...")
    face_engine.load()
    print("Камера: смотрите в камеру. Обработка нескольких кадров...")

    for _ in range(skip_frames):
        cap.read()  # прогрев

    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("Не удалось прочитать кадр.")
        return

    faces = face_engine.get_all_faces(frame)
    n = len(faces)
    print(f"Найдено лиц на кадре: {n}")
    for i, f in enumerate(faces):
        print(f"  Лицо {i + 1}: bbox={f['bbox']}, det_score={f.get('det_score', 0):.3f}")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        test_from_file(sys.argv[1])
    else:
        print("Путь к фото не указан — проверка с веб-камеры (один кадр).")
        print("Чтобы проверить по файлу: python test_face_detection.py путь/к/фото.jpg\n")
        test_from_camera()
