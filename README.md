# SE-Preço3D

**Sistema Especialista para Precificação, Orçamento e Viabilidade Financeira de Serviços de Impressão 3D (FDM/FFF)**

Trabalho da disciplina **Inteligência Artificial e LFA** — UDF Centro Universitário (A1).
Tema: **Finanças**, da lista de aplicações de Sistemas Especialistas (aula de 03/11/2026).

## O que o sistema faz

Um prestador de serviços de impressão 3D informa o material, o peso, o tempo de impressão, a finalidade da peça, a quantidade, se é urgente e, se houver, o orçamento do cliente. O sistema responde com:

- a taxa de falha estimada e o custo de material já com as perdas;
- o consumo e o custo de energia, calculados a partir das temperaturas do bico e da mesa;
- o custo total, a margem aplicada e o preço sugerido (total e por peça);
- a decisão: **VIÁVEL**, **VIÁVEL COM NEGOCIAÇÃO** ou **INVIÁVEL**;
- a explicação de quais regras dispararam e por quê.

## Arquitetura

| Componente | Onde fica no código |
|---|---|
| Base de conhecimento (fatos) | `MATERIAIS` e `PARAMETROS` |
| Base de conhecimento (regras SE–ENTÃO) | `REGRAS` (R1, R2, R3) |
| Memória de trabalho | dicionário de fatos passado ao motor |
| Motor de inferência | `MotorInferencia` (encadeamento para frente) |
| Módulo de explicação | `MotorInferencia.explicacao` |
| Interface | `modo_interativo()` (terminal) |

## As 3 regras

| Regra | SE | ENTÃO |
|---|---|---|
| **R1 — Risco e perda de material** | material, temperatura da mesa, tempo e finalidade conhecidos | taxa de falha = falha base do material + 5% (mesa ≥ 90 °C) + 5% (tempo > 12 h) + 3% (funcional), limitada a 40%; custo de material × (1 + taxa de falha) |
| **R2 — Custo energético e operacional** | temperaturas de bico e mesa e taxa de falha conhecidas | potência = 60 W + mesa (60/110/180 W por faixa de temperatura) + bico (35/45 W), +10% se exige câmara fechada; energia e depreciação contam as reimpressões |
| **R3 — Margem, preço e viabilidade** | custos de R1 e R2 conhecidos | margem 40% (decorativa) ou 60% (funcional), +25 p.p. se urgente, +10 p.p. se risco alto, −10 p.p. se lote ≥ 10; preço = custo × (1 + margem); decisão conforme o orçamento do cliente e a margem mínima de 20% |

A ordem R1 → R2 → R3 não é fixa no código: ela surge do encadeamento para frente, porque cada regra só dispara quando os fatos de que precisa já foram deduzidos.

## Como executar

Requisito: **Python 3.10 ou superior**. Não há dependências externas.

```bash
git clone <url-do-repositorio>
cd se-precificacao-3d

python se_precificacao.py          # modo interativo
python se_precificacao.py --demo   # os 4 casos do artigo
python -m unittest -v              # 15 testes automatizados