# Sinalização do Vereda

Um Worker com um Durable Object por sala. Não toca na mídia — só repassa
ofertas, respostas, candidatos ICE e mensagens de texto.

## Publicar

```
npm install -g wrangler
wrangler login
wrangler deploy
```

O endereço sai no final (`https://vereda.SEU-SUBDOMINIO.workers.dev`). Cole-o
no campo **Servidor** da tela inicial do app, ou fixe-o em `index.html` na
constante `SIGNAL_DEFAULT`.

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
