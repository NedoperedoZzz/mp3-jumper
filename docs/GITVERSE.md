# Практические замечания по GitVerse

- Workflow хранятся в `.gitverse/workflows/`.
- У каждого workflow собственный `on:` и набор `jobs:`.
- Для облачного раннера используем `runs-on: ubuntu-latest`.
- Получение кода: `actions/checkout@v4`.
- Сохранение/загрузка результатов: `actions/upload-artifact@v4` и `actions/download-artifact@v4`.
- В `02-project.yaml` второй job (`consume`) запускается после первого (`produce`) благодаря `needs`.
- Ручной запуск реализован через `workflow_dispatch:`.
- Для запуска Quality CI после форка сначала включите CI/CD и при необходимости выполните ручной запуск. Дальше `push` в `master` создаёт новые проверки.
- Секреты храните в настройках репозитория, не в отслеживаемых файлах.
- Артефакты ограничены по объёму и сроку хранения: указывайте ссылки на конкретные запуски, а не рассчитывайте на бессрочное хранение.

Документация:
- https://gitverse.ru/docs/cicd/quick-start/
- https://gitverse.ru/docs/cicd/manuals/artifacts/
- https://gitverse.ru/docs/cicd/faq/

Это шаблон для проверки на реальном GitVerse; корректность выполнения на облачном раннере должна быть подтверждена пилотным форком.
