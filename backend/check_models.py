import google.generativeai as genai
import os

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    print(
        "Variável GOOGLE_API_KEY não definida. Execute: $env:GOOGLE_API_KEY = 'sua_chave'"
    )
else:
    genai.configure(api_key=API_KEY)
    for m in genai.list_models():
        print(m.name)
