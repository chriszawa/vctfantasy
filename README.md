# Fantasy VCT

Fantasy game do VCT Americas no estilo Cartola: pontuação rodada a rodada com dados do VLR.gg.

## Como funciona

- `index.html` — o site (menu, escalação, pontuação com regras editáveis, importação de séries).
- `.github/workflows/coletar.yml` — o workflow **Coletar rodada**: liga a [vlrggapi](https://github.com/axsddlr/vlrggapi) dentro do GitHub, baixa as séries e salva em `data/rodada.json`.
- `scripts/coletar.py` — o coletor usado pelo workflow.
- `scripts/rodada.py` — a mesma pontuação do site, em Python, para rodar no terminal.

## Atualizar a rodada

1. Aba **Actions** → **Coletar rodada** → **Run workflow**.
2. Informe o ID do evento (o número em `vlr.gg/event/ID/...`) e a semana, ex.: `Week 4`.
3. Em uns 2 minutos o site publicado mostra a rodada nova.

## Pontuação

Por mapa: ACS ÷ 10, morte −0,5, assistência +0,3, first kill +1, first death −1, KAST ≥ 75% +2, ADR ≥ 120 +1 / ≥ 150 +2.
Na série: média dos mapas × multiplicador de kills por round (1,0 → 1,1x; 1,2 → 1,2x) × multiplicador do resultado (2-0 1,25x; 2-1 1,15x; 1-2 1,05x; 0-2 1,00x).
Coach: média da série dos 5 jogadores × multiplicador do resultado.

## Admin

Abra `chriszawa.github.io/vctfantasy/#admin` (a aba não aparece no menu).
Conecte com um token do GitHub (fine-grained, só o repositório vctfantasy, permissão Contents: Read and write).
Lá dá para enviar a imagem de cada time e ajustar função, overall, preço, tag e atributos de cada jogador.
Os arquivos ficam em `data/times.json`, `data/times/` e `data/ajustes.json`.
