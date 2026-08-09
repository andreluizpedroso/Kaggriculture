# Kaggriculture

Bot para a competição Kaggle [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture): uma simulação de fazenda em turnos onde dois jogadores competem, ao longo de uma temporada de 30 dias (720 turnos), pra terminar com mais dinheiro no banco. O ranking geral da competição é por skill rating (estilo Elo/Bradley-Terry) calculado ao longo de várias partidas — não por uma métrica de submissão única. Prêmios: $50.000 no total, 10 posições de $5.000.

**Status: submetido e ativo no leaderboard.**

## Abordagem

O agente combina uma rota de temporada em 5 fases (Bootstrap → Expand → Rotate & Compound → Protect Value → Cash) com decisões sensíveis ao mercado em tempo real — o que plantar/criar e a ordem de venda são decididos a cada turno a partir dos preços de mercado atuais (incluindo a fórmula de precificação exata do motor do jogo), não hardcoded.

### Estrutura do projeto

- `main.py` — arquivo único de submissão (gerado a partir de `src/`, ver `scripts/build_submission.py`)
- `src/agent.py` — lógica do agente
- `src/config.py` — tabela de economia do jogo e constantes ajustáveis
- `src/simulate.py` — harness de teste local contra agentes de referência
- `tests/` — testes unitários das funções de decisão

## Como rodar localmente

```bash
uv venv .venv
uv pip install --python .venv kaggle-environments pytest
```

> `pip install -U kaggle-environments` puro pode falhar dependendo da versão do `pip` (dependências extras como `open-spiel`/`pokerkit`). `uv` resolveu sem problemas neste projeto — ver PROGRESS.md.

Rodar os testes:

```bash
.venv/Scripts/python.exe -m pytest tests/
```

Rodar partidas locais contra os agentes `random` e `starter` (várias seeds, reporta saldo final e tempo por turno):

```bash
.venv/Scripts/python.exe -m src.simulate
```

## Links

- Competição: https://www.kaggle.com/competitions/kaggriculture
- Repositório: https://github.com/andreluizpedroso/Kaggriculture
