"""TechFix Informática: aplicação de atendimento (abertura de ordens de serviço).

Executar, com o ambiente virtual ativo:
    python app_gradio.py

As credenciais do Supabase são lidas do arquivo .env (SUPABASE_URL e SUPABASE_KEY),
nunca escritas no código. Veja o .env.example.
"""

# Imports
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import gradio as gr
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import create_client

# Configuração
PASTA = Path(__file__).resolve().parent
load_dotenv(PASTA / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

FUSO = ZoneInfo("America/Sao_Paulo")
# Mesma regra da restrição chk_email_formato do banco
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Caracteres de formatação aceitos no celular e removidos antes de gravar: espaço ( ) - . +
FORMATACAO_CELULAR = re.compile(r"[\s().+\-]")

# Mensagens amigáveis para as restrições definidas no schema.sql
MENSAGENS_RESTRICOES = {
    "uq_clientes_email": "Já existe um cliente com este e-mail.",
    "chk_email_formato": "O e-mail está em formato inválido.",
    "chk_email_minusculo": "O e-mail deve estar em letras minúsculas.",
    "chk_celular_formato": "O celular deve ter de 10 a 13 dígitos, apenas números.",
    "chk_nome_preenchido": "O nome do cliente é obrigatório.",
    "chk_endereco_preenchido": "O endereço é obrigatório.",
    "chk_modelo_preenchido": "O modelo do computador é obrigatório.",
    "chk_problema_preenchido": "O problema apresentado é obrigatório.",
    "fk_os_cliente": "O cliente informado não existe.",
}

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Erro: defina SUPABASE_URL e SUPABASE_KEY no arquivo .env (veja o .env.example).")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# Validação
def validar(nome, endereco, email, celular, modelo, problema):
    """Normaliza os campos e devolve (dados, lista de erros)."""
    dados = {
        "nome": (nome or "").strip(),
        "endereco": (endereco or "").strip(),
        "email": (email or "").strip().lower(),
        "celular": FORMATACAO_CELULAR.sub("", celular or ""),
        "modelo": (modelo or "").strip(),
        "problema": (problema or "").strip(),
    }

    erros = []
    obrigatorios = {
        "Nome do Cliente": dados["nome"],
        "Endereço": dados["endereco"],
        "E-mail": dados["email"],
        "Celular/WhatsApp": dados["celular"],
        "Modelo do Computador": dados["modelo"],
        "Problema Apresentado": dados["problema"],
    }
    faltando = [rotulo for rotulo, valor in obrigatorios.items() if not valor]
    if faltando:
        erros.append("Preencha os campos: " + ", ".join(faltando) + ".")

    if dados["email"] and not EMAIL_REGEX.match(dados["email"]):
        erros.append("E-mail inválido. Use o formato nome@dominio.com.")

    if dados["celular"]:
        if not re.fullmatch(r"[0-9]+", dados["celular"]):
            erros.append("O celular deve conter apenas números (DDD + número).")
        elif not 10 <= len(dados["celular"]) <= 13:
            erros.append("O celular deve ter de 10 a 13 dígitos (DDD + número).")

    return dados, erros


# Acesso ao banco
def traduzir_erro_banco(erro):
    """Converte um erro do Supabase em mensagem amigável."""
    texto = f"{erro.message} {erro.details}"
    for restricao, mensagem in MENSAGENS_RESTRICOES.items():
        if restricao in texto:
            return mensagem
    if erro.code == "42501":
        return ("Sem permissão para gravar no banco. Confira a chave no .env "
                "e as políticas de acesso (RLS) no Supabase.")
    return f"Erro do banco de dados: {erro.message}"


def buscar_cliente_por_email(email):
    resposta = (
        supabase.table("clientes")
        .select("id, nome")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    return resposta.data[0] if resposta.data else None


def obter_ou_criar_cliente(dados):
    """Reaproveita o cliente se o e-mail já existir; caso contrário, cria um novo.

    Devolve (cliente, foi_criado). Os dados de um cliente existente não são alterados.
    """
    cliente = buscar_cliente_por_email(dados["email"])
    if cliente:
        return cliente, False

    try:
        resposta = (
            supabase.table("clientes")
            .insert({
                "nome": dados["nome"],
                "endereco": dados["endereco"],
                "email": dados["email"],
                "celular_whatsapp": dados["celular"],
            })
            .execute()
        )
        return resposta.data[0], True
    except APIError as erro:
        # Outro atendente cadastrou o mesmo e-mail no mesmo instante: reaproveita esse cliente
        if erro.code == "23505":
            cliente = buscar_cliente_por_email(dados["email"])
            if cliente:
                return cliente, False
        raise


def criar_ordem_servico(cliente_id, dados):
    resposta = (
        supabase.table("ordens_servico")
        .insert({
            "cliente_id": cliente_id,
            "modelo_computador": dados["modelo"],
            "problema_relatado": dados["problema"],
            "status": "Aberto",
        })
        .execute()
    )
    return resposta.data[0]


# Mensagens
def formatar_data(texto_iso):
    """Converte a data do banco (UTC) para o horário de Brasília."""
    try:
        data = datetime.fromisoformat(texto_iso).astimezone(FUSO)
    except (TypeError, ValueError):
        data = datetime.now(FUSO)
    return data.strftime("%d/%m/%Y %H:%M")


def mensagem_erro(erros):
    itens = "\n".join(f"- {erro}" for erro in erros)
    return f"### ❌ Não foi possível cadastrar\n{itens}"


def mensagem_sucesso(ordem, cliente, foi_criado, dados):
    if foi_criado:
        situacao_cliente = "novo cliente cadastrado"
    else:
        situacao_cliente = "cliente já cadastrado; dados cadastrais mantidos"
    return (
        f"### ✅ Ordem de Serviço nº {ordem['id']} aberta com sucesso!\n"
        f"- **Cliente:** {cliente['nome']} ({situacao_cliente})\n"
        f"- **E-mail:** {dados['email']}\n"
        f"- **Equipamento:** {ordem['modelo_computador']}\n"
        f"- **Status:** {ordem['status']}\n"
        f"- **Abertura:** {formatar_data(ordem['data_abertura'])} (horário de Brasília)"
    )


# Funções dos botões
def cadastrar(nome, endereco, email, celular, modelo, problema):
    dados, erros = validar(nome, endereco, email, celular, modelo, problema)
    if erros:
        return mensagem_erro(erros)

    try:
        cliente, foi_criado = obter_ou_criar_cliente(dados)
    except APIError as erro:
        return mensagem_erro([traduzir_erro_banco(erro)])
    except Exception as erro:
        return mensagem_erro([
            "Não foi possível conectar ao banco de dados. Verifique a internet e tente novamente.",
            f"Detalhe técnico: {erro}",
        ])

    try:
        ordem = criar_ordem_servico(cliente["id"], dados)
    except APIError as erro:
        erros = [traduzir_erro_banco(erro)]
        if foi_criado:
            erros.append(f"O cliente {cliente['nome']} foi cadastrado, mas a ordem de serviço não. "
                         "Clique em Cadastrar novamente para abri-la.")
        return mensagem_erro(erros)
    except Exception as erro:
        return mensagem_erro([
            "Não foi possível conectar ao banco de dados ao abrir a ordem de serviço.",
            f"Detalhe técnico: {erro}",
        ])

    return mensagem_sucesso(ordem, cliente, foi_criado, dados)


def limpar():
    """Esvazia os seis campos e a área de mensagens."""
    return "", "", "", "", "", "", ""


# Interface
with gr.Blocks(title="TechFix Informática | Atendimento") as app:
    gr.Markdown(
        "# 🛠️ TechFix Informática\n"
        "## Abertura de Ordem de Serviço\n"
        "Preencha os dados do cliente e do equipamento e clique em **Cadastrar**. "
        "Se o e-mail já estiver cadastrado, a ordem de serviço é aberta para esse cliente. "
        "Todos os campos são obrigatórios."
    )

    # Em telas pequenas (celular), as duas colunas ficam uma embaixo da outra
    with gr.Row():
        with gr.Column(min_width=300):
            gr.Markdown("### 👤 Dados do Cliente")
            nome = gr.Textbox(label="Nome do Cliente", placeholder="Ex.: Ana Souza")
            endereco = gr.Textbox(
                label="Endereço", placeholder="Ex.: Rua das Flores, 123, Centro, Campinas/SP"
            )
            email = gr.Textbox(
                label="E-mail", placeholder="Ex.: ana.souza@email.com", type="email"
            )
            celular = gr.Textbox(
                label="Celular/WhatsApp",
                placeholder="Ex.: 19999990000 (DDD + número, só números)",
            )

        with gr.Column(min_width=300):
            gr.Markdown("### 💻 Dados do Equipamento")
            modelo = gr.Textbox(
                label="Modelo do Computador", placeholder="Ex.: Notebook Dell Inspiron 15"
            )
            problema = gr.Textbox(
                label="Problema Apresentado",
                placeholder="Descreva o defeito relatado pelo cliente...",
                lines=5,
            )

    with gr.Row():
        btn_cadastrar = gr.Button("✅ Cadastrar", variant="primary", scale=2)
        btn_limpar = gr.Button("🧹 Limpar", variant="secondary", scale=1)

    resultado = gr.Markdown()

    campos = [nome, endereco, email, celular, modelo, problema]
    btn_cadastrar.click(fn=cadastrar, inputs=campos, outputs=resultado)
    btn_limpar.click(fn=limpar, outputs=campos + [resultado])


if __name__ == "__main__":
    # share=True gera um link público temporário para testar no celular
    app.launch(share=True, theme=gr.themes.Soft())
