// Vereda — sinalização.
//
// Dois trabalhos, e só esses dois: entregar a lista de servidores ICE e
// repassar mensagens entre quem está na mesma sala. A mídia (voz e tela) nunca
// passa por aqui — vai direto de um navegador para o outro. É o que mantém a
// conta perto de zero: o Worker só vê texto curto.
//
// Uma sala = um Durable Object, nomeado pelo código da sala. Quem entrar com o
// mesmo código cai no mesmo objeto, em qualquer lugar do mundo.

// O endereço do Worker é público — está embutido no HTML do app, que por sua
// vez está num repositório público. Sem checar de onde o pedido vem, qualquer
// site poderia apontar para cá e gastar a cota gratuita em nome desta conta.
//
// Vale a ressalva: isto barra reaproveitamento casual (alguém copiar o app e
// esquecer de trocar o servidor) e o app embutido em outro site, porque só um
// navegador de verdade manda um Origin que não dá para falsificar em nome de
// outro site. Não barra um script dedicado fora do navegador — esse pode
// simplesmente inventar o cabeçalho Origin que quiser. Contra isso, a defesa
// seria outra (token por sessão, limite de taxa), não uma checagem de Origin.
const ORIGENS_PADRAO = ['https://wallasace.github.io'];

function origensPermitidas(env) {
  const extra = (env.ORIGENS_EXTRA || '').split(',').map((o) => o.trim()).filter(Boolean);
  return new Set([...ORIGENS_PADRAO, ...extra]);
}

function origemPermitida(origem, env) {
  if (!origem) return false; // navegador sempre manda Origin nisto; sem ela, não é um navegador.
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origem)) return true; // desenvolvimento local
  return origensPermitidas(env).has(origem);
}

const corsHeaders = (origem) => ({
  'access-control-allow-origin': origem,
  'access-control-allow-methods': 'GET, POST, OPTIONS',
  'access-control-allow-headers': 'content-type',
  vary: 'origin', // a resposta muda conforme o Origin do pedido — não cacheável entre origens
});

const json = (body, status, origem) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...(origem ? corsHeaders(origem) : {}) },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // /admin é para você visitar direto pelo navegador, digitando o
    // endereço — não é o app chamando via fetch(). Uma navegação direta não
    // manda o mesmo Origin que uma chamada de dentro do app manda (às vezes
    // não manda Origin nenhum), então esta rota tem seu próprio cadeado —
    // um token, não a checagem de Origin que protege /ice e /room.
    if (url.pathname === '/admin') return admin(request, url, env);

    const origem = request.headers.get('origin');
    const permitida = origemPermitida(origem, env);

    if (request.method === 'OPTIONS') {
      return permitida
        ? new Response(null, { status: 204, headers: corsHeaders(origem) })
        : json({ error: 'origin_not_allowed' }, 403, null);
    }

    if (!permitida) return json({ error: 'origin_not_allowed' }, 403, null);

    // O cliente pede os servidores ICE aqui em vez de trazê-los embutidos:
    // as credenciais do TURN são temporárias e não podem morar no HTML.
    if (url.pathname === '/ice') return json(await iceServers(env), 200, origem);

    const room = url.pathname.match(/^\/room\/([a-z0-9-]{1,64})$/i);
    if (room) {
      const id = env.ROOM.idFromName(room[1].toLowerCase());
      return env.ROOM.get(id).fetch(request);
    }

    return json({ error: 'not_found' }, 404, origem);
  },
};

// Painel bem pequeno de propósito: quantas salas e pessoas agora, e quantas
// entradas desde sempre. Para requisições/dia, CPU e o resto da cota, o
// próprio painel da Cloudflare (Workers & Pages → vereda → Metrics) já
// mostra tudo isso de graça, com mais precisão do que eu reproduziria aqui —
// não faz sentido duplicar o que já existe e é mais confiável.
async function admin(request, url, env) {
  const token = url.searchParams.get('token') || (request.headers.get('authorization') || '').replace(/^Bearer\s+/i, '');
  if (!env.ADMIN_TOKEN) return json({ error: 'admin_nao_configurado' }, 501, null);
  if (token !== env.ADMIN_TOKEN) return json({ error: 'unauthorized' }, 401, null);
  if (!env.REGISTRO) return json({ error: 'registro_nao_configurado' }, 501, null);

  const id = env.REGISTRO.idFromName('global');
  const resposta = await env.REGISTRO.get(id).fetch('http://registro/');
  const dados = await resposta.json();

  if (url.searchParams.get('formato') === 'json') return json(dados, 200, null);

  const pagina = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vereda — painel</title>
<style>
  body{background:#101722;color:#e8eef7;font:15px/1.5 -apple-system,sans-serif;max-width:480px;margin:40px auto;padding:0 20px}
  h1{font-size:20px}
  .num{font-size:36px;font-weight:700;color:#7fb0ea}
  .linha{display:flex;justify-content:space-between;align-items:baseline;padding:14px 0;border-bottom:1px solid #2a3648}
  a{color:#7fb0ea}
</style></head><body>
<h1>Vereda — painel</h1>
<div class="linha"><span>Salas ativas agora</span><span class="num">${dados.salasAtivas}</span></div>
<div class="linha"><span>Pessoas conectadas agora</span><span class="num">${dados.pessoasAgora}</span></div>
<div class="linha"><span>Entradas desde sempre</span><span class="num">${dados.entradasTotais}</span></div>
<p style="color:#8494a9;font-size:13px;margin-top:24px">Requisições por dia, CPU e o resto da cota gratuita:
<a href="https://dash.cloudflare.com" target="_blank">painel da Cloudflare</a> → Workers &amp; Pages → vereda → Metrics.</p>
</body></html>`;
  return new Response(pagina, { headers: { 'content-type': 'text/html; charset=utf-8' } });
}

// STUN só descobre o seu endereço público; quando a operadora usa CGNAT — o
// caso comum fora das capitais — isso não basta e a chamada precisa do TURN
// para reencaminhar o tráfego. Sem as chaves configuradas o app ainda funciona,
// só que apenas entre redes que aceitam conexão direta.
async function iceServers(env) {
  const stunOnly = { iceServers: [{ urls: ['stun:stun.cloudflare.com:3478'] }], turn: false };

  if (!env.TURN_KEY_ID || !env.TURN_KEY_API_TOKEN) return stunOnly;

  try {
    const res = await fetch(
      `https://rtc.live.cloudflare.com/v1/turn/keys/${env.TURN_KEY_ID}/credentials/generate-ice-servers`,
      {
        method: 'POST',
        headers: {
          authorization: `Bearer ${env.TURN_KEY_API_TOKEN}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ ttl: 21600 }), // 6h: mais que qualquer reunião
      },
    );
    if (!res.ok) return stunOnly;
    const body = await res.json();
    return { iceServers: body.iceServers, turn: true };
  } catch {
    return stunOnly;
  }
}

export class Room {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.cap = Number(env.ROOM_CAP || 10);

    // Quanto tempo sem dar sinal de vida antes de a pessoa ser considerada
    // fora. O cliente manda "ping" a cada 25 s, então o padrão tolera três
    // perdidos. Vêm do ambiente para dar para testar a expulsão sem esperar.
    this.silencioMaximo = Number(env.SILENCIO_MAXIMO || 70_000);
    this.intervaloRonda = Number(env.INTERVALO_RONDA || 30_000);

    // A senha de admin da sala, se alguém já tiver definido uma. Guardada em
    // texto simples de propósito: a ameaça que isto evita é "qualquer um na
    // sala consegue expulsar os outros", não um invasor com acesso à conta
    // Cloudflare — para essa segunda coisa, hash não mudaria nada, porque quem
    // lê o storage já tem acesso a tudo.
    this.senhaAdmin = null;
    state.blockConcurrencyWhile(async () => {
      this.senhaAdmin = (await state.storage.get('senhaAdmin')) || null;
    });
  }

  async fetch(request) {
    if (request.headers.get('upgrade') !== 'websocket') {
      return json({ error: 'expected_websocket' }, 426);
    }

    const sockets = this.state.getWebSockets();
    if (sockets.length >= this.cap) return json({ error: 'room_full', cap: this.cap }, 503);

    const url = new URL(request.url);
    const name = (url.searchParams.get('name') || 'alguém').slice(0, 40);
    const senha = url.searchParams.get('senha') || '';
    const id = crypto.randomUUID().slice(0, 8);

    // Sem senha ainda na sala: quem chegar com uma a define e já entra como
    // admin. Com senha já definida: só quem digitar a mesma vira admin — dá
    // para dividir moderação, é só compartilhar a senha com um co-anfitrião.
    let admin = false;
    if (senha) {
      if (!this.senhaAdmin) {
        this.senhaAdmin = senha.slice(0, 100);
        await this.state.storage.put('senhaAdmin', this.senhaAdmin);
        admin = true;
      } else if (senha === this.senhaAdmin) {
        admin = true;
      }
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Hibernação: o Durable Object pode dormir entre mensagens sem derrubar as
    // conexões, e o tempo ocioso não é cobrado. O estado de cada participante
    // viaja anexado ao próprio socket para sobreviver a esse sono.
    const novaSala = sockets.length === 0;
    this.state.acceptWebSocket(server);
    server.serializeAttachment({ id, name, muted: false, sharing: false, admin, visto: Date.now() });
    await this.agendarRonda();
    await this.reportar('entrou', { novaSala });

    const peers = sockets.map((ws) => ws.deserializeAttachment()).filter(Boolean);

    server.send(JSON.stringify({ t: 'welcome', id, name, admin, temSenha: !!this.senhaAdmin, peers, cap: this.cap }));
    this.broadcast({ t: 'join', id, name, muted: false, sharing: false, admin }, server);

    return new Response(null, { status: 101, webSocket: client });
  }

  // O painel de tráfego é opcional — sem o binding REGISTRO configurado (a
  // maioria das cópias deste projeto não vai ter), a sala funciona
  // exatamente igual, só sem alimentar um contador que ninguém está olhando.
  async reportar(tipo, extra) {
    if (!this.env.REGISTRO) return;
    try {
      const id = this.env.REGISTRO.idFromName('global');
      await this.env.REGISTRO.get(id).fetch('http://registro/evento', {
        method: 'POST',
        body: JSON.stringify({ tipo, ...extra }),
      });
    } catch {
      // o painel é só um extra; uma falha aqui não pode derrubar a sala
    }
  }

  async webSocketMessage(ws, raw) {
    const me = ws.deserializeAttachment();
    if (!me) return;

    // Qualquer mensagem prova que a pessoa está viva; o ping serve para
    // provar isso quando não há mais nada a dizer.
    ws.serializeAttachment({ ...me, visto: Date.now() });

    if (raw === 'ping') {
      ws.send('pong');
      return;
    }

    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }

    switch (msg.t) {
      // Oferta, resposta e candidatos ICE de um par para outro. O servidor não
      // lê o conteúdo, só entrega no destinatário certo.
      case 'signal': {
        const target = this.state
          .getWebSockets()
          .find((s) => s.deserializeAttachment()?.id === msg.to);
        if (target) target.send(JSON.stringify({ t: 'signal', from: me.id, data: msg.data }));
        break;
      }

      case 'chat': {
        const text = String(msg.text ?? '').slice(0, 2000);
        if (!text.trim()) return;
        this.broadcast({ t: 'chat', from: me.id, name: me.name, text, ts: Date.now() });
        break;
      }

      case 'state': {
        const muted = !!msg.muted;
        const sharing = !!msg.sharing;

        // Uma tela por vez. Em malha, quem apresenta sobe uma cópia do vídeo
        // para cada participante; duas apresentações somadas estouram qualquer
        // link doméstico antes de a imagem ficar legível.
        if (sharing && !me.sharing) {
          const busy = this.state
            .getWebSockets()
            .some((s) => s !== ws && s.deserializeAttachment()?.sharing);
          if (busy) {
            ws.send(JSON.stringify({ t: 'error', code: 'share_busy' }));
            return;
          }
        }

        ws.serializeAttachment({ ...me, muted, sharing });
        this.broadcast({ t: 'state', id: me.id, muted, sharing });
        break;
      }

      // O admin vem do próprio servidor (serializeAttachment na entrada), não
      // do que o cliente alega — quem não é admin de verdade não consegue
      // forjar isto mandando {admin:true} na mensagem.
      case 'kick': {
        if (!me.admin || msg.id === me.id) return;
        const alvo = this.state.getWebSockets().find((s) => s.deserializeAttachment()?.id === msg.id);
        if (!alvo) return;
        const quemAlvo = alvo.deserializeAttachment();
        try { alvo.close(4001, 'expulso pelo admin'); } catch {}
        this.broadcast({ t: 'leave', id: quemAlvo.id, expulso: true });
        break;
      }
    }
  }

  // A ronda existe porque o fechamento limpo é o caso feliz. Aba morta, link
  // que caiu, celular que dormiu: nesses, o socket fica aberto do lado de cá e
  // a pessoa vira um fantasma que ninguém consegue expulsar — e que continua
  // ocupando uma das dez vagas.
  async alarm() {
    const limite = Date.now() - this.silencioMaximo;
    let restantes = 0;

    for (const ws of this.state.getWebSockets()) {
      const quem = ws.deserializeAttachment();
      if (quem && quem.visto > limite) { restantes++; continue; }
      try { ws.close(1001, 'sem sinal'); } catch {}
      if (quem) this.broadcast({ t: 'leave', id: quem.id }, ws);
    }

    if (restantes) await this.agendarRonda();
  }

  async agendarRonda() {
    if (await this.state.storage.getAlarm()) return;
    await this.state.storage.setAlarm(Date.now() + this.intervaloRonda);
  }

  async webSocketClose(ws) {
    await this.gone(ws);
  }

  async webSocketError(ws) {
    await this.gone(ws);
  }

  async gone(ws) {
    const me = ws.deserializeAttachment();
    if (!me) return;
    this.broadcast({ t: 'leave', id: me.id }, ws);
    // Único lugar que conta saídas: fechamento normal, expulsão e a ronda de
    // fantasmas passam todos por aqui (fechar um socket sempre dispara isto),
    // então contar em mais de um lugar contaria a mesma saída duas vezes.
    const salaVazia = this.state.getWebSockets().every((s) => s === ws);
    await this.reportar('saiu', { salaVazia });
  }

  broadcast(msg, except) {
    const payload = JSON.stringify(msg);
    for (const ws of this.state.getWebSockets()) {
      if (ws === except) continue;
      try {
        ws.send(payload);
      } catch {
        // socket já morto; o close handler limpa
      }
    }
  }
}

// Um único Durable Object, sempre com o mesmo nome ('global'), guardando só
// três números. Room chama /evento a cada entrada e saída; o painel em
// admin() lê o snapshot atual. Sem lista de salas nem de pessoas — só
// contagem, que é tudo que "leve, conveniente, prático e eficiente" pedia.
export class Registro {
  constructor(state) {
    this.state = state;
    this.dados = { salasAtivas: 0, pessoasAgora: 0, entradasTotais: 0 };
    state.blockConcurrencyWhile(async () => {
      this.dados = (await state.storage.get('dados')) || this.dados;
    });
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/evento') {
      const { tipo, novaSala, salaVazia } = await request.json();

      if (tipo === 'entrou') {
        this.dados.pessoasAgora++;
        this.dados.entradasTotais++;
        if (novaSala) this.dados.salasAtivas++;
      } else if (tipo === 'saiu') {
        this.dados.pessoasAgora = Math.max(0, this.dados.pessoasAgora - 1);
        if (salaVazia) this.dados.salasAtivas = Math.max(0, this.dados.salasAtivas - 1);
      }

      await this.state.storage.put('dados', this.dados);
      return new Response('ok');
    }

    return new Response(JSON.stringify(this.dados), {
      headers: { 'content-type': 'application/json' },
    });
  }
}
