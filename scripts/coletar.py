"""
Coleta as séries de uma rodada na vlrggapi e salva em data/rodada.json.

Roda dentro do GitHub Actions (workflow "Coletar rodada"), com a API ligada
em http://127.0.0.1:3001. Também funciona na sua máquina com a API ligada.

  python scripts/coletar.py --event-id 2501 --semana "Week 4"
  python scripts/coletar.py --matches 706375 706376
"""

import argparse
import json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", default="")
    ap.add_argument("--semana", default="", help='trecho do nome da semana, ex.: "Week 4"')
    ap.add_argument("--matches", nargs="*", default=[])
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
