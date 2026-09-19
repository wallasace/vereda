// Vereda — sinalização.
//
// Dois trabalhos, e só esses dois: entregar a lista de servidores ICE e
// repassar mensagens entre quem está na mesma sala. A mídia (voz e tela) nunca
// passa por aqui — vai direto de um navegador para o outro. É o que mantém a
// conta perto de zero: o Worker só vê texto curto.
//
// Uma sala = um Durable Object, nomeado pelo código da sala. Quem entrar com o
// mesmo código cai no mesmo objeto, em qualquer lugar do mundo.

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
  'access-control-allow-headers': 'content-type',
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...CORS },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

    // O cliente pede os servidores ICE aqui em vez de trazê-los embutidos:
    // as credenciais do TURN são temporárias e não podem morar no HTML.
    if (url.pathname === '/ice') return json(await iceServers(env));

    const room = url.pathname.match(/^\/room\/([a-z0-9-]{1,64})$/i);
    if (room) {
      const id = env.ROOM.idFromName(room[1].toLowerCase());
      return env.ROOM.get(id).fetch(request);
    }

    return json({ error: 'not_found' }, 404);
  },
};

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

    // Numa conversa em andamento a sinalização fica calada por minutos, e
    // operadora de celular derruba TCP ocioso sem avisar: o navegador segue
    // achando que está na sala e não recebe mais nada. O cliente manda "ping",
    // e esta resposta automática sai sem acordar o Durable Object — mantém a
    // conexão viva e não conta como requisição cobrada.
    state.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
  }

  async fetch(request) {
    if (request.headers.get('upgrade') !== 'websocket') {
      return json({ error: 'expected_websocket' }, 426);
    }

    const sockets = this.state.getWebSockets();
    if (sockets.length >= this.cap) return json({ error: 'room_full', cap: this.cap }, 503);

    const url = new URL(request.url);
    const name = (url.searchParams.get('name') || 'alguém').slice(0, 40);
    const id = crypto.randomUUID().slice(0, 8);

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Hibernação: o Durable Object pode dormir entre mensagens sem derrubar as
    // conexões, e o tempo ocioso não é cobrado. O estado de cada participante
    // viaja anexado ao próprio socket para sobreviver a esse sono.
    this.state.acceptWebSocket(server);
    server.serializeAttachment({ id, name, muted: false, sharing: false });

    const peers = sockets.map((ws) => ws.deserializeAttachment()).filter(Boolean);

    server.send(JSON.stringify({ t: 'welcome', id, name, peers, cap: this.cap }));
    this.broadcast({ t: 'join', id, name, muted: false, sharing: false }, server);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws, raw) {
    const me = ws.deserializeAttachment();
    if (!me) return;

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
    }
  }

  webSocketClose(ws) {
    this.gone(ws);
  }

  webSocketError(ws) {
    this.gone(ws);
  }

  gone(ws) {
    const me = ws.deserializeAttachment();
    if (me) this.broadcast({ t: 'leave', id: me.id }, ws);
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
