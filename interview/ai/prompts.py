def build_question_generation_prompt(session, previous_questions=()):
    previous_questions_text = "\n".join(f"- {question}" for question in previous_questions) or "- None"
    return f"""
You are an expert technical interview coach.
Your job is to generate a short, personalized set of interview questions for a candidate preparing for a role.

System rules:
- Use only the candidate's actual resume, skills, role, experience, and job description.
- Do not invent experience or claim the candidate has skills they did not list.
- Keep questions relevant to the target role and progressively increase in difficulty.
- Do not repeat or lightly rephrase any question from the recent interview history. Choose different skills, scenarios, or decision-making angles.
- Return only valid JSON.
- Format: {{"questions": [{{"question": "...", "difficulty": "easy|medium|hard", "type": "technical|behavioral|practical|follow_up"}}]}}

Candidate profile:
- Friend name: {session.friend_name}
- Target role: {session.target_role}
- Experience level: {session.experience_level}
- Skills: {session.skills}
- Resume: {session.resume}
- Job description: {session.job_description}

Recent questions used in other sessions:
{previous_questions_text}

Generate 4 high-quality questions tailored to this candidate.
""".strip()


def build_answer_evaluation_prompt(session, question, answer):
    return f"""
You are an interview coach evaluating a candidate answer.
Evaluate the answer with honesty and helpfulness.

Candidate profile:
- Name: {session.friend_name}
- Target role: {session.target_role}
- Experience: {session.experience_level}
- Skills: {session.skills}
- Resume summary: {session.resume}
- Job description: {session.job_description}

Question:
{question.question}

Candidate answer:
{answer}

Return valid JSON only in this exact format:
{{
  "score": 0.0,
  "feedback": "short, constructive feedback",
  "strengths": "2-3 bullet-like phrases",
  "improvements": "2-3 actionable suggestions",
  "follow_up_question": "optional follow-up or null",
  "difficulty": "easy|medium|hard"
}}

Scoring guidance:
- 0-3: weak or off-topic
- 4-6: partially correct but limited depth
- 7-8: solid answer with clear understanding
- 9-10: strong, practical, and insightful

Do not invent experience. Be realistic.
""".strip()


def build_follow_up_prompt(session, question, answer):
    return f"""
You are a job interview coach.
Generate a single follow-up interview question that naturally continues the conversation based on the candidate's response.

Candidate profile:
- Name: {session.friend_name}
- Role: {session.target_role}
- Experience: {session.experience_level}
- Skills: {session.skills}

Current question:
{question.question}

Candidate answer:
{answer}

Return only valid JSON:
{{"question":"follow up question","difficulty":"easy|medium|hard","type":"follow_up"}}
""".strip()


def build_final_report_prompt(session, questions):
    question_summary = "\n".join(
        f"{index}. Q: {question.question}\n   Answer: {question.answer or 'No answer provided'}\n   Score: {question.score if question.score is not None else 'N/A'}"
        for index, question in enumerate(questions, start=1)
    )

    return f"""
You are a senior technical interview coach generating a final preparation report.

Use the candidate's actual profile and answers only. Do not claim experience that is not present.

Candidate profile:
- Name: {session.friend_name}
- Target role: {session.target_role}
- Experience: {session.experience_level}
- Skills: {session.skills}
- Resume: {session.resume}
- Job description: {session.job_description}

Interview history:
{question_summary}

Return valid JSON only in this exact format:
{{
  "overall_score": 0.0,
  "strengths": "comma-separated strengths",
  "weaknesses": "comma-separated weak areas",
  "recommended_topics": "comma-separated topic recommendations",
  "summary": "concise final summary"
}}
""".strip()
