"""
Coleta as séries de uma rodada na vlrggapi e salva em data/rodada.json.

Roda dentro do GitHub Actions (workflow "Coletar rodada"), com a API ligada
em http://127.0.0.1:3001. Também funciona na sua máquina com a API ligada.

  python scripts/coletar.py --event-id 2501 --semana "Week 4"
  python scripts/coletar.py --matches 706375 706376
"""

import argparse
import json
import re
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "http://127.0.0.1:3001"
SAIDA = pathlib.Path(__file__).resolve().parent.parent / "data" / "rodada.json"


def buscar(caminho, tentativas=4):
    url = f"{API}{caminho}"
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                corpo = json.load(r)
            if corpo.get("status") != "success":
                raise RuntimeError(f"Resposta inesperada: {corpo}")
            return corpo["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and n < tentativas - 1:
                espera = int(e.headers.get("Retry-After") or 20)
                print(f"Limite da API, esperando {espera}s...", file=sys.stderr)
                time.sleep(espera)
                continue
            raise
        except urllib.error.URLError:
            if n < tentativas - 1:
                time.sleep(5)
                continue
            raise


def baixar_html(mid):
    req = urllib.request.Request(f"https://www.vlr.gg/{mid}", headers={"User-Agent": "Mozilla/5.0 (fantasy-vct)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def salvar_html(mid, html):
    pasta = SAIDA.parent / "html"
    pasta.mkdir(exist_ok=True)
    (pasta / f"{mid}.html").write_text(html, encoding="utf-8")


def agentes_por_mapa(html):
    """{mapa: {jogador: agente}} lido da página do VLR.

    A vlrggapi procura o agente dentro da célula do jogador, mas o VLR hoje
    coloca o agente na célula ao lado (.ovw-cell.mod-agents), então ele vem vazio.
    """
    resultado = {}
    inicios = list(re.finditer(r'<div class="vm-stats-game[^"]*"\s+data-game-id="([^"]+)"', html))
    for i, ini in enumerate(inicios):
        if ini.group(1) == "all":
            continue
        fim = inicios[i + 1].start() if i + 1 < len(inicios) else len(html)
        bloco = html[ini.end():fim]
        nome = re.search(r'<div class="map-name">\s*<span[^>]*>\s*([^<]+?)\s*<', bloco)
        if not nome:
            continue
        jogadores = {}
        for linha in re.split(r'<div class="ovw-row"', bloco)[1:]:
            pn = re.search(r'class="ovw-player-name[^"]*">\s*([^<]+?)\s*<', linha)
            ag = re.search(r'mod-agents.*?<img[^>]*title="([^"]+)"', linha, re.S)
            if pn and ag:
                jogadores[pn.group(1)] = ag.group(1)
        resultado[nome.group(1)] = jogadores
    return resultado


def preencher_agentes(serie, html):
    mapa_agentes = agentes_por_mapa(html)
    faltando = 0
    for m in serie.get("maps", []):
        ags = mapa_agentes.get(m.get("map_name", ""), {})
        for lado in ("team1", "team2"):
            for p in (m.get("players") or {}).get(lado, []):
                if not p.get("agent"):
                    p["agent"] = ags.get(p.get("name", ""), "")
                    faltando += not p["agent"]
    if faltando:
        print(f"Aviso: {faltando} jogador(es) sem agente na série {serie.get('match_id')}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", default="")
    ap.add_argument("--semana", default="", help='trecho do nome da semana, ex.: "Week 4"')
    ap.add_argument("--matches", nargs="*", default=[])
    ap.add_argument("--salvar-html", action="store_true", help="guarda a página crua do VLR em data/html (diagnóstico)")
    a = ap.parse_args()

    ids = [m for m in a.matches if m]
    evento_nome = ""
    if a.event_id:
        jogos = buscar(f"/v2/events/matches?event_id={a.event_id}")["segments"]
        for m in jogos:
            rotulo = f'{m.get("stage", "")} {m.get("event_series", "")}'
            concluido = m.get("status", "").lower() == "completed"
            if concluido and (not a.semana or a.semana.lower() in rotulo.lower()):
                ids.append(m["match_id"])
        print(f"{len(ids)} série(s) concluída(s) encontrada(s).", file=sys.stderr)

    if not ids:
        sys.exit("Nenhuma série encontrada. Confira o ID do evento e o nome da semana.")

    series = []
    for i, mid in enumerate(dict.fromkeys(ids)):
        if i:
            time.sleep(3.5)  # limite de 20 req/min da API
        print(f"Baixando série {mid}...", file=sys.stderr)
        s = buscar(f"/v2/match/details?match_id={mid}")
        if isinstance(s, dict) and "segments" in s:  # formato real da API: {"segments": [serie]}
            s = s["segments"][0]
        try:
            html = baixar_html(mid)
            preencher_agentes(s, html)
            if a.salvar_html:
                salvar_html(mid, html)
        except Exception as e:  # sem agente a pontuação continua valendo; só a função vira Flex
            print(f"Aviso: não consegui ler os agentes da série {mid}: {e}", file=sys.stderr)
        evento_nome = evento_nome or (s.get("event") or {}).get("name", "")
        series.append(s)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({
        "rotulo": " · ".join(x for x in [evento_nome, a.semana] if x) or "Rodada",
        "event_id": a.event_id,
        "semana": a.semana,
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series": series,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Salvo em {SAIDA} ({len(series)} séries).", file=sys.stderr)


if __name__ == "__main__":
    main()
