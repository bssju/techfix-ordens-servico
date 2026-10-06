"""Teste de conexão com o Supabase. Rode antes dos apps:

    python testar_conexao.py

Lê SUPABASE_URL e SUPABASE_KEY do arquivo .env e faz uma leitura simples na view.
"""

# Imports
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# Configuração
PASTA = Path(__file__).resolve().parent
load_dotenv(PASTA / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()


# Funções
def mascarar(valor):
    """Mostra só o começo e o fim de um valor sensível."""
    if len(valor) <= 20:
        return "***"
    return f"{valor[:15]}...{valor[-4:]}"


def main():
    print("Teste de conexão com o Supabase")
    print("=" * 40)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERRO: SUPABASE_URL ou SUPABASE_KEY não encontradas.")
        print(f"Confira se o arquivo .env existe em: {PASTA}")
        return

    print(f"URL:   {SUPABASE_URL}")
    print(f"Chave: {mascarar(SUPABASE_KEY)}")

    if SUPABASE_KEY.startswith("sb_secret_"):
        print("ATENÇÃO: esta é a SECRET key. Troque pela publishable (sb_publishable_...).")
        return

    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        resposta = (
            supabase.table("vw_ordens_completa")
            .select("os_id, status, cliente_nome")
            .limit(5)
            .execute()
        )
    except Exception as erro:
        print(f"ERRO na conexão: {erro}")
        print("Confira a URL e a chave no .env e se o schema.sql foi executado no Supabase.")
        return

    print(f"\nConexão OK. Registros lidos da view: {len(resposta.data)}")
    for linha in resposta.data:
        print(f"  OS {linha['os_id']} | {linha['status']} | {linha['cliente_nome']}")


if __name__ == "__main__":
    main()
