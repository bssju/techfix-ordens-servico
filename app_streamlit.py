"""TechFix Informática: painel do gerente (consulta, cadastro, edição, exclusão e indicadores).

Executar, com o ambiente virtual ativo:
    streamlit run app_streamlit.py

As credenciais do Supabase são lidas do arquivo .env (SUPABASE_URL e SUPABASE_KEY),
nunca escritas no código. Veja o .env.example.
"""

# Imports
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import create_client

# Configuração
PASTA = Path(__file__).resolve().parent
load_dotenv(PASTA / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

FUSO = "America/Sao_Paulo"
STATUS = ["Aberto", "Em análise", "Aguardando peça", "Concluído", "Entregue"]
# Mesmas regras das restrições do banco (schema.sql)
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FORMATACAO_CELULAR = re.compile(r"[\s().+\-]")

COLUNAS_ORDENS = [
    "os_id", "status", "modelo_computador", "problema_relatado", "data_abertura",
    "data_atualizacao", "cliente_id", "cliente_nome", "cliente_email",
    "cliente_celular", "cliente_endereco",
]
COLUNAS_CLIENTES = ["id", "nome", "endereco", "email", "celular_whatsapp", "data_cadastro"]
ROTULOS_TABELA = {
    "os_id": "OS",
    "status": "Status",
    "cliente_nome": "Cliente",
    "cliente_email": "E-mail",
    "cliente_celular": "Celular",
    "cliente_endereco": "Endereço",
    "modelo_computador": "Equipamento",
    "problema_relatado": "Problema",
    "data_abertura": "Abertura",
    "data_atualizacao": "Última atualização",
}

MENSAGENS_RESTRICOES = {
    "uq_clientes_email": "Já existe um cliente com este e-mail.",
    "chk_email_formato": "O e-mail está em formato inválido.",
    "chk_email_minusculo": "O e-mail deve estar em letras minúsculas.",
    "chk_celular_formato": "O celular deve ter de 10 a 13 dígitos, apenas números.",
    "chk_nome_preenchido": "O nome do cliente é obrigatório.",
    "chk_endereco_preenchido": "O endereço é obrigatório.",
    "chk_modelo_preenchido": "O modelo do computador é obrigatório.",
    "chk_problema_preenchido": "O problema apresentado é obrigatório.",
    "chk_status_valido": "Status inválido.",
}

st.set_page_config(page_title="TechFix | Painel do Gerente", page_icon="🛠️", layout="wide")


# Conexão
@st.cache_resource
def conectar():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Defina SUPABASE_URL e SUPABASE_KEY no arquivo .env (veja o .env.example).")
    st.stop()

supabase = conectar()


# Mensagens de erro e de retorno ao usuário
def traduzir_erro(erro):
    """Converte qualquer erro de acesso ao banco em mensagem amigável."""
    if not isinstance(erro, APIError):
        return f"Não foi possível conectar ao banco de dados. Verifique a internet e tente novamente. ({erro})"
    texto = f"{erro.message} {erro.details}"
    for restricao, mensagem in MENSAGENS_RESTRICOES.items():
        if restricao in texto:
            return mensagem
    if erro.code == "23503":
        return ("Este cliente tem ordens de serviço e não pode ser excluído. "
                "Exclua antes as ordens de serviço dele.")
    if erro.code == "42501":
        return ("Sem permissão no banco. Confira a chave no .env e as políticas de acesso (RLS) "
                "no Supabase.")
    return f"Erro do banco de dados: {erro.message}"


def avisar(area, tipo, texto):
    """Guarda uma mensagem para ser exibida depois do recarregamento da página."""
    st.session_state[f"aviso_{area}"] = (tipo, texto)


def exibir_aviso(area):
    aviso = st.session_state.pop(f"aviso_{area}", None)
    if aviso:
        tipo, texto = aviso
        if tipo == "ok":
            st.success(texto)
        else:
            st.error(texto)


def concluir(area, texto):
    """Depois de gravar no banco: guarda a mensagem, limpa o cache e recarrega os dados."""
    avisar(area, "ok", texto)
    st.cache_data.clear()
    st.rerun()


# Validação
def normalizar_cliente(nome, endereco, email, celular):
    return {
        "nome": (nome or "").strip(),
        "endereco": (endereco or "").strip(),
        "email": (email or "").strip().lower(),
        "celular_whatsapp": FORMATACAO_CELULAR.sub("", celular or ""),
    }


def validar_cliente(dados):
    erros = []
    rotulos = {"nome": "Nome", "endereco": "Endereço", "email": "E-mail",
               "celular_whatsapp": "Celular/WhatsApp"}
    faltando = [rotulo for campo, rotulo in rotulos.items() if not dados[campo]]
    if faltando:
        erros.append("Preencha os campos: " + ", ".join(faltando) + ".")
    if dados["email"] and not EMAIL_REGEX.match(dados["email"]):
        erros.append("E-mail inválido. Use o formato nome@dominio.com.")
    celular = dados["celular_whatsapp"]
    if celular:
        if not re.fullmatch(r"[0-9]+", celular):
            erros.append("O celular deve conter apenas números (DDD + número).")
        elif not 10 <= len(celular) <= 13:
            erros.append("O celular deve ter de 10 a 13 dígitos (DDD + número).")
    return erros


# Leitura dos dados (com cache; o cache é limpo após cada gravação)
@st.cache_data(ttl=60, show_spinner="Carregando dados do Supabase...")
def carregar_ordens():
    resposta = (
        supabase.table("vw_ordens_completa").select("*").order("os_id", desc=True).execute()
    )
    return pd.DataFrame(resposta.data, columns=COLUNAS_ORDENS)


@st.cache_data(ttl=60, show_spinner=False)
def carregar_clientes():
    resposta = supabase.table("clientes").select("*").order("nome").execute()
    return pd.DataFrame(resposta.data, columns=COLUNAS_CLIENTES)


def para_brasilia(serie):
    """Converte datas do banco (UTC) para texto no horário de Brasília."""
    datas = pd.to_datetime(serie, utc=True, format="ISO8601").dt.tz_convert(FUSO)
    return datas.dt.strftime("%d/%m/%Y %H:%M")


def preparar_tabela(df):
    tabela = df[list(ROTULOS_TABELA)].copy()
    tabela["data_abertura"] = para_brasilia(tabela["data_abertura"])
    tabela["data_atualizacao"] = para_brasilia(tabela["data_atualizacao"])
    return tabela.rename(columns=ROTULOS_TABELA)


# Escrita no banco
def buscar_cliente_por_email(email):
    resposta = (
        supabase.table("clientes").select("id, nome").eq("email", email).limit(1).execute()
    )
    return resposta.data[0] if resposta.data else None


def obter_ou_criar_cliente(dados):
    """Reaproveita o cliente se o e-mail já existir (sem alterar os dados dele)."""
    cliente = buscar_cliente_por_email(dados["email"])
    if cliente:
        return cliente, False
    resposta = supabase.table("clientes").insert(dados).execute()
    return resposta.data[0], True


def criar_ordem_servico(cliente_id, modelo, problema):
    resposta = (
        supabase.table("ordens_servico")
        .insert({
            "cliente_id": cliente_id,
            "modelo_computador": modelo,
            "problema_relatado": problema,
            "status": "Aberto",
        })
        .execute()
    )
    return resposta.data[0]


# Página
st.title("🛠️ TechFix Informática | Painel do Gerente")
st.caption("Consulte, cadastre, edite e acompanhe as ordens de serviço. Horários de Brasília.")

try:
    ordens = carregar_ordens()
    clientes = carregar_clientes()
except Exception as erro:
    st.error(f"❌ Não foi possível carregar os dados. {traduzir_erro(erro)}")
    st.info("💡 Verifique a conexão com a internet, o arquivo .env e se o schema.sql foi "
            "executado no Supabase.")
    st.stop()

nomes_clientes = dict(zip(clientes["id"], clientes["nome"] + " (" + clientes["email"] + ")"))


def rotulo_cliente(cliente_id):
    return nomes_clientes.get(cliente_id, f"Cliente {cliente_id}")


def rotulo_os(os_id):
    linha = ordens.loc[ordens["os_id"] == os_id].iloc[0]
    return f"OS {os_id} | {linha['cliente_nome']} | {linha['modelo_computador']} | {linha['status']}"


# Barra lateral: filtros da aba Consultar
with st.sidebar:
    st.header("🎛️ Filtros")
    st.caption("Valem para a aba Consultar.")
    filtro_nome = st.text_input("Nome do cliente", placeholder="Ex.: Ana")
    filtro_email = st.text_input("E-mail", placeholder="Ex.: @teste.com")
    filtro_status = st.multiselect("Status", STATUS, placeholder="Todos os status")
    st.divider()
    if st.button("🔄 Atualizar dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()

aba_consultar, aba_cadastrar, aba_editar, aba_indicadores = st.tabs(
    ["🔎 Consultar", "➕ Cadastrar", "✏️ Editar/Excluir", "📊 Indicadores"]
)


# Aba 1: Consultar
with aba_consultar:
    filtradas = ordens
    if filtro_nome:
        filtradas = filtradas[
            filtradas["cliente_nome"].str.contains(filtro_nome.strip(), case=False, regex=False)
        ]
    if filtro_email:
        filtradas = filtradas[
            filtradas["cliente_email"].str.contains(filtro_email.strip(), case=False, regex=False)
        ]
    if filtro_status:
        filtradas = filtradas[filtradas["status"].isin(filtro_status)]

    st.subheader(f"Ordens de serviço ({len(filtradas)} de {len(ordens)})")
    if filtradas.empty:
        st.info("Nenhuma ordem de serviço encontrada com esses filtros.")
    else:
        tabela = preparar_tabela(filtradas)
        st.dataframe(tabela, hide_index=True, width="stretch")
        st.download_button(
            "⬇️ Exportar CSV (dados filtrados)",
            data=tabela.to_csv(index=False).encode("utf-8-sig"),
            file_name="ordens_servico_filtradas.csv",
            mime="text/csv",
        )


# Aba 2: Cadastrar nova OS
with aba_cadastrar:
    exibir_aviso("cadastrar")
    st.subheader("Nova ordem de serviço")
    origem = st.radio("Cliente", ["Cliente já cadastrado", "Novo cliente"], horizontal=True)

    # A versão no nome do formulário zera os campos depois de um cadastro bem-sucedido
    versao = st.session_state.get("versao_form_cadastro", 0)
    with st.form(f"form_cadastro_{versao}"):
        cliente_id = None
        dados_cliente = None
        if origem == "Cliente já cadastrado":
            cliente_id = st.selectbox(
                "Cliente", clientes["id"], format_func=rotulo_cliente,
                index=None, placeholder="Selecione o cliente",
            )
        else:
            nome = st.text_input("Nome do cliente", placeholder="Ex.: Ana Souza")
            endereco = st.text_input("Endereço", placeholder="Ex.: Rua das Flores, 123, Campinas/SP")
            email = st.text_input("E-mail", placeholder="Ex.: ana.souza@email.com")
            celular = st.text_input("Celular/WhatsApp", placeholder="Ex.: 19999990000")
            dados_cliente = normalizar_cliente(nome, endereco, email, celular)
        modelo = st.text_input("Modelo do computador", placeholder="Ex.: Notebook Dell Inspiron 15")
        problema = st.text_area("Problema apresentado", placeholder="Descreva o defeito relatado...")
        enviado = st.form_submit_button("➕ Cadastrar OS", type="primary")

    if enviado:
        modelo, problema = modelo.strip(), problema.strip()
        erros = []
        if origem == "Cliente já cadastrado" and cliente_id is None:
            erros.append("Selecione o cliente.")
        if dados_cliente is not None:
            erros += validar_cliente(dados_cliente)
        if not modelo or not problema:
            erros.append("Preencha o modelo do computador e o problema apresentado.")

        if erros:
            st.error("❌ Não foi possível cadastrar:\n\n" + "\n".join(f"- {e}" for e in erros))
        else:
            try:
                observacao = ""
                if dados_cliente is not None:
                    cliente, foi_criado = obter_ou_criar_cliente(dados_cliente)
                    cliente_id = cliente["id"]
                    if not foi_criado:
                        observacao = (f" O e-mail já pertencia a {cliente['nome']}; "
                                      "a OS foi aberta para esse cliente, sem alterar o cadastro.")
                ordem = criar_ordem_servico(cliente_id, modelo, problema)
            except Exception as erro:
                st.error(f"❌ {traduzir_erro(erro)}")
            else:
                st.session_state["versao_form_cadastro"] = versao + 1
                concluir("cadastrar", f"✅ OS nº {ordem['id']} aberta com status Aberto.{observacao}")


# Aba 3: Editar/Excluir
with aba_editar:
    exibir_aviso("editar")
    col_os, col_cliente = st.columns(2, gap="large")

    with col_os:
        st.subheader("🧾 Ordem de serviço")
        if ordens.empty:
            st.info("Nenhuma ordem de serviço cadastrada.")
        else:
            os_id = st.selectbox("Selecione a OS", ordens["os_id"], format_func=rotulo_os)
            os_atual = ordens.loc[ordens["os_id"] == os_id].iloc[0]
            st.caption(f"Problema relatado: {os_atual['problema_relatado']}")

            novo_status = st.selectbox(
                "Status", STATUS, index=STATUS.index(os_atual["status"]), key=f"status_{os_id}"
            )
            if st.button("💾 Salvar status", disabled=novo_status == os_atual["status"]):
                try:
                    supabase.table("ordens_servico").update({"status": novo_status}).eq("id", int(os_id)).execute()
                except Exception as erro:
                    st.error(f"❌ {traduzir_erro(erro)}")
                else:
                    concluir("editar", f"✅ OS nº {os_id}: status alterado para {novo_status}.")

            st.markdown("**Excluir esta OS**")
            confirma_os = st.checkbox(
                f"Confirmo que quero excluir a OS nº {os_id} (não pode ser desfeito)",
                key=f"confirma_os_{os_id}",
            )
            if st.button("🗑️ Excluir OS", disabled=not confirma_os):
                try:
                    supabase.table("ordens_servico").delete().eq("id", int(os_id)).execute()
                except Exception as erro:
                    st.error(f"❌ {traduzir_erro(erro)}")
                else:
                    concluir("editar", f"✅ OS nº {os_id} excluída.")

    with col_cliente:
        st.subheader("👤 Cliente")
        if clientes.empty:
            st.info("Nenhum cliente cadastrado.")
        else:
            cliente_id = st.selectbox("Selecione o cliente", clientes["id"], format_func=rotulo_cliente)
            cliente = clientes.loc[clientes["id"] == cliente_id].iloc[0]

            # Um formulário por cliente, para os campos virem preenchidos com os dados dele
            with st.form(f"form_cliente_{cliente_id}"):
                nome = st.text_input("Nome", value=cliente["nome"])
                endereco = st.text_input("Endereço", value=cliente["endereco"])
                email = st.text_input("E-mail", value=cliente["email"])
                celular = st.text_input("Celular/WhatsApp", value=cliente["celular_whatsapp"])
                salvar_cliente = st.form_submit_button("💾 Salvar dados do cliente")

            if salvar_cliente:
                dados = normalizar_cliente(nome, endereco, email, celular)
                erros = validar_cliente(dados)
                if erros:
                    st.error("❌ Não foi possível salvar:\n\n" + "\n".join(f"- {e}" for e in erros))
                else:
                    try:
                        supabase.table("clientes").update(dados).eq("id", int(cliente_id)).execute()
                    except Exception as erro:
                        st.error(f"❌ {traduzir_erro(erro)}")
                    else:
                        concluir("editar", f"✅ Dados de {dados['nome']} atualizados.")

            st.markdown("**Excluir este cliente**")
            qtd_os = int((ordens["cliente_id"] == cliente_id).sum())
            if qtd_os:
                st.warning(
                    f"Este cliente tem {qtd_os} ordem(ns) de serviço. Para preservar o histórico, "
                    "o banco só permite excluir clientes sem OS: exclua antes as OS dele."
                )
            else:
                confirma_cliente = st.checkbox(
                    "Confirmo que quero excluir este cliente (não pode ser desfeito)",
                    key=f"confirma_cliente_{cliente_id}",
                )
                if st.button("🗑️ Excluir cliente", disabled=not confirma_cliente):
                    try:
                        supabase.table("clientes").delete().eq("id", int(cliente_id)).execute()
                    except Exception as erro:
                        st.error(f"❌ {traduzir_erro(erro)}")
                    else:
                        concluir("editar", f"✅ Cliente {cliente['nome']} excluído.")


# Aba 4: Indicadores
with aba_indicadores:
    st.subheader("Ordens de serviço por status")
    contagem = ordens["status"].value_counts().reindex(STATUS, fill_value=0)

    colunas = st.columns(len(STATUS) + 1)
    colunas[0].metric("Total de OS", len(ordens))
    for coluna, status in zip(colunas[1:], STATUS):
        coluna.metric(status, int(contagem[status]))

    grafico = pd.DataFrame({"Status": STATUS, "Quantidade de OS": contagem.values})
    st.bar_chart(grafico, x="Status", y="Quantidade de OS", sort=False)
    st.caption(f"{len(clientes)} clientes cadastrados.")
