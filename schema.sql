-- =====================================================
-- ESQUEMA DE BANCO DE DADOS - TECHFIX INFORMÁTICA
-- Sistema de Ordens de Serviço
-- PostgreSQL / Supabase
-- =====================================================
-- Como usar: copie este arquivo inteiro no SQL Editor do Supabase e clique em Run.
-- Ordem: tabelas -> índices -> trigger -> view -> permissões e RLS.


-- =====================================================
-- 1. TABELA DE CLIENTES
-- =====================================================
-- Um mesmo cliente pode trazer vários equipamentos ao longo do tempo,
-- por isso os dados do cliente ficam numa tabela separada das ordens de serviço (relação 1:N).
create table public.clientes (
    id                bigint generated always as identity primary key,
    nome              text not null,
    endereco          text not null,
    email             text not null,
    celular_whatsapp  text not null,
    data_cadastro     timestamptz not null default now(),

    -- E-mail único: é por ele que o app de cadastro reconhece um cliente que já existe
    constraint uq_clientes_email unique (email),

    -- E-mail sempre em minúsculas, para que "Ana@x.com" e "ana@x.com" não virem dois clientes
    constraint chk_email_minusculo check (email = lower(email)),

    -- Formato simples de e-mail: texto@texto.dominio, sem espaços
    constraint chk_email_formato check (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),

    -- Celular/WhatsApp: somente dígitos, de 10 a 13 caracteres (DDD + número, com ou sem o 55 do Brasil)
    constraint chk_celular_formato check (celular_whatsapp ~ '^[0-9]{10,13}$'),

    -- Campos de texto obrigatórios não podem conter apenas espaços
    constraint chk_nome_preenchido check (btrim(nome) <> ''),
    constraint chk_endereco_preenchido check (btrim(endereco) <> '')
);


-- =====================================================
-- 2. TABELA DE ORDENS DE SERVIÇO
-- =====================================================
-- Cada linha é um atendimento: o equipamento trazido, o problema e o andamento do reparo.
create table public.ordens_servico (
    id                 bigint generated always as identity primary key,
    cliente_id         bigint not null,
    modelo_computador  text not null,
    problema_relatado  text not null,
    status             text not null default 'Aberto',
    data_abertura      timestamptz not null default now(),
    data_atualizacao   timestamptz not null default now(),

    -- Chave estrangeira para clientes.
    -- ON DELETE RESTRICT: o banco recusa excluir um cliente que ainda tenha ordens de serviço,
    -- para que o histórico de reparos não seja apagado por engano.
    -- Para excluir um cliente, é preciso excluir antes as ordens de serviço dele.
    constraint fk_os_cliente foreign key (cliente_id)
        references public.clientes (id) on delete restrict,

    -- Status aceita apenas as etapas do fluxo de atendimento
    constraint chk_status_valido check (
        status in ('Aberto', 'Em análise', 'Aguardando peça', 'Concluído', 'Entregue')
    ),

    -- Campos de texto obrigatórios não podem conter apenas espaços
    constraint chk_modelo_preenchido check (btrim(modelo_computador) <> ''),
    constraint chk_problema_preenchido check (btrim(problema_relatado) <> '')
);


-- =====================================================
-- 3. ÍNDICES PARA PERFORMANCE
-- =====================================================
-- O PostgreSQL não cria índice automaticamente em chaves estrangeiras.
-- Este índice acelera a junção com clientes e a busca das OS de um cliente.
create index idx_os_cliente on public.ordens_servico (cliente_id);

-- Acelera os filtros e as contagens por status do painel do gerente
create index idx_os_status on public.ordens_servico (status);

-- Observação: o e-mail já tem índice, criado automaticamente pela restrição UNIQUE.


-- =====================================================
-- 4. TRIGGER PARA ATUALIZAÇÃO AUTOMÁTICA DA DATA
-- =====================================================
-- Sempre que uma ordem de serviço for alterada (por exemplo, mudança de status),
-- data_atualizacao recebe a data/hora atual. Como fica no banco, vale para qualquer
-- caminho de edição: painel Streamlit, Table Editor do Supabase ou SQL.
create or replace function public.atualizar_data_atualizacao()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.data_atualizacao = now();
    return new;
end;
$$;

create trigger trg_os_data_atualizacao
    before update on public.ordens_servico
    for each row
    execute function public.atualizar_data_atualizacao();


-- =====================================================
-- 5. VIEW PARA CONSULTAS DO PAINEL
-- =====================================================
-- Junta cada ordem de serviço com os dados do cliente, para a aba "Consultar" do Streamlit.
-- security_invoker = true: a view respeita as políticas de RLS de quem consulta
-- (sem SECURITY DEFINER).
create or replace view public.vw_ordens_completa
with (security_invoker = true) as
select
    os.id                 as os_id,
    os.status,
    os.modelo_computador,
    os.problema_relatado,
    os.data_abertura,
    os.data_atualizacao,
    c.id                  as cliente_id,
    c.nome                as cliente_nome,
    c.email               as cliente_email,
    c.celular_whatsapp    as cliente_celular,
    c.endereco            as cliente_endereco
from public.ordens_servico os
join public.clientes c on c.id = os.cliente_id;


-- =====================================================
-- 6. PERMISSÕES E POLÍTICAS DE ACESSO (RLS)
-- =====================================================
-- Os apps acessam o banco com a chave pública (anon / publishable), nunca com a secret key.
-- Permissões explícitas para os papéis usados por essa chave:
grant select, insert, update, delete on public.clientes       to anon, authenticated;
grant select, insert, update, delete on public.ordens_servico to anon, authenticated;
grant select                         on public.vw_ordens_completa to anon, authenticated;

-- RLS habilitado em todas as tabelas, seguido de uma política aberta (padrão da aula).
-- Observação: a política aberta permite que qualquer pessoa com a chave pública leia e altere
-- os dados. É adequado para um projeto acadêmico com dados fictícios; em produção, o acesso
-- deveria exigir login (Supabase Auth) e políticas restritas por usuário.
alter table public.clientes       enable row level security;
alter table public.ordens_servico enable row level security;

create policy "Acesso total" on public.clientes
    for all to public
    using (true)
    with check (true);

create policy "Acesso total" on public.ordens_servico
    for all to public
    using (true)
    with check (true);
