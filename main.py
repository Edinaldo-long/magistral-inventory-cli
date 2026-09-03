import io
import itertools
import os
import socket
import sys
import threading
import time
import firebirdsql

# CONFIGURAÇÕES DE REDE E BANCO (Carregadas via variáveis de ambiente para segurança)
DB_LOCAL = os.getenv("DB_HOST_LOCAL", "192.168.100.108")
DB_REMOTO = os.getenv("DB_HOST_REMOTO", "10.224.166.55")
DB_NAME = os.getenv("DB_NAME", "3")
DB_USER = os.getenv("DB_USER", "SYSDBA")
DB_PASS = os.getenv("DB_PASSWORD", "masterkey")

# IMPRESSORA TÉRMICA ARGOX (PPLA VIA SOCKET RAW)
PRINT_LOCAL = os.getenv("PRINT_HOST_LOCAL", "192.168.100.121")
PRINT_REMOTO = os.getenv("PRINT_HOST_REMOTO", "10.224.166.55")


class IndicadorAtividade:
    def __init__(self, mensagem="Conectando"):
        self.mensagem = mensagem
        self.rodando = False
        self.thread = None

    def _animar(self):
        icones = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        while self.rodando:
            sys.stdout.write(f"\r{next(icones)} {self.mensagem}...")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(self.mensagem) + 12) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self.rodando = True
        self.thread = threading.Thread(target=self._animar)
        self.thread.daemon = True
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.rodando = False
        if self.thread:
            self.thread.join()


def formatar_codigo(cd):
    try:
        return str(int(float(cd)))
    except Exception:
        return str(cd)


def normalizar_unidade(tp_unidade):
    chave = str(tp_unidade).strip().upper() if tp_unidade is not None else ""
    if chave in ("1", "KILO", "KG", "QUILO"):
        return "kg", 1000000.0
    elif chave in ("2", "L", "LITRO"):
        return "L", 1000000.0
    elif chave in ("3", "ML"):
        return "ml", 1000.0
    elif chave in ("4", "UI"):
        return "UI", 1.0
    elif chave in ("5", "UN", "CAPS", "UNIDADE"):
        return "un", 1.0
    else:
        return "g", 1000.0


def formatar_quantidade(valor_banco, tp_unidade):
    sigla, divisor = normalizar_unidade(tp_unidade)
    try:
        num = float(valor_banco or 0.0) / divisor
        if num == 0:
            return f"0 {sigla}"
        if num.is_integer():
            return f"{int(num)} {sigla}"
        txt = f"{num:.6f}".rstrip("0").rstrip(".")
        return f"{txt} {sigla}".replace(".", ",")
    except Exception:
        return f"{valor_banco} {sigla}"


def formatar_fator(valor):
    try:
        num = float(valor or 1.0)
        if num == 0:
            return "1,000"
        if num > 10.0:
            fator_real = 100.0 / num
            return f"{fator_real:.3f}".replace(".", ",")
        return f"{num:.3f}".replace(".", ",")
    except Exception:
        return str(valor).replace(".", ",")


def testar_porta(host, porta=3050, timeout=3.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, porta))
        s.close()
        return True
    except Exception:
        return False


def obter_host_ativo(ip_local, ip_remoto, porta=3050):
    if testar_porta(ip_local, porta, timeout=1.0):
        return ip_local, "Wi-Fi Local"
    if testar_porta(ip_remoto, porta, timeout=4.5):
        return ip_remoto, "VPN / Remoto"
    return None, None


def conectar():
    with IndicadorAtividade("Buscando rota e conectando ao banco"):
        host_ativo, tipo_rede = obter_host_ativo(DB_LOCAL, DB_REMOTO, 3050)
        if not host_ativo:
            print("\n[✘] Erro: Host inacessivel localmente ou via VPN.")
            return None, None

        config = {
            "host": host_ativo,
            "port": 3050,
            "database": DB_NAME,
            "user": DB_USER,
            "password": DB_PASS,
            "charset": "WIN1252",
            "auth_plugin_name": "Legacy_Auth",
        }
        try:
            con = firebirdsql.connect(**config)
            print(f"🔗 [Conectado via {tipo_rede} - {host_ativo}]")
            return con, tipo_rede
        except Exception as e:
            print(f"\n[✘] Erro de autenticacao no Firebird: {e}")
            return None, None


def enviar_ppla_argox(
    tipo_rede_atual,
    nome_mp,
    lote,
    fator,
    dt_rec,
    dt_fab,
    dt_val,
    fornecedor="NAO INFORMADO",
    nf="0",
    dcb="",
    copias=1,
):
    host_impressora = PRINT_LOCAL if tipo_rede_atual == "Wi-Fi Local" else PRINT_REMOTO
    qtd_str = f"{int(copias):04d}"
    nome_mp_fmt = nome_mp.upper()[:30].center(30)
    forn_fmt = fornecedor[:25]
    dcb_fmt = f"DCB: {dcb}" if dcb else ""

    ppla = (
        "\x02L\r\n"
        "D11\r\n"
        "H10\r\n"
        f"191100000300020{nome_mp_fmt}\r\n"
        f"121100000650030Forn.: {forn_fmt:<25} NF.: {nf}\r\n"
        f"121100000950030Lote: {lote}\r\n"
        f"121100001250030Receb.: {dt_rec}  Fab.: {dt_fab}  Val.: {dt_val}\r\n"
        f"121100001550030{dcb_fmt:<25} Fator: {fator}\r\n"
        f"Q{qtd_str}\r\n"
        "E"
    )

    with IndicadorAtividade(f"Enviando para a Argox ({host_impressora}:9100)"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((host_impressora, 9100))
            s.sendall(ppla.encode("latin-1"))
            s.close()
            print(f"✅ [OK] {copias} rotulo(s) impresso(s) com sucesso na Argox!")
        except Exception as e:
            print(f"❌ Falha ao conectar na impressora ({host_impressora}:9100): {e}")


def menu_por_local(con):
    cur = con.cursor()
    with IndicadorAtividade("Carregando locais de estoque"):
        cur.execute(
            """
            SELECT CD_LOCALIZACAO_LOTE, DS_LOCALIZACAO_LOTE 
            FROM T_LOCALIZACAO_LOTE 
            ORDER BY DS_LOCALIZACAO_LOTE
        """
        )
        locais = cur.fetchall()

    if not locais:
        print("\n[!] Nenhum local cadastrado.")
        return

    print("\n--- LOCAIS DE ESTOQUE ---")
    for idx, (c_loc, d_loc) in enumerate(locais, 1):
        print(f"[{idx:2d}] {d_loc.strip()}")

    sel = input("\nNumero do local (ou 'v' para voltar): ").strip()
    if sel.lower() == "v" or not sel.isdigit():
        return

    idx_sel = int(sel) - 1
    if idx_sel < 0 or idx_sel >= len(locais):
        print("Opcao invalida!")
        return

    cd_local_esc, ds_local_esc = locais[idx_sel]

    with IndicadorAtividade(f"Buscando itens em {ds_local_esc.strip()}"):
        cur.execute(
            """
            SELECT 
                p.CD_PRODUTO,
                p.DS_PRODUTO,
                l.NR_LOTE,
                l.QT_ESTOQUE,
                l.DT_VALIDADE,
                COALESCE(p.TP_UNIDADE, '0') AS TP_UNIDADE
            FROM T_PRODUTO_LOTE l
            INNER JOIN T_PRODUTO p ON p.CD_PRODUTO = l.CD_PRODUTO
            WHERE l.CD_LOCALIZACAO_LOTE = ?
              AND l.QT_ESTOQUE > 0
            ORDER BY p.DS_PRODUTO, l.DT_VALIDADE ASC
        """,
            (cd_local_esc,),
        )
        itens = cur.fetchall()

    if not itens:
        print(f"\n[!] Nenhum item com saldo positivo em: {ds_local_esc.strip()}")
        input("\nPressione Enter para continuar...")
        return

    print(f"\n📍 {ds_local_esc.strip().upper()} ({len(itens)} itens com saldo)")
    print("─" * 42)

    for it in itens:
        cd, desc, lote, saldo, dt_val, tp_un = it
        cod_limpo = formatar_codigo(cd)
        val_str = dt_val.strftime("%d/%m/%y") if dt_val else "--/--/--"
        peso_str = formatar_quantidade(saldo, tp_un)

        print(f"• [{cod_limpo}] {desc.strip()[:35]}")
        print(f"  Lote: {str(lote).strip()}")
        print(f"  Saldo: {peso_str:<10} | Val: {val_str}")
        print("  " + "┄" * 38)

    input("\nPressione Enter para voltar...")


def main():
    while True:
        print("\n" + "=" * 48)
        print("  ESTOQUE & LOCALIZACAO DE MATERIA-PRIMA")
        print("=" * 48)
        print("[1] Buscar Produto por Nome ou Codigo")
        print("[2] Listar Itens por Local de Estoque")
        print("[s] Sair")

        escolha = input("\nOpcao: ").strip().lower()

        if escolha == "s":
            print("\nSaindo...")
            break
        elif escolha == "2":
            con, _ = conectar()
            if con:
                menu_por_local(con)
                con.close()
            continue
        elif escolha != "1" and escolha != "":
            termo = escolha
        else:
            termo = input("\nProduto (Nome/Codigo) ou 'v' para voltar: ").strip()
            if termo.lower() == "v" or not termo:
                continue

        con, tipo_rede = conectar()
        if not con:
            continue
        cur = con.cursor()

        with IndicadorAtividade("Buscando produtos"):
            cur.execute(
                """
                SELECT 
                    p.CD_PRODUTO, 
                    p.DS_PRODUTO, 
                    COALESCE(p.TP_UNIDADE, '0') AS TP_UNIDADE,
                    COALESCE(p.CD_DCB, '') AS CD_DCB
                FROM T_PRODUTO p
                WHERE UPPER(p.DS_PRODUTO) LIKE UPPER(?) 
                   OR TRIM(CAST(p.CD_PRODUTO AS VARCHAR(20))) LIKE ?
                ORDER BY p.DS_PRODUTO
            """,
                (f"%{termo}%", f"%{termo}%"),
            )
            prods = cur.fetchall()

        if not prods:
            print("\n[!] Nenhum produto encontrado.")
            con.close()
            continue

        print("\n--- PRODUTOS ENCONTRADOS ---")
        for idx, p in enumerate(prods, 1):
            cod_limpo = formatar_codigo(p[0])
            sigla_u, _ = normalizar_unidade(p[2])
            print(f"[{idx:2d}] {cod_limpo} - {p[1]} [{sigla_u}]")

        sel_p = input("\nSelecione o produto (ou 'v' para voltar): ").strip()
        if sel_p.lower() == "v" or not sel_p.isdigit():
            con.close()
            continue

        idx_p = int(sel_p) - 1
        if idx_p < 0 or idx_p >= len(prods):
            con.close()
            continue

        cd_produto, ds_produto, tp_unidade, cd_dcb = prods[idx_p]
        sigla_u, divisor_u = normalizar_unidade(tp_unidade)

        while True:
            with IndicadorAtividade("Buscando lotes cadastrados"):
                cur.execute(
                    """
                    SELECT 
                        l.NR_LOTE, 
                        l.DT_RECEBIMENTO, 
                        l.QT_ESTOQUE, 
                        COALESCE(l.FT_DILUICAO, 1.000) AS FATOR,
                        l.DT_FABRICACAO, 
                        l.DT_VALIDADE,
                        COALESCE(loc.DS_LOCALIZACAO_LOTE, CAST(l.CD_LOCALIZACAO_LOTE AS VARCHAR(50))) AS NOME_LOCAL,
                        COALESCE(l.ID_LOTE_USO, 'N') AS ID_LOTE_USO,
                        COALESCE(f.NM_FORNECEDOR, 'NAO INFORMADO') AS NM_FORNECEDOR,
                        COALESCE(e.NR_DOCUMENTO, 0) AS NR_NF
                    FROM T_PRODUTO_LOTE l
                    LEFT JOIN T_LOCALIZACAO_LOTE loc ON loc.CD_LOCALIZACAO_LOTE = l.CD_LOCALIZACAO_LOTE
                    LEFT JOIN T_FORNECEDOR f ON f.CD_FORNECEDOR = l.CD_FORNECEDOR
                    LEFT JOIN T_ENTRADA_LOTE e ON e.CD_PRODUTO = l.CD_PRODUTO 
                                              AND e.NR_LOTE = l.NR_LOTE 
                                              AND CAST(e.DT_ENTRADA AS DATE) = CAST(l.DT_RECEBIMENTO AS DATE)
                    WHERE l.CD_PRODUTO = ?
                    ORDER BY l.DT_RECEBIMENTO DESC
                """,
                    (cd_produto,),
                )
                lotes = cur.fetchall()

            if not lotes:
                print("\n[!] Nenhum lote cadastrado para este produto.")
                break

            cod_produto_formatado = formatar_codigo(cd_produto)
            print(f"\n📦 {ds_produto} ({sigla_u}) [Cod: {cod_produto_formatado}]")
            print("─" * 42)

            saldo_total_bruto = 0.0
            for idx, l in enumerate(lotes, 1):
                (
                    nr_lote,
                    dt_rec,
                    saldo_val,
                    fator,
                    dt_fab,
                    dt_val,
                    nome_local,
                    id_lote_uso,
                    nm_fornecedor,
                    nr_nf,
                ) = l
                val_num = float(saldo_val or 0.0)
                saldo_total_bruto += val_num

                rec_str = dt_rec.strftime("%d/%m/%y") if dt_rec else "--/--/--"
                val_str = dt_val.strftime("%d/%m/%y") if dt_val else "--/--/--"
                peso_formatado = formatar_quantidade(val_num, tp_unidade)
                fator_formatado = formatar_fator(fator)

                local_exibicao = (
                    str(nome_local).strip()
                    if nome_local and str(nome_local).strip() not in ("None", "")
                    else "SEM LOCAL"
                )
                status_icone = "🟢" if val_num > 0 else "⚪"
                tag_uso = " ⭐ [EM USO]" if str(id_lote_uso).strip().upper() == "S" else ""

                nf_txt = (
                    str(int(nr_nf))
                    if isinstance(nr_nf, (int, float)) and nr_nf != 0
                    else str(nr_nf).split(".")[0]
                )

                print(f"[{idx:2d}] {status_icone} LOTE: {str(nr_lote).strip()}{tag_uso}")
                print(f"     LOCAL : {local_exibicao}")
                print(f"     SALDO : {peso_formatado}")
                print(f"     REC.  : {rec_str}  |  VAL.: {val_str}")
                print(f"     FORN. : {str(nm_fornecedor).strip()[:20]} | NF: {nf_txt}")
                print(f"     FATOR : {fator_formatado}")
                print("     " + "┄" * 35)

            print(
                f"\nTOTAL EM ESTOQUE: {formatar_quantidade(saldo_total_bruto, tp_unidade)}".upper()
            )
            print("=" * 48)

            sel_l = input("\nSelecione o lote (ou 'v' para voltar): ").strip()
            if sel_l.lower() == "v" or not sel_l.isdigit():
                break

            idx_l = int(sel_l) - 1
            if idx_l < 0 or idx_l >= len(lotes):
                print("Opcao invalida!")
                continue

            lote_sel = lotes[idx_l]
            (
                nr_lote,
                dt_rec,
                saldo_val,
                fator,
                dt_fab,
                dt_val,
                nome_local,
                id_lote_uso,
                nm_fornecedor,
                nr_nf,
            ) = lote_sel

            rec_formatada = dt_rec.strftime("%d/%m/%Y") if dt_rec else "SEM DATA"

            print(f"\n--- OPCOES PARA O LOTE: {nr_lote} (Rec: {rec_formatada}) ---")
            print("[1] Ajustar Saldo / Estoque deste lote")
            print("[2] Alterar Localizacao deste lote")
            print("[3] Imprimir Rotulo Padrao Magistral (Argox)")
            print("[4] Definir como Lote em Uso (Padrao)")
            print("[5] Renomear Materia-Prima (Corrigir Nome)")
            print("[v] Voltar para a lista de lotes")

            opcao = input("Opcao: ").strip().lower()

            if opcao == "1":
                novo_peso_txt = (
                    input(f"\nDigite a nova quantidade ({sigla_u}): ")
                    .strip()
                    .replace(",", ".")
                )
                try:
                    novo_val_usuario = float(novo_peso_txt)
                    novo_saldo_banco = novo_val_usuario * divisor_u
                    confirma = (
                        input(
                            f"Confirmar alteracao do lote {nr_lote} (Rec: {rec_formatada}) para {novo_val_usuario} {sigla_u}? (s/n): "
                        )
                        .strip()
                        .lower()
                    )

                    if confirma == "s":
                        with IndicadorAtividade("Atualizando estoque no banco"):
                            cur.execute(
                                """
                                UPDATE T_PRODUTO_LOTE 
                                SET QT_ESTOQUE = ? 
                                WHERE CD_PRODUTO = ? AND NR_LOTE = ? AND DT_RECEBIMENTO = ?
                            """,
                                (novo_saldo_banco, cd_produto, nr_lote, dt_rec),
                            )
                            con.commit()
                        print("✅ Estoque atualizado com sucesso!")
                    else:
                        print("Operacao cancelada.")
                except ValueError:
                    print("\n[✘] Formato numerico invalido.")

            elif opcao == "2":
                with IndicadorAtividade("Buscando locais disponiveis"):
                    cur.execute(
                        "SELECT CD_LOCALIZACAO_LOTE, DS_LOCALIZACAO_LOTE FROM T_LOCALIZACAO_LOTE ORDER BY DS_LOCALIZACAO_LOTE"
                    )
                    locais_cadastrados = cur.fetchall()

                if locais_cadastrados:
                    print("\n--- LOCAIS DISPONIVEIS ---")
                    for idx_loc, (c_loc, d_loc) in enumerate(locais_cadastrados, 1):
                        print(f"[{idx_loc:2d}] {d_loc.strip()}")

                    novo_idx = input("\nEscolha o numero do novo local: ").strip()
                    if novo_idx.isdigit():
                        p_idx = int(novo_idx) - 1
                        if 0 <= p_idx < len(locais_cadastrados):
                            cod_escolhido = locais_cadastrados[p_idx][0]
                            with IndicadorAtividade("Atualizando localizacao"):
                                cur.execute(
                                    """
                                    UPDATE T_PRODUTO_LOTE 
                                    SET CD_LOCALIZACAO_LOTE = ? 
                                    WHERE CD_PRODUTO = ? AND NR_LOTE = ? AND DT_RECEBIMENTO = ?
                                """,
                                    (cod_escolhido, cd_produto, nr_lote, dt_rec),
                                )
                                con.commit()
                            print("✅ Localizacao atualizada com sucesso!")
                else:
                    novo_local = input("\nDigite a nova localizacao: ").strip()
                    if novo_local:
                        with IndicadorAtividade("Atualizando localizacao"):
                            cur.execute(
                                """
                                UPDATE T_PRODUTO_LOTE 
                                SET CD_LOCALIZACAO_LOTE = ? 
                                WHERE CD_PRODUTO = ? AND NR_LOTE = ? AND DT_RECEBIMENTO = ?
                            """,
                                (novo_local, cd_produto, nr_lote, dt_rec),
                            )
                            con.commit()
                        print("✅ Localizacao atualizada!")

            elif opcao == "3":
                rec_argox = dt_rec.strftime("%d/%m/%y") if dt_rec else "--/--/--"
                fab_argox = dt_fab.strftime("%d/%m/%y") if dt_fab else "--/--/--"
                val_argox = dt_val.strftime("%d/%m/%y") if dt_val else "--/--/--"
                nf_limpa = (
                    str(int(nr_nf))
                    if isinstance(nr_nf, (int, float)) and nr_nf != 0
                    else str(nr_nf).split(".")[0]
                )

                qtd_input = input("\nQuantidade de copias [Padrao: 1]: ").strip()
                num_copias = (
                    int(qtd_input)
                    if qtd_input.isdigit() and int(qtd_input) > 0
                    else 1
                )

                enviar_ppla_argox(
                    tipo_rede_atual=tipo_rede,
                    nome_mp=ds_produto,
                    lote=nr_lote,
                    fator=formatar_fator(fator),
                    dt_rec=rec_argox,
                    dt_fab=fab_argox,
                    dt_val=val_argox,
                    fornecedor=str(nm_fornecedor).strip(),
                    nf=nf_limpa,
                    dcb=str(cd_dcb).strip(),
                    copias=num_copias,
                )

            elif opcao == "4":
                with IndicadorAtividade("Definindo lote padrao de uso"):
                    cur.execute(
                        "UPDATE T_PRODUTO_LOTE SET ID_LOTE_USO = 'N' WHERE CD_PRODUTO = ?",
                        (cd_produto,),
                    )
                    cur.execute(
                        """
                        UPDATE T_PRODUTO_LOTE 
                        SET ID_LOTE_USO = 'S' 
                        WHERE CD_PRODUTO = ? AND NR_LOTE = ? AND DT_RECEBIMENTO = ?
                    """,
                        (cd_produto, nr_lote, dt_rec),
                    )
                    con.commit()
                print(f"⭐ Lote {nr_lote} (Rec: {rec_formatada}) definido como EM USO!")

            elif opcao == "5":
                print(f"\nNome Atual: {ds_produto}")
                novo_nome = input("Digite o Novo Nome Oficial: ").strip().upper()
                if novo_nome:
                    conf = input(
                        f"Confirmar alteracao para '{novo_nome}'? (s/n): "
                    ).strip().lower()
                    if conf == "s":
                        with IndicadorAtividade("Atualizando nome da materia-prima"):
                            cur.execute(
                                "UPDATE T_PRODUTO SET DS_PRODUTO = ? WHERE CD_PRODUTO = ?",
                                (novo_nome, cd_produto),
                            )
                            con.commit()
                        ds_produto = novo_nome
                        print(f"✅ Materia-prima renomeada para: {novo_nome}")

        con.close()


if __name__ == "__main__":
    main()
