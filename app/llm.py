import os

import ollama


def generate_mix_title(prompt: str, temperature: float = 0.1) -> str:
    """
    Генерирует название для микса на основе промпта через Ollama.
    """
    model_name = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

    system_prompt = (
        "You are a creative electronic music DJ. Your task is to invent "
        "a short, catchy and atmospheric name for a music mix "
        "(1-3 words max). CRITICAL: DO NOT use any of the artist names "
        "or track titles provided in the input. Instead, create a "
        "completely new name that fits the vibe (e.g., 'Midnight Pulse', "
        "'Neon Dreams'). Output ONLY the mix name, no quotes, no extra words."
    )

    try:
        response = ollama.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            options={
                "temperature": temperature,
                "num_predict": 25,  # Ограничиваем длину ответа
            },
        )

        # Извлекаем текст ответа и очищаем от кавычек
        title = response["message"]["content"].strip()
        title = title.strip('"').strip("'")
        return title

    except Exception as e:
        print(f"[Ollama Error] {type(e).__name__}: {e}")
        return "Midnight Mix (Fallback)"
