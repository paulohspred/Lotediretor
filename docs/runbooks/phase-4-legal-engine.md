# Runbook — Fase 4: motor jurídico

Leis nunca são sobrescritas: cada documento tem versões com vigência
(`valid_from`/`valid_to`) e registro no sistema (`recorded_at`). Parâmetros
urbanísticos são regras estruturadas que apontam para o dispositivo legal que
as sustenta. **Só regras conferidas por uma pessoa aparecem como confirmadas.**

Requer PostgreSQL ≥ 15 (usa `UNIQUE NULLS NOT DISTINCT`).

## 1. Migration e catálogo inicial

```bash
export LOTEDIRETOR_DB_DSN="postgresql:///lotediretor?host=/var/run/postgresql"
python3 tools/db/migrate.py                 # aplica 006
python3 tools/legal/seed_catalog.py         # Planos Diretores das capitais (metadados)
                                            # + LC 565/2023 de Barueri (artigos transcritos,
                                            #   aliases setor→zona, regras CANDIDATAS)
```

## 2. Ingerir uma lei (PDF com texto, HTML ou TXT)

```bash
python3 tools/legal/ingest.py lei.pdf \
  --jurisdiction MUNICIPAL --ibge 3505708 --kind LEI_COMPLEMENTAR \
  --number 565/2023 --title "LC 565/2023 — Uso e ocupação do solo" \
  --valid-from 2023-12-11 --source-id sp-barueri-lpuos-lc565-2023 \
  --url https://portal.barueri.sp.gov.br/... \
  --zone-article SER=35 --zone-article SRE=36
```

- PDF escaneado é **recusado**: faça OCR separadamente e revise.
- Conteúdo idêntico não cria nova versão. `--close-previous` encerra a
  vigência da versão anterior no dia anterior a `--valid-from`.
- `--zone-article ZONA=ARTIGO` extrai regras **candidatas** daquele artigo.

## 3. Revisão humana (obrigatória para "confirmado")

```bash
python3 tools/legal/review_rules.py list --ibge 3505708 --zone SER
python3 tools/legal/review_rules.py confirm <rule_id> \
  --reviewer "Nome — CAU A00000-0" --note "Conferido com o art. 35, p. 16 do PDF oficial"
```

`reject` e `conflict` funcionam igual. Toda decisão fica em
`ld_legal.rule_review_event`. A tela de revisão no painel administrativo
chega na Fase 5.

## 4. API

- `GET /legal/search?q=recuo+frontal&ibge=3505708[&date=AAAA-MM-DD]`
- `GET /legal/rules?ibge=3505708&zone=A-04[&include_candidates=true]`
- `GET /legal/documents?ibge=3505708`

No dossiê do lote, a seção "Parâmetros urbanísticos" mostra valores
confirmados; candidatos aparecem marcados "[Aguardando revisão]" com o aviso
"Não use para decisão".
