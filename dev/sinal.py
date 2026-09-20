#!/usr/bin/env python3
"""Sinalização local, só para desenvolvimento.

Fala o mesmo protocolo do Worker (worker/src/index.js) para dar para testar a
malha sem publicar nada e sem Node instalado. Serve também os arquivos do app,
então um comando só levanta tudo:

    python3 dev/sinal.py              # http://localhost:8788
    python3 dev/sinal.py --tls        # https na rede local, para testar no celular

Com --tls ele gera um certificado próprio e escuta em todas as interfaces. O
navegador vai reclamar que o certificado é desconhecido — é mesmo, foi esta
máquina que o assinou. Aceitando o aviso, a página passa a valer como segura e
o microfone e a tela liberam.

Se TURN_KEY_ID e TURN_KEY_API_TOKEN estiverem no ambiente, /ice devolve as
credenciais reais da Cloudflare, do mesmo jeito que o Worker faz:

    TURN_KEY_ID=... TURN_KEY_API_TOKEN=... python3 dev/sinal.py --tls

Não use isto em produção: sem limite de abuso, sem autenticação, e fala
WebSocket no mínimo necessário para funcionar num navegador moderno.
"""

import base64, hashlib, json, os, re, socket, ssl, struct, subprocess, sys, threading, time, uuid, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CAP = 10
SILENCIO_MAXIMO = 70   # segundos sem sinal de vida até ser considerado fora
INTERVALO_RONDA = 30

salas = {}           # sala -> [conexão]
senhas = {}           # sala -> senha de admin, se alguém já tiver definido uma
trava = threading.Lock()


class Conexao:
    def __init__(self, sock, nome):
        self.sock, self.nome = sock, nome
        self.id = uuid.uuid4().hex[:8]
        self.mudo = self.apresentando = self.admin = False
        self.visto = time.time()
        self.envio = threading.Lock()

    def resumo(self):
        return {"id": self.id, "name": self.nome, "muted": self.mudo,
                "sharing": self.apresentando, "admin": self.admin}

    def _quadro(self, opcode, payload):
        cab = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            cab.append(n)
        elif n < 65536:
            cab.append(126); cab += struct.pack(">H", n)
        else:
            cab.append(127); cab += struct.pack(">Q", n)
        with self.envio:
            try:
                self.sock.sendall(bytes(cab) + payload)
            except OSError:
                pass

    def manda(self, obj):
        self._quadro(0x1, json.dumps(obj).encode())

    def fechar(self, codigo=1000, motivo=""):
        # Frame de fechamento de verdade, com código — sem isto o navegador do
        # outro lado recebe um encerramento genérico (1006) em vez do código
        # que diz por que foi desconectado, e o cliente não sabe diferenciar
        # "expulso" de "a rede caiu".
        self._quadro(0x8, struct.pack(">H", codigo) + motivo.encode("utf-8")[:123])
        # Um FIN limpo (não um RST): fecha só o lado de escrita, e dá um
        # instante para o quadro acima realmente sair pela rede antes de
        # qualquer coisa atrapalhar. Sem isto, o navegador às vezes via só um
        # encerramento abrupto (1006) e nunca chegava a ler o código 4001.
        time.sleep(0.05)
        try:
            self.sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def difunde(sala, obj, menos=None):
    with trava:
        alvos = [c for c in salas.get(sala, []) if c is not menos]
    for c in alvos:
        c.manda(obj)


SEM_TURN = {"iceServers": [{"urls": ["stun:stun.cloudflare.com:3478"]}], "turn": False}


def ice():
    """As mesmas credenciais que o Worker serve, para o teste entre redes
    diferentes valer alguma coisa: sem TURN, celular no 4G e computador no
    Wi-Fi de casa quase nunca se acham."""
    kid, token = os.environ.get("TURN_KEY_ID"), os.environ.get("TURN_KEY_API_TOKEN")
    if not kid or not token:
        return SEM_TURN
    try:
        req = urllib.request.Request(
            f"https://rtc.live.cloudflare.com/v1/turn/keys/{kid}/credentials/generate-ice-servers",
            data=json.dumps({"ttl": 21600}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return {"iceServers": json.loads(r.read())["iceServers"], "turn": True}
    except Exception as e:
        print(f"  ! TURN indisponível ({e}) — seguindo só com STUN", flush=True)
        return SEM_TURN


def certificado(pasta):
    """Um certificado assinado por esta máquina, válido para o IP de LAN. Não
    vale nada para o mundo; vale para o navegador liberar microfone e tela."""
    cert, chave = os.path.join(pasta, "dev-cert.pem"), os.path.join(pasta, "dev-key.pem")
    if os.path.isfile(cert) and os.path.isfile(chave):
        return cert, chave
    nomes = f"IP:{ip_local()},IP:127.0.0.1,DNS:localhost"
    base = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365",
            "-keyout", chave, "-out", cert, "-subj", "/CN=vereda-dev"]
    try:
        subprocess.run(base + ["-addext", f"subjectAltName={nomes}"],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # openssl antigo não conhece -addext; o mesmo pedido cabe num arquivo.
        conf = os.path.join(pasta, "dev-openssl.cnf")
        with open(conf, "w") as f:
            f.write("[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n"
                    "[dn]\nCN=vereda-dev\n[v3]\nsubjectAltName=" + nomes + "\n")
        subprocess.run(base + ["-config", conf], check=True, capture_output=True)
    print(f"  certificado gerado em {cert}", flush=True)
    return cert, chave


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Alça(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        caminho = self.path.split("?")[0]

        if caminho == "/ice":
            return self.json(ice())

        if caminho.startswith("/room/"):
            return self.websocket(caminho[len("/room/"):])

        return self.arquivo(caminho)

    # ---------------------------------------------------------------- HTTP

    def json(self, obj, status=200):
        corpo = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("content-length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def arquivo(self, caminho):
        rel = caminho.lstrip("/") or "index.html"
        destino = os.path.normpath(os.path.join(RAIZ, rel))
        if not destino.startswith(RAIZ) or not os.path.isfile(destino):
            return self.json({"error": "not_found"}, 404)
        tipos = {".html": "text/html", ".js": "text/javascript", ".json": "application/json",
                 ".webmanifest": "application/manifest+json", ".png": "image/png", ".css": "text/css"}
        with open(destino, "rb") as f:
            corpo = f.read()
        self.send_response(200)
        self.send_header("content-type", tipos.get(os.path.splitext(destino)[1], "application/octet-stream"))
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    # ---------------------------------------------------------------- WebSocket

    def websocket(self, sala):
        chave = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not chave:
            return self.json({"error": "expected_websocket"}, 426)

        aceite = base64.b64encode(hashlib.sha1((chave + GUID).encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", aceite)
        self.end_headers()

        nome, senha = "alguém", ""
        if "?" in self.path:
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.split("?", 1)[1])
            nome = qs.get("name", ["alguém"])[0][:40]
            senha = qs.get("senha", [""])[0]

        eu = Conexao(self.connection, nome)
        with trava:
            fila = salas.setdefault(sala, [])
            if len(fila) >= CAP:
                eu.manda({"t": "error", "code": "room_full"})
                return
            outros = [c.resumo() for c in fila]
            fila.append(eu)

            # Sem senha ainda: quem chegar com uma a define e já entra como
            # admin. Com senha já definida: só quem digitar a mesma vira
            # admin — dá para dividir moderação com um co-anfitrião.
            senha_atual = senhas.get(sala)
            if senha:
                if not senha_atual:
                    senhas[sala] = senha[:100]
                    eu.admin = True
                elif senha == senha_atual:
                    eu.admin = True
            tem_senha = bool(senhas.get(sala))

        eu.manda({"t": "welcome", "id": eu.id, "name": nome, "admin": eu.admin,
                  "temSenha": tem_senha, "peers": outros, "cap": CAP})
        difunde(sala, {"t": "join", **eu.resumo()}, menos=eu)
        print(f"  + {nome} ({eu.id}) em '{sala}' — {len(outros)+1} na sala", flush=True)

        try:
            while True:
                msg = self.quadro()
                if msg is None:
                    break
                self.trata(sala, eu, msg)
        except OSError:
            pass
        finally:
            with trava:
                if eu in salas.get(sala, []):
                    salas[sala].remove(eu)
                if not salas.get(sala):
                    salas.pop(sala, None)
                    senhas.pop(sala, None)  # sala esvaziou; a senha de admin não serve mais
            difunde(sala, {"t": "leave", "id": eu.id})
            print(f"  - {nome} ({eu.id}) saiu de '{sala}'", flush=True)

    def quadro(self):
        cab = self.rfile.read(2)
        if len(cab) < 2:
            return None
        op = cab[0] & 0x0F
        mascarado = cab[1] & 0x80
        n = cab[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self.rfile.read(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self.rfile.read(8))[0]
        chave = self.rfile.read(4) if mascarado else b"\0\0\0\0"
        dados = bytearray(self.rfile.read(n))
        for i in range(n):
            dados[i] ^= chave[i % 4]
        if op == 0x8:
            return None
        if op == 0x9:                       # ping -> pong
            self.connection.sendall(bytes([0x8A, len(dados)]) + bytes(dados))
            return {}
        if op != 0x1:
            return {}
        texto = dados.decode(errors="replace")
        if texto == "ping":
            self.connection.sendall(bytes([0x81, 4]) + b"pong")
            return {"t": "ping"}
        try:
            return json.loads(texto)
        except ValueError:
            return {}

    def trata(self, sala, eu, m):
        t = m.get("t")
        eu.visto = time.time()   # qualquer mensagem prova que está vivo
        if t == "ping":
            return
        if t == "signal":
            with trava:
                alvo = next((c for c in salas.get(sala, []) if c.id == m.get("to")), None)
            if alvo:
                alvo.manda({"t": "signal", "from": eu.id, "data": m.get("data")})

        elif t == "chat":
            texto = str(m.get("text", ""))[:2000]
            imagem = m.get("imagem")
            if not (isinstance(imagem, str) and len(imagem) <= 500000
                    and re.match(r"^data:image/(png|jpe?g|webp|gif);base64,", imagem)):
                imagem = None
            if texto.strip() or imagem:
                resposta_a = m.get("replyTo")
                reply_to = None
                if isinstance(resposta_a, dict):
                    reply_to = {"name": str(resposta_a.get("name", ""))[:40],
                                "text": str(resposta_a.get("text", ""))[:300]}
                # `time` já é importado no topo do arquivo; um import local
                # aqui tornaria o nome local à função inteira e quebraria o
                # `eu.visto = time.time()` de cima, derrubando a conexão a
                # cada mensagem — foi exatamente esse bug que apareceu aqui.
                difunde(sala, {"t": "chat", "from": eu.id, "name": eu.nome,
                               "text": texto, "ts": int(time.time() * 1000),
                               "replyTo": reply_to, "imagem": imagem})

        elif t == "digitando":
            difunde(sala, {"t": "digitando", "id": eu.id}, menos=eu)

        elif t == "state":
            quer = bool(m.get("sharing"))
            if quer and not eu.apresentando:
                with trava:
                    ocupado = any(c.apresentando for c in salas.get(sala, []) if c is not eu)
                if ocupado:
                    return eu.manda({"t": "error", "code": "share_busy"})
            eu.mudo = bool(m.get("muted"))
            eu.apresentando = quer
            difunde(sala, {"t": "state", "id": eu.id, "muted": eu.mudo, "sharing": eu.apresentando})

        elif t == "kick":
            # O admin vem do que o SERVIDOR marcou na entrada, não do que a
            # mensagem alega — mesma garantia do Worker.
            if not eu.admin or m.get("id") == eu.id:
                return
            with trava:
                alvo = next((c for c in salas.get(sala, []) if c.id == m.get("id")), None)
            if alvo:
                alvo.fechar(4001, "expulso pelo admin")
                difunde(sala, {"t": "leave", "id": alvo.id, "expulso": True})


def ronda():
    """Aba morta, link caído, celular que dormiu: nesses casos o socket fica
    aberto deste lado e a pessoa vira um fantasma que ocupa uma vaga. O mesmo
    que o alarme do Durable Object faz no Worker."""
    while True:
        time.sleep(INTERVALO_RONDA)
        limite = time.time() - SILENCIO_MAXIMO
        with trava:
            mortos = [(nome, c) for nome, fila in salas.items() for c in fila if c.visto < limite]
        for nome, c in mortos:
            print(f"  ! {c.nome} ({c.id}) sem sinal — removido de '{nome}'", flush=True)
            with trava:
                if c in salas.get(nome, []):
                    salas[nome].remove(c)
            try:
                c.sock.close()
            except OSError:
                pass
            difunde(nome, {"t": "leave", "id": c.id})


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tls = "--tls" in sys.argv
    porta = int(args[0]) if args else 8788

    # Sem TLS fica preso a esta máquina de propósito; com TLS o ponto é
    # justamente abrir para os outros aparelhos da rede.
    host = "0.0.0.0" if tls else "127.0.0.1"
    servidor = ThreadingHTTPServer((host, porta), Alça)

    if tls:
        pasta = os.path.dirname(os.path.abspath(__file__))
        cert, chave = certificado(pasta)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, chave)
        servidor.socket = ctx.wrap_socket(servidor.socket, server_side=True)
        endereco = f"https://{ip_local()}:{porta}"
    else:
        endereco = f"http://localhost:{porta}"

    threading.Thread(target=ronda, daemon=True).start()
    print(f"Vereda (dev) em {endereco}", flush=True)
    print(f"  TURN: {'configurado' if ice()['turn'] else 'ausente (só STUN)'}", flush=True)
    if tls:
        print("  Abra esse endereço no celular e aceite o aviso de certificado.", flush=True)
        print(f"  No campo Servidor do app, use o mesmo {endereco}", flush=True)
    print("  Ctrl+C para parar", flush=True)
    servidor.serve_forever()
