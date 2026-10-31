# agent-demo

Nejmenší aplikace, na které pracují vývojoví agenti asome (asome-platform, fáze F5).

- `make test` – testy (závislosti jen s hashi z `requirements-dev.lock`).
- `make run` – server na portu 8080: `GET /healthz`, `GET /api/info`.
- Úkol pro agenty: issue se štítkem `agent:todo` (dá ho vlastník) nebo `/task` v dev botovi.
- Změny `.github/`, `CODEOWNERS` a podobně schvaluje jen vlastník (CODEOWNERS, tier T0).
- Po merge do `main` workflow `release` postaví, prověří a podepíše image; staging ho nasadí sám.
