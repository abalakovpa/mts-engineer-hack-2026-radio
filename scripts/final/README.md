# Воспроизведение рабочих результатов

Из корня репозитория, Python 3.12. В текущей облачной машине подготовлен virtualenv с доступом к установленным пакетам и Shapely:

```sh
source /workspace/radio-runtime/venv/bin/activate
python3 scripts/final/calculate.py
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/prepare_coverage_model.py
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/build_project.py
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/evaluate_coverage.py --step 0.25
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/evaluate_coverage.py --step 0.5 --resolution-only
python3 scripts/final/validate.py
```

После этих команд подготовить инженерные дополнения, презентацию и пять отдельных артефактов:

```sh
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/final_engineering.py
python3 scripts/final/final_presentation.py
MPLCONFIGDIR=/tmp/radio-mpl python3 scripts/final/package_submission.py
python3 scripts/final/validate.py
```

Экспорт PDF: Pandoc + XeLaTeX и DejaVu Sans/Mono. Проверка PDF: pdfinfo/pdftotext. Презентация и PDF-предпросмотр формируются по общему макету, а не рендерингом в PowerPoint. Скрипт final_engineering.py добавляет листы портового плана, DCS и комплектности в XLSX; его выполнять после evaluate_coverage.py. Личные поля — presentation/profile-input.json. Архив, манифест и правила отправки — submission/README.md. Загрузка на платформу не автоматизирована.

Зависимости зафиксированы в requirements.txt. В новой среде создать virtualenv, активировать его и установить `python -m pip install -r scripts/final/requirements.txt`; путь активации заменить на путь нового virtualenv. Исходные DOCX/DWG/XLSX/PDF/PNG не редактируются.

Для повторного извлечения CAD см. `design/final/README.md` и `extract_cad.py`. Генерация проекта использует уже сохранённый compact JSON и не требует конвертера при каждом запуске. Производные файлы перечислены в `docs/final/design-project.md`; их не следует редактировать вручную вместо входов генератора.

`calculate.py` использует Decimal. `prepare_coverage_model.py` восстанавливает группы площади и препятствия. `build_project.py` читает явные входы design/final/project-input.json, пересчитывает топологию и создаёт схемы/XLSX/PPTX. `evaluate_coverage.py` добавляет карты, листы покрытия и численные результаты в презентацию. Поэтому после отдельного запуска build_project.py необходимо снова выполнить evaluate_coverage.py. Оценки компонентов не являются паспортными данными; карты — прогнозы выбранной модели.

Для повторного исследования вариантов, без автоматического изменения принятого project-input.json: `python3 scripts/final/coverage.py --step 0.5`. Исходный 48-антенный вариант сохранён в coverage/baseline-candidate.json. Локальный поиск позиций выполнен optimize_positions.py; он создаёт предложения, а не автоматически меняет проект. Оригинальные предложения и сравнение до переносов сохранены.

`validate.py` проверяет неизменность исходников, дерево, длины, XLSX, RF-точки, структуру презентации, суммы весов и монотонность сценариев. Лучи кэшируются с отпечатком геометрии и координат; после переноса пересчитываются изменившиеся пути. Некоторые сценарии покрытия проходят 95%, другие не проходят; тесты согласованности не подменяют эти исходы.
