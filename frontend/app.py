"""Research Scout UI. Talks only to the FastAPI backend (Planning §18)."""

import os

import httpx
import streamlit as st

API = os.environ.get("API_BASE_URL", "http://localhost:8000") + "/api/v1"
api = httpx.Client(base_url=API, timeout=120)


def call(method: str, path: str, **kwargs):
    """Return parsed JSON, or show the API error and return None."""
    try:
        r = api.request(method, path, **kwargs)
    except httpx.HTTPError as e:
        st.error(f"Backend unreachable at {API}: {e}")
        return None
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        st.error(f"{r.status_code}: {detail}")
        return None
    return r.json()


def add_sources():
    st.subheader("Add a source")
    url_tab, post_tab = st.tabs(["Faculty / lab URL", "Social post (LinkedIn, Facebook)"])

    with url_tab, st.form("url"):
        url = st.text_input("Public page URL", placeholder="https://www.cs.toronto.edu/~someone/")
        if st.form_submit_button("Fetch, extract and enrich") and url:
            with st.status("Processing…", expanded=True) as status:
                st.write("Fetching page")
                ingested = call("POST", "/sources/ingest", json={"url": url})
                if not ingested:
                    status.update(label="Failed", state="error")
                    return
                st.write("Extracting with Gemini")
                extracted = call("POST", f"/sources/{ingested['source_id']}/extract")
                if not extracted:
                    status.update(label="Failed", state="error")
                    return
                st.write(f"Page type: **{extracted['page_kind']}** · "
                         f"{extracted['verified_fields']} verified, {extracted['unverified_fields']} unverified fields")
                for w in extracted["warnings"]:
                    st.warning(w)
                if extracted["professor_id"]:
                    st.write("Resolving identity on OpenAlex")
                    refreshed = call("POST", f"/professors/{extracted['professor_id']}/refresh")
                    if refreshed:
                        st.write(f"OpenAlex: **{refreshed['status']}** — {refreshed['reason']}")
                    st.session_state.selected = extracted["professor_id"]
                    status.update(label="Done", state="complete")
                else:
                    status.update(label="No single professor on this page", state="complete")

    with post_tab, st.form("post"):
        st.caption("Posts are saved as unverified leads. Confirm on the official university page before relying on them.")
        text = st.text_area("Post text")
        post_url = st.text_input("Post URL (optional, stored but never fetched)")
        if st.form_submit_button("Save lead") and text.strip():
            ingested = call("POST", "/sources/ingest", json={"text": text, "url": post_url or None})
            if ingested:
                extracted = call("POST", f"/sources/{ingested['source_id']}/extract")
                if extracted:
                    st.success(f"Lead saved ({extracted['page_kind']}); "
                               f"{extracted['verified_fields'] + extracted['unverified_fields']} claims recorded as unverified.")


def professor_detail(prof_id: str):
    p = call("GET", f"/professors/{prof_id}")
    if not p:
        return
    st.header(p["name"])
    st.caption(" · ".join(filter(None, [p["title"], p["email"]])))
    if p["faculty_url"]:
        st.markdown(f"[Faculty page]({p['faculty_url']})")
    if st.button("Refresh publications"):
        if call("POST", f"/professors/{prof_id}/refresh"):
            st.rerun()

    research, pubs, sources = st.tabs(["Research", "Publications", "Sources"])
    with research:
        st.markdown(f"**Research topics:** {p['research_summary'] or 'unknown'}")
        accepting = {True: "Yes (stated on page)", False: "No (stated on page)", None: "Not stated"}
        st.markdown(f"**Accepting students:** {accepting[p['accepting_students']]}")
        ids = [f"[OpenAlex](https://openalex.org/{p['openalex_id']})" if p["openalex_id"] else "OpenAlex: unresolved"]
        if p["orcid"]:
            ids.append(f"[ORCID](https://orcid.org/{p['orcid']})")
        st.markdown(" · ".join(ids))
    with pubs:
        if not p["publications"]:
            st.info("No publications linked yet. Use Refresh publications.")
        for pub in p["publications"]:
            link = pub["open_access_url"] or pub["url"]
            title = f"[{pub['title']}]({link})" if link else pub["title"]
            st.markdown(f"**{pub['publication_year'] or '—'}** · {title} · _{pub['author_position'] or ''} author_")
            if pub["abstract"]:
                with st.expander("Abstract"):
                    st.write(pub["abstract"])
    with sources:
        st.dataframe(
            [{"field": e["field_name"], "value": e["value"], "status": e["verification_status"], "quote": e["excerpt"]}
             for e in p["evidence"]],
            width="stretch", hide_index=True,
        )


def research_page():
    st.title("Research Scout")
    add_sources()
    st.divider()
    professors = call("GET", "/professors") or []
    if not professors:
        st.info("No professors yet. Add a faculty page above.")
        return
    names = {p["id"]: p["name"] for p in professors}
    ids = list(names)
    default = ids.index(st.session_state["selected"]) if st.session_state.get("selected") in names else 0
    prof_id = st.selectbox("Professor", ids, index=default, format_func=names.get)
    professor_detail(prof_id)


def lines(text: str) -> list[str]:
    return [x.strip() for x in text.replace(",", "\n").splitlines() if x.strip()]


def profile_page():
    st.title("Candidate profile")
    try:
        r = api.get("/profile")
        current = r.json() if r.status_code == 200 else {}
    except httpx.HTTPError as e:
        st.error(f"Backend unreachable at {API}: {e}")
        return
    prefs = current.get("funding_preferences", {})

    with st.form("profile"):
        name = st.text_input("Name", current.get("name", ""))
        interests = st.text_area("Research interests (one per line)", "\n".join(current.get("research_interests", [])))
        skills = st.text_area("Technical skills (one per line)", "\n".join(current.get("skills", [])))
        start = st.text_input("Intended start term", current.get("intended_start_term") or "", placeholder="Fall 2027")
        goals = st.text_area("Career goals", current.get("career_goals") or "")

        st.markdown("**Education**")
        education = st.data_editor(
            current.get("education") or [{"degree": "", "field": "", "university": "", "country": "",
                                          "graduation_year": None, "gpa": None, "gpa_scale": None}],
            column_order=["degree", "field", "university", "country", "graduation_year", "gpa", "gpa_scale"],
            num_rows="dynamic", width="stretch",
        )

        st.markdown("**Funding**")
        tuition = st.checkbox("Need tuition coverage", prefs.get("needs_tuition_coverage", True))
        stipend = st.checkbox("Need living stipend", prefs.get("needs_living_stipend", True))
        at_admission = st.checkbox("Funding must be confirmed at admission (needed for visa proof of funds)",
                                   prefs.get("requires_funding_at_admission", True))
        max_cost = st.number_input("Max unfunded cost (USD)", min_value=0.0,
                                   value=float(prefs.get("max_unfunded_cost_usd") or 0.0), step=1000.0)

        if st.form_submit_button("Save profile"):
            body = {
                "name": name,
                "research_interests": lines(interests),
                "skills": lines(skills),
                "intended_start_term": start or None,
                "career_goals": goals or None,
                "education": [row for row in education if row.get("degree") and row.get("university")],
                "experience": current.get("experience", []),
                "test_scores": current.get("test_scores", []),
                "funding_preferences": {
                    "needs_tuition_coverage": tuition,
                    "needs_living_stipend": stipend,
                    "requires_funding_at_admission": at_admission,
                    "max_unfunded_cost_usd": max_cost or None,
                },
            }
            if call("PUT", "/profile", json=body):
                st.success("Saved")


st.set_page_config(page_title="Research Scout", layout="wide")
st.navigation([
    st.Page(research_page, title="Research", icon=":material/school:"),
    st.Page(profile_page, title="Profile", icon=":material/person:"),
]).run()
