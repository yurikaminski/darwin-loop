# M1 · SDK Wrap — Captura de sinais

| | |
| :--- | :--- |
| **Milestone** | M1 |
| **Tier** | 🔓 Core (MIT) |
| **Track (downstream)** | SDK |
| **Estimativa** | 13.5h (sênior ÷ 2) |
| **Janela estimada** | 23–24/06/2026 |
| **Depende de** | M0 (contrato de ingest + modelo de dados) |
| **Destrava** | M2 (Classificação), M6 (Wizard) |
| **Ref. PRD** | v3.0 §5.1 (Adapter), §5.2 (Signal Detection), §10 (Privacy), §13 (Telemetria) |

> O SDK que embrulha o cliente LLM do agente, captura cada interação (sem alterar resposta nem latência), detecta sinais de feedback diretos e indiretos, anonimiza, e envia ao backend para classificação.

---

## 1. Propósito

Ser a **camada de instrumentação** do DarwinLoop: o ponto onde os dados nascem. O dev "embrulha" seu cliente de LLM com o adapter do DarwinLoop e, a partir daí, toda interação do agente passa a gerar telemetria de feedback — **sem nenhuma mudança no comportamento do agente** e sem o dev escrever lógica de captura.

É o degrau `INSTRUMENT` da escada de valor: commodity em si, mas é a fonte de todo o resto (e do flywheel de pesquisa).

## 2. O que faz (escopo)

1. **Embrulha o cliente do agente** (adapter drop-in) — substitui o cliente oficial (ex.: `anthropic.Anthropic()`) por um wrapper com API idêntica.
2. **Captura o turn** — extrai e normaliza `{system_prompt_hash, user_message, assistant_response, tokens_used, agent_id, session_id, timestamp}`.
3. **Detecta sinais diretos** — eventos explícitos do usuário (thumbs up/down, rating) recebidos do app cliente.
4. **Detecta sinais indiretos** — padrões comportamentais (re-prompt, correção, frustração, abandono) a partir das mensagens do usuário.
5. **Anonimiza** — passa o conteúdo pelo Privacy Scrubber antes de qualquer dado sair da máquina.
6. **Envia ao backend** — despacha o evento para a API de ingest (definida no M0) de forma assíncrona e não-bloqueante.

## 3. Onde se encaixa

```
[Agente do cliente] → ((SDK Wrap · M1)) → [API de ingest · M0] → [Judge · M2]
                          ↑ captura            ↑ contrato            ↑ classifica
```

- **Entra depois de:** M0 ter definido o modelo de dados e o contrato de ingest.
- **Sai para:** M2, que consome os episódios capturados e os classifica.

## 4. Requisitos funcionais

| ID | Requisito |
| :--- | :--- |
| FR-M1.1 | O adapter **não modifica** a resposta retornada ao código do dev nem adiciona latência perceptível. |
| FR-M1.2 | Normaliza cada interação no objeto de turno padrão (campos do §2.2). |
| FR-M1.3 | Captura sinais **diretos** (thumbs/rating) quando o app os fornece. |
| FR-M1.4 | Detecta sinais **indiretos** conforme a taxonomia de sinais (definida no M0). |
| FR-M1.5 | O **Privacy Scrubber** remove PII antes de qualquer envio — nenhum conteúdo cru sai da máquina. |
| FR-M1.6 | O envio ao backend é **assíncrono / fire-and-forget**; a thread do agente nunca é bloqueada. |
| FR-M1.7 | Nenhum conteúdo de conversa é persistido localmente em texto cru (apenas hash). |

## 5. Requisitos não-funcionais

| ID | Atributo | Requisito |
| :--- | :--- | :--- |
| NFR-M1.1 | Latência | Caminho síncrono (detecção que precede o LLM) < 10ms P99. |
| NFR-M1.2 | Não-bloqueio | Fila cheia → descarta com WARNING; agente nunca espera. |
| NFR-M1.3 | Offline | Funciona sem rede; buffer local até o envio. |
| NFR-M1.4 | BYOK | Qualquer chamada LLM (ex.: detecção judge-first) usa a chave do dev. |

## 6. Decisões de produto em aberto

> Estas são as tasks de **definição** deste módulo (upstream). Precisam ser resolvidas antes da implementação.

| Decisão | Pergunta a resolver | Task |
| :--- | :--- | :--- |
| **Sinais diretos** | Quais capturar (thumbs/rating) e como o SDK os recebe do app? | `Definir sinais diretos a capturar` |
| **Método de detecção indireta** | Triagem por keyword (barata, <10ms) **vs** delegar ao LLM Judge (judge-first, mais preciso, mais caro)? | `Definir método de detecção dos sinais indiretos` |
| **Política de scrubber** | Que PII remover (email, telefone, CPF, nomes, endereços…) e como (pluggable)? | `Definir política de anonimização / scrubber` |
| **Primeiro adapter** | Começar por Anthropic, OpenAI ou genérico? | `Definir qual adapter/framework vem primeiro` |

## 7. Contrato / interfaces

- **Consome:** o **contrato da API de ingest** (definido no M0) — payload `{evento, turno, sinais}`.
- **Expõe ao dev:** um cliente wrapper com API idêntica ao SDK original + configuração mínima (agent_id, chave BYOK, URL de ingest, telemetria).

## 8. Critérios de aceite (Definition of Done)

- [ ] O dev embrulha seu cliente com o adapter e **não precisa mudar mais nada** no código.
- [ ] Uma interação gera um turno normalizado, **sem alterar a resposta** ao usuário.
- [ ] Um sinal **direto** e um **indireto** são detectados em cenários de teste.
- [ ] O conteúdo passa pelo scrubber — nenhum PII sai da máquina (verificado em teste).
- [ ] O evento chega ao backend de ingest de forma assíncrona, sem bloquear o agente.

## 9. Fora de escopo

- Classificação do tipo de falha → **M2**.
- Suporte a múltiplos frameworks de uma vez → começamos por **um** adapter.
- Fila de retry com entrega garantida → **EE / backlog**.
- Detecção via classificador ML re-treinado → **EE**.

## 10. Estimativa, cronograma e dependências

| Task | Sr (h) | Est (h) | Início | Fim |
| :--- | :--: | :--: | :--- | :--- |
| [Story] Capturar feedback direto e indireto sem alterar o agente | 2 | 1 | 23/06 | 23/06 |
| Definir sinais diretos a capturar (thumbs/rating) e como | 6 | 3 | 23/06 | 23/06 |
| Definir método de detecção dos sinais indiretos (keyword vs judge-first) | 8 | 4 | 23/06 | 24/06 |
| Definir política de anonimização / scrubber (que PII remover) | 8 | 4 | 24/06 | 24/06 |
| Definir qual adapter/framework vem primeiro | 3 | 1.5 | 24/06 | 24/06 |
| **Total** | **27** | **13.5** | | |

- **Bloqueado por:** M0 → `Contrato da API de ingest`, `Modelo conceitual de dados`.
- **Bloqueia:** M2 (`[Story] Classificar`), M6 (`[Story] Dev configura wizard`).
- Dentro do módulo: a `[Story]` destrava as 4 definições.

## 11. Referências

- PRD v3.0 — §5.1 Adapter Layer (FR-A1…A7), §5.2 Signal Detection (FR-S1…S9), §10 Security & Privacy, §13 Telemetria & Consentimento.
- Mapa Core/Misto/EE — PRD v3.0 §11 (este módulo é majoritariamente Core).
