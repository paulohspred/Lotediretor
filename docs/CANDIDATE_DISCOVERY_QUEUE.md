# Candidate Discovery Queue

A fila existe para impedir que descoberta na internet seja confundida com fonte aprovada.

## Estados

`DISCOVERED`  
Encontramos uma pista, URL, documento, nome de sistema ou serviço.

`AUTHORITY_CONFIRMED`  
A autoridade responsável e o domínio oficial foram confirmados.

`TERMS_REVIEW`  
Licença, termos de uso e possibilidade de armazenamento/redistribuição estão sendo avaliados.

`SCHEMA_REVIEW`  
Campos, geometrias, identificadores, atualização e cobertura estão sendo inspecionados.

`PRIVACY_REVIEW`  
Há risco de CPF/CNPJ, proprietário, requerente, documento, telefone, e-mail ou outro dado pessoal/restrito.

`APPROVED_FOR_CONNECTOR`  
Fonte pode ser coletada/materializada segundo a política aprovada.

`APPROVED_QUERY_ONLY`  
Pode ser consultada em fluxo permitido, mas não espelhada/materializada livremente.

`BLOCKED_AUTH_REQUIRED`  
Existe, mas requer autenticação/credencial que o LoteDiretor não possui legitimamente.

`REJECTED`  
Fonte incorreta, não oficial, incompatível com termos, insegura ou sem utilidade suficiente.

## Regra

Nenhum candidato entra automaticamente em produção.

O fluxo é:

```
Discovery
  -> Authority
  -> Terms/license
  -> Schema
  -> Privacy
  -> Coverage/update/history
  -> Approval
  -> Connector
  -> Snapshot + hash + lineage
```

## Dados pessoais

Quando uma API pública lista campos como `Proprietario`, `CPF`, `CNPJ`, `Requerente` ou documentos, isso aumenta a exigência de revisão — não a prioridade de coleta.

O conector deverá trabalhar com **allowlist de campos**, não simplesmente copiar tudo que o endpoint retorna.
