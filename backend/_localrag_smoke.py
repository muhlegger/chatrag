"""Smoke test do pipeline RAG sem depender do Ollama.

Executa a cadeia LocalRetrievalQA com um retriever e um LLM mockados
para garantir que a lógica de orquestração está funcional.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from main import LocalRetrievalQA


@dataclass
class DummyDoc:
    page_content: str
    metadata: dict


class StubRetriever:
    def __init__(self) -> None:
        self.calls = []
        self._docs = [
            DummyDoc(
                page_content="Conteudo de teste RAG",
                metadata={"source": "dummy.pdf", "page": 0},
            )
        ]

    def invoke(self, question: str):
        self.calls.append(("sync", question))
        return self._docs

    async def ainvoke(self, question: str):
        self.calls.append(("async", question))
        return self._docs


def main() -> None:
    prompt = PromptTemplate(
        template="Pergunta: {question}\nContexto: {context}",
        input_variables=["context", "question"],
    )
    llm = RunnableLambda(lambda _: "Resposta sintetica (mock)")
    retriever = StubRetriever()
    chain = LocalRetrievalQA(retriever=retriever, prompt=prompt, llm=llm)

    sync_result = chain.invoke({"query": "Teste"})
    assert sync_result["result"].strip()
    assert sync_result["source_documents"]

    async_result = asyncio.run(chain.ainvoke({"query": "Teste async"}))
    assert async_result["result"].strip()
    assert len(retriever.calls) == 2

    print("localrag smoke ok")


if __name__ == "__main__":
    main()
