# Backlog do Vereda

Coisas registradas para depois — nenhuma implementada ainda. Uma seção por
item, com o pedido original e por que importa.

## ~~Moderação: admin com poder de expulsar~~ — feito em 2026-09-20

Senha opcional na entrada. Quem primeiro digitar uma a define para a sala e
já entra como admin; quem digitar a mesma depois também vira admin — dá para
dividir moderação com um co-anfitrião. Sem senha, a sala continua exatamente
como antes, sem ninguém admin.

A checagem é 100% do lado do servidor: o Durable Object marca `admin: true`
no momento da entrada e guarda isso anexado ao próprio WebSocket — o cliente
nunca é a fonte da verdade. Verificado tentando um não-admin expulsar alguém
via mensagem forjada: o servidor ignora, mesmo que a mensagem minta.

Expulsar fecha o WebSocket do alvo com o código 4001, que o cliente trata à
parte de uma queda de conexão normal: mostra "você foi removido" em tela
cheia e não tenta reconectar (reconectar devolveria a pessoa para a mesma
sala da qual acabou de sair). Verificado com o código chegando certo em
produção, incluindo a demora real da rede (não aparece em 800ms; aparece
dentro de uns 3s).

**O que isto não cobre, para ser honesto sobre o limite:** não é um banimento
de verdade. A sala continua sendo "quem tem o link, entra" — a pessoa
expulsa pode simplesmente entrar de novo pelo mesmo link, com uma conexão
nova e um id novo (não existe conta, não existe identidade estável entre
conexões para banir). Impedir isso de verdade pediria outra coisa — trocar o
link, ou uma lista de banidos por IP, que o Cloudflare também não facilita.
Não foi pedido "controle total" no sentido de travar a sala para novas
entradas — isso fica registrado como próximo passo natural, não como o que
foi entregue agora.

## ~~Painel de administração~~ — feito em 2026-09-20

Rota `/admin` no próprio Worker, protegida por token (`wrangler secret put
ADMIN_TOKEN`), mostrando salas ativas agora, pessoas conectadas agora e
entradas desde sempre. Documentado em `worker/README.md`.

Decisão de escopo: não duplica requisições/dia, CPU ou uso de cota — isso o
[painel da própria Cloudflare](https://dash.cloudflare.com) já mostra de
graça, com mais precisão do que eu reproduziria contando por fora. Construir
de novo o que já existe e é mais confiável não seria "leve" nem "eficiente".

Arquitetura: Cloudflare não lista Durable Objects existentes (uma sala = um
DO isolado, sem como enumerar todos), então um segundo DO (`Registro`, uma
única instância chamada `'global'`) é quem soma. Cada `Room` avisa `Registro`
ao ganhar o primeiro participante, ao receber cada entrada, e ao perder cada
saída — o ponto de saída é único (`gone()`, chamado por todo caminho de
desconexão: normal, expulsão, fantasma) para não contar a mesma saída duas
vezes. Opcional por natureza: sem o binding `REGISTRO` configurado, `Room`
segue funcionando igual, só sem alimentar um contador que ninguém está
olhando.

Verificado em produção com uma entrada e saída reais pelo app: painel foi de
0/0/0 para 1/1/1 e voltou para 0/0 (mantendo o acumulado em 1). Localmente,
onde o valor de partida carregava um resíduo de um teste anterior derrubado
à força, as variações bateram exatas em cada entrada e saída — o que importa
para confiar na lógica, já que o valor absoluto em produção nasce do zero.

Revisão de 2026-09-21, a pedido explícito ("quais salas ativas, usuários e
possibilidade de expulsar"): o painel passou a listar cada sala com seus
participantes por nome, com um botão "Expulsar" por pessoa. `Registro`
passou de três contadores soltos para `{ sala: { pessoas: [{id, nome}] } }`
— salas ativas e pessoas agora são sempre calculadas a partir dessa lista,
nunca contadas à parte, pra não desalinhar. O botão aciona uma rota nova
(`POST /admin/kick`) que chega direto no `Room` certo e fecha a conexão com
o mesmo código 4001 do kick de dentro da sala — só que disparado de fora,
com o token do painel, sem precisar estar entre os participantes. Testado
direto contra a produção com um cliente WebSocket cru: a pessoa expulsa
recebe o close 4001 de verdade e a sala some do painel assim que esvazia.

## ~~Escolha de dispositivo de áudio~~ — feito em 2026-09-20

Painel de configurações (`#config-veu`), acessível pela tela de entrada e por
um botão na barra durante a chamada. Troca de microfone usa `replaceTrack`
por conexão (ou `addTrack` para quem entrou sem microfone). Saída de som via
`setSinkId`, escondida quando o navegador não suporta (Safari e Firefox).

## ~~Volume e mudo por pessoa~~ — feito em 2026-09-20, revisado em 2026-09-21

Mexe direto no `.volume` do elemento `<audio>` daquela pessoa — voz e áudio
da tela dela, se estiver apresentando — então é puramente local: não manda
nada pela rede, não afeta o que ninguém mais ouve. Verificado com um
oscilador de áudio sintético indo pela tela compartilhada: o `.volume` do
elemento real mudou a cada ajuste.

Revisão de 2026-09-21: os três níveis fixos (nítido/baixo/mudo) viraram um
slider contínuo de 0–100% no menu de contexto, a pedido explícito. O botão
rápido na ficha virou mute/unmute de um clique, lembrando o nível anterior
para restaurar. O menu de contexto em si passou a abrir também com botão
direito na tela grande de quem está apresentando, não só na ficha pequena.

## ~~Escolha de resolução~~ — feito em 2026-09-20

Quem transmite escolhe a largura de captura (854/1280/1920) no painel de
configurações, aplicável também com a tela já aberta via
`track.applyConstraints()` quando o navegador permite. Quem assiste escolhe a
qualidade que quer receber daquela transmissão especificamente — um seletor
sobre o vídeo, que manda `{qualidadePedida: fator}` pelo canal de sinalização
já existente; o remetente aplica `scaleResolutionDownBy` só na conexão
daquele espectador. Verificado ponta a ponta: pedir "Leve" (fator 4) numa
fonte de 1920×1080 chegou como 480×270 do outro lado.

## ~~Escolha de taxa de quadros~~ — feito em 2026-09-20

Simétrico à escolha de resolução, no mesmo painel e no mesmo seletor sobre o
vídeo de quem assiste. Quem transmite escolhe entre 5/12/20fps; quem assiste
pode pedir menos (nunca mais) do que isso para aquela transmissão
especificamente. Verificado com números reais de `getStats()`: o padrão
mostrou 12fps de saída mesmo com a fonte fornecendo 24; pedir "Leve" (5)
mudou a entrada para exatamente 5fps; pedir mais do que o remetente escolheu
ficou preso no teto dele, como projetado.

Achado no caminho: o campo `framesPerSecond` do `getStats()` é uma média
suavizada e pode mostrar um número enganosamente baixo logo depois de trocar
os parâmetros de codificação — a contagem real de quadros (`framesEncoded`,
com o tempo entre duas leituras) é a fonte confiável.

## ~~Reconexão automática quando um par cai~~ — feito em 2026-09-20

Reportado em teste ao vivo com várias pessoas: uma conexão que falhava ou
desconectava (rede oscilou, NAT perdeu o mapeamento) ficava vermelha pelo
resto da chamada, sem nada tentando de novo — só sair e voltar da sala
resolvia, e isso também explicava casos de áudio unidirecional (um ouve, o
outro não). `onconnectionstatechange` passou de só reportar estado para
também tentar `pc.restartIce()` sozinho: espera um pouco se foi só
"disconnected" (costuma ser soluço passageiro), tenta na hora se foi
"failed", com o intervalo crescendo a cada nova falha.

Limite honesto: isto ajuda quedas transitórias, mas não resolve pares que
nunca conseguem se conectar via STUN puro (NAT simétrico, comum em rede
móvel/CGNAT) — a correção estrutural para esse caso é TURN, que este
projeto ainda não liga por padrão.

## ~~Cancelamento de ruído no microfone~~ — feito em 2026-09-20

Pedido em teste ao vivo: dava para ouvir muito nitidamente o som ambiente de
cada pessoa na sala o tempo todo, não só quando alguém falava. Um gate de
ruído (`AudioWorklet`, sem biblioteca nenhuma) abaixa o ganho do microfone
quando ninguém está falando, com um filtro passa-altas fixo para cortar
zumbido/estrondo grave. Controle num selo embaixo do botão de microfone:
liga/desliga e escolhe intensidade (Leve/Padrão/Forte), persistido por sala.

Testado com sinal sintético antes de publicar: ~40x de atenuação no
silêncio, passagem limpa na fala.

## ~~Anexar imagem no chat~~ — feito em 2026-09-20

Antes, a única forma de mandar imagem era colar um link (que já virava
cartão automaticamente — isso continua "nativo", sem botão dedicado). A
pedido explícito, o botão de imagem passou a abrir um seletor de arquivo de
verdade, e colar (Ctrl+V) uma imagem copiada no campo do chat também
anexa. Sem servidor de upload, a imagem é redimensionada e comprimida no
próprio navegador (máx. 1280px, JPEG) e viaja embutida como data-URL dentro
da mensagem — Worker e dev server validam formato e um teto de tamanho
(~450 KB) antes de repassar.

## ~~Efeitos sonoros, áudio geral e slider de volume~~ — feito em 2026-09-20

Três pedidos juntos: efeitos sonoros sintetizados na hora (osciladores
curtos via Web Audio, sem arquivo nenhum) para quando alguém entra/sai na
sala inteira, e para mutar/desmutar o microfone como feedback só de quem
clicou. Um botão "Áudio" na barra de chamada, ao lado do microfone, silencia
tudo que vem de fora com um clique (ensurdecer) sem mexer no volume
individual de ninguém — desligar guarda o volume de cada pessoa e volta
exatamente de onde estava ao religar.

## ~~Código de acesso obrigatório, com bloqueio de força bruta~~ — feito em 2026-09-21

Pedido explícito: sem um código que só o dono da sala distribui, ninguém
deveria conseguir entrar em sala nenhuma — só a home page fica visível. A
checagem de verdade é no Worker (`/ice` e `/room/*` exigem `?acesso=`
correto antes de responder qualquer coisa), não no cliente; sem
`SENHA_ACESSO` configurada, o gate fica desligado (uma cópia deste projeto
sem configurar nada continua funcionando como antes).

Revisão no mesmo dia, depois de uma auditoria de segurança pedida: nada
limitava quantas vezes alguém podia tentar adivinhar o código, e senhas
curtas (as pensadas para serem faladas/digitadas por humanos) são viáveis
de forçar por script. Um Durable Object por IP (`LimiteTaxa`) conta erros
seguidos e bloqueia por um tempo crescente a partir do 5º erro — a checagem
do bloqueio vem antes de olhar a senha, então nem revela se a tentativa
seria certa enquanto bloqueado. A senha de admin de sala ganhou o mesmo
tratamento, só que local ao `Room` (sem precisar de IP).

Decisão registrada: o link de convite continua sem o código embutido, de
propósito — embutir tornaria o link sozinho suficiente para entrar, e
quem recebe um link o encaminha muito mais fácil (e sem querer) do que uma
senha combinada à parte. Menos prático, mas mantém o dono da sala como
único ponto de controle de quem entra.

## Considerado e descartado: SFU pra tela compartilhada — 2026-09-21

O teto real da malha P2P (ver "Malha, e por quê" no README) é o upload de
quem apresenta a tela: uma cópia do vídeo por espectador, o que fica
pesado a partir de uns 5-6 pessoas assistindo. A ideia era trocar só o
transporte da tela compartilhada (nunca a voz, que já funciona bem em
malha até 10 pessoas) por um SFU — Cloudflare Realtime/Calls, mesmo
produto que já serve o TURN deste projeto, com 1000 GB grátis de egress
por mês.

Cheguei a montar o esqueleto: um Durable Object (`UsoSfu`) estimando uso e
cortando em 50% do teto grátis, com barra visível no painel de admin —
testado e funcionando (revertido junto com o resto). Não cheguei a mexer
na parte de verdade (publicar/assinar a tela via SFU, que reescreveria boa
parte do módulo `malha`), porque esbarrou antes: criar o App na Cloudflare
Realtime pediu cartão cadastrado, mesmo pra ficar dentro da faixa grátis —
e isso foi recusado explicitamente. Sem cartão, sem SFU.

Fica registrado pra não ser reproposto sem essa lembrança: se um dia isso
mudar (Cloudflare parar de exigir cartão pro tier grátis, ou o dono do
projeto decidir que tudo bem cadastrar um), o desenho já pensado (SFU só
pra tela, voz/chat intocados, freio de 50% de uso, fallback pra malha
quando o freio estourar ou o SFU não estiver configurado) continua valendo
como ponto de partida.

**Ainda não confirmado, mas relevante**: TURN usa o mesmo produto
(Cloudflare Realtime) — não dá pra garantir sem testar, mas é bem possível
que ligar TURN esbarre no mesmo pedido de cartão. Vale testar antes de
assumir que TURN é mais fácil de ligar só porque já estava mapeado antes.

## Investigar: apresentar tela pode pesar na máquina de quem apresenta

Relato de um usuário: o jogo dele ficou mais lento enquanto apresentava a
tela. Ainda não investigado diretamente — precisa dos dados da máquina dele
(CPU, se tem aceleração de hardware para o codificador) para confirmar.

Ligação plausível com a investigação de latência de vídeo de 2026-09-20: ali
ficou confirmado que codificar a 1080p consome CPU/GPU perceptível de quem
apresenta, e a captura foi reduzida para 1280 de largura por essa razão.

**Atualização 2026-09-20:** acrescentado um vigia (`vigiarCpu()`) que consulta
`qualityLimitationReason` da própria transmissão a cada 4s e mostra uma pílula
("qualidade reduzida (CPU)") quando o navegador está represando quadros por
falta de CPU. Isso dá visibilidade a quem apresenta, na própria máquina —
ainda não dá para eu confirmar de longe se resolve o caso do amigo, porque
depende do hardware dele. Continua em aberto: perguntar a ele se a pílula
aparece na próxima vez que isso acontecer, e se a queda de nitidez automática
(`degradationPreference: 'maintain-framerate'`, já em produção) foi suficiente
para o jogo não travar.

## Trancar a sala para novos entrantes

Poder natural de admin que ficou de fora do kick por escopo: parar de aceitar
gente nova sem precisar trocar o link. Barato de fazer — um campo a mais no
Durable Object (`trancada: bool`), um comando `{t:'trancar'}` só para admin,
e recusar `acceptWebSocket` com um erro claro quando estiver trancada.

## Do reskin de 2026-09-20 (interface nexo/knot, sem logo)

Ficou de fora por não ter dado real por trás no mock original — decorativo,
sem mecanismo de sincronizar entre participantes:

- **Foto de perfil e ícones de avatar predefinidos.** O mock guarda isso só
  localmente; mostrar sua escolha para os outros exigiria um jeito de
  compartilhar imagem entre participantes que o Vereda não tem hoje.
- **Título pessoal** (subtítulo abaixo do nome, tipo "Bom demais no CS").
  Simples de adicionar — um campo a mais no protocolo de entrada — só não
  foi pedido desta vez.
- **Busca dentro do chat.** Moderado, cliente-only, sem protocolo novo.

## Silenciar/ajustar volume remotamente

Diferente do volume local já implementado (que só muda o que VOCÊ ouve): o
admin poder abaixar ou mutar o áudio de alguém para TODOS na sala, não só
para si. Pediria um comando novo no protocolo (parecido com `kick`), com a
mesma verificação de admin no servidor.
