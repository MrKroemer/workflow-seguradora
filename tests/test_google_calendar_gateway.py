from datetime import date

from rpa_corretora.integrations.google_calendar_gateway import GoogleCalendarGateway


def test_google_calendar_gateway_maps_colors_and_fields(monkeypatch) -> None:
    gateway = GoogleCalendarGateway(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(
        gateway,
        "_google_get",
        lambda path, access_token: {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Cobranca de parcela - Ana Silva",
                    "colorId": "11",
                    "start": {"date": "2026-03-30"},
                    "description": "Telefone: +55 (83) 99989-7477",
                },
                {
                    "id": "evt-2",
                    "summary": "Nao mapeado",
                    "colorId": "1",
                    "start": {"date": "2026-03-30"},
                },
            ]
        },
    )

    commitments = gateway.fetch_daily_commitments(date(2026, 3, 30))

    assert len(commitments) == 1
    commitment = commitments[0]
    assert commitment.id == "evt-1"
    assert commitment.color == "VERMELHO"
    assert commitment.client_name == "Ana Silva"
    assert commitment.whatsapp_number == "+5583999897477"
