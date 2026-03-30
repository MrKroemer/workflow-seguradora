from __future__ import annotations


def proposta_seguro_auto_message(client_name: str) -> str:
    return (
        f"Prezado(a) {client_name},\n"
        "Enviamos para voce a proposta do seu seguro auto.\n"
        "Leia com atencao e assine digitalmente nos campos indicados.\n"
        "Em seguida, encaminhe o documento assinado para o meu e-mail.\n"
        "Saiba por que sua apolice e digital:\n"
        "- Rapida: Receba sua apolice em ate 24 horas.\n"
        "- Pratica: Tenha acesso a qualquer hora e lugar.\n"
        "- Segura: Seus dados estao protegidos.\n"
        "- Sustentavel: Menos papel, mais cuidado com o meio ambiente.\n"
        "Precisa de ajuda? Conte comigo.\n"
        "Estou a disposicao para tirar qualquer duvida: (83) 9 9989-7477.\n"
        "Em casos urgentes, entre em contato imediatamente pelo mesmo numero."
    )


def cobranca_parcela_message(client_name: str) -> str:
    return (
        f"Ola, {client_name}. Identificamos parcela pendente do seu seguro. "
        "Pode me confirmar o pagamento para regularizarmos no sistema?"
    )
