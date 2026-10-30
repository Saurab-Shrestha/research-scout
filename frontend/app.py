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
    st.caption(" · ".join(filter(None, [p["university"], p["title"], p["email"]])))
    if p["faculty_url"]:
        st.markdown(f"[Faculty page]({p['faculty_url']})")
    refresh_col, page_col = st.columns(2)
    if refresh_col.button("Refresh publications"):
        if call("POST", f"/professors/{prof_id}/refresh"):
            st.rerun()
    if page_col.button("Find faculty page", disabled=bool(p["faculty_url"])):
        with st.spinner("Searching and verifying candidate pages (up to a minute)…"):
            found = call("POST", f"/professors/{prof_id}/find-page")
        if found:
            for a in found["attempts"]:
                st.write(f"`{a['result']}` {a['url']}")
            if found["status"] == "found":
                st.rerun()
            st.warning("No page could be verified for this professor.")

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
        st.info("No professors yet. Add a faculty page above or run a search on the Discover page.")
        return
    names = {p["id"]: f"{p['name']} — {p['university'] or 'unknown university'}" for p in professors}
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


AREAS = {"machine_learning": "Machine learning", "artificial_intelligence": "Artificial intelligence",
         "quantum_computing": "Quantum computing"}
STATUS_ICON = {"queued": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}


@st.fragment(run_every="3s")
def job_progress():
    recent = call("GET", "/research-jobs", params={"limit": 5}) or []
    if not recent:
        st.info("No searches yet.")
        return
    for job in recent:
        inputs = job["input"]
        if job["job_type"] == "evaluation":
            label = f"Evaluation of {len(inputs.get('professor_ids') or []) or 'all'} professors"
        else:
            label = ", ".join(AREAS.get(a, a) for a in inputs.get("research_areas", []))
        if inputs.get("query"):
            label = f"{label} + “{inputs['query']}”" if label else inputs["query"]
        with st.expander(f"{STATUS_ICON.get(job['status'], '')} {label} · {job['status']}",
                         expanded=job is recent[0]):
            for e in call("GET", f"/research-jobs/{job['id']}/events") or []:
                st.write(f"`{e['event_type']}` {e['message']}")
            if job["error_message"]:
                st.error(job["error_message"])
            result = job["result"] or {}
            if result.get("professor_ids"):
                profs = call("GET", "/professors", params={"ids": result["professor_ids"], "limit": 200}) or []
                st.dataframe(
                    [{"professor": p["name"], "university": p["university"], "title": p["title"],
                      "faculty page": p["faculty_url"]} for p in profs],
                    column_config={"faculty page": st.column_config.LinkColumn()},
                    width="stretch", hide_index=True,
                )


def discover_page():
    st.title("Discover")
    st.caption("Finds active researchers from OpenAlex publication data, then links their recent papers. "
               "Funding and openings are verified in a later step.")
    with st.form("discover"):
        areas = st.multiselect("Research areas", list(AREAS), default=["quantum_computing", "machine_learning"],
                               format_func=AREAS.get)
        query = st.text_input("Additional topic (optional)", placeholder="quantum machine learning")
        countries = st.multiselect("Countries", ["US", "CA"], default=["US", "CA"],
                                   format_func={"US": "USA", "CA": "Canada"}.get)
        degrees = st.multiselect("Degree types", ["phd", "thesis_masters", "course_masters"],
                                 default=["phd", "thesis_masters"],
                                 format_func={"phd": "PhD", "thesis_masters": "Thesis master's",
                                              "course_masters": "Course-based master's"}.get)
        max_results = st.slider("Max professors", 5, 100, 30, step=5)
        find_pages = st.checkbox("Find and verify faculty pages (about 1 minute per professor)", value=True)
        if st.form_submit_button("Start search"):
            if not areas and not query.strip():
                st.error("Pick a research area or enter a topic.")
            elif not countries:
                st.error("Pick at least one country.")
            elif call("POST", "/research-jobs", json={
                "research_areas": areas, "query": query or None, "countries": countries,
                "degree_types": degrees, "max_results": max_results, "find_pages": find_pages,
            }):
                st.success("Search queued. The worker picks it up within a few seconds.")
    st.subheader("Recent searches")
    job_progress()


FUNDING_LABEL = {"confirmed_full": "✅ Confirmed full", "confirmed_partial": "🟡 Confirmed partial",
                 "advertised_unverified": "⚠️ Advertised, unverified", "potential": "❔ Potential",
                 "unknown": "❔ Unknown", "unfunded": "❌ Unfunded"}
DEGREE_LABEL = {"phd": "PhD", "thesis_masters": "Thesis master's", "course_masters": "Course master's"}


def opportunity_detail(opp_id: str):
    d = call("GET", f"/opportunities/{opp_id}")
    if not d:
        return
    st.subheader(f"{d['professor']} · {d['university']}")
    st.caption(f"{d['program']} · {DEGREE_LABEL.get(d['degree_type'])} · score {d['overall_score']}")
    links = [f"[Faculty page]({d['faculty_url']})" if d["faculty_url"] else None,
             f"[Program page]({d['program_url']})" if d["program_url"] else None]
    st.markdown(" · ".join(filter(None, links)) or "No verified pages")
    if st.button("Save to tracker", key=f"track-{opp_id}"):
        if call("POST", "/applications", json={"opportunity_id": opp_id}):
            st.success("Saved. See the Tracker page for the suggested next step.")
    research, funding, elig, evidence, drafts = st.tabs(["Research fit", "Funding", "Eligibility", "Evidence", "Drafts"])
    with research:
        for m in d["explanation"].get("research_matches", []):
            st.markdown(f"**{m['interest']}** ↔ _{m['paper']}_ ({m['year']}) · similarity {m['similarity']}")
    with funding:
        st.markdown(f"**{FUNDING_LABEL.get(d['funding_status'])}** — {d['funding_explanation']}")
        if d["stipend"]:
            st.markdown(f"Stipend: **{d['stipend']}**")
    with elig:
        icon = {"ok": "✅", "warn": "⚠️", "unknown": "❔", "fail": "❌"}
        st.markdown(f"**{d['eligibility_status'].replace('_', ' ')}**")
        for c in d["explanation"].get("eligibility_checks", []):
            st.write(f"{icon[c['status']]} **{c['name']}** — {c['detail']}")
    with evidence:
        st.dataframe(d["program_evidence"], width="stretch", hide_index=True)
        for p in d["requirements"].get("pages", []):
            st.write(f"`{p['result']}` {p['url']}")
    with drafts:
        drafts_tab(opp_id)


def drafts_tab(opp_id: str):
    st.caption("Drafts are never sent. Edit, check the warnings, then send from your own email.")
    left, right = st.columns(2)
    for col, kind, label in ((left, "email", "Draft email to professor"), (right, "sop_outline", "Draft SOP outline")):
        if col.button(label, key=f"{kind}-{opp_id}"):
            with st.spinner("Writing…"):
                call("POST", f"/opportunities/{opp_id}/drafts", json={"kind": kind})
    for dr in call("GET", f"/opportunities/{opp_id}/drafts") or []:
        title = "Email" if dr["kind"] == "email" else "SOP outline"
        with st.expander(f"{title} · {dr['created_at'][:16].replace('T', ' ')}", expanded=False):
            for w in dr["warnings"]:
                st.warning(w)
            subject = st.text_input("Subject", dr["subject"], key=f"s-{dr['id']}") if dr["kind"] == "email" else None
            body = st.text_area("Body", dr["body"], height=320, key=f"b-{dr['id']}")
            if st.button("Save edits", key=f"save-{dr['id']}"):
                payload = {"body": body} | ({"subject": subject} if subject is not None else {})
                if call("PATCH", f"/drafts/{dr['id']}", json=payload):
                    st.success("Saved.")


def opportunities_page():
    st.title("Opportunities")
    st.caption("Ranking = 35% research fit + 25% funding + 20% eligibility + 10% availability + 10% timing. "
               "A prioritisation heuristic, not an admission prediction.")
    with st.expander("Evaluate professors (finds program pages, funding and deadlines; ~2 minutes per professor and degree)"):
        professors = call("GET", "/professors", params={"limit": 200}) or []
        chosen = st.multiselect("Professors (empty = all)", [p["id"] for p in professors],
                                format_func={p["id"]: f"{p['name']} — {p['university']}" for p in professors}.get)
        degrees = st.multiselect("Degree types", list(DEGREE_LABEL), default=["phd", "thesis_masters"],
                                 format_func=DEGREE_LABEL.get)
        if st.button("Start evaluation") and degrees:
            if call("POST", "/opportunities/evaluate", json={"professor_ids": chosen or None, "degree_types": degrees}):
                st.success("Evaluation queued. Progress appears on the Discover page under recent jobs.")

    c1, c2, c3 = st.columns(3)
    degree = c1.selectbox("Degree", [None, *DEGREE_LABEL], format_func=lambda d: "All" if d is None else DEGREE_LABEL[d])
    country = c2.selectbox("Country", [None, "US", "CA"], format_func=lambda c: c or "All")
    show_excluded = c3.checkbox("Show excluded (ineligible / unfunded)")
    params = {"include_excluded": show_excluded, **({"degree_type": degree} if degree else {}),
              **({"country": country} if country else {})}
    opps = call("GET", "/opportunities", params=params) or []
    if not opps:
        st.info("No scored opportunities yet. Run an evaluation above.")
        return
    st.dataframe(
        [{"score": o["overall_score"], "professor": o["professor"], "university": o["university"],
          "degree": DEGREE_LABEL.get(o["degree_type"]), "funding": FUNDING_LABEL.get(o["funding_status"]),
          "stipend": o["stipend"], "eligibility": o["eligibility_status"].replace("_", " "),
          "deadline": o["deadline"], "research": o["scores"]["research"], "excluded": o["excluded_reason"]}
         for o in opps],
        width="stretch", hide_index=True,
        column_config={"score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                       "research": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")},
    )
    labels = {o["id"]: f"{o['overall_score']:.0f} · {o['professor']} · {DEGREE_LABEL.get(o['degree_type'])}" for o in opps}
    opportunity_detail(st.selectbox("Details", list(labels), format_func=labels.get))


TRACKER_STATUSES = ["shortlisted", "researching", "contacted", "replied", "applying", "submitted",
                    "interview", "offer", "rejected", "declined", "withdrawn"]


def tracker_page():
    st.title("Application tracker")
    apps = call("GET", "/applications") or []
    if not apps:
        st.info("Nothing tracked yet. Use “Save to tracker” on the Opportunities page.")
        return
    today = __import__("datetime").date.today().isoformat()
    due = [a for a in apps if a["next_action_at"] and a["next_action_at"] <= today]
    c1, c2, c3 = st.columns(3)
    c1.metric("Tracked", len(apps))
    c2.metric("Actions due", len(due))
    c3.metric("Contacted", sum(a["contacted_at"] is not None for a in apps))

    rows = [{"id": a["id"], "professor": a["professor"], "university": a["university"],
             "degree": DEGREE_LABEL.get(a["degree_type"]), "status": a["status"], "next action": a["next_action"],
             "due": a["next_action_at"], "deadline": a["deadline"], "notes": a["notes"]} for a in apps]
    edited = st.data_editor(
        rows, hide_index=True, width="stretch", key="tracker",
        disabled=["id", "professor", "university", "degree", "deadline"],
        column_order=["professor", "university", "degree", "status", "next action", "due", "deadline", "notes"],
        column_config={"status": st.column_config.SelectboxColumn(options=TRACKER_STATUSES, required=True),
                       "due": st.column_config.DateColumn(), "deadline": st.column_config.DateColumn()},
    )
    if st.button("Save changes"):
        saved = 0
        for before, after in zip(rows, edited):
            patch = {}
            if after["status"] != before["status"]:
                patch["status"] = after["status"]
            if after["notes"] != before["notes"]:
                patch["notes"] = after["notes"] or ""
            if after["next action"] != before["next action"]:
                patch["next_action"] = after["next action"]
            if str(after["due"] or "") != str(before["due"] or ""):
                patch["next_action_at"] = str(after["due"])[:10] if after["due"] else None
            if patch and call("PATCH", f"/applications/{before['id']}", json=patch):
                saved += 1
        st.success(f"Saved {saved} change(s).")
        st.rerun()


st.set_page_config(page_title="Research Scout", layout="wide")
st.navigation([
    st.Page(discover_page, title="Discover", icon=":material/travel_explore:"),
    st.Page(opportunities_page, title="Opportunities", icon=":material/leaderboard:"),
    st.Page(tracker_page, title="Tracker", icon=":material/checklist:"),
    st.Page(research_page, title="Research", icon=":material/school:"),
    st.Page(profile_page, title="Profile", icon=":material/person:"),
]).run()
