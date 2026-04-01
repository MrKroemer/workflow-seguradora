from decimal import Decimal

from rpa_corretora.domain.models import PortalPolicyData
from rpa_corretora.integrations.insurer_portal_porto import (
    FallbackInsurerPortalGateway,
    parse_porto_policy_data_from_text,
)


def test_parse_porto_policy_data_from_text_extracts_premium_and_commission() -> None:
    text = """
    Dados da apolice
    Premio total: R$ 2.450,90
    Valor comissao: R$ 367,63
    """

    parsed = parse_porto_policy_data_from_text(policy_id="12345", text=text)

    assert parsed is not None
    assert parsed.policy_id == "12345"
    assert parsed.insurer == "Porto Seguro"
    assert parsed.premio_total == Decimal("2450.90")
    assert parsed.comissao == Decimal("367.63")


def test_parse_porto_policy_data_from_text_returns_none_when_missing_values() -> None:
    text = "Somente informacoes basicas da apolice sem valores financeiros"

    parsed = parse_porto_policy_data_from_text(policy_id="12345", text=text)

    assert parsed is None


def test_parse_porto_policy_data_from_text_extracts_dashboard_wording() -> None:
    text = """
    Minha carteira
    Premio liquido emitido - Total (Mar/26)
    R$ 18.421
    Comissoes emitidas
    R$ 2.964,52
    """

    parsed = parse_porto_policy_data_from_text(policy_id="PORTO-1", text=text)

    assert parsed is not None
    assert parsed.policy_id == "PORTO-1"
    assert parsed.insurer == "Porto Seguro"
    assert parsed.premio_total == Decimal("18421")
    assert parsed.comissao == Decimal("2964.52")


def test_fallback_gateway_uses_secondary_for_missing_policy_ids() -> None:
    class PrimaryGateway:
        def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
            _ = policy_ids
            return [
                PortalPolicyData(
                    policy_id="A1",
                    insurer="Porto Seguro",
                    premio_total=Decimal("100.00"),
                    comissao=Decimal("10.00"),
                )
            ]

    class SecondaryGateway:
        def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
            return [
                PortalPolicyData(
                    policy_id=policy_id,
                    insurer="Stub",
                    premio_total=Decimal("1.00"),
                    comissao=Decimal("0.10"),
                )
                for policy_id in policy_ids
            ]

    gateway = FallbackInsurerPortalGateway(primary=PrimaryGateway(), fallback=SecondaryGateway())
    items = gateway.fetch_policy_data(["A1", "B2"])

    assert len(items) == 2
    assert {item.policy_id for item in items} == {"A1", "B2"}
