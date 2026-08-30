# 💊 Magistral Inventory CLI & Thermal Printing System

Sistema em linha de comando (CLI) desenvolvido em Python para gestão em tempo real, auditoria e rastreabilidade de matérias-primas farmacêuticas integradas ao banco de dados Firebird. O projeto inclui impressão direta via socket raw em impressoras térmicas industriais Argox (PPLA) e roteamento de rede resiliente (Wi-Fi Local / VPN).

---

## 🎯 Principais Funcionalidades

- **Rastreabilidade Sanitária Rigorosa (ANVISA RDC 67/2007):**
  - Isolamento estrito de operações por Chave Composta: `(CD_PRODUTO, NR_LOTE, DT_RECEBIMENTO)`.
  - Controle preciso de fracionamentos internos e entregas parceladas do mesmo lote do fabricante.
- **Roteamento Dinâmico de Conexão:**
  - Fallback automático via *socket probe* entre rede Wi-Fi local e túnel remoto (VPN).
- **Impressão Térmica Direta (PPLA):**
  - Geração de código de comando PPLA enviado via TCP Raw Socket (porta 9100) para impressoras Argox, incluindo DCB, NF de entrada, fabricante, fator de correção e datas regulatórias.
- **Interface Otimizada para Mobile (Termux / Android):**
  - Visualização em cartões de 3 linhas que evitam quebra de texto em telas compactas.
  - Indicador de carregamento assíncrono (threads com *spinner animation*).
- **Gestão de Estoque e Localizações:**
  - Conversão automática de unidades (g, kg, mL, L, UI, un).
  - Consulta rápida de itens com saldo positivo agrupados por gaveta/armário.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.x
- **Banco de Dados:** Firebird SQL (via driver `firebirdsql` e autenticação com `passlib`)
- **Protocolos de Comunicação:** TCP/IP Raw Sockets (porta 3050 para banco e 9100 para impressora)
- **Linguagem de Impressão:** PPLA (Argox)
- **Ambiente de Execução:** Linux, Windows, macOS e Android (Termux)

---

## ⚙️ Instalação e Execução

### 1. Clonar o repositório:
```bash
git clone [https://github.com/Edinaldo-long/magistral-inventory-cli.git](https://github.com/Edinaldo-long/magistral-inventory-cli.git)
cd magistral-inventory-cli
