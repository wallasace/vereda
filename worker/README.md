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

## Painel (`/admin`)

Quantas salas e pessoas estão ativas agora, e quantas entradas desde sempre —
não muito mais que isso. Para requisições/dia, CPU e o resto da cota
gratuita, o [painel da própria Cloudflare](https://dash.cloudflare.com)
(Workers & Pages → vereda → Metrics) já mostra tudo isso, com mais precisão
do que valeria reproduzir aqui.

Precisa de um token, gerado uma vez e guardado só por você — não é secreto no
sentido de proteger dados sensíveis, é para o link não ficar aberto para
qualquer um que descubra o endereço:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))" | wrangler secret put ADMIN_TOKEN
```

Depois, o painel fica em `https://SEU-WORKER.workers.dev/admin?token=SEU-TOKEN`
(acrescente `&formato=json` para a versão sem HTML). Sem o segredo
configurado, a rota responde 501 em vez de expor qualquer coisa.

## Custo

Plano gratuito: 100 mil requisições/dia, e mensagens de WebSocket contam 20:1.
Uma reunião de uma hora com dez pessoas gasta algumas centenas de requisições.
A hibernação mantém o objeto sem cobrança enquanto ninguém fala.
