from decimal import Decimal

from rpa_corretora.integrations.insurer_portal_wave2 import (
    parse_allianz_policy_data_from_text,
    parse_azul_policy_data_from_text,
    parse_bradesco_policy_data_from_text,
    parse_hdi_policy_data_from_text,
    parse_suhai_policy_data_from_text,
    parse_tokio_policy_data_from_text,
)


def test_parse_bradesco_policy_data_from_text_extracts_values() -> None:
    text = """
    Detalhes da apolice
    Premio bruto: R$ 3.010,55
    Comissao bruta: R$ 451,58
    """

    parsed = parse_bradesco_policy_data_from_text(policy_id="B-10", text=text)

    assert parsed is not None
    assert parsed.insurer == "Bradesco"
    assert parsed.premio_total == Decimal("3010.55")
    assert parsed.comissao == Decimal("451.58")


def test_parse_allianz_policy_data_from_text_extracts_values() -> None:
    text = """
    Consulta Allianz
    Valor premio
    R$ 1.400,00
    Comissao prevista
    R$ 210,00
    """

    parsed = parse_allianz_policy_data_from_text(policy_id="A-20", text=text)

    assert parsed is not None
    assert parsed.insurer == "Allianz"
    assert parsed.premio_total == Decimal("1400.00")
    assert parsed.comissao == Decimal("210.00")


def test_parse_suhai_policy_data_from_text_extracts_values() -> None:
    text = """
    Resultado Suhai
    Premio mensal: R$ 980,99
    Comissao liquida: R$ 147,15
    """

    parsed = parse_suhai_policy_data_from_text(policy_id="S-30", text=text)

    assert parsed is not None
    assert parsed.insurer == "Suhai"
    assert parsed.premio_total == Decimal("980.99")
    assert parsed.comissao == Decimal("147.15")


def test_parse_tokio_policy_data_from_text_extracts_values() -> None:
    text = """
    Painel Tokio Marine
    Premio liquido emitido: R$ 18.421,00
    Comissoes pagas: R$ 2.964,52
    """

    parsed = parse_tokio_policy_data_from_text(policy_id="T-40", text=text)

    assert parsed is not None
    assert parsed.insurer == "Tokio Marine"
    assert parsed.premio_total == Decimal("18421.00")
    assert parsed.comissao == Decimal("2964.52")


def test_parse_hdi_policy_data_from_text_extracts_values() -> None:
    text = """
    HDI Digital
    Valor da cotacao: R$ 3.901,98
    Comissao especial: R$ 585,29
    """

    parsed = parse_hdi_policy_data_from_text(policy_id="H-50", text=text)

    assert parsed is not None
    assert parsed.insurer == "HDI"
    assert parsed.premio_total == Decimal("3901.98")
    assert parsed.comissao == Decimal("585.29")


def test_parse_azul_policy_data_from_text_extracts_values() -> None:
    text = """
    Portal Azul
    Consultar Cota Premio: R$ 1.250,00
    Extrato de Comissoes: R$ 187,50
    """

    parsed = parse_azul_policy_data_from_text(policy_id="Z-60", text=text)

    assert parsed is not None
    assert parsed.insurer == "Azul"
    assert parsed.premio_total == Decimal("1250.00")
    assert parsed.comissao == Decimal("187.50")
