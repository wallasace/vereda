# Sinalização do Vereda

Um Worker com um Durable Object por sala. Não toca na mídia — só repassa
ofertas, respostas, candidatos ICE e mensagens de texto.

## Publicar

```
npm install -g wrangler
wrangler login
wrangler deploy
```

Publicado em:

    https://vereda.wallasace.workers.dev

Esse endereço já está em `SIGNAL_DEFAULT`, no `index.html`. O subdomínio
`workers.dev` é um por conta, não por projeto: todos os Workers desta conta
moram embaixo dele.

## TURN (necessário para locais remotos)

Sem TURN, a chamada só fecha entre redes que aceitam conexão direta. Operadora
rural quase sempre usa CGNAT, onde isso falha. Em
**Cloudflare Dashboard → Realtime → TURN**, crie uma chave e guarde os dois
valores como segredos:

```
wrangler secret put TURN_KEY_ID
wrangler secret put TURN_KEY_API_TOKEN
```

Sem eles o app continua funcionando, só que apenas em rede amigável. Com eles,
`GET /ice` passa a devolver `"turn": true`.

## Custo

Plano gratuito: 100 mil requisições/dia, e mensagens de WebSocket contam 20:1.
Uma reunião de uma hora com dez pessoas gasta algumas centenas de requisições.
A hibernação mantém o objeto sem cobrança enquanto ninguém fala.
