import os
import sys
import socket
from datetime import datetime
from dotenv import load_dotenv
import firebirdsql

# Garante suporte a UTF-8 no terminal
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

DB_HOST_LOCAL = os.getenv("DB_HOST_LOCAL", "192.168.100.108")
DB_HOST_VPN = os.getenv("DB_HOST_VPN", "10.147.17.108")
DB_PORT = int(os.getenv("DB_PORT", 3050))
DB_PATH = os.getenv("DB_PATH", "C:/Sistemas/Pharma/Dados/BANCO.FDB")
DB_USER = os.getenv("DB_USER", "SYSDBA")
DB_PASS = os.getenv("DB_PASSWORD", "masterkey")

def test_host(host, port=3050, timeout=1.5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except Exception:
        return False

def get_connection():
    target_host = None
    if test_host(DB_HOST_LOCAL, DB_PORT):
        target_host = DB_HOST_LOCAL
    elif test_host(DB_HOST_VPN, DB_PORT):
        target_host = DB_HOST_VPN

    if not target_host:
        print("\n[X] Erro: Servidor inacessivel no Wi-Fi local e no ZeroTier.")
        return None

    try:
        conn = firebirdsql.connect(
            host=target_host,
            database=DB_PATH,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            charset='WIN1252'
        )
        return conn
    except Exception as e:
        print(f"\n[X] Falha ao conectar no Firebird ({target_host}): {e}")
        return None

def listar_locais(cur):
    cur.execute("""
        SELECT CD_LOCALIZACAO_LOTE, DS_LOCALIZACAO_LOTE 
        FROM T_LOCALIZACAO_LOTE 
        ORDER BY DS_LOCALIZACAO_LOTE ASC
    """)
    return cur.fetchall()

def buscar_produtos(cur, termo):
    if termo.isdigit():
        sql = """
            SELECT FIRST 20 CD_PRODUTO, DS_PRODUTO 
            FROM T_PRODUTO 
            WHERE CD_PRODUTO = ?
        """
        cur.execute(sql, (int(termo),))
    else:
        sql = """
            SELECT FIRST 20 CD_PRODUTO, DS_PRODUTO 
            FROM T_PRODUTO 
            WHERE UPPER(DS_PRODUTO) LIKE ? 
            ORDER BY DS_PRODUTO ASC
        """
        cur.execute(sql, (f"%{termo.upper()}%",))
    return cur.fetchall()

def obter_lotes_produto(cur, cd_produto):
    sql = """
        SELECT 
            L.CD_PRODUTO,
            L.NR_LOTE,
            L.DT_RECEBIMENTO,
            L.QT_ESTOQUE,
            L.CD_LOCALIZACAO_LOTE,
            LOC.DS_LOCALIZACAO_LOTE,
            L.ID_LOTE_USO,
            L.DT_VALIDADE,
            F.DS_FORNECEDOR
        FROM T_PRODUTO_LOTE L
        LEFT JOIN T_LOCALIZACAO_LOTE LOC ON LOC.CD_LOCALIZACAO_LOTE = L.CD_LOCALIZACAO_LOTE
        LEFT JOIN T_FORNECEDOR F ON F.CD_FORNECEDOR = L.CD_FORNECEDOR
        WHERE L.CD_PRODUTO = ?
        ORDER BY L.ID_LOTE_USO DESC, L.DT_RECEBIMENTO DESC
    """
    cur.execute(sql, (cd_produto,))
    return cur.fetchall()

def alterar_local_lote(conn, lote_info):
    cd_produto = lote_info[0]
    nr_lote = lote_info[1]
    dt_recebimento = lote_info[2]
    cur = conn.cursor()

    locais = listar_locais(cur)
    print("\n" + "=" * 45)
    print("           ESCOLHA O NOVO LOCAL")
    print("=" * 45)
    for loc in locais:
        print(f"[{loc[0]:>2}] {loc[1]}")
    print("-" * 45)

    escolha = input("Digite o codigo do local (ou 'v' para cancelar): ").strip()
    if escolha.lower() == 'v' or not escolha.isdigit():
        print("Operacao cancelada.")
        return

    novo_local = int(escolha)
    try:
        sql_update = """
            UPDATE T_PRODUTO_LOTE
            SET CD_LOCALIZACAO_LOTE = ?
            WHERE CD_PRODUTO = ? 
              AND NR_LOTE = ? 
              AND DT_RECEBIMENTO = ?
        """
        cur.execute(sql_update, (novo_local, cd_produto, nr_lote, dt_recebimento))
        conn.commit()
        print("\n[OK] Localizacao atualizada com sucesso no banco!")
    except Exception as e:
        conn.rollback()
        print(f"\n[X] Erro ao atualizar no banco: {e}")

def formatar_data(dt):
    if not dt:
        return "N/D"
    if isinstance(dt, (datetime, )):
        return dt.strftime("%d/%m/%y")
    return str(dt)[:10]

def exibir_detalhes_e_movimentar(conn, cd_produto, nome_produto):
    while True:
        cur = conn.cursor()
        lotes = obter_lotes_produto(cur, cd_produto)

        print(f"\n>> {nome_produto} [Cod: {cd_produto}]")
        print("-" * 55)

        if not lotes:
            print("Nenhum lote registrado para este produto.")
            return

        for idx, l in enumerate(lotes, 1):
            em_uso = " ★ [EM USO]" if l[6] == 'S' else ""
            local_nome = l[5] if l[5] else "SEM LOCAL"
            saldo = f"{l[3]:,.0f}".replace(",", ".")
            validade = formatar_data(l[7])
            recebimento = formatar_data(l[2])
            forn = (l[8] or "N/D")[:25]

            print(f"[{idx}] 📦 LOTE: {l[1]} {em_uso}")
            print(f"    LOCAL: {local_nome} (Cod: {l[4]})")
            print(f"    SALDO: {saldo} | REC: {recebimento} | VAL: {validade}")
            print(f"    FORN : {forn}")
            print("    " + "-" * 40)

        print("\n[M] Mover / Alterar Local de um Pote")
        print("[V] Voltar")
        acao = input("Opcao: ").strip().lower()

        if acao == 'v':
            break
        elif acao == 'm':
            num = input("Qual o numero do item que deseja mover? ").strip()
            if num.isdigit() and 1 <= int(num) <= len(lotes):
                alterar_local_lote(conn, lotes[int(num) - 1])
            else:
                print("Item invalido.")

def menu_principal():
    while True:
        print("\n" + "=" * 45)
        print("      ESTOQUE & LOCALIZACAO DE MATERIA-PRIMA")
        print("=" * 45)
        print("[1] Buscar Produto por Nome ou Codigo")
        print("[S] Sair")
        opcao = input("\nOpcao: ").strip().lower()

        if opcao == 's':
            print("Encerrando...")
            break
        elif opcao == '1':
            termo = input("\nProduto (Nome/Codigo) ou 'v' para voltar: ").strip()
            if termo.lower() == 'v' or not termo:
                continue

            print("Buscando rota e conectando ao banco...")
            conn = get_connection()
            if not conn:
                continue

            cur = conn.cursor()
            prods = buscar_produtos(cur, termo)

            if not prods:
                print("Nenhum produto encontrado com esse termo.")
                conn.close()
                continue

            print("\nProdutos Encontrados:")
            for i, p in enumerate(prods, 1):
                print(f"[{i:2}] {p[0]:<6} - {p[1]}")

            escolha = input("\nSelecione o produto (ou 'v' para voltar): ").strip()
            if escolha.lower() == 'v' or not escolha.isdigit():
                conn.close()
                continue

            idx_escolha = int(escolha) - 1
            if 0 <= idx_escolha < len(prods):
                prod_selecionado = prods[idx_escolha]
                exibir_detalhes_e_movimentar(conn, prod_selecionado[0], prod_selecionado[1])
            else:
                print("Selecao invalida.")

            conn.close()

if __name__ == "__main__":
    menu_principal()