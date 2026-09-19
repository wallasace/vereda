<div align="center">

# Vereda

**Conversa por voz, texto e tela** — a mídia vai direto de um navegador para o
outro, sem passar por servidor nenhum.

[Abrir no navegador](https://wallasace.github.io/vereda/) ·
[Como publicar](#publicar) · [Quanto custa](#quanto-custa)

![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-7fb0ea.svg)
![Tamanho](https://img.shields.io/badge/app-36%20KB-4bc89a.svg)
![Sem build](https://img.shields.io/badge/build-nenhum-4bc89a.svg)

</div>

Um arquivo HTML, sem dependências e sem etapa de build. O servidor existe, mas
só entrega recados: quem fala com quem, e o texto do chat. A voz e a tela nunca
o atravessam.

## O que faz

- **Voz** para até 10 pessoas, com cancelamento de eco e anel de quem está falando
- **Texto**, com histórico da sessão
- **Tela compartilhada**, uma por vez, com taxa ajustada ao tamanho da sala
- **Sala por link**: quem abre o mesmo endereço cai no mesmo lugar
- Reconecta sozinho quando o link cai
- Instala como aplicativo pelo próprio navegador

## Como está montado

```
index.html        o app inteiro — interface, WebRTC, chat
worker/           sinalização: um Worker da Cloudflare, um Durable Object por sala
dev/sinal.py      o mesmo protocolo em Python, para desenvolver sem publicar nada
sw.js             cache da casca, para abrir rápido e sobreviver a link ruim
```

### Malha, e por quê

Cada pessoa mantém uma conexão direta com cada uma das outras. Para voz isso é
barato: nove faixas de 32 kbps somam menos de 0,3 Mbps de subida. Para tela não
é — quem apresenta sobe uma cópia do vídeo para cada participante, e com dez
pessoas isso passaria de 10 Mbps.

Daí as três defesas no código: **uma tela por vez**, **taxa dividida pelo número
de participantes** (`ajustarBanda`) e **`contentHint = 'detail'`**, que gasta os
bits em nitidez em vez de quadros por segundo — texto e slides precisam ser
lidos, não precisam ser fluidos.

A camada de mídia fica isolada no bloco `malha`, atrás de
`abrir/fechar/iniciarTela/pararTela`. Quando a malha ficar apertada, um SFU
entra ali sem tocar no resto do app.

### A conexão que morre calada

Depois que todo mundo conectou, a sinalização fica em silêncio — e operadora de
celular derruba TCP ocioso sem avisar ninguém. O `onclose` não dispara, e a
pessoa continua na sala sem receber mais nada.

O cliente manda `ping` a cada 25 s e reconecta se não vier `pong` em um minuto.
No Worker isso é `setWebSocketAutoResponse`, que responde **sem acordar o
Durable Object**: mantém a conexão viva e não conta como requisição cobrada.

### Negociação

Os dois lados podem fazer uma oferta ao mesmo tempo. Em vez de combinar de quem
é a vez, cada par recebe papéis opostos decididos pelo `id` da sessão: na
colisão, o lado "educado" cede e refaz. É o padrão *perfect negotiation* do
WebRTC, e é o que deixa a tela entrar e sair no meio da conversa sem travar.

## Desenvolver

Sem Node, sem instalar nada:

```bash
python3 dev/sinal.py
```

Abra `http://localhost:8788`, preencha **Servidor** com `http://localhost:8788`
e entre. Para testar com duas pessoas, abra a mesma URL em outra janela.

### Testar no celular, na mesma rede

Microfone e tela só são liberados em `localhost` ou sob HTTPS. Para alcançar
outro aparelho é preciso o segundo:

```bash
python3 dev/sinal.py --tls
```

Ele gera um certificado próprio para o IP desta máquina e escuta em toda a
rede local. O endereço sai no terminal. No celular, abra-o, **aceite o aviso de
certificado** — foi este computador que o assinou, o navegador tem razão em
desconfiar — e use o mesmo endereço no campo **Servidor**.

Vale só para a mesma rede Wi-Fi. Como os dois aparelhos estão atrás do mesmo
NAT, a conexão fecha direto e o TURN não faz falta.

### Com TURN, para testar entre redes diferentes

Celular no 4G e computador no Wi-Fi de casa quase nunca se acham sozinhos. Com
as chaves da Cloudflare no ambiente, o servidor de desenvolvimento serve as
mesmas credenciais que o Worker serviria:

```bash
TURN_KEY_ID=... TURN_KEY_API_TOKEN=... python3 dev/sinal.py --tls
```

A linha `TURN:` no início do terminal diz se pegou.

## Publicar

### 1. Sinalização (Cloudflare Workers)

Precisa de Node instalado.

```bash
cd worker
npm install -g wrangler
wrangler login
wrangler deploy
```

O endereço sai no final. Ele já está fixado em `SIGNAL_DEFAULT`, no topo do
`<script>` do `index.html`, e por isso o campo **Servidor** nem aparece na tela
inicial:

    https://vereda.vereda-sinalizacao.workers.dev

Ao trocar esse valor, qualquer endereço que um navegador tenha guardado de uma
publicação anterior é descartado — senão um endereço de teste sobreviveria à
publicação e apontaria para uma máquina que ninguém alcança.

### 2. TURN — o passo que faz funcionar no interior

Sem TURN, a chamada só fecha entre redes que aceitam conexão direta. Operadora
rural quase sempre usa CGNAT, onde isso falha. Em **Cloudflare Dashboard →
Realtime → TURN**, crie uma chave:

```bash
wrangler secret put TURN_KEY_ID
wrangler secret put TURN_KEY_API_TOKEN
```

O app mostra `sem TURN` no canto quando as chaves não estão configuradas.

### 3. O app (GitHub Pages)

Suba o repositório e ligue **Settings → Pages → Deploy from a branch → main**.
Não há build: o que está no repositório é o que vai para o ar.

## Quanto custa

| | Gratuito por mês | Dá para |
|---|---|---|
| Workers + Durable Objects | 100 mil requisições/dia | muito além de 10 pessoas |
| Cloudflare TURN | 1.000 GB | ~160 h de reunião |
| GitHub Pages | ilimitado para site estático | — |

Só o tráfego que passa pelo TURN é cobrado, e só depois dos 1.000 GB, a
US$ 0,05/GB. As conexões diretas — a maioria — não custam nada.

## Limites conhecidos

- **Uma tela por vez.** É uma decisão, não uma falta: duas apresentações em
  malha estouram o link antes de a imagem ficar legível.
- **Dez pessoas.** Acima disso a malha não se sustenta e o caminho é o SFU.
- **Sem webcam.** A tela foi o que se pediu primeiro; a câmera cabe no mesmo
  desenho quando fizer falta.
- **Sem gravação e sem histórico.** Fechou a aba, acabou o chat.

## Licença

MIT.
