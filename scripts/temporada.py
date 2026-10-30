"""
Coleta as estatísticas da temporada (por evento) e as próximas partidas.

Salva:
  data/temporada.json  — linhas de stats por evento (base das cartas e do preço)
  data/proximas.json   — próximas partidas do VCT Americas

Roda no workflow "Coletar rodada", com a vlrggapi ligada em 127.0.0.1:3001.

  python scripts/temporada.py --eventos 2682 2860 2977
"""

import argparse
import json
import re
import pathlib
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from coletar import buscar  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def segmentos(dados):
    if isinstance(dados, dict) and "segments" in dados:
        return dados["segments"]
    return dados if isinstance(dados, list) else []


PADRAO_2026 = re.compile(r"^(VCT 2026: Americas|Valorant Masters .*2026|Valorant Champions 2026)", re.I)


def eventos_do_ano():
    """Procura nos eventos concluídos os da temporada 2026: liga Americas, Masters e Champions."""
    achados = []
    for pagina in range(1, 6):
        try:
            time.sleep(3.5)
            lista = segmentos(buscar(f"/v2/events?q=completed&page={pagina}"))
        except Exception as e:
            print(f"Aviso: falhou a página {pagina} de eventos: {e}", file=sys.stderr)
            break
        if not lista:
            break
        for ev in lista:
            titulo = ev.get("title", "")
            if PADRAO_2026.search(titulo) and ev.get("event_id"):
                achados.append((str(ev["event_id"]), titulo))
    vistos, saida = set(), []
    for eid, t in achados:
        if eid not in vistos:
            vistos.add(eid)
            saida.append((eid, t))
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eventos", nargs="*", default=[], help="IDs fixos (somados aos encontrados)")
    ap.add_argument("--sem-busca", action="store_true", help="não procurar os eventos de 2026 automaticamente")
    ap.add_argument("--filtro-proximas", default="Americas",
                    help="trecho do nome do evento para as próximas partidas")
    a = ap.parse_args()

    alvo = {} if a.sem_busca else dict(eventos_do_ano())
    for e in a.eventos:
        if e:
            alvo.setdefault(e, "")
    print(f"Eventos da temporada: {alvo}", file=sys.stderr)

    eventos = []
    for i, (ev, titulo) in enumerate(alvo.items()):
        if i:
            time.sleep(3.5)
        print(f"Stats do evento {ev}...", file=sys.stderr)
        try:
            linhas = segmentos(buscar(f"/v2/stats?region=all&timespan=all&event_id={ev}"))
        except Exception as e:
            print(f"Aviso: falhou o evento {ev}: {e}", file=sys.stderr)
            continue
        eventos.append({"event_id": ev, "nome": titulo, "jogadores": linhas})
        print(f"  {len(linhas)} jogadores", file=sys.stderr)

    if eventos:
        (DATA / "temporada.json").write_text(json.dumps({
            "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "eventos": eventos,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    proximas = []
    try:
        time.sleep(3.5)
        for m in segmentos(buscar("/v2/match?q=upcoming")):
            evento = m.get("match_event", "")
            if a.filtro_proximas.lower() in evento.lower():
                proximas.append({k: m.get(k, "") for k in (
                    "team1", "team2", "match_event", "match_series", "unix_timestamp",
                    "time_until_match", "match_page")})
    except Exception as e:
        print(f"Aviso: não consegui ler as próximas partidas: {e}", file=sys.stderr)
    (DATA / "proximas.json").write_text(json.dumps({
        "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "partidas": proximas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(proximas)} próxima(s) partida(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
