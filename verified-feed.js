/* Public official notices: separate from the historical 821-post dashboard snapshot. */
(() => {
  "use strict";
  const anchor = document.getElementById("intro-notice");
  if (!anchor || document.getElementById("cheongma-verified-feed")) return;

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  const panel = el("details", undefined, "cm-verified-panel");
  panel.id = "cheongma-verified-feed";
  panel.setAttribute("aria-label", "전북 공식 게시물 별도 검증 현황");

  const head = el("summary", "전북 공식 게시물 · 검증 자료 연결 준비 중");
  const explanation = el("p",
    "이 영역은 전북특별자치도 공식 고시·공고 제목 검색에 한정됩니다. 기존 포털의 821건은 2026.10.28 시범 스냅샷입니다.",
    "cm-verified-description");
  const status = el("p", "검증된 공식 게시물 데이터 연결을 확인하는 중입니다.", "cm-verified-status");
  status.setAttribute("role", "status");
  const rows = el("div", undefined, "cm-verified-list");
  panel.append(head, explanation, status, rows);
  anchor.after(panel);

  function isOfficial(item) {
    if (!item || typeof item !== "object" || !/^S24_JEONBUK_GOSI:[0-9]+$/.test(item.id || "")) return false;
    if (typeof item.title !== "string" || !item.title.trim() || item.title.length > 500) return false;
    if (typeof item.published_at !== "string" || !/^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(item.published_at)) return false;
    try {
      const link = new URL(item.url);
      return link.protocol === "https:"
        && link.hostname === "www.jeonbuk.go.kr"
        && link.pathname === "/board/view.jeonbuk"
        && link.username === ""
        && link.password === ""
        && link.hash === ""
        && link.searchParams.get("boardId") === "BBS_0000129"
        && link.searchParams.get("dataSid") === item.id.split(":")[1];
    } catch (_) {
      return false;
    }
  }

  function isVerified(feed) {
    return !!feed && feed.schema_version === 1
      && feed.status === "verified"
      && feed.source_id === "S24_JEONBUK_GOSI"
      && feed.search_terms_verified === 9
      && feed.all_search_pages_verified === true
      && feed.original_body_and_attachments_verified === false
      && feed.legal_changes_confirmed === false
      && typeof feed.last_verified_kst === "string"
      && !Number.isNaN(Date.parse(feed.last_verified_kst))
      && Array.isArray(feed.records)
      && feed.records.length <= 1000
      && feed.records.length === feed.notice_count
      && feed.records.every(isOfficial)
      && new Set(feed.records.map(r => r.id)).size === feed.records.length;
  }

  fetch(new URL("./verified-notices.json", document.baseURI), {cache: "no-store"})
    .then(response => {
      if (!response.ok) throw new Error("Official verified feed unavailable");
      return response.json();
    })
    .then(feed => {
      if (feed && feed.schema_version === 1 && feed.status === "not_connected") {
        head.textContent = "전북 공식 게시물 · 자동 갱신 연결 준비 중";
        status.textContent =
          "기존 시범 자료는 정상 이용 가능합니다. 확인된 수집 결과를 공개용 자료로 안전하게 연결한 뒤 이 영역에 게시합니다.";
        return;
      }
      if (!isVerified(feed)) throw new Error("Invalid or incomplete verification evidence");
      head.textContent = "전북 공식 고시·공고 검증 · " + feed.notice_count + "건";
      status.textContent = "최종 확인: " + feed.last_verified_kst
        + " · 등록 검색어 9개와 해당 제목 검색의 전체 페이지 검증. 법규 개정 확정·원문 및 첨부 검증 완료가 아닙니다.";
      const fragment = document.createDocumentFragment();
      for (const item of feed.records.slice(0, 100)) {
        const row = el("div", undefined, "cm-verified-item");
        const link = el("a", item.title);
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        const date = el("span",
          item.published_at + " · " + (item.notice_no || "공고번호 미기재"),
          "cm-verified-date");
        row.append(link, date);
        fragment.append(row);
      }
      if (feed.records.length > 100)
        fragment.append(el("p", "처음 100건만 표시됩니다.", "cm-verified-description"));
      rows.replaceChildren(fragment);
    })
    .catch(() => {
      head.textContent = "전북 공식 게시물 · 검증 데이터 미연결";
      status.textContent =
        "공개 자료의 검증 상태를 확인할 수 없습니다. 기존 821건은 2026.10.28 시범 자료이며 최신 법규 확인으로 간주하면 안 됩니다.";
    });
})();
