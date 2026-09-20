# Backlog do Vereda

Coisas registradas para depois — nenhuma implementada ainda. Uma seção por
item, com o pedido original e por que importa.

## Moderação: um admin por sala

Quem cria a sala precisa de um jeito de se identificar como dona dela — hoje
todo mundo tem o mesmo poder — e, a partir disso, poder expulsar alguém e ter
controle total sobre a sala.

Implica autenticação, mesmo que leve (uma senha de sala, um token no link),
e um comando de moderação no protocolo do Worker (`kick`, por exemplo), com
o Durable Object aplicando a regra em vez de confiar no cliente.

## Painel de administração

Visão de tráfego e desempenho do servidor de sinalização — quantas salas
ativas, quantas pessoas, uso da cota gratuita da Cloudflare. Em aberto se
fica embutido no próprio app ou é uma página separada; a régua é pesar o
mais leve e prático de manter.

## Escolha de dispositivo de áudio

Selecionar o microfone e a saída de som, em vez de usar sempre o padrão do
sistema. `MediaDevices.enumerateDevices()` para a lista, `setSinkId()` para
trocar a saída (Safari ainda não suporta `setSinkId` até onde sei — checar de
novo quando for implementar).

## Volume e mudo por pessoa

Abaixar o volume de alguém especificamente ou mutá-lo do seu lado (mudo
local, sem afetar os outros participantes) — diferente do mudo que a própria
pessoa aplica em si.

## Escolha de resolução e taxa de quadros

Tanto para quem transmite a tela (resolução e fps de saída) quanto para quem
assiste (fps de entrada, se for possível pedir menos do que o remetente
manda). Hoje isso é fixo: 1280 de largura, 12fps, teto de banda dividido
entre os participantes — ver `ajustarBanda()` e `iniciarTela()` em
`index.html`.

## Investigar: apresentar tela pode pesar na máquina de quem apresenta

Relato de um usuário: o jogo dele ficou mais lento enquanto apresentava a
tela. Ainda não investigado diretamente — precisa dos dados da máquina dele
(CPU, se tem aceleração de hardware para o codificador) para confirmar.

Ligação plausível com a investigação de latência de vídeo de 2026-09-20: ali
ficou confirmado que codificar a 1080p consome CPU/GPU perceptível de quem
apresenta, e a captura foi reduzida para 1280 de largura por essa razão. Vale
conferir se isso já é suficiente ou se o relato pede algo mais — por exemplo,
detectar quando `qualityLimitationReason` do próprio remetente vira `'cpu'`
e reagir (baixar resolução automaticamente), em vez de só ter reduzido o teto
de partida.
