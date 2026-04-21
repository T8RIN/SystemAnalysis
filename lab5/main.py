from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
VIDEO_SUFFIXES = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm", ".wmv"}


@dataclass(frozen=True)
class RuntimeDependencies:
    cv2: Any
    np: Any
    yolo_cls: Any


@dataclass(frozen=True)
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_name: str


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_runtime_dependencies() -> RuntimeDependencies:
    missing: List[str] = []
    os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".ultralytics"))

    try:
        import cv2  # type: ignore
    except ModuleNotFoundError:
        cv2 = None
        missing.append("opencv-python")

    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError:
        np = None
        missing.append("numpy")

    try:
        from ultralytics import YOLO  # type: ignore
    except ModuleNotFoundError:
        YOLO = None
        missing.append("ultralytics")

    if missing:
        package_list = ", ".join(missing)
        raise RuntimeError(
            "Не установлены зависимости: "
            f"{package_list}. Создайте окружение на Python 3.11 и выполните:\n"
            "python3.11 -m venv .venv\n"
            "./.venv/bin/python -m pip install -r requirements.txt"
        )

    return RuntimeDependencies(cv2=cv2, np=np, yolo_cls=YOLO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YOLO11: обнаружение людей или лиц на изображении, видео и с веб-камеры."
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--source",
        help="Путь к изображению или видеофайлу.",
    )
    source_group.add_argument(
        "--camera",
        type=int,
        help="Индекс веб-камеры. Если ничего не передано, используется камера 0.",
    )
    parser.add_argument(
        "--model",
        default="yolo11n.pt",
        help="Имя предобученной модели или путь к файлу весов. По умолчанию: yolo11n.pt",
    )
    parser.add_argument(
        "--target-class",
        default="person",
        help="Имя класса, который нужно оставить после фильтрации. По умолчанию: person",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Порог уверенности модели от 0 до 1. По умолчанию: 0.25",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Размер входного изображения для модели. По умолчанию: 640",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Устройство для инференса, например cpu, mps, cuda:0. По умолчанию выбирается автоматически.",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const=str(OUTPUT_DIR),
        default=None,
        help="Сохранить результат. Можно указать файл или директорию. Если путь не указан, используется outputs/.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Не открывать окно OpenCV, только выполнить обработку и при необходимости сохранить результат.",
    )
    parser.add_argument(
        "--line-width",
        type=int,
        default=2,
        help="Толщина рамки. По умолчанию: 2",
    )
    parser.add_argument(
        "--font-scale",
        type=float,
        default=0.7,
        help="Масштаб шрифта для подписей. По умолчанию: 0.7",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Ограничить количество кадров для отладки.",
    )
    parser.add_argument(
        "--list-classes",
        action="store_true",
        help="Показать доступные классы модели и завершить работу.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not 0.0 <= args.conf <= 1.0:
        raise ValueError("Аргумент --conf должен находиться в диапазоне от 0 до 1.")

    if args.imgsz <= 0:
        raise ValueError("Аргумент --imgsz должен быть положительным целым числом.")

    if args.line_width <= 0:
        raise ValueError("Аргумент --line-width должен быть положительным целым числом.")

    if args.font_scale <= 0:
        raise ValueError("Аргумент --font-scale должен быть положительным числом.")

    if args.max_frames is not None and args.max_frames <= 0:
        raise ValueError("Аргумент --max-frames должен быть положительным целым числом.")


def detect_source_kind(args: argparse.Namespace) -> str:
    if args.camera is not None or args.source is None:
        return "stream"

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"Файл не найден: {source_path}")

    if source_path.suffix.lower() in IMAGE_SUFFIXES:
        return "image"
    return "stream"


def normalize_model_names(raw_names: Any) -> Dict[int, str]:
    if isinstance(raw_names, dict):
        return {int(class_id): str(class_name) for class_id, class_name in raw_names.items()}
    if isinstance(raw_names, list):
        return {index: str(class_name) for index, class_name in enumerate(raw_names)}
    raise TypeError("Не удалось прочитать список классов модели.")


def resolve_target_class(model_names: Dict[int, str], target_class: str) -> Tuple[int, str]:
    target_normalized = target_class.strip().casefold()
    for class_id, class_name in model_names.items():
        if class_name.casefold() == target_normalized:
            return class_id, class_name

    available_classes = ", ".join(model_names.values())
    raise ValueError(
        f"Класс '{target_class}' отсутствует в выбранной модели. Доступные классы: {available_classes}"
    )


def default_output_filename(source_kind: str, source_value: str) -> str:
    suffix = ".jpg" if source_kind == "image" else ".mp4"
    stem = Path(source_value).stem if source_value else "camera_0"
    if not stem:
        stem = "result"
    return f"{stem}_annotated{suffix}"


def resolve_output_path(
    save_argument: Optional[str],
    source_kind: str,
    source_value: str,
) -> Optional[Path]:
    if save_argument is None:
        return None

    ensure_output_dir()
    candidate = Path(save_argument)

    if candidate.is_dir() or candidate.suffix == "":
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / default_output_filename(source_kind, source_value)

    candidate.parent.mkdir(parents=True, exist_ok=True)
    if source_kind == "stream" and candidate.suffix.lower() == "":
        candidate = candidate.with_suffix(".mp4")
    if source_kind == "image" and candidate.suffix.lower() == "":
        candidate = candidate.with_suffix(".jpg")
    return candidate


def load_model(runtime: RuntimeDependencies, model_name: str) -> Any:
    try:
        return runtime.yolo_cls(model_name)
    except Exception as exc:
        raise RuntimeError(
            f"Не удалось загрузить модель '{model_name}'. "
            "Если передано имя весов, убедитесь, что модель доступна локально или может быть скачана."
        ) from exc


def run_prediction(
    model: Any,
    frame: Any,
    conf: float,
    imgsz: int,
    device: Optional[str],
) -> Any:
    predict_kwargs: Dict[str, Any] = {
        "source": frame,
        "conf": conf,
        "imgsz": imgsz,
        "verbose": False,
    }
    if device:
        predict_kwargs["device"] = device
    return model.predict(**predict_kwargs)


def extract_detections(
    result: Any,
    target_class_id: int,
    target_class_name: str,
    confidence_threshold: float,
) -> List[Detection]:
    detections: List[Detection] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections

    for box in boxes:
        class_tensor = getattr(box, "cls", None)
        confidence_tensor = getattr(box, "conf", None)
        coords_tensor = getattr(box, "xyxy", None)
        if class_tensor is None or confidence_tensor is None or coords_tensor is None:
            continue

        class_id = int(class_tensor[0].item())
        confidence = float(confidence_tensor[0].item())
        if class_id != target_class_id or confidence < confidence_threshold:
            continue

        coordinates = coords_tensor[0].tolist()
        x1, y1, x2, y2 = [int(round(value)) for value in coordinates]
        detections.append(
            Detection(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=confidence,
                class_name=target_class_name,
            )
        )
    return detections


def draw_text_background(
    cv2: Any,
    image: Any,
    text: str,
    origin: Tuple[int, int],
    *,
    font_scale: float,
    text_color: Tuple[int, int, int],
    background_color: Tuple[int, int, int],
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 2 if font_scale >= 0.75 else 1
    text_size, baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = origin
    padding = 6

    top_left = (x - padding, y - text_size[1] - baseline - padding)
    bottom_right = (x + text_size[0] + padding, y + padding)
    cv2.rectangle(image, top_left, bottom_right, background_color, thickness=-1)
    cv2.putText(image, text, (x, y - 2), font, font_scale, text_color, thickness, cv2.LINE_AA)


def annotate_frame(
    cv2: Any,
    frame: Any,
    detections: List[Detection],
    target_class_name: str,
    line_width: int,
    font_scale: float,
) -> Any:
    annotated = frame.copy()
    box_color = (0, 200, 0)
    text_color = (10, 10, 10)
    header_background = (30, 220, 30)

    for detection in detections:
        cv2.rectangle(
            annotated,
            (detection.x1, detection.y1),
            (detection.x2, detection.y2),
            box_color,
            thickness=line_width,
        )

        label = f"{detection.class_name} {detection.confidence:.2f}"
        label_y = max(detection.y1, 24)
        draw_text_background(
            cv2,
            annotated,
            label,
            (detection.x1 + 4, label_y),
            font_scale=max(0.55, font_scale),
            text_color=text_color,
            background_color=box_color,
        )

    summary_text = f"{target_class_name}: {len(detections)}"
    draw_text_background(
        cv2,
        annotated,
        summary_text,
        (16, 32),
        font_scale=max(0.8, font_scale + 0.15),
        text_color=text_color,
        background_color=header_background,
    )
    return annotated


def show_image_window(cv2: Any, title: str, image: Any) -> None:
    cv2.imshow(title, image)
    while True:
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27, 13, 32):
            break
    cv2.destroyAllWindows()


def create_video_writer(cv2: Any, output_path: Path, fps: float, frame_size: Tuple[int, int]) -> Any:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, frame_size)
    if not writer.isOpened():
        raise RuntimeError(f"Не удалось открыть файл для записи видео: {output_path}")
    return writer


def open_capture(cv2: Any, args: argparse.Namespace) -> Any:
    source: Any = args.camera if args.camera is not None else args.source
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Не удалось открыть источник данных: {source}")
    return capture


def process_image(
    runtime: RuntimeDependencies,
    model: Any,
    args: argparse.Namespace,
    target_class_id: int,
    target_class_name: str,
    output_path: Optional[Path],
) -> int:
    assert args.source is not None

    image = runtime.cv2.imread(str(Path(args.source)))
    if image is None:
        raise RuntimeError(f"Не удалось загрузить изображение: {args.source}")

    results = run_prediction(model, image, args.conf, args.imgsz, args.device)
    detections = extract_detections(results[0], target_class_id, target_class_name, args.conf)
    annotated = annotate_frame(
        runtime.cv2,
        image,
        detections,
        target_class_name,
        args.line_width,
        args.font_scale,
    )

    print(f"Найдено объектов класса '{target_class_name}': {len(detections)}")

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not runtime.cv2.imwrite(str(output_path), annotated):
            raise RuntimeError(f"Не удалось сохранить изображение: {output_path}")
        print(f"Размеченное изображение сохранено: {output_path}")

    if not args.no_show:
        try:
            show_image_window(runtime.cv2, "YOLO11 Detection", annotated)
        except Exception as exc:
            print(
                "Не удалось показать окно OpenCV. "
                "Если вы запускаете код без графической среды, добавьте --no-show.",
                file=sys.stderr,
            )
            raise RuntimeError("Ошибка отображения OpenCV.") from exc

    return len(detections)


def process_stream(
    runtime: RuntimeDependencies,
    model: Any,
    args: argparse.Namespace,
    target_class_id: int,
    target_class_name: str,
    output_path: Optional[Path],
) -> int:
    capture = open_capture(runtime.cv2, args)
    writer: Optional[Any] = None
    frame_index = 0
    max_detected = 0
    show_window = not args.no_show

    try:
        fps = capture.get(runtime.cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 25.0

        frame_width = int(capture.get(runtime.cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(capture.get(runtime.cv2.CAP_PROP_FRAME_HEIGHT))

        if output_path is not None:
            writer = create_video_writer(runtime.cv2, output_path, fps, (frame_width, frame_height))

        while True:
            ok, frame = capture.read()
            if not ok:
                break

            frame_index += 1
            results = run_prediction(model, frame, args.conf, args.imgsz, args.device)
            detections = extract_detections(results[0], target_class_id, target_class_name, args.conf)
            max_detected = max(max_detected, len(detections))

            annotated = annotate_frame(
                runtime.cv2,
                frame,
                detections,
                target_class_name,
                args.line_width,
                args.font_scale,
            )

            if writer is not None:
                writer.write(annotated)

            if show_window:
                try:
                    runtime.cv2.imshow("YOLO11 Detection", annotated)
                    key = runtime.cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                except Exception:
                    print(
                        "Не удалось открыть окно OpenCV. Продолжаю обработку без показа. "
                        "Для явного отключения используйте --no-show.",
                        file=sys.stderr,
                    )
                    show_window = False

            if args.max_frames is not None and frame_index >= args.max_frames:
                break
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        runtime.cv2.destroyAllWindows()

    print(f"Обработано кадров: {frame_index}")
    print(f"Максимальное количество '{target_class_name}' в одном кадре: {max_detected}")

    if output_path is not None:
        print(f"Размеченное видео сохранено: {output_path}")

    return max_detected


def main() -> int:
    args = parse_args()
    validate_args(args)

    if args.source is None and args.camera is None:
        args.camera = 0

    runtime = load_runtime_dependencies()
    source_kind = detect_source_kind(args)
    source_value = args.source if args.source is not None else f"camera_{args.camera}"
    output_path = resolve_output_path(args.save, source_kind, source_value)

    model = load_model(runtime, args.model)
    model_names = normalize_model_names(model.names)

    if args.list_classes:
        print("Доступные классы модели:")
        for class_id, class_name in model_names.items():
            print(f"{class_id}: {class_name}")
        return 0

    target_class_id, target_class_name = resolve_target_class(model_names, args.target_class)

    if source_kind == "image":
        process_image(runtime, model, args, target_class_id, target_class_name, output_path)
    else:
        process_stream(runtime, model, args, target_class_id, target_class_name, output_path)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1)
