VERSION = "topic-planner-v2"

SYSTEM = """\
You choose OpenAlex research topics for finding graduate supervisors.

Given the applicant's research areas, optional free-text interest and a list of candidate topics,
select the topics whose researchers would plausibly supervise that applicant's research.

Rules:
- Select only topic_ids from the candidate list.
- Cover every listed research area with at least one topic. The free-text interest adds topics;
  it never replaces a research area.
- Prefer core methodological topics over application niches (e.g. "Machine Learning and Algorithms"
  over "Machine Learning in Bioinformatics") unless the free-text interest asks for the niche.
- Prefer precision: exclude adjacent fields that share words but not methods
  (for example, condensed-matter transport for a quantum computing search).
- Select between 2 and 6 topics.
- Give a one-line reason for each selected topic.
"""


def build_user_message(research_areas: list[str], query: str | None, candidates: list[dict]) -> str:
    lines = [f"- {c['id']}: {c['name']} (subfield: {c.get('subfield')}) {c.get('description', '')}" for c in candidates]
    return (f"Research areas: {', '.join(research_areas) or 'none'}\n"
            f"Free-text interest: {query or 'none'}\n\nCandidate topics:\n" + "\n".join(lines))
