import { API_BASE } from "./env";
import type { DocumentModel, Section } from "./types";

const esc = (t: string) =>
  t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** 문서를 어디든 붙여 넣을 수 있는 단독 HTML 로. 이미지는 절대 주소로 박는다. */
export function documentToHtml(doc: DocumentModel): string {
  const body = doc.sections
    .filter((s) => s.visible !== false)
    .map(blockToHtml)
    .filter(Boolean)
    .join("\n    ");

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>${esc(doc.title)}</title>
<style>
  body { margin:0; background:#EDEDE8; font-family:Pretendard,system-ui,sans-serif; }
  .page { max-width:860px; margin:36px auto; padding:56px 64px; background:#F7F7F3;
          border:1px solid #DCDCD4; border-radius:4px; }
  .eyebrow { font-size:12px; letter-spacing:.22em; color:#8A8A80; }
  h1 { font-size:42px; line-height:1.34; color:#17171A; letter-spacing:-.02em; margin:0; }
  h2 { font-size:20px; color:#17171A; margin:10px 0 0; }
  p  { font-size:15px; line-height:1.85; color:#3A3A3F; }
  .sub { font-size:14px; color:#6A6A64; }
  .note { text-align:center; font-size:12px; color:#A0A098; }
  img { display:block; width:100%; border-radius:2px; }
</style>
</head>
<body>
  <div class="page">
    ${body}
  </div>
</body>
</html>`;
}

function blockToHtml(s: Section): string {
  const c = s.content;
  switch (s.type) {
    case "eyebrow":
      return `<p class="eyebrow">${esc(c.text ?? "")}</p>`;
    case "headline":
      return `<h1>${(c.lines ?? []).map(esc).join("<br>")}</h1>`;
    case "heading":
      return `<h2>${esc(c.text ?? "")}</h2>`;
    case "paragraph":
      return `<p>${esc(c.text ?? "")}</p>`;
    case "subclaim":
      return `<p class="sub">${esc(c.text ?? "")}</p>`;
    case "stat":
      return `<p>${esc(c.prefix ?? "")} <strong>${esc(c.value ?? "")}</strong> ${esc(c.suffix ?? "")}</p>`;
    case "image":
      return c.url ? `<img src="${API_BASE}${c.url}" alt="${esc(c.alt ?? "")}">` : "";
    case "note":
      return `<p class="note">${esc(c.text ?? "")}</p>`;
    default:
      return "";
  }
}

/** 브라우저에서 파일로 내려받게 한다. */
export function download(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** 파일명으로 못 쓰는 문자를 지운다. */
export function safeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, "").trim() || "document";
}
