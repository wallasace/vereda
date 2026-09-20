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

## Painel de administração

Visão de tráfego e desempenho do servidor de sinalização — quantas salas
ativas, quantas pessoas, uso da cota gratuita da Cloudflare. Em aberto se
fica embutido no próprio app ou é uma página separada; a régua é pesar o
mais leve e prático de manter.

## ~~Escolha de dispositivo de áudio~~ — feito em 2026-09-20

Painel de configurações (`#config-veu`), acessível pela tela de entrada e por
um botão na barra durante a chamada. Troca de microfone usa `replaceTrack`
por conexão (ou `addTrack` para quem entrou sem microfone). Saída de som via
`setSinkId`, escondida quando o navegador não suporta (Safari e Firefox).

## ~~Volume e mudo por pessoa~~ — feito em 2026-09-20

Um botão em cada ficha (só nas dos outros, nunca na própria) cicla três
níveis: nítido, baixo, mudo. Mexe direto no `.volume` do elemento `<audio>`
daquela pessoa — voz e áudio da tela dela, se estiver apresentando — então é
puramente local: não manda nada pela rede, não afeta o que ninguém mais
ouve. Verificado com um oscilador de áudio sintético indo pela tela
compartilhada: o `.volume` do elemento real mudou 1 → 0,35 → 0 a cada
clique. Ainda não feito.

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
