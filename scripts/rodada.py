"""
Fantasy VCT — cálculo de pontuação de uma rodada.

Lê os dados da vlrggapi (rodando localmente) e calcula a pontuação de cada
jogador e de cada coach no modelo:

  Por mapa:
    ACS / 10
    morte -0,5 | assistência +0,3 | first kill +1 | first death -1
    KAST >= 75%  -> +2
    ADR >= 120   -> +1  |  ADR >= 150 -> +2

  Na série:
    média dos mapas jogados
    x multiplicador de kills por round (só se a pontuação for positiva)
    x multiplicador do resultado da série (só se a pontuação for positiva)

  Coach: média da série dos 5 jogadores do time x multiplicador do resultado.

Uso:
  python rodada.py --event-id 2501 --semana "Week 4"
  python rodada.py --matches 706375 706376
  python rodada.py --fixture exemplo.json        (teste offline)
"""

import argparse
import csv
import json
import sys
import time
import urllib.request

API_PADRAO = "http://127.0.0.1:3001"

# ---------------------------------------------------------------- regras ----

PESOS = {"morte": -0.5, "assistencia": 0.3, "fk": 1.0, "fd": -1.0}
KAST_MINIMO, KAST_BONUS = 75, 2
ADR_FAIXAS = [(150, 2), (120, 1)]           # (ADR mínimo, bônus), maior primeiro
KPR_FAIXAS = [(1.2, 1.2), (1.0, 1.1)]       # (kills por round mínimo, mult.)

MULT_SERIE = {
    # (mapas vencidos, mapas perdidos): multiplicador
    (2, 0): 1.25, (2, 1): 1.15, (1, 2): 1.05, (0, 2): 1.00,
    (3, 0): 1.30, (3, 1): 1.20, (3, 2): 1.15,
    (2, 3): 1.05, (1, 3): 1.00, (0, 3): 1.00,
}

# ------------------------------------------------------------- utilidades ---


def num(valor):
    """Converte '77%', '172.3', '+9', '' em número."""
    if valor is None:
        return 0.0
    s = str(valor).replace("%", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def buscar(api, caminho):
    url = f"{api}{caminho}"
    with urllib.request.urlopen(url, timeout=60) as r:
        corpo = json.load(r)
    if corpo.get("status") != "success":
        raise RuntimeError(f"Resposta inesperada de {url}: {corpo}")
    return corpo["data"]


def ids_da_semana(api, event_id, semana):
    dados = buscar(api, f"/v2/events/matches?event_id={event_id}")
    ids = []
    for m in dados["segments"]:
        rotulo = f'{m.get("stage", "")} {m.get("event_series", "")}'
        if semana.lower() in rotulo.lower() and m.get("status", "").lower() == "completed":
            ids.append(m["match_id"])
    return ids


# --------------------------------------------------------------- cálculo ----


def pontos_mapa(p):
    pts = num(p["acs"]) / 10
    pts += PESOS["morte"] * num(p["deaths"])
    pts += PESOS["assistencia"] * num(p["assists"])
    pts += PESOS["fk"] * num(p["fk"])
    pts += PESOS["fd"] * num(p["fd"])
    if num(p["kast"]) >= KAST_MINIMO:
        pts += KAST_BONUS
    adr = num(p["adr"])
    for minimo, bonus in ADR_FAIXAS:
        if adr >= minimo:
            pts += bonus
            break
    return pts


def faixa(valor, faixas):
    for minimo, mult in faixas:
        if valor >= minimo:
            return mult
    return 1.0


def calcular_serie(match):
    """Devolve (linhas de jogadores, linhas de coach, avisos) de uma série."""
    avisos = []
    times = [match["teams"][0]["name"], match["teams"][1]["name"]]
    mapas_jogados = [m for m in match["maps"] if m.get("players", {}).get("team1")]

    # placar de mapas da série
    vitorias = {times[0]: 0, times[1]: 0}
    for m in mapas_jogados:
        s1 = num(m["score"]["team1"]["total"])
        s2 = num(m["score"]["team2"]["total"])
        vitorias[times[0] if s1 > s2 else times[1]] += 1

    jogadores = {}  # nome -> dados acumulados
    for m in mapas_jogados:
        s1 = num(m["score"]["team1"]["total"])
        s2 = num(m["score"]["team2"]["total"])
        rounds = int(s1 + s2)
        for lado, time_nome in (("team1", times[0]), ("team2", times[1])):
            lista = m["players"][lado]
            if len(lista) != 5:
                avisos.append(f'{m["map_name"]}: {time_nome} com {len(lista)} jogadores')
            for p in lista:
                j = jogadores.setdefault(p["name"], {
                    "time": time_nome, "mapas": [], "kills": 0, "rounds": 0, "agentes": []})
                j["mapas"].append((m["map_name"], pontos_mapa(p)))
                j["kills"] += num(p["kills"])
                j["rounds"] += rounds
                j["agentes"].append(p.get("agent", ""))

    linhas = []
    for nome, j in jogadores.items():
        media = sum(x for _, x in j["mapas"]) / len(j["mapas"])
        kpr = j["kills"] / j["rounds"] if j["rounds"] else 0
        adversario = times[1] if j["time"] == times[0] else times[0]
        placar = (vitorias[j["time"]], vitorias[adversario])
        m_kill = faixa(kpr, KPR_FAIXAS)
        m_serie = MULT_SERIE.get(placar, 1.0)
        final = media * m_kill * m_serie if media > 0 else media
        linhas.append({
            "jogador": nome, "time": j["time"], "adversario": adversario,
            "placar": f"{placar[0]}-{placar[1]}",
            "agentes": "/".join(j["agentes"]),
            "mapas": " | ".join(f"{mp} {x:.2f}" for mp, x in j["mapas"]),
            "media_serie": round(media, 2), "kpr": round(kpr, 2),
            "mult_kill": m_kill, "mult_serie": m_serie, "final": round(final, 2),
        })

    coaches = []
    for t in times:
        do_time = [l for l in linhas if l["time"] == t]
        adversario = times[1] if t == times[0] else times[0]
        placar = (vitorias[t], vitorias[adversario])
        media = sum(l["media_serie"] for l in do_time) / len(do_time)
        m_serie = MULT_SERIE.get(placar, 1.0)
        coaches.append({
            "coach": t, "placar": f"{placar[0]}-{placar[1]}",
            "media_time": round(media, 2), "mult_serie": m_serie,
            "final": round(media * m_serie if media > 0 else media, 2),
        })
    return linhas, coaches, avisos


# ----------------------------------------------------------------- saída ----


def imprimir(jogadores, coaches):
    print(f'\n{"JOGADOR":<14}{"TIME":<18}{"PLACAR":<8}{"MÉDIA":>8}{"KPR":>7}'
          f'{"xKILL":>7}{"xSÉRIE":>8}{"FINAL":>9}')
    for l in sorted(jogadores, key=lambda x: -x["final"]):
        print(f'{l["jogador"]:<14}{l["time"][:17]:<18}{l["placar"]:<8}{l["media_serie"]:>8.2f}'
              f'{l["kpr"]:>7.2f}{l["mult_kill"]:>7.2f}{l["mult_serie"]:>8.2f}{l["final"]:>9.2f}')
    print(f'\n{"COACH":<32}{"PLACAR":<8}{"MÉDIA":>8}{"xSÉRIE":>8}{"FINAL":>9}')
    for c in sorted(coaches, key=lambda x: -x["final"]):
        print(f'{c["coach"][:31]:<32}{c["placar"]:<8}{c["media_time"]:>8.2f}'
              f'{c["mult_serie"]:>8.2f}{c["final"]:>9.2f}')


def salvar_csv(caminho, linhas):
    if not linhas:
        return
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)


def main():
    ap = argparse.ArgumentParser(description="Pontuação da rodada do Fantasy VCT")
    ap.add_argument("--api", default=API_PADRAO)
    ap.add_argument("--event-id")
    ap.add_argument("--semana", help='trecho do nome da semana, ex.: "Week 4"')
    ap.add_argument("--matches", nargs="*", default=[])
    ap.add_argument("--fixture", help="JSON salvo de /v2/match/details (lista ou objeto)")
    ap.add_argument("--saida", default="rodada")
    a = ap.parse_args()

    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            dados = json.load(f)
        series = dados if isinstance(dados, list) else [dados]
    else:
        ids = list(a.matches)
        if a.event_id:
            if not a.semana:
                sys.exit("Informe --semana junto com --event-id")
            ids += ids_da_semana(a.api, a.event_id, a.semana)
        if not ids:
            sys.exit("Nenhuma série encontrada.")
        series = []
        for i, mid in enumerate(ids):
            if i:
                time.sleep(3.5)  # respeita o limite de 20 req/min da API
            print(f"Buscando série {mid}...", file=sys.stderr)
            series.append(buscar(a.api, f"/v2/match/details?match_id={mid}"))

    todos_j, todos_c = [], []
    for s in series:
        j, c, avisos = calcular_serie(s)
        for av in avisos:
            print(f"AVISO ({s.get('match_id')}): {av}", file=sys.stderr)
        todos_j += j
        todos_c += c

    imprimir(todos_j, todos_c)
    salvar_csv(f"{a.saida}_jogadores.csv", todos_j)
    salvar_csv(f"{a.saida}_coaches.csv", todos_c)
    print(f"\nCSV salvos: {a.saida}_jogadores.csv e {a.saida}_coaches.csv")


if __name__ == "__main__":
    main()
