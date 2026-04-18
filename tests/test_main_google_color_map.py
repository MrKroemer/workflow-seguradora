from rpa_corretora.main import _build_google_color_map_from_env


def test_google_color_map_defaults_include_amarelo_e_tangerina(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_COLOR_IDS_VERMELHO", raising=False)
    monkeypatch.delenv("GOOGLE_COLOR_IDS_AZUL", raising=False)
    monkeypatch.delenv("GOOGLE_COLOR_IDS_CINZA", raising=False)
    monkeypatch.delenv("GOOGLE_COLOR_IDS_VERDE", raising=False)
    monkeypatch.delenv("GOOGLE_COLOR_IDS_AMARELO", raising=False)
    monkeypatch.delenv("GOOGLE_COLOR_IDS_TANGERINA", raising=False)

    color_map = _build_google_color_map_from_env()

    assert color_map["5"] == "AMARELO"
    assert color_map["6"] == "TANGERINA"


def test_google_color_map_allows_env_override_for_amarelo_e_tangerina(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_COLOR_IDS_AMARELO", "2,5")
    monkeypatch.setenv("GOOGLE_COLOR_IDS_TANGERINA", "6,14")

    color_map = _build_google_color_map_from_env()

    assert color_map["2"] == "AMARELO"
    assert color_map["5"] == "AMARELO"
    assert color_map["6"] == "TANGERINA"
    assert color_map["14"] == "TANGERINA"
