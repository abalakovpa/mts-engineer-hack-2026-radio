# Пересборка и проверка решения

Из корня репозитория. Python 3.12; зависимости в requirements.txt.
В новой среде создать virtualenv и установить пакеты:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r scripts/final/requirements.txt
```

Для PDF требуются Pandoc, XeLaTeX, pdfinfo/pdftotext и шрифты DejaVu Sans/Mono.
Презентация использует официальный шаблон со встроенными шрифтами МТС;
для рендеринга PPTX требуется LibreOffice (soffice).
В подготовленной облачной среде virtualenv — `/workspace/radio-runtime/venv`.
Конвертер DWG нужен только при повторном извлечении CAD; компактная геометрия
уже сохранена. [Геометрия и единицы](../../design/final/README.md).

## Полная последовательность

```sh
export MPLCONFIGDIR=/tmp/radio-mpl
export XDG_CACHE_HOME=/tmp/radio-report-cache
export OPENBLAS_NUM_THREADS=1
python scripts/final/calculate.py
python scripts/final/prepare_coverage_model.py
python scripts/final/build_project.py
python scripts/final/evaluate_coverage.py --step 0.25
python scripts/final/evaluate_coverage.py --step 0.5 --resolution-only
python scripts/final/final_engineering.py
python scripts/final/quality_analysis.py
python scripts/final/check_geometry.py
python scripts/final/write_design_docs.py
python scripts/final/final_presentation.py
python scripts/final/write_status_docs.py
python scripts/final/package_submission.py --include-presentation
python scripts/final/validate.py
```

Входы проекта — design/final/project-input.json; роли и личные сведения —
presentation/profile-input.json. Исходные документы не редактируются.
После изменения RF-входов выполнять всю последовательность. build_project.py
создаёт спецификацию, evaluate_coverage.py и final_engineering.py добавляют
листы покрытия, портового плана и комплектности.

Лучевые кэши propagation-*.npz не хранятся на GitHub; при отсутствии они
генерируются автоматически с отпечатками геометрии и координат.
check_geometry.py проверяет текущую схему при пределе короткого стыка 0,15 м.
write_design_docs.py и write_status_docs.py формируют пояснения из текущих
проверенных JSON; старые исследовательские варианты для этого не нужны.

## Экспорт технических документов

Техническая часть содержит три PDF и XLSX. Презентация сформирована
по официальному шаблону presentation/source-template.pptx.
При изменении только пояснительного текста или оформления:

```sh
python scripts/final/package_submission.py
python scripts/final/validate.py
```

Тексты формируются solution_documents.py из проверенной модели. Экспорт
не меняет расчётные данные и исключает служебные листы из XLSX.

## Добавление презентации

Для обновления презентации с сохранением четырёх готовых документов:

```sh
python scripts/final/final_presentation.py
python scripts/final/write_status_docs.py
python scripts/final/package_submission.py --include-presentation --reuse-technical
python scripts/final/validate.py
```

## Что проверяется

Неизменность исходников; арифметика S/S−1 и Erlang B; доли мощности,
пути, длины и количества; 384 RF-значения; 39 RSRP-сценариев, 33 сценария качества LTE, 12 сценариев DCS C/I и монотонность;
контроль геометрии; портовый план и DCS; XLSX/PPTX; поля, навигация,
векторные схемы и значения экспортированных PDF; содержимое ZIP и SHA-256.
Проверки согласованности не подтверждают фактические KPI.

Оформление PDF — docs/final/deliverables/pdf-header.tex, pdf-design.lua,
pdf_design.py. XLSX использует общую style() из build_project.py; экспорт
автоматически вызывает format_equipment.py для всех листов. Загрузка архива на конкурсную платформу выполняется участником.

## Сценарное качество DL

quality_analysis.py использует существующие поля RSRP и BCCH. Внешние помехи представлены суммарными уровнями на входе UE; частотный план не создаётся. Модель RSRQ включает оба TX-порта и EPRE данных. Формируются карты, обратные бюджеты помех и три технических листа XLSX. После изменения сценариев выполнить quality_analysis.py, final_presentation.py, package_submission.py --include-presentation и validate.py. --reuse-technical допускается только при неизменном отчёте качества.
