import re

from .client import AIClientError, HuggingFaceClient
from .prompts import (
    build_answer_evaluation_prompt,
    build_final_report_prompt,
    build_follow_up_prompt,
    build_question_generation_prompt,
)
from ..models import InterviewQuestion, MAX_INTERVIEW_QUESTIONS


class AIService:
    _PLACEHOLDER_ANSWERS = {
        "",
        "na",
        "n a",
        "none",
        "not applicable",
        "skip",
        "idk",
        "i dont know",
        "dont know",
        "no idea",
        "unknown",
    }

    def __init__(self, client=None):
        self.client = client or HuggingFaceClient()

    def generate_questions(self, session) -> list[dict[str, str]]:
        previous_questions = list(
            InterviewQuestion.objects.exclude(session=session)
            .order_by("-created_at")
            .values_list("question", flat=True)[:30]
        )
        try:
            prompt = build_question_generation_prompt(session, previous_questions)
            raw = self.client.complete(prompt, "You are a helpful interview coach focused on realistic, personalized preparation.")
            data = self.client.parse_json(raw)
            items = data.get("questions") or []
            cleaned: list[dict[str, str]] = []
            used_questions = {self._normalize_question(item) for item in previous_questions}
            for item in items[:5]:
                question = (item.get("question") or "").strip()
                normalized = self._normalize_question(question)
                if not question or normalized in used_questions:
                    continue
                used_questions.add(normalized)
                cleaned.append(
                    {
                        "question": question,
                        "difficulty": (item.get("difficulty") or "medium").lower(),
                        "type": (item.get("type") or "technical").lower(),
                    }
                )
            if cleaned:
                return cleaned
        except (AIClientError, AttributeError, TypeError, ValueError):
            pass

        return self._fallback_questions(session, previous_questions)

    @staticmethod
    def _normalize_question(question):
        return " ".join(re.findall(r"[a-z0-9]+", (question or "").lower()))

    def evaluate_answer(self, session, question, answer):
        if self._is_placeholder_answer(answer):
            return {
                "score": 0.0,
                "feedback": "This response does not answer the question. Explain your approach and support it with a relevant example.",
                "strengths": "No interview-relevant evidence was provided.",
                "improvements": "Address the question directly, describe your reasoning, and give a concrete example.",
                "follow_up_question": None,
                "difficulty": "medium",
            }

        try:
            prompt = build_answer_evaluation_prompt(session, question, answer)
            raw = self.client.complete(prompt, "You are a professional technical interview coach.")
            data = self.client.parse_json(raw)
            score = float(data.get("score", 0.0))
            score = max(0.0, min(10.0, score))
            return {
                "score": round(score, 1),
                "feedback": str(data.get("feedback") or "Your answer was thoughtful and relevant."),
                "strengths": str(data.get("strengths") or "Clear communication and practical reasoning."),
                "improvements": str(data.get("improvements") or "Add more concrete examples and structure your answer."),
                "follow_up_question": data.get("follow_up_question") or None,
                "difficulty": str(data.get("difficulty") or "medium").lower(),
            }
        except (AIClientError, AttributeError, TypeError, ValueError):
            score = self._fallback_answer_score(session, answer)
            feedback = self._fallback_feedback(session, score)
            return {
                "score": round(score, 1),
                "feedback": feedback,
                "strengths": self._fallback_strengths(session, score),
                "improvements": self._fallback_improvements(session, score),
                "follow_up_question": self._fallback_follow_up(session, question, answer),
                "difficulty": self._fallback_difficulty(score),
            }

    def _candidate_terms(self, session):
        if session is None:
            return []

        raw = " ".join(
            [
                getattr(session, "friend_name", "") or "",
                getattr(session, "target_role", "") or "",
                getattr(session, "experience_level", "") or "",
                getattr(session, "skills", "") or "",
                getattr(session, "resume", "") or "",
                getattr(session, "job_description", "") or "",
            ]
        )
        tokens = re.findall(r"[a-z0-9]+", raw.lower())
        return [token for token in tokens if len(token) > 2]

    def _fallback_answer_score(self, session, answer):
        raw_answer = answer or ""
        answer_text = raw_answer.lower()
        tokens = re.findall(r"[a-z0-9]+", answer_text)

        if not tokens:
            return 0.0

        role_terms = self._candidate_terms(session)
        relevance_hits = sum(1 for term in role_terms if term in answer_text)
        structure_markers = [
            "i built",
            "i designed",
            "i used",
            "because",
            "for example",
            "first",
            "then",
            "finally",
            "tested",
            "optimized",
            "trade-off",
            "tradeoff",
            "latency",
            "monitoring",
            "api",
            "database",
            "queries",
        ]
        structure_hits = sum(1 for marker in structure_markers if marker in answer_text)
        metric_hit = bool(re.search(r"\b\d+\b|ms|seconds|latency|users|requests|uptime|coverage\b", answer_text))

        score = 1.5 + min(len(tokens) / 18, 2.0) + min(relevance_hits / 1.5, 3.0) + min(structure_hits / 2, 1.5) + (1.0 if metric_hit else 0.0)
        return round(min(10.0, max(0.0, score)), 1)

    def _fallback_feedback(self, session, score):
        candidate = (getattr(session, "friend_name", "") or "Candidate").strip() or "Candidate"
        role = (getattr(session, "target_role", "") or "role").strip() or "role"
        if score >= 8.0:
            return f"{candidate}, this is a strong {role.lower()} answer. You explain the trade-offs clearly and tie the solution to business or technical outcomes."
        if score >= 6.0:
            return f"{candidate}, your {role.lower()} answer is solid but could be sharper. Add a more explicit example, explain the design trade-offs, and state the impact on reliability or speed."
        if score >= 4.0:
            return f"{candidate}, you have the right direction, but this answer needs more substance. Explain the problem, the decisions you made, and the outcome in concrete terms."
        return f"{candidate}, this answer is too vague for a {role.lower()} interview. Be specific about the scenario, the technical decisions, and the measurable result."

    def _fallback_strengths(self, session, score):
        if score >= 8.0:
            return "Clear technical reasoning, structured explanation, and measurable results."
        if score >= 6.0:
            return "Relevant direction and a usable technical approach."
        if score >= 4.0:
            return "A reasonable starting point with some domain awareness."
        return "No concrete evidence was provided, so the answer could not be evaluated meaningfully."

    def _fallback_improvements(self, session, score):
        if score >= 8.0:
            return "Keep describing trade-offs, quantify impact, and connect choices to user or business outcomes."
        if score >= 6.0:
            return "Use a real example, explain why you chose that approach, and include one or two measurable outcomes."
        if score >= 4.0:
            return "Frame the problem, outline your decision-making, and include concrete examples and results."
        return "Answer the question directly, provide a specific example, and explain the decision behind your approach."

    def _fallback_difficulty(self, score):
        if score >= 8.0:
            return "hard"
        if score >= 5.0:
            return "medium"
        return "easy"

    @classmethod
    def _is_placeholder_answer(cls, answer):
        normalized = " ".join(re.findall(r"[a-z0-9]+", (answer or "").lower()))
        words = normalized.split()

        return normalized in cls._PLACEHOLDER_ANSWERS or (
            bool(words) and len(words) <= 3 and set(words).issubset({"na", "n", "a"})
        )

    def generate_follow_up_question(self, session, question, answer):
        try:
            prompt = build_follow_up_prompt(session, question, answer)
            raw = self.client.complete(prompt, "You are a focused interview coach asking a single follow-up question.")
            data = self.client.parse_json(raw)
            question_text = (data.get("question") or "").strip()
            if question_text:
                return {
                    "question": question_text,
                    "difficulty": (data.get("difficulty") or "medium").lower(),
                    "type": (data.get("type") or "follow_up").lower(),
                }
        except (AIClientError, AttributeError, TypeError, ValueError):
            pass
        return self._fallback_follow_up(session, question, answer)

    def generate_report(self, session):
        questions = list(
            session.questions.filter(question_number__lte=MAX_INTERVIEW_QUESTIONS).order_by("question_number")
        )
        if not questions:
            return {
                "overall_score": 0.0,
                "strengths": "No strengths could be assessed because no answers were submitted.",
                "weaknesses": "No interview answers are available to assess.",
                "recommended_topics": "Answer the interview questions with relevant examples from your experience.",
                "summary": "The interview was started, but no answers were recorded, so performance could not be assessed.",
            }

        placeholder_count = sum(self._is_placeholder_answer(question.answer) for question in questions)
        if placeholder_count == len(questions):
            scores = [float(question.score or 0.0) for question in questions if question.score is not None]
            average = sum(scores) / len(scores) if scores else 0.0
            return {
                "overall_score": round(min(10.0, max(0.0, average)), 1),
                "strengths": "No interview-relevant strengths could be assessed from the responses.",
                "weaknesses": "The responses did not address the interview questions.",
                "recommended_topics": "Practice structured answers, role-specific fundamentals, and concrete project examples",
                "summary": "The submitted responses did not address the interview questions, so they were too brief or unrelated to assess. Answer each question directly and explain your reasoning with a relevant example.",
            }

        try:
            prompt = build_final_report_prompt(session, questions)
            raw = self.client.complete(prompt, "You are a precise interview coach writing a final coaching summary.")
            data = self.client.parse_json(raw)
            scores = [float(q.score or 0.0) for q in questions if q.score is not None]
            average = sum(scores) / len(scores) if scores else 0.0
            strengths = str(data.get("strengths") or self._report_strengths(average))
            if average < 4.0:
                strengths = self._report_strengths(average)
            return {
                "overall_score": round(min(10.0, max(0.0, average)), 1),
                "strengths": strengths,
                "weaknesses": str(data.get("weaknesses") or self._report_weaknesses(average)),
                "recommended_topics": str(data.get("recommended_topics") or "Review the topics covered by the interview questions and practice concrete examples."),
                "summary": str(data.get("summary") or self._report_summary(average)),
            }
        except (AIClientError, AttributeError, TypeError, ValueError):
            scores = [float(q.score or 0.0) for q in questions if q.score is not None]
            average = sum(scores) / len(scores) if scores else 0.0

            return {
                "overall_score": round(min(10.0, max(0.0, average)), 1),
                "strengths": self._report_strengths(average),
                "weaknesses": self._report_weaknesses(average),
                "recommended_topics": "Review the topics covered by the interview questions and practice concrete examples.",
                "summary": self._report_summary(average),
            }

    def _report_strengths(self, average):
        if average < 4.0:
            return "No clear interview-relevant strengths were demonstrated in these answers."
        if average < 6.0:
            return "Some relevant understanding was demonstrated, but it was not consistent across the answers."
        return "The answers showed relevant understanding in the areas reflected by the individual question scores."

    def _report_weaknesses(self, average):
        if average < 4.0:
            return "Answers were mostly incomplete or did not address the questions directly."
        if average < 6.0:
            return "Answers need more relevant detail, clear reasoning, and concrete examples."
        return "Continue adding concrete evidence, trade-offs, and measurable outcomes to strengthen answers."

    def _report_summary(self, average):
        if average < 4.0:
            return "The responses did not provide enough relevant evidence to demonstrate role-specific skills. Practice answering each question directly and support claims with specific examples."
        if average < 6.0:
            return "The responses showed partial understanding, but relevance and supporting detail were inconsistent. Practice structuring answers around the problem, your actions, and the result."
        return "The responses showed relevant understanding overall. Continue strengthening them with specific examples, clear trade-offs, and measurable outcomes."

    def _fallback_questions(self, session, previous_questions=()):
        skill_names = [part.strip() for part in (session.skills or "Python").split(",") if part.strip()]
        primary_skill = skill_names[0] if skill_names else "Python"
        friend_name = getattr(session, "friend_name", "Candidate") or "Candidate"
        role = getattr(session, "target_role", "developer") or "developer"
        job_focus = (getattr(session, "job_description", "") or "").strip()
        focus = job_focus[:80] if job_focus else "building reliable systems"
        variants = [
            [
                f"{friend_name}, describe a project where {primary_skill} helped you solve a problem relevant to {role}.",
                f"For a {role} role, how would you design a feature for this need: {focus}?",
                f"What trade-off did you make in a {primary_skill} project, and what was the impact?",
                f"A {role} service is failing under load. What evidence would you collect before choosing a fix?",
            ],
            [
                f"{friend_name}, how have you used {primary_skill} to improve a real project, and how did you verify the improvement?",
                f"Given this job focus, {focus}, how would you break the work into reliable steps as a {role}?",
                f"Tell me about a time you chose a simpler {primary_skill} solution over a more complex one. Why?",
                f"A production change causes slow requests in a {role} system. How would you isolate the cause?",
            ],
            [
                f"{friend_name}, what is the most difficult {primary_skill} problem you have solved, and what did you learn?",
                f"How would you approach the main challenge in this role: {focus}?",
                f"When have you had to balance delivery speed and maintainability in your {primary_skill} work?",
                f"How would you prioritize debugging if a {role} application showed intermittent failures?",
            ],
        ]
        variant_index = getattr(session, "pk", 0) or 0
        prompts = variants[variant_index % len(variants):] + variants[:variant_index % len(variants)]
        previous = {self._normalize_question(question) for question in previous_questions}
        selected = []
        for group in prompts:
            for index, text in enumerate(group):
                normalized = self._normalize_question(text)
                if normalized not in previous:
                    selected.append(
                        {
                            "question": text,
                            "difficulty": ("easy", "medium", "medium", "hard")[index],
                            "type": ("technical", "practical", "behavioral", "technical")[index],
                        }
                    )
                    previous.add(normalized)
                if len(selected) >= 4:
                    return selected
        return selected

    def _fallback_follow_up(self, session, question, answer):
        candidate = (getattr(session, "friend_name", "") or "Candidate").strip() or "Candidate"
        role = (getattr(session, "target_role", "") or "developer").strip() or "developer"
        strongest_skill = (getattr(session, "skills", "") or "Python").split(",")[0].strip() or "Python"
        return (
            f"{candidate}, if you had to deliver this solution in a tighter timeline for a {role} role, "
            f"what would you simplify and what would you keep in place to protect quality using {strongest_skill}?"
        )
