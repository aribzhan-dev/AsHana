# Структура проекта

Созданы backend/bootstrap, миграции, тесты, frontend app/pages/shared,
infrastructure/docker, compose.yaml и scripts. Domain/application и бизнес-модули
будут добавляться по мере реализации. Ниже **целевая** структура; не все слои уже нужны.
Браузерные тесты основы находятся в `frontend/tests/e2e/`.

```text
AsHana/
  AGENTS.md                 # canonical agent instructions
  CLAUDE.md                 # entrypoint referencing AGENTS.md
  .agents/skills/           # shared project skills
  .claude/
    agents/                 # role descriptions
    commands/               # manual workflow prompts
    rules/                  # path-scoped rules
    skills/                 # symlink to shared skills
    hooks/                  # policy only; no active hooks yet
  docs/
    product/
    architecture/decisions/
    engineering/
    modules/
  tasks/
  backend/
    src/ashana/
      bootstrap/
      shared/
      modules/<module>/
        domain/
        application/
        infrastructure/
        presentation/
    migrations/
    tests/{unit,integration}/
    pyproject.toml
    uv.lock
  frontend/
    src/{app,pages,features,entities,shared}/
    src/shared/{ui,api,locales,lib}/
    tests/
    package.json
    pnpm-lock.yaml
  e2e/
  infrastructure/docker/
  compose.yaml
  .env.example
```

Frontend: app собирает приложение, pages собирают экраны, features реализуют действия,
entities представляют предметные данные, shared содержит общие элементы без бизнес-зависимостей.
Запрет циклов и импорта app/pages из shared. API client типизировать по OpenAPI.
Не создавать пустые слои для каждого простого компонента.
