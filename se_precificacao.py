#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SE-Preço3D — Sistema Especialista para Precificação, Orçamento e
Viabilidade Financeira de Serviços de Impressão 3D (FDM/FFF).

Disciplina: Inteligência Artificial e LFA — UDF Centro Universitário
Tema da atividade: Finanças (lista de aplicações de SE, aula de 03/11/2026)
Autores: Riandro Deian Ferreira Dias, Davi Mendes Borges, Bianca Cristina das Neves, Enzo Coletto
Referência estrutural: Marinho et al. (2019), SBCAS — DOI 10.5753/sbcas.2019.6295

Arquitetura clássica de um Sistema Especialista:
  * Base de conhecimento  -> tabela MATERIAIS + PARAMETROS + 3 regras SE–ENTÃO
  * Memória de trabalho   -> dicionário de fatos (entradas + fatos derivados)
  * Motor de inferência   -> encadeamento para frente (forward chaining)
  * Módulo de explicação  -> registro de quais regras dispararam e por quê
  * Interface             -> menu interativo no terminal

Encadeamento das regras:
  R1 (risco e perda)  ->  R2 (energia e operação)  ->  R3 (margem, preço e viabilidade)
  R2 depende da taxa de falha derivada por R1; R3 depende dos custos de R1 e R2.

Execução:
  python se_precificacao.py           # modo interativo
  python se_precificacao.py --demo    # roda os casos de demonstração
  python -m unittest -v               # roda os testes automatizados

ATENÇÃO: preços de filamento, tarifa de energia, potências e taxas de falha
abaixo são VALORES DE REFERÊNCIA ILUSTRATIVOS, definidos como hipóteses do
especialista. Antes de uso real, calibre-os com notas fiscais do seu
fornecedor, a tarifa da sua distribuidora e medições com wattímetro.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# 1. BASE DE CONHECIMENTO — FATOS DO DOMÍNIO
# ---------------------------------------------------------------------------

# Perfil de cada material: custo, temperaturas típicas e risco base de falha.
# temp_bico / temp_mesa em °C; preco_kg em R$/kg; falha_base em fração (0.05 = 5%).
MATERIAIS: dict[str, dict] = {
    "PLA":   {"preco_kg": 110.0, "temp_bico": 205, "temp_mesa": 60,
              "falha_base": 0.05, "enclausurado": False,
              "perfil": "baixo custo e fácil de imprimir"},
    "PETG":  {"preco_kg": 130.0, "temp_bico": 235, "temp_mesa": 80,
              "falha_base": 0.08, "enclausurado": False,
              "perfil": "intermediário; boa resistência mecânica"},
    "ABS":   {"preco_kg": 120.0, "temp_bico": 245, "temp_mesa": 100,
              "falha_base": 0.15, "enclausurado": True,
              "perfil": "exige mesa quente e câmara fechada; empenamento frequente"},
    "TPU":   {"preco_kg": 180.0, "temp_bico": 225, "temp_mesa": 50,
              "falha_base": 0.12, "enclausurado": False,
              "perfil": "flexível; impressão lenta"},
    "NYLON": {"preco_kg": 250.0, "temp_bico": 255, "temp_mesa": 90,
              "falha_base": 0.18, "enclausurado": True,
              "perfil": "técnico; higroscópico e alto custo"},
}

# Parâmetros financeiros e operacionais do prestador de serviço.
PARAMETROS: dict[str, float] = {
    "tarifa_kwh": 0.85,         # R$/kWh (tarifa de exemplo)
    "depreciacao_hora": 1.20,   # R$/h de máquina (desgaste de bico, correias, etc.)
    "custo_fixo_pedido": 10.00, # R$ por pedido (fatiamento, preparo, embalagem)
    "potencia_base_w": 60.0,    # W médios de eletrônica, motores e ventoinhas
    "margem_minima": 0.20,      # menor margem aceitável numa negociação
    "teto_falha": 0.40,         # limite superior da taxa de falha estimada
}

FINALIDADES = ("decorativa", "funcional")


# ---------------------------------------------------------------------------
# 2. ESTRUTURA DE REGRAS E MOTOR DE INFERÊNCIA
# ---------------------------------------------------------------------------

@dataclass
class Regra:
    """Regra de produção: SE condicao(fatos) ENTÃO acao(fatos)."""
    codigo: str
    nome: str
    texto: str                                  # forma SE–ENTÃO legível
    requer: tuple[str, ...]                     # fatos que precisam existir
    condicao: Callable[[dict], bool]
    acao: Callable[[dict], tuple[dict, list[str]]]  # (novos fatos, justificativas)


@dataclass
class MotorInferencia:
    """Motor de encadeamento para frente (forward chaining).

    A cada ciclo, percorre a agenda de regras e dispara a primeira regra
    ainda não disparada cujas premissas estão na memória de trabalho e
    cuja condição é verdadeira. Para quando nenhuma regra nova dispara.
    """
    regras: list[Regra]
    explicacao: list[str] = field(default_factory=list)

    def inferir(self, fatos: dict) -> dict:
        memoria = dict(fatos)
        disparadas: set[str] = set()
        ciclo = 0
        while True:
            ciclo += 1
            disparou = False
            for regra in self.regras:
                if regra.codigo in disparadas:
                    continue
                if not all(chave in memoria for chave in regra.requer):
                    continue  # premissas ainda não deduzidas
                if not regra.condicao(memoria):
                    continue
                novos, porques = regra.acao(memoria)
                memoria.update(novos)
                disparadas.add(regra.codigo)
                self.explicacao.append(f"[ciclo {ciclo}] {regra.codigo} — {regra.nome}")
                self.explicacao.extend(f"    • {p}" for p in porques)
                disparou = True
                break  # reinicia a varredura: novos fatos podem habilitar outras regras
            if not disparou:
                break
        memoria["regras_disparadas"] = [r.codigo for r in self.regras if r.codigo in disparadas]
        return memoria


# ---------------------------------------------------------------------------
# 3. AS TRÊS REGRAS PRINCIPAIS
# ---------------------------------------------------------------------------

def _acao_r1(f: dict) -> tuple[dict, list[str]]:
    """R1 — Risco e perda de material."""
    mat = MATERIAIS[f["material"]]
    porques = [f"Material {f['material']} ({mat['perfil']}): falha base {mat['falha_base']:.0%}."]
    taxa = mat["falha_base"]

    # Subcondição 1.1: mesa >= 90 °C aumenta empenamento e descolamento.
    if f["temp_mesa"] >= 90:
        taxa += 0.05
        porques.append(f"Mesa a {f['temp_mesa']} °C (>= 90 °C): +5% de risco de empenamento.")
    # Subcondição 1.2: impressão longa (> 12 h por peça) acumula chance de falha.
    if f["tempo_h"] > 12:
        taxa += 0.05
        porques.append(f"Tempo de {f['tempo_h']} h por peça (> 12 h): +5% de risco.")
    # Subcondição 1.3: peça funcional tem tolerância dimensional menor -> mais descarte.
    if f["finalidade"] == "funcional":
        taxa += 0.03
        porques.append("Peça funcional (tolerância dimensional exigente): +3% de descarte.")

    taxa = min(taxa, PARAMETROS["teto_falha"])
    nivel = "baixo" if taxa < 0.10 else ("médio" if taxa < 0.20 else "alto")

    custo_material = f["peso_g"] / 1000 * mat["preco_kg"] * f["quantidade"]
    custo_material_aj = custo_material * (1 + taxa)
    porques.append(
        f"Taxa de falha = {taxa:.0%} (risco {nivel}). Material: R$ {custo_material:.2f} "
        f"x (1 + {taxa:.2f}) = R$ {custo_material_aj:.2f}."
    )
    return {"taxa_falha": round(taxa, 4), "nivel_risco": nivel,
            "custo_material": round(custo_material, 2),
            "custo_material_ajustado": round(custo_material_aj, 2)}, porques


def _acao_r2(f: dict) -> tuple[dict, list[str]]:
    """R2 — Custo energético e operacional conforme temperaturas."""
    porques = []
    # Subcondição 2.1: classe de potência da mesa aquecida pela temperatura.
    if f["temp_mesa"] >= 90:
        p_mesa, classe = 180.0, "alta"
    elif f["temp_mesa"] >= 61:
        p_mesa, classe = 110.0, "média"
    else:
        p_mesa, classe = 60.0, "baixa"
    # Subcondição 2.2: bico acima de 240 °C consome mais.
    p_bico = 45.0 if f["temp_bico"] >= 240 else 35.0
    potencia = PARAMETROS["potencia_base_w"] + p_mesa + p_bico
    porques.append(
        f"Mesa {f['temp_mesa']} °C -> classe {classe} ({p_mesa:.0f} W); "
        f"bico {f['temp_bico']} °C -> {p_bico:.0f} W; base {PARAMETROS['potencia_base_w']:.0f} W."
    )
    # Subcondição 2.3: materiais que exigem câmara fechada.
    if MATERIAIS[f["material"]]["enclausurado"]:
        potencia *= 1.10
        porques.append("Material exige câmara fechada: +10% de potência média.")

    # A energia e o tempo de máquina gastos em impressões que falham também são custo.
    fator_perda = 1 + f["taxa_falha"]
    horas = f["tempo_h"] * f["quantidade"] * fator_perda
    kwh = potencia / 1000 * horas
    custo_energia = kwh * PARAMETROS["tarifa_kwh"]
    custo_maquina = horas * PARAMETROS["depreciacao_hora"]
    porques.append(
        f"Potência média {potencia:.1f} W x {horas:.2f} h (inclui reimpressões) = {kwh:.2f} kWh "
        f"-> energia R$ {custo_energia:.2f}; depreciação R$ {custo_maquina:.2f}."
    )
    return {"potencia_w": round(potencia, 1), "classe_energia": classe,
            "consumo_kwh": round(kwh, 2), "custo_energia": round(custo_energia, 2),
            "custo_maquina": round(custo_maquina, 2)}, porques


def _acao_r3(f: dict) -> tuple[dict, list[str]]:
    """R3 — Margem de lucro, preço final e viabilidade."""
    porques = []
    custo_total = (f["custo_material_ajustado"] + f["custo_energia"]
                   + f["custo_maquina"] + PARAMETROS["custo_fixo_pedido"])
    porques.append(
        f"Custo total = material {f['custo_material_ajustado']:.2f} + energia {f['custo_energia']:.2f} "
        f"+ máquina {f['custo_maquina']:.2f} + fixo {PARAMETROS['custo_fixo_pedido']:.2f} "
        f"= R$ {custo_total:.2f}."
    )
    # Subcondição 3.1: margem base pela finalidade.
    margem = 0.60 if f["finalidade"] == "funcional" else 0.40
    porques.append(f"Peça {f['finalidade']}: margem base {margem:.0%}.")
    # Subcondição 3.2: urgência.
    if f["urgente"]:
        margem += 0.25
        porques.append("Encomenda urgente (fura a fila da impressora): +25 p.p. de margem.")
    # Subcondição 3.3: prêmio de risco quando R1 classificou risco alto.
    if f["nivel_risco"] == "alto":
        margem += 0.10
        porques.append("Risco alto (R1): +10 p.p. de prêmio de risco.")
    # Subcondição 3.4: desconto por volume.
    if f["quantidade"] >= 10:
        margem -= 0.10
        porques.append(f"Lote de {f['quantidade']} peças (>= 10): -10 p.p. por volume.")

    preco = custo_total * (1 + margem)
    unitario = preco / f["quantidade"]
    porques.append(f"Preço sugerido = {custo_total:.2f} x (1 + {margem:.2f}) = R$ {preco:.2f} "
                   f"(R$ {unitario:.2f}/peça).")

    # Subcondição 3.5: viabilidade frente ao orçamento do cliente.
    orc = f.get("orcamento_cliente")
    piso = custo_total * (1 + PARAMETROS["margem_minima"])
    if orc is None:
        decisao, preco_final = "VIÁVEL", preco
        porques.append("Cliente não informou orçamento: adotar o preço sugerido.")
    elif orc >= preco:
        decisao, preco_final = "VIÁVEL", preco
        porques.append(f"Orçamento R$ {orc:.2f} >= preço sugerido: aceitar.")
    elif orc >= piso:
        decisao, preco_final = "VIÁVEL COM NEGOCIAÇÃO", orc
        porques.append(f"Orçamento R$ {orc:.2f} abaixo do sugerido, mas acima do piso "
                       f"R$ {piso:.2f} (margem mínima {PARAMETROS['margem_minima']:.0%}): negociar.")
    else:
        decisao, preco_final = "INVIÁVEL", preco
        porques.append(f"Orçamento R$ {orc:.2f} abaixo do piso R$ {piso:.2f}: recusar ou "
                       "propor material/finalidade alternativos.")
    margem_efetiva = preco_final / custo_total - 1
    return {"custo_total": round(custo_total, 2), "margem_aplicada": round(margem, 4),
            "preco_sugerido": round(preco, 2), "preco_unitario": round(unitario, 2),
            "piso_negociacao": round(piso, 2), "decisao": decisao,
            "preco_final": round(preco_final, 2),
            "margem_efetiva": round(margem_efetiva, 4)}, porques


REGRAS: list[Regra] = [
    Regra(
        codigo="R1", nome="Risco e perda de material",
        texto=("SE material, temperatura da mesa, tempo de impressão e finalidade são conhecidos "
               "ENTÃO taxa_falha = falha_base(material) + 5% [mesa >= 90 °C] + 5% [tempo > 12 h] "
               "+ 3% [funcional] E custo_material_ajustado = custo_material x (1 + taxa_falha)"),
        requer=("material", "peso_g", "quantidade", "temp_mesa", "tempo_h", "finalidade"),
        condicao=lambda f: f["material"] in MATERIAIS,
        acao=_acao_r1,
    ),
    Regra(
        codigo="R2", nome="Custo energético e operacional por temperatura",
        texto=("SE temperaturas de bico e mesa e taxa_falha são conhecidas "
               "ENTÃO potência = base + P_mesa(classe) + P_bico (+10% se câmara fechada) "
               "E custo_energia = potência x horas x (1 + taxa_falha) x tarifa "
               "E custo_maquina = horas x (1 + taxa_falha) x depreciação"),
        requer=("temp_bico", "temp_mesa", "tempo_h", "quantidade", "taxa_falha"),
        condicao=lambda f: True,
        acao=_acao_r2,
    ),
    Regra(
        codigo="R3", nome="Margem, preço final e viabilidade",
        texto=("SE custos de material, energia e máquina são conhecidos "
               "ENTÃO margem = 40% [decorativa] ou 60% [funcional] + 25 p.p. [urgente] "
               "+ 10 p.p. [risco alto] - 10 p.p. [lote >= 10] E preço = custo_total x (1 + margem) "
               "E decisão = VIÁVEL | VIÁVEL COM NEGOCIAÇÃO | INVIÁVEL conforme o orçamento"),
        requer=("custo_material_ajustado", "custo_energia", "custo_maquina",
                "finalidade", "urgente", "quantidade", "nivel_risco"),
        condicao=lambda f: True,
        acao=_acao_r3,
    ),
]


# ---------------------------------------------------------------------------
# 4. VALIDAÇÃO E API DE ALTO NÍVEL
# ---------------------------------------------------------------------------

def montar_fatos(material: str, peso_g: float, tempo_h: float, finalidade: str,
                 quantidade: int = 1, urgente: bool = False,
                 temp_bico: float | None = None, temp_mesa: float | None = None,
                 orcamento_cliente: float | None = None) -> dict:
    """Valida as entradas e devolve a memória de trabalho inicial.

    Se as temperaturas não forem informadas, usa os valores típicos do material.
    """
    material = material.strip().upper()
    if material not in MATERIAIS:
        raise ValueError(f"Material desconhecido: {material}. Opções: {', '.join(MATERIAIS)}")
    finalidade = finalidade.strip().lower()
    if finalidade not in FINALIDADES:
        raise ValueError(f"Finalidade deve ser uma de: {', '.join(FINALIDADES)}")
    if peso_g <= 0 or tempo_h <= 0:
        raise ValueError("Peso e tempo de impressão devem ser positivos.")
    if quantidade < 1:
        raise ValueError("Quantidade deve ser >= 1.")
    if orcamento_cliente is not None and orcamento_cliente <= 0:
        raise ValueError("Orçamento do cliente deve ser positivo.")
    perfil = MATERIAIS[material]
    bico = float(temp_bico if temp_bico is not None else perfil["temp_bico"])
    mesa = float(temp_mesa if temp_mesa is not None else perfil["temp_mesa"])
    if bico <= 0 or mesa < 0:
        raise ValueError("Temperatura do bico deve ser positiva e da mesa não pode ser negativa.")
    return {
        "material": material, "peso_g": float(peso_g), "tempo_h": float(tempo_h),
        "finalidade": finalidade, "quantidade": int(quantidade), "urgente": bool(urgente),
        "temp_bico": bico, "temp_mesa": mesa,
        **({"orcamento_cliente": float(orcamento_cliente)}
           if orcamento_cliente is not None else {}),
    }


def consultar(**entradas) -> tuple[dict, list[str]]:
    """Recebe as entradas do pedido, roda o motor e devolve (resultado, explicação)."""
    fatos = montar_fatos(**entradas)
    motor = MotorInferencia(regras=REGRAS)
    resultado = motor.inferir(fatos)
    return resultado, motor.explicacao


# ---------------------------------------------------------------------------
# 5. CASOS DE DEMONSTRAÇÃO (Tabelas 4 e 5 do artigo)
# ---------------------------------------------------------------------------

CASOS_DEMO: dict[str, dict] = {
    "C1 — Vaso decorativo": dict(
        material="PLA", peso_g=120, tempo_h=6, finalidade="decorativa",
        quantidade=1, temp_mesa=60),
    "C2 — Suporte mecânico urgente": dict(
        material="ABS", peso_g=250, tempo_h=14, finalidade="funcional",
        quantidade=1, temp_mesa=100, urgente=True),
    "C3 — Lote de chaveiros": dict(
        material="PETG", peso_g=15, tempo_h=1, finalidade="decorativa",
        quantidade=20, temp_mesa=80, orcamento_cliente=100.0),
    "C4 — Junta flexível": dict(
        material="TPU", peso_g=80, tempo_h=8, finalidade="funcional",
        quantidade=1, temp_mesa=50, orcamento_cliente=40.0),
}


# ---------------------------------------------------------------------------
# 6. INTERFACE (TERMINAL)
# ---------------------------------------------------------------------------

def imprimir_resultado(r: dict, explicacao: list[str]) -> None:
    """Mostra o resultado do orçamento e a explicação do raciocínio."""
    print()
    print(f"Taxa de falha: {r['taxa_falha']:.0%} (risco {r['nivel_risco']})")
    print(f"Material (com perdas): R$ {r['custo_material_ajustado']:.2f}")
    print(f"Energia: R$ {r['custo_energia']:.2f}  ({r['consumo_kwh']:.2f} kWh, "
          f"{r['potencia_w']:.1f} W, classe {r['classe_energia']})")
    print(f"Máquina (depreciação): R$ {r['custo_maquina']:.2f}")
    print(f"Custo total: R$ {r['custo_total']:.2f}")
    print(f"Margem aplicada: {r['margem_aplicada']:.0%}")
    print(f"Preço sugerido: R$ {r['preco_sugerido']:.2f} "
          f"(R$ {r['preco_unitario']:.2f} por peça)")
    print(f"DECISÃO: {r['decisao']}  |  preço final R$ {r['preco_final']:.2f} "
          f"(margem efetiva {r['margem_efetiva']:.0%})")
    print()
    print("Por quê? (regras disparadas: " + ", ".join(r["regras_disparadas"]) + ")")
    for linha in explicacao:
        print(linha)
    print()


def executar_demo() -> None:
    """Roda os quatro casos do artigo."""
    for titulo, entradas in CASOS_DEMO.items():
        print("=" * 70)
        print(titulo)
        print("=" * 70)
        resultado, explicacao = consultar(**entradas)
        imprimir_resultado(resultado, explicacao)


def listar_regras() -> None:
    """Mostra as regras da base de conhecimento na forma SE–ENTÃO."""
    for regra in REGRAS:
        print(f"\n{regra.codigo} — {regra.nome}")
        print(f"  {regra.texto}")
    print()


def _ler_numero(pergunta: str, tipo=float, opcional: bool = False):
    """Lê um número do teclado; repete a pergunta se o valor for inválido."""
    while True:
        texto = input(pergunta).strip().replace(",", ".")
        if opcional and texto == "":
            return None
        try:
            return tipo(texto)
        except ValueError:
            print("  Valor inválido, tente de novo.")


def _ler_sim_nao(pergunta: str) -> bool:
    return input(pergunta).strip().lower() in ("s", "sim", "y", "yes")


def novo_orcamento() -> None:
    """Pergunta os dados do pedido e mostra o orçamento."""
    print("\nMateriais disponíveis: " + ", ".join(MATERIAIS))
    material = input("Material: ")
    peso = _ler_numero("Peso da peça (g): ")
    tempo = _ler_numero("Tempo de impressão por peça (h): ")
    finalidade = input("Finalidade (decorativa/funcional): ")
    quantidade = _ler_numero("Quantidade [1]: ", tipo=int, opcional=True) or 1
    urgente = _ler_sim_nao("Urgente? (s/n): ")
    bico = _ler_numero("Temperatura do bico em °C [Enter = padrão do material]: ",
                       opcional=True)
    mesa = _ler_numero("Temperatura da mesa em °C [Enter = padrão do material]: ",
                       opcional=True)
    orcamento = _ler_numero("Orçamento do cliente em R$ [Enter = não informou]: ",
                            opcional=True)
    try:
        resultado, explicacao = consultar(
            material=material, peso_g=peso, tempo_h=tempo, finalidade=finalidade,
            quantidade=quantidade, urgente=urgente, temp_bico=bico, temp_mesa=mesa,
            orcamento_cliente=orcamento)
    except ValueError as erro:
        print(f"\nEntrada inválida: {erro}\n")
        return
    imprimir_resultado(resultado, explicacao)


def modo_interativo() -> None:
    """Menu principal no terminal."""
    while True:
        print("=== SE-Preço3D — Precificação de Impressão 3D ===")
        print("1) Novo orçamento")
        print("2) Casos de demonstração")
        print("3) Listar as regras")
        print("4) Sair")
        opcao = input("Escolha: ").strip()
        if opcao == "1":
            novo_orcamento()
        elif opcao == "2":
            executar_demo()
        elif opcao == "3":
            listar_regras()
        elif opcao == "4":
            print("Até logo!")
            break
        else:
            print("Opção inválida.\n")


def main() -> None:
    if "--demo" in sys.argv:
        executar_demo()
    else:
        modo_interativo()


if __name__ == "__main__":
    main()
