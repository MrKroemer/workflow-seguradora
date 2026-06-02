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


def renovacao_cliente_message(client_name: str) -> str:
    return (
        f"Ola, {client_name}. Seu seguro esta em periodo de renovacao. "
        "Para atualizar a cotacao, por favor envie os dados necessarios "
        "(dados pessoais, dados do veiculo e informacoes de uso atualizadas)."
    )


def atraso_boleto_message(client_name: str) -> str:
    return (
        f"Ola, {client_name}. Identificamos boleto/parcela vencida ha mais de 5 dias. "
        "Por favor, confirme a regularizacao para mantermos seu seguro em dia."
    )


def liberacao_banco_message() -> str:
    return (
        "INFORMATIVO LIBERACAO BANCO\n\n"
        "Prezado(a) Cliente,\n\n"
        "A cobranca do seu seguro esta disponivel para liberacao na sua conta corrente. "
        "Para garantir a cobertura, libere em ate 48 horas no Internet Banking, "
        "seguindo estes passos:\n\n"
        "1. Acesse o Internet Banking com agencia, conta e senha.\n"
        "2. Localize a area de Seguros ou Debitos Automaticos.\n"
        "3. Encontre a cobranca do seguro (seguradora, apolice, etc.).\n"
        "4. Autorize ou libere o debito.\n\n"
        "Observacao: os procedimentos podem variar conforme o banco."
    )
