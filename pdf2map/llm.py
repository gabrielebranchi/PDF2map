"""Client minimale per Ollama (API HTTP locale, nessuna dipendenza oltre a requests)."""
from __future__ import annotations

import json
import re

import requests

_BASE_PROMPT = """You turn a passage of a document into a hierarchical concept map.

Rules:
- Write every title in the same language as the passage.
- Return ONLY JSON matching the given schema.
- "title" of the root: the main topic of the passage (max 8 words).
- Each node is a short noun phrase (max 8 words), never a full sentence.
- Use 3 to 5 children per node, only where the text supports them; fewer is fine.
- Deeper levels hold more specific concepts, definitions, examples, numbers or names from the text.
- "page" is the number N of the closest [p.N] marker where the concept appears.
- Use only information present in the passage. Do not invent anything."""

_EXPLAIN_PROMPT = """
- Every node except the root also has a "summary": 1 or 2 sentences (max 40 words) that explain the concept
  the way a teacher would, using SPECIFIC content from the passage: definitions, how it works, causes,
  numbers, names, examples.
- Never just repeat the title. Never write vague filler such as "this is an important concept" or
  "this section discusses". If the passage says nothing more about a node, leave its summary empty."""


_GROUP_PROMPT = """You organize a list of topics from a document into a table of contents.
The topics are numbered in document order.

Rules:
- Split the list into 3 to 7 chapters made of CONSECUTIVE topics.
  For each chapter give "start": the number of its first topic. The first chapter starts at 0.
- Chapter titles are short noun phrases (max 6 words), in the same language as the topics,
  describing what the topics of that chapter have in common.
- Do not invent topics."""

_GROUP_EXPLAIN = """
- Each chapter also has a "summary": one full sentence (max 30 words) saying what the chapter covers,
  not a list of keywords."""


def group_prompt(explain: bool = False) -> str:
    return _GROUP_PROMPT + (_GROUP_EXPLAIN if explain else "")


def group_schema(explain: bool = False) -> dict:
    props: dict = {"title": {"type": "string"}}
    if explain:
        props["summary"] = {"type": "string"}
    props["start"] = {"type": "integer"}
    return {
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "items": {"type": "object", "properties": props, "required": ["title", "start"]},
                "maxItems": 8,
            }
        },
        "required": ["chapters"],
    }


def system_prompt(explain: bool = False) -> str:
    return _BASE_PROMPT + (_EXPLAIN_PROMPT if explain else "")


def build_schema(depth: int, explain: bool = False) -> dict:
    """Schema JSON con annidamento a profondità fissa (gli schemi ricorsivi non sono affidabili)."""
    props: dict = {"title": {"type": "string"}}
    if explain:
        props["summary"] = {"type": "string"}
    props["page"] = {"type": "integer"}
    node: dict = {"type": "object", "properties": dict(props), "required": ["title"]}
    for _ in range(depth - 1):
        node = {
            "type": "object",
            "properties": {**props, "children": {"type": "array", "items": node, "maxItems": 5}},
            "required": ["title"],
        }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "children": {"type": "array", "items": node, "maxItems": 6},
        },
        "required": ["title", "children"],
    }


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


class OllamaClient:
    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434",
                 num_ctx: int = 8192, timeout: int = 600, temperature: float = 0.0, seed: int = 42):
        self.model, self.host, self.num_ctx, self.timeout = model, host.rstrip("/"), num_ctx, timeout
        self.temperature, self.seed = temperature, seed

    def list_models(self) -> list[str]:
        r = requests.get(f"{self.host}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def check(self) -> None:
        """Verifica che Ollama sia raggiungibile e che il modello sia scaricato."""
        try:
            names = self.list_models()
        except requests.RequestException as e:
            raise RuntimeError(
                f"Ollama non risponde su {self.host}. Avvialo con `ollama serve` "
                "(o apri l'app Ollama) e riprova."
            ) from e
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            raise RuntimeError(f"Modello '{self.model}' non trovato. Scaricalo con: ollama pull {self.model}")

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        """Risposta JSON dal modello. Con temperatura 0 e seed fisso lo stesso PDF dà (quasi sempre) la stessa mappa.

        Se la risposta non è JSON valido si riprova con seed diverso e un po' di temperatura:
        ripetere la stessa richiesta darebbe lo stesso errore.
        """
        last: Exception | None = None
        for attempt in range(3):
            r = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": schema,
                    "options": {
                        "temperature": self.temperature if attempt == 0 else max(self.temperature, 0.3),
                        "seed": self.seed + attempt,
                        "num_ctx": self.num_ctx,
                        "num_predict": 3500,
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            try:
                return _parse_json(r.json()["message"]["content"])
            except (json.JSONDecodeError, KeyError) as e:
                last = e
        raise last  # type: ignore[misc]
