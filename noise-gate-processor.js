// Gate de ruído simples: acompanha o volume da entrada com um envelope
// suavizado e abaixa o ganho quando ninguém está falando, em vez de cortar
// pra zero — silêncio digital total soa mais estranho no ouvido do outro
// lado do que um resíduo bem baixo. Roda no thread de áudio (AudioWorklet),
// sem depender de biblioteca nenhuma.
class NoiseGateProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{ name: 'threshold', defaultValue: 0.018, minValue: 0.001, maxValue: 0.3, automationRate: 'k-rate' }];
  }

  constructor() {
    super();
    this.envelope = 0;
    this.ganho = 1;
    this.ativo = true;
    // Constantes de tempo convertidas pra coeficiente por amostra, na taxa
    // real do contexto — sem isto o gate reagiria diferente em 44,1kHz e 48kHz.
    this.coefEnvelope = 1 - Math.exp(-1 / (0.015 * sampleRate)); // quão rápido "percebe" o volume
    this.coefAtaque = 1 - Math.exp(-1 / (0.008 * sampleRate));   // abre rápido quando alguém começa a falar
    this.coefLibera = 1 - Math.exp(-1 / (0.25 * sampleRate));    // fecha devagar, pra não cortar o fim da palavra
    this.GANHO_MINIMO = 0.06;
    this.port.onmessage = (evento) => {
      if (evento.data && typeof evento.data.ativo === 'boolean') this.ativo = evento.data.ativo;
    };
  }

  process(entradas, saidas, parametros) {
    const entrada = entradas[0];
    const saida = saidas[0];
    if (!entrada || !entrada.length) return true;
    const limiar = parametros.threshold[0];
    for (let canal = 0; canal < entrada.length; canal++) {
      const inCanal = entrada[canal];
      const outCanal = saida[canal];
      if (!inCanal || !outCanal) continue;
      if (!this.ativo) { outCanal.set(inCanal); continue; }
      for (let i = 0; i < inCanal.length; i++) {
        const amostra = inCanal[i];
        this.envelope += (Math.abs(amostra) - this.envelope) * this.coefEnvelope;
        const alvo = this.envelope > limiar ? 1 : this.GANHO_MINIMO;
        const coef = alvo > this.ganho ? this.coefAtaque : this.coefLibera;
        this.ganho += (alvo - this.ganho) * coef;
        outCanal[i] = amostra * this.ganho;
      }
    }
    return true;
  }
}

registerProcessor('noise-gate', NoiseGateProcessor);
