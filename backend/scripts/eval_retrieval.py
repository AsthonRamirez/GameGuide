"""Mide la calidad de la RECUPERACIÓN con un conjunto fijo de preguntas.

Para cada pregunta de tests/eval_questions.json verifica que al menos uno de los términos esperados
(`expect_any`) aparezca en el título, la URL o el contenido de los fragmentos recuperados.

    cd backend
    python -m scripts.eval_retrieval                  # solo recuperación (no gasta cuota de IA)
    python -m scripts.eval_retrieval --answers        # además genera respuesta y revisa los términos
    python -m scripts.eval_retrieval --csv resultados.csv

Úsalo antes y después de cada cambio (chunking, umbrales, modelo...) y compara con datos, no con impresiones.
Requiere internet (Wiki/Modrinth) y el modelo de embeddings; las respuestas requieren llave de IA.
"""
import argparse
import csv
import json
import time
from pathlib import Path

from app.services import gameguide as gg

QUESTIONS = Path(__file__).resolve().parents[1] / "tests" / "eval_questions.json"


def hit(chunks, terms):
    blob = " ".join(f'{c["title"]} {c["url"]} {c["content"]}' for c in chunks).lower()
    return any(t.lower() in blob for t in terms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", action="store_true", help="generar respuestas con la IA (consume cuota)")
    ap.add_argument("--csv", help="guardar resultados en CSV")
    ap.add_argument("--edition", default="Java Edition")
    ap.add_argument("--version", default="")
    args = ap.parse_args()

    items = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    rows, retrieval_hits, answer_hits = [], 0, 0
    for n, item in enumerate(items, 1):
        t0 = time.perf_counter()
        res = gg.retrieve_knowledge(item["question"], args.edition, args.version)
        retrieved_ok = hit(res.chunks, item["expect_any"])
        retrieval_hits += retrieved_ok
        answer_ok = ""
        if args.answers:
            answer, model = gg.generate_answer(item["question"], res.chunks, args.edition, args.version)
            answer_ok = model not in ("error", "sin_llamada") and hit([{"title": "", "url": "", "content": answer}], item["expect_any"])
            answer_hits += bool(answer_ok)
            time.sleep(1)  # respeta la cuota gratuita
        ms = int((time.perf_counter() - t0) * 1000)
        top = res.chunks[0]["title"] if res.chunks else "—"
        print(f"{n:>2}. {'OK ' if retrieved_ok else 'FALLA'} {ms:>5} ms  top={top[:35]:<35} | {item['question']}")
        rows.append({"question": item["question"], "retrieval_ok": retrieved_ok, "answer_ok": answer_ok,
                     "top_title": top, "n_chunks": len(res.chunks), "ms": ms, "debug": res.debug})

    total = len(items)
    print(f"\nRecuperación correcta: {retrieval_hits}/{total} ({retrieval_hits / total:.0%})")
    if args.answers:
        print(f"Respuesta con términos esperados: {answer_hits}/{total} ({answer_hits / total:.0%})")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("CSV guardado en", args.csv)


if __name__ == "__main__":
    main()
