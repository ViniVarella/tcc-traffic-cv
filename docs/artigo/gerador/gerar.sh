#!/bin/zsh
# Gera "Artigo TCC - 2026-2.docx" na raiz do repositório a partir de artigo.js.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/Artigo TCC - 2026-2.docx"
cd "$(dirname "$0")" && node artigo.js "$ROOT" "$OUT" && zip -d "$OUT" '*/' >/dev/null 2>&1; true
