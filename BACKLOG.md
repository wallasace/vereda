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

## ~~Escolha de dispositivo de áudio~~ — feito em 2026-09-20

Painel de configurações (`#config-veu`), acessível pela tela de entrada e por
um botão na barra durante a chamada. Troca de microfone usa `replaceTrack`
por conexão (ou `addTrack` para quem entrou sem microfone). Saída de som via
`setSinkId`, escondida quando o navegador não suporta (Safari e Firefox).

## Volume e mudo por pessoa

Abaixar o volume de alguém especificamente ou mutá-lo do seu lado (mudo
local, sem afetar os outros participantes) — diferente do mudo que a própria
pessoa aplica em si. Ainda não feito.

## ~~Escolha de resolução~~ — feito em 2026-09-20

Quem transmite escolhe a largura de captura (854/1280/1920) no painel de
configurações, aplicável também com a tela já aberta via
`track.applyConstraints()` quando o navegador permite. Quem assiste escolhe a
qualidade que quer receber daquela transmissão especificamente — um seletor
sobre o vídeo, que manda `{qualidadePedida: fator}` pelo canal de sinalização
já existente; o remetente aplica `scaleResolutionDownBy` só na conexão
daquele espectador. Verificado ponta a ponta: pedir "Leve" (fator 4) numa
fonte de 1920×1080 chegou como 480×270 do outro lado.

**Taxa de quadros continua sem escolha** — fixa em 12fps tanto para
transmitir quanto para assistir. Não foi pedido desta vez; seria simétrico
implementar (`frameRate` na captura, e um `maxFramerate` por conexão como já
existe para a escala).

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
