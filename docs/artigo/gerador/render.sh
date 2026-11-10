#!/bin/zsh
# Exporta o .docx para PDF pelo próprio Word e mede cada página (altura final do
# conteúdo) e salva um PNG por página em docs/artigo/render/.
# Uso: docs/artigo/gerador/render.sh "Artigo TCC - 2026-2.docx"
DOCX="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
PDF="${DOCX%.docx}.pdf"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PNG_DIR="$ROOT/docs/artigo/render"
rm -f "$PDF"
rm -rf "$PNG_DIR" && mkdir -p "$PNG_DIR"
osascript <<OSA
tell application "Microsoft Word"
  open POSIX file "$DOCX"
  save as active document file name "$PDF" file format format PDF
  close active document saving no
end tell
OSA
"$ROOT/.venv/bin/python" - "$PDF" "$PNG_DIR" <<'PY'
import sys, pymupdf
d = pymupdf.open(sys.argv[1])
print("PAGINAS:", d.page_count)
for i, pg in enumerate(d):
    fim = max((b[3] for b in pg.get_text("blocks")), default=0)
    print(f"  pg{i+1}: conteudo termina em y={fim:.0f} de {pg.rect.height:.0f}")
    pg.get_pixmap(dpi=76).save(f"{sys.argv[2]}/pg{i+1:02d}.png")
PY
