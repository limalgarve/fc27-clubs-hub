# FC27 Clubs Hub — V6 Online

Dashboard web para EA SPORTS FC Clubs, com multiclubes, histórico acumulativo,
partidas, estatísticas individuais, rankings e exportação Excel.

## Produção
O projeto está pronto para deploy em serviços Python/ASGI.

### Variáveis
- `ADMIN_TOKEN`: protege o botão Atualizar Clube.
- `DATA_DIR`: diretório do SQLite.

### Render
O `render.yaml` já inclui build, start, health check e Python 3.13.

> IMPORTANTE: em hospedagem com filesystem efêmero, SQLite não é persistente.
> Para histórico permanente no Render, adicione um Persistent Disk e altere
> `DATA_DIR` para o mount path, ou migre para PostgreSQL.

### Start command
`uvicorn app:app --host 0.0.0.0 --port $PORT`

### Health check
`/health`

## Segurança
Visitantes podem consultar os dados. A atualização pode ser protegida com
`ADMIN_TOKEN`; o navegador solicita a senha e a guarda apenas no localStorage.

## Licença da API
Consulte `LICENSE_FC27_API.md`.
