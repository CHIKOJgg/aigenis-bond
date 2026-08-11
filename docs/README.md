# Документация — Bonds Engine

**Bonds Engine** — Fixed Income платформа: сбор данных MOEX → скоринг → ML →
Desk-аналитика → подписки (B2C + B2B).

## Документация по приложению — `docs/app/`

| Гайд | Для чего |
|---|---|
| [QUICKSTART.md](app/QUICKSTART.md) | Запуск за 5 минут |
| [DEPLOYMENT.md](app/DEPLOYMENT.md) | Деплой, SSL, туннели, публичный демо-инстанс |
| [DEVELOPMENT.md](app/DEVELOPMENT.md) | Локальная разработка, тесты, код-стайл |
| [OPERATIONS.md](app/OPERATIONS.md) | Мониторинг, алерты, бэкапы, обновление |
| [SECURITY.md](app/SECURITY.md) | Аутентификация, вебхуки, SSRF, секреты |
| [API.md](app/API.md) | Справочник REST API (включая Aigenis-контракт) |
| [METHODOLOGY.md](app/METHODOLOGY.md) | Методология Score, issuer risk и ограничения модели |
| [architecture.md](app/architecture.md) | Архитектура, потоки данных, модули |

## Гайды по Aigenis — `docs/aigenis/`

| Гайд | Для чего |
|---|---|
| [company-profile.md](aigenis/company-profile.md) | Кто такие «Айгенис»: юрлица, продукты, боли, окно возможностей |
| [negotiation-guide.md](aigenis/negotiation-guide.md) | Как вести переговоры: письма, встречи, возражения, сделка |
| [technical-due-diligence.md](aigenis/technical-due-diligence.md) | Ответы для CTO: интеграция, данные, безопасность, DD |
| [one-pager.md](aigenis/one-pager.md) | Executive summary для отправки ЛПР |
| [demo-runbook.md](aigenis/demo-runbook.md) | Проверенный live-demo сценарий и troubleshooting |
| [pitch-script.md](aigenis/pitch-script.md) | Полный сценарий встречи, walkthrough, 30 вопросов и ответов |
| [speaker-notes.md](aigenis/speaker-notes.md) | Шпаргалка на одну страницу перед звонком |

> Все черновики, устаревшие версии и противоречащие материалы удалены.
> Standalone demo работает на live read-only API; `demo-data/` используется
> только для тестов и contract examples.
> Единые цифры во всех документах: **306 автотестов, 1500+ облигаций,
> 9 сервисов, версия 4.0.0**.
