#!/usr/bin/env python3
"""Testes de fumaça do protocolo de sinalização (dev/sinal.py).

Sobe uma instância à parte (porta 8799, não mexe na que você já tem aberta
em 8788) e fala o protocolo bruto de WebSocket com ela — sem navegador, sem
Cloudflare, só pra pegar regressão no que o servidor decide sozinho:
entrada, saída, chat, admin de sala (com o bloqueio de tentativas) e o
gate de código de acesso.

    python3 dev/testes.py

Não substitui testar no navegador de verdade: WebRTC em si (voz, tela)
nunca passa pelo servidor de sinalização, só o sinal usado pra combinar a
ligação direta entre os navegadores — e o Worker de produção (Durable
Objects de verdade, LimiteTaxa por IP) tem suas próprias diferenças de
comportamento que só aparecem lá (já aconteceu nesta sala: getWebSockets()
depois de hibernar só funciona certo no objeto real).
"""

import base64, json, os, socket, struct, subprocess, sys, time, urllib.error, urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTA = 8799
HOST = "localhost"


class Cliente:
    def __init__(self, sala, nome, senha=None, acesso=None, porta=PORTA):
        self.sock = socket.create_connection((HOST, porta), timeout=5)
        self._sobra = b""
        chave = base64.b64encode(os.urandom(16)).decode()
        path = f"/room/{sala}?name={nome}"
        if senha is not None:
            path += f"&senha={senha}"
        if acesso is not None:
            path += f"&acesso={acesso}"
        pedido = (f"GET {path} HTTP/1.1\r\nHost: {HOST}:{porta}\r\n"
                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(pedido.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        cabeca, _, resto = resp.partition(b"\r\n\r\n")
        self.status_linha = cabeca.split(b"\r\n")[0].decode()
        self._sobra = resto
        self.aberto = " 101 " in self.status_linha

    def _recvall(self, n):
        b, self._sobra = self._sobra, b""
        while len(b) < n:
            pedaco = self.sock.recv(n - len(b))
            if not pedaco:
                break
            b += pedaco
        if len(b) > n:
            self._sobra, b = b[n:], b[:n]
        return b

    def receber(self, timeout=3):
        """Devolve o dict de uma mensagem, None se a conexão fechou (frame
        de close ou EOF), ou levanta socket.timeout se nada chegou a tempo."""
        self.sock.settimeout(timeout)
        cab = self._recvall(2)
        if len(cab) < 2:
            return None
        op = cab[0] & 0x0F
        n = cab[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recvall(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recvall(8))[0]
        dados = self._recvall(n)
        if op == 0x8:
            return None
        try:
            return json.loads(dados)
        except Exception:
            return dados

    def mandar(self, obj):
        payload = json.dumps(obj).encode()
        mascara = os.urandom(4)
        mascarado = bytes(b ^ mascara[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        if n < 126:
            cab = bytes([0x81, 0x80 | n])
        elif n < 65536:
            cab = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            cab = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(cab + mascara + mascarado)

    def fechar(self):
        try:
            self.sock.close()
        except OSError:
            pass


def sala_unica(prefixo):
    return f"{prefixo}-{int(time.time() * 1000)}"


# ---------------------------------------------------------------- testes

TESTES = []


def teste(nome):
    def decorador(fn):
        TESTES.append((nome, fn))
        return fn
    return decorador


@teste("entra e recebe welcome")
def _():
    c = Cliente(sala_unica("t1"), "Alice")
    assert c.aberto, f"handshake falhou: {c.status_linha}"
    m = c.receber()
    assert m["t"] == "welcome" and m["name"] == "Alice", m
    c.fechar()


@teste("segunda pessoa dispara join na primeira, saída dispara leave")
def _():
    sala = sala_unica("t2")
    a = Cliente(sala, "Alice"); a.receber()
    b = Cliente(sala, "Bruno"); b.receber()
    m = a.receber()
    assert m["t"] == "join" and m["name"] == "Bruno", m
    b.fechar()
    m = a.receber()
    assert m["t"] == "leave", m
    a.fechar()


@teste("chat: texto simples chega no outro lado")
def _():
    sala = sala_unica("t3")
    a = Cliente(sala, "Alice"); a.receber()
    b = Cliente(sala, "Bruno"); b.receber()
    a.receber()  # join do Bruno
    a.mandar({"t": "chat", "text": "oi"})
    m = b.receber()
    assert m["t"] == "chat" and m["text"] == "oi", m
    a.fechar(); b.fechar()


@teste("chat: imagem embutida chega, imagem grande demais é descartada")
def _():
    sala = sala_unica("t4")
    a = Cliente(sala, "Alice"); a.receber()
    b = Cliente(sala, "Bruno"); b.receber()
    a.receber()

    minipng = "data:image/png;base64," + base64.b64encode(b"x" * 20).decode()
    a.mandar({"t": "chat", "text": "", "imagem": minipng})
    m = b.receber()
    assert m["t"] == "chat" and m["imagem"] == minipng, m

    grande = "data:image/png;base64," + ("A" * 600000)
    a.mandar({"t": "chat", "text": "com imagem grande", "imagem": grande})
    m = b.receber()
    assert m["t"] == "chat" and m["text"] == "com imagem grande" and not m.get("imagem"), m
    a.fechar(); b.fechar()


@teste("admin: primeira senha define, mesma senha depois vira admin, errada não")
def _():
    sala = sala_unica("t5")
    dono = Cliente(sala, "Dono", senha="segredo")
    assert dono.receber()["admin"] is True

    coanfitriao = Cliente(sala, "Coanfitriao", senha="segredo")
    assert coanfitriao.receber()["admin"] is True

    fulano = Cliente(sala, "Fulano", senha="chute")
    assert fulano.receber()["admin"] is False

    dono.fechar(); coanfitriao.fechar(); fulano.fechar()


@teste("admin: bloqueia após tentativas erradas demais, mesmo com senha certa")
def _():
    sala = sala_unica("t6")
    dono = Cliente(sala, "Dono", senha="segredo")
    dono.receber()

    chutes = [Cliente(sala, f"Chute{i}", senha="chute") for i in range(5)]
    for c in chutes:
        m = c.receber()
        assert m["admin"] is False, m

    tarde_demais = Cliente(sala, "TardeDemais", senha="segredo")
    m = tarde_demais.receber()
    assert m["admin"] is False, f"deveria estar bloqueado mesmo com senha certa: {m}"

    dono.fechar()
    for c in chutes:
        c.fechar()
    tarde_demais.fechar()


@teste("kick: só admin consegue expulsar")
def _():
    sala = sala_unica("t7")
    dono = Cliente(sala, "Dono", senha="segredo")
    dono.receber()

    alvo = Cliente(sala, "Alvo")
    w_alvo = alvo.receber()
    dono.receber()  # join do Alvo

    fulano = Cliente(sala, "Fulano")
    fulano.receber()
    dono.receber(); alvo.receber()  # join do Fulano

    alvo_id = w_alvo["id"]

    fulano.mandar({"t": "kick", "id": alvo_id})
    try:
        m = alvo.receber(timeout=1)
        raise AssertionError(f"kick de não-admin não deveria ter efeito, mas chegou: {m}")
    except socket.timeout:
        pass  # esperado — nada aconteceu

    dono.mandar({"t": "kick", "id": alvo_id})
    resultado = alvo.receber(timeout=3)
    assert resultado is None, f"esperava a conexão fechar, veio mensagem: {resultado}"

    dono.fechar(); fulano.fechar()


@teste("sala cheia: quem tenta entrar a mais recebe erro claro, não silêncio")
def _():
    sala = sala_unica("t8")
    CAP = 10
    membros = [Cliente(sala, f"Pessoa{i}") for i in range(CAP)]
    for c in membros:
        assert c.aberto, f"handshake falhou: {c.status_linha}"
        c.receber()  # welcome

    extra = Cliente(sala, "OnzeAvo")
    assert extra.aberto, f"handshake deveria abrir mesmo pra recusar depois: {extra.status_linha}"
    m = extra.receber()
    assert m == {"t": "error", "code": "room_full"}, m
    fechou = extra.receber(timeout=2)
    assert fechou is None, f"esperava a conexão fechar em seguida, veio: {fechou}"

    for c in membros:
        c.fechar()
    extra.fechar()


def testar_gate_acesso():
    """Sobe uma segunda instância, só pra este teste, com SENHA_ACESSO
    configurada — testar isso na instância principal misturaria com todos
    os testes acima, que não passam código nenhum."""
    porta = PORTA + 1
    env = dict(os.environ, SENHA_ACESSO="segredo-de-teste")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(RAIZ, "dev", "sinal.py"), str(porta)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _esperar_servidor(porta)

        def pedir(acesso):
            url = f"http://{HOST}:{porta}/ice"
            if acesso is not None:
                url += f"?acesso={acesso}"
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        assert pedir(None) == 401, "sem código deveria recusar"
        assert pedir("errado") == 401, "código errado deveria recusar"
        assert pedir("segredo-de-teste") == 200, "código certo deveria passar"
        print("  OK  gate de acesso: sem código e código errado recusam, código certo passa")
        return True
    except Exception as e:
        print(f"  FALHOU  gate de acesso: {e}")
        return False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _esperar_servidor(porta, tentativas=30):
    for _ in range(tentativas):
        try:
            with socket.create_connection((HOST, porta), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"servidor não respondeu em localhost:{porta} a tempo")


def main():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(RAIZ, "dev", "sinal.py"), str(PORTA)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
    try:
        _esperar_servidor(PORTA)
        for nome, fn in TESTES:
            try:
                fn()
                print(f"  OK  {nome}")
            except Exception as e:
                ok = False
                print(f"  FALHOU  {nome}: {e}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    if not testar_gate_acesso():
        ok = False

    print()
    print("tudo passou" if ok else "teve teste que falhou")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
