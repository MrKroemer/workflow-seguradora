from decimal import Decimal

from rpa_corretora.domain.models import PortalPolicyData
from rpa_corretora.integrations.insurer_portal_wave1 import (
    CascadingInsurerPortalGateway,
    parse_mapfre_policy_data_from_text,
    parse_yelum_policy_data_from_text,
)


def test_parse_yelum_policy_data_from_text_extracts_values() -> None:
    text = """
    Dados da apolice
    Premio total: R$ 1.980,40
    Comissao corretor: R$ 287,16
    """

    parsed = parse_yelum_policy_data_from_text(policy_id="Y-100", text=text)

    assert parsed is not None
    assert parsed.policy_id == "Y-100"
    assert parsed.insurer == "Yelum"
    assert parsed.premio_total == Decimal("1980.40")
    assert parsed.comissao == Decimal("287.16")


def test_parse_mapfre_policy_data_from_text_extracts_values() -> None:
    text = """
    Apolice detalhada
    Premio total da apolice
    R$ 2.300,00
    Comissao total
    R$ 322,00
    """

    parsed = parse_mapfre_policy_data_from_text(policy_id="M-200", text=text)

    assert parsed is not None
    assert parsed.policy_id == "M-200"
    assert parsed.insurer == "Mapfre"
    assert parsed.premio_total == Decimal("2300.00")
    assert parsed.comissao == Decimal("322.00")


def test_cascading_gateway_queries_next_gateways_for_missing_items() -> None:
    class YelumGateway:
        def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
            if "A1" in policy_ids:
                return [
                    PortalPolicyData(
                        policy_id="A1",
                        insurer="Yelum",
                        premio_total=Decimal("100.00"),
                        comissao=Decimal("10.00"),
                    )
                ]
            return []

    class PortoGateway:
        def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
            if "B2" in policy_ids:
                return [
                    PortalPolicyData(
                        policy_id="B2",
                        insurer="Porto Seguro",
                        premio_total=Decimal("200.00"),
                        comissao=Decimal("20.00"),
                    )
                ]
            return []

    class StubGateway:
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

    gateway = CascadingInsurerPortalGateway(
        gateways=[YelumGateway(), PortoGateway()],
        fallback=StubGateway(),
    )
    items = gateway.fetch_policy_data(["A1", "B2", "C3"])
    by_id = {item.policy_id: item for item in items}

    assert by_id["A1"].insurer == "Yelum"
    assert by_id["B2"].insurer == "Porto Seguro"
    assert by_id["C3"].insurer == "Stub"
