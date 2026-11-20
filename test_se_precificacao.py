# -*- coding: utf-8 -*-
"""Testes automatizados do SE-Preço3D.

Rodar:  python -m unittest -v
Cada teste verifica uma regra (ou subcondição) isoladamente e os quatro
casos de demonstração descritos no artigo.
"""

import unittest

from se_precificacao import CASOS_DEMO, PARAMETROS, consultar, montar_fatos


class TestRegraR1RiscoPerda(unittest.TestCase):
    def test_pla_simples_tem_risco_baixo(self):
        r, _ = consultar(material="PLA", peso_g=100, tempo_h=4, finalidade="decorativa")
        self.assertAlmostEqual(r["taxa_falha"], 0.05)
        self.assertEqual(r["nivel_risco"], "baixo")

    def test_acrescimos_de_mesa_tempo_e_funcional(self):
        # ABS: 15% + 5% (mesa 100 °C) + 5% (14 h) + 3% (funcional) = 28%
        r, _ = consultar(material="ABS", peso_g=100, tempo_h=14, finalidade="funcional")
        self.assertAlmostEqual(r["taxa_falha"], 0.28)
        self.assertEqual(r["nivel_risco"], "alto")

    def test_taxa_de_falha_respeita_teto(self):
        r, _ = consultar(material="NYLON", peso_g=50, tempo_h=30, finalidade="funcional",
                         temp_mesa=110)
        self.assertLessEqual(r["taxa_falha"], PARAMETROS["teto_falha"])

    def test_custo_material_inclui_perdas(self):
        # 120 g de PLA a R$ 110/kg = R$ 13,20; com 5% de perda = R$ 13,86
        r, _ = consultar(material="PLA", peso_g=120, tempo_h=6, finalidade="decorativa")
        self.assertAlmostEqual(r["custo_material"], 13.20)
        self.assertAlmostEqual(r["custo_material_ajustado"], 13.86)


class TestRegraR2Energia(unittest.TestCase):
    def test_classes_de_potencia_pela_mesa(self):
        baixa, _ = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="decorativa")
        media, _ = consultar(material="PETG", peso_g=50, tempo_h=2, finalidade="decorativa")
        alta, _ = consultar(material="ABS", peso_g=50, tempo_h=2, finalidade="decorativa")
        self.assertEqual(baixa["classe_energia"], "baixa")
        self.assertEqual(media["classe_energia"], "média")
        self.assertEqual(alta["classe_energia"], "alta")
        self.assertLess(baixa["potencia_w"], media["potencia_w"])
        self.assertLess(media["potencia_w"], alta["potencia_w"])

    def test_mesa_quente_custa_mais_energia_que_mesa_fria(self):
        fria, _ = consultar(material="PLA", peso_g=50, tempo_h=5, finalidade="decorativa",
                            temp_mesa=60)
        quente, _ = consultar(material="PLA", peso_g=50, tempo_h=5, finalidade="decorativa",
                              temp_mesa=95)
        self.assertGreater(quente["custo_energia"], fria["custo_energia"])

    def test_camara_fechada_acrescenta_10_por_cento(self):
        # ABS: (60 + 180 + 45) x 1,10 = 313,5 W
        r, _ = consultar(material="ABS", peso_g=50, tempo_h=2, finalidade="decorativa")
        self.assertAlmostEqual(r["potencia_w"], 313.5)


class TestRegraR3PrecoViabilidade(unittest.TestCase):
    def test_margens_base_por_finalidade(self):
        dec, _ = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="decorativa")
        fun, _ = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="funcional")
        self.assertAlmostEqual(dec["margem_aplicada"], 0.40)
        self.assertAlmostEqual(fun["margem_aplicada"], 0.60)

    def test_urgencia_e_desconto_de_volume(self):
        urg, _ = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="decorativa",
                           urgente=True)
        lote, _ = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="decorativa",
                            quantidade=10)
        self.assertAlmostEqual(urg["margem_aplicada"], 0.65)
        self.assertAlmostEqual(lote["margem_aplicada"], 0.30)

    def test_preco_e_custo_vezes_um_mais_margem(self):
        r, _ = consultar(material="PLA", peso_g=120, tempo_h=6, finalidade="decorativa")
        self.assertAlmostEqual(r["preco_sugerido"],
                               round(r["custo_total"] * (1 + r["margem_aplicada"]), 2), places=2)

    def test_tres_decisoes_de_viabilidade(self):
        base = dict(material="PETG", peso_g=15, tempo_h=1, finalidade="decorativa", quantidade=20)
        ok, _ = consultar(**base, orcamento_cliente=150)
        neg, _ = consultar(**base, orcamento_cliente=100)
        nao, _ = consultar(**base, orcamento_cliente=50)
        self.assertEqual(ok["decisao"], "VIÁVEL")
        self.assertEqual(neg["decisao"], "VIÁVEL COM NEGOCIAÇÃO")
        self.assertEqual(neg["preco_final"], 100.0)
        self.assertGreaterEqual(neg["margem_efetiva"], PARAMETROS["margem_minima"])
        self.assertEqual(nao["decisao"], "INVIÁVEL")


class TestMotorEEntradas(unittest.TestCase):
    def test_encadeamento_dispara_r1_r2_r3_em_ordem(self):
        _, explicacao = consultar(material="PLA", peso_g=50, tempo_h=2, finalidade="decorativa")
        cabecalhos = [l for l in explicacao if l.startswith("[ciclo")]
        self.assertEqual(len(cabecalhos), 3)
        self.assertIn("R1", cabecalhos[0])
        self.assertIn("R2", cabecalhos[1])
        self.assertIn("R3", cabecalhos[2])

    def test_temperaturas_padrao_do_material(self):
        f = montar_fatos(material="abs", peso_g=10, tempo_h=1, finalidade="Funcional")
        self.assertEqual(f["material"], "ABS")
        self.assertEqual(f["temp_mesa"], 100)
        self.assertEqual(f["finalidade"], "funcional")

    def test_entradas_invalidas_sao_rejeitadas(self):
        with self.assertRaises(ValueError):
            montar_fatos(material="MADEIRA", peso_g=10, tempo_h=1, finalidade="decorativa")
        with self.assertRaises(ValueError):
            montar_fatos(material="PLA", peso_g=-5, tempo_h=1, finalidade="decorativa")
        with self.assertRaises(ValueError):
            montar_fatos(material="PLA", peso_g=10, tempo_h=1, finalidade="artística")


class TestCasosDoArtigo(unittest.TestCase):
    """Os valores abaixo são exatamente os publicados na Tabela de resultados do artigo."""

    esperado = {
        "C1": (32.25, 45.15, "VIÁVEL"),
        "C2": (74.68, 145.63, "VIÁVEL"),
        "C3": (81.80, 106.34, "VIÁVEL COM NEGOCIAÇÃO"),
        "C4": (38.81, 62.10, "INVIÁVEL"),
    }

    def test_casos_demo(self):
        for titulo, entradas in CASOS_DEMO.items():
            codigo = titulo.split()[0]
            custo, preco, decisao = self.esperado[codigo]
            with self.subTest(caso=codigo):
                r, _ = consultar(**entradas)
                self.assertAlmostEqual(r["custo_total"], custo, places=2)
                self.assertAlmostEqual(r["preco_sugerido"], preco, places=2)
                self.assertEqual(r["decisao"], decisao)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```[cite: 11]

---

### 3. `README.md`

```markdown
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