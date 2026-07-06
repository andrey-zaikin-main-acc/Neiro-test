# KD AI Test Bench

MVP локального веб-стенда для проверки сценария сравнения mock-результатов MinerU, PaddleOCR, Qwen3-VL и Qwen3-8B-text на комплектах конструкторской документации электронных плат.

## Возможности MVP

- загрузка PDF через простой HTML-интерфейс без React;
- извлечение имени файла, размера, числа страниц и базового числа изображений;
- сохранение `TestRun` в SQLite;
- mock-адаптеры всех моделей без API-ключей и внешних вызовов: реальные нейросети на этом шаге не подключены;
- mock-результаты нужны только для проверки MVP-пайплайна и не должны использоваться для оценки качества реальных моделей;
- запись реалистичных raw/normalized JSON в локальные data-каталоги;
- ручное заполнение input/output tokens, visual tokens, критических ошибок и итоговой оценки;
- экспорт всех запусков в CSV и просмотр JSON API.

## Запуск на Windows через PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[test]
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Тесты

```powershell
pytest -q
```

Откройте http://127.0.0.1:8000 и загрузите PDF. Реальные PDF, результаты обработки и `.env` не коммитятся.

## Docker Compose

```powershell
docker compose up --build
```

Приложение будет доступно на http://127.0.0.1:8000.

## Структура

- `app/api` — маршруты загрузки, ручного обновления, JSON API и CSV-экспорта;
- `app/services` — адаптеры моделей, метрики, нормализация, валидация BOM;
- `app/models` — Pydantic-схемы;
- `data/input`, `data/raw_output`, `data/normalized`, `data/reports` — локальные рабочие каталоги, исключены из Git;
- `tests` — минимальные unit-тесты.

## Что требует ручной настройки

- реальные API-ключи и запуск MinerU/Qwen/Qwen3-VL не подключены намеренно;
- определение таблиц без OCR/парсеров не выполняется: `table_count` остаётся `null` / «не определено» до будущей интеграции;
- качество BOM проверяется простыми deterministic-правилами без LLM.
