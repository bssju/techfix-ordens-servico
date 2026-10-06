# TechFix Informática — Sistema de Ordens de Serviço

**Aluna:** Juliana Burato  
**Atividade 2:** Aplicações em Data Science  
Curso de Especialização em Ciência de Dados — Extecamp (UNICAMP)

Solução web para a loja fictícia TechFix: uma aplicação de atendimento em **Gradio** (balcão e celular) e um painel do gerente em **Streamlit**, compartilhando um banco PostgreSQL no **Supabase**. Todos os dados usados são fictícios.

---

## Estrutura

```
techfix/
├── sql/schema.sql       # criação do banco: tabelas, restrições, índices, trigger, view e RLS
├── app_gradio.py        # atendimento: cadastro do cliente e abertura da OS
├── app_streamlit.py     # painel do gerente: CRUD completo e indicadores
├── testar_conexao.py    # teste rápido da conexão com o Supabase
├── requirements.txt
├── .env.example         # nomes das variáveis, sem valores
├── README.md
└── evidencias/          # prints das telas e das tabelas
```

## Parte 1. Banco de dados (`sql/schema.sql`)

- Tabelas `clientes` e `ordens_servico` (relação 1:N), com chave primária `bigint` gerada automaticamente.
- Chave estrangeira `ordens_servico.cliente_id → clientes.id` com **ON DELETE RESTRICT**: um cliente com OS não pode ser excluído, preservando o histórico de reparos.
- `NOT NULL` nos campos essenciais, `UNIQUE` no e-mail e `CHECK` no status (Aberto, Em análise, Aguardando peça, Concluído, Entregue), no formato do e-mail (em minúsculas) e no celular (somente dígitos, 10 a 13).
- Índices em `cliente_id` e `status`, trigger que atualiza `data_atualizacao` a cada alteração e view `vw_ordens_completa` (com `security_invoker`) usada pelo painel.
- RLS habilitado com política de acesso aberta, conforme o padrão da aula.

## Parte 2. Atendimento (`app_gradio.py`)

- `gr.Blocks` com `gr.Row`/`gr.Column` (as colunas viram uma só no celular), título, instrução de uso, rótulos e placeholders.
- **Cadastrar:** valida campos obrigatórios, e-mail e celular; reaproveita o cliente pelo e-mail sem alterar o cadastro; abre a OS com status "Aberto" e informa o número gerado.
- **Limpar:** esvazia todos os campos. `share=True` gera o link público temporário para uso no celular.

## Parte 3. Painel do gerente (`app_streamlit.py`)

- Abas **Consultar**, **Cadastrar**, **Editar/Excluir** e **Indicadores**.
- Filtros por nome, e-mail e status na barra lateral, com **exportação do CSV filtrado** (desafio opcional).
- Alteração do status da OS e dos dados do cliente; exclusão de OS ou cliente sempre com confirmação.
- `st.metric` com o total de OS por status e `st.bar_chart`.

## Como executar

1. Crie um projeto no Supabase e execute `sql/schema.sql` no SQL Editor.
2. Copie `.env.example` para `.env` e preencha `SUPABASE_URL` e `SUPABASE_KEY` com a chave **publishable/anon** (nunca a secret).
3. Instale e execute:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python testar_conexao.py          # confere a conexão
python app_gradio.py              # atendimento
streamlit run app_streamlit.py    # painel do gerente
```

Testado com Python 3.14.7 no Windows.

## Segurança e boas práticas

- Chaves apenas no `.env`, fora do código e da entrega (listado no `.gitignore`); `.env.example` sem valores.
- Os apps usam a chave pública (publishable/anon); a secret key não é usada.
- `try/except` em todo acesso ao banco, com mensagens amigáveis ao usuário.
- Somente dados fictícios (LGPD).

**Limitação conhecida:** a política de acesso aberta permite que quem tiver a chave pública leia e altere os dados. O Security Advisor do Supabase não aponta erros, apenas o aviso esperado "RLS Policy Always True". Em produção, o acesso exigiria login (Supabase Auth) e políticas por usuário.

## Evidências (`evidencias/`)

| Arquivo | Conteúdo |
|---|---|
| `a_gradio_celular_*` | Gradio aberto no celular |
| `b_cadastro_*.png` | Mensagens de cadastro com o número da OS: cliente novo e cliente já cadastrado (reaproveitado pelo e-mail) |
| `c_supabase_*.png` | Tabelas preenchidas no Table Editor do Supabase |
| `d_streamlit_*.png` | Painel Streamlit: consulta, edição e indicadores |
