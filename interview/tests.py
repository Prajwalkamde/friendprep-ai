from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .ai.client import AIClientError, HuggingFaceClient
from .ai.service import AIService
from .models import MAX_INTERVIEW_QUESTIONS, InterviewQuestion, InterviewReport, InterviewSession


class InterviewModelsTestCase(TestCase):
    def test_session_question_and_report_creation(self):
        session = InterviewSession.objects.create(
            friend_name="Alex",
            target_role="Python Developer",
            experience_level="2 years",
            skills="Django, Python, SQL",
            resume="Built APIs and dashboards.",
            job_description="Develop APIs and improve backend performance.",
            status="active",
        )
        question = InterviewQuestion.objects.create(
            session=session,
            question_number=1,
            question="Explain Django ORM.",
            difficulty="easy",
            question_type="technical",
            answer="Use ORM to map models to tables.",
            feedback="Good answer.",
            score=8.5,
        )
        report = InterviewReport.objects.create(
            session=session,
            overall_score=8.4,
            strengths="Django fundamentals",
            weaknesses="Testing coverage",
            recommended_topics="SQL, testing",
            summary="Strong backend foundation.",
        )

        self.assertEqual(str(session), "Alex - Python Developer")
        self.assertEqual(str(question), "1. Explain Django ORM.")
        self.assertEqual(str(report), "Alex report")


class HuggingFaceClientTestCase(SimpleTestCase):
    @override_settings(HF_TOKEN="test-token")
    @patch("interview.ai.client.requests.post")
    def test_rejects_a_success_response_without_a_message(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": []}
        mock_post.return_value = response

        with self.assertRaises(AIClientError):
            HuggingFaceClient().complete("Question", "System prompt")


class AIServiceTestCase(SimpleTestCase):
    def test_placeholder_answer_receives_zero_score_without_calling_the_provider(self):
        result = AIService().evaluate_answer(None, None, "NA NA")

        self.assertEqual(result["score"], 0.0)
        self.assertIn("does not answer", result["feedback"])
        self.assertIsNone(result["follow_up_question"])

    def test_fallback_evaluation_is_specific_to_the_candidate_and_answer_quality(self):
        session = type(
            "Session",
            (),
            {
                "friend_name": "Aisha",
                "target_role": "Backend Engineer",
                "experience_level": "3 years",
                "skills": "Python, Django, PostgreSQL",
                "resume": "Built APIs and dashboards.",
                "job_description": "Build reliable services and optimize database performance.",
            },
        )()

        weak = AIService().evaluate_answer(session, None, "NA")
        strong = AIService().evaluate_answer(
            session,
            None,
            "I designed a Django API with PostgreSQL queries, added indexing, and validated the flow with integration tests to keep latency under control.",
        )

        self.assertLess(weak["score"], strong["score"])
        self.assertGreater(strong["score"], 6.5)
        self.assertTrue("Aisha" in strong["feedback"] or "Backend Engineer" in strong["feedback"])
        self.assertNotEqual(weak["feedback"], strong["feedback"])

    def test_fallback_questions_use_candidate_context_instead_of_repeating_stock_prompts(self):
        session = type(
            "Session",
            (),
            {
                "friend_name": "Aisha",
                "target_role": "Backend Engineer",
                "experience_level": "3 years",
                "skills": "Python, Django, PostgreSQL",
                "resume": "Built APIs and dashboards.",
                "job_description": "Build reliable services and optimize database performance.",
            },
        )()

        questions = AIService()._fallback_questions(session)

        self.assertTrue(any("Aisha" in q["question"] for q in questions))
        self.assertTrue(any("Backend Engineer" in q["question"] for q in questions))


@override_settings(HF_TOKEN="")
class InterviewViewsTestCase(TestCase):
    def test_home_page(self):
        response = self.client.get(reverse("interview:home"))
        self.assertEqual(response.status_code, 200)

    def test_setup_form_creates_session(self):
        payload = {
            "friend_name": "Jamie",
            "target_role": "Backend Engineer",
            "experience_level": "3 years",
            "skills": "Python, Django, PostgreSQL",
            "resume": "Built a Django API and dashboard.",
            "job_description": "Need a backend engineer to build APIs and optimize queries.",
        }
        response = self.client.post(reverse("interview:setup"), payload)
        self.assertEqual(response.status_code, 302)
        session = InterviewSession.objects.get(friend_name="Jamie")
        self.assertEqual(session.status, "active")
        self.assertEqual(session.questions.count(), 4)
        self.assertEqual(
            response["Location"],
            reverse("interview:interview", args=[session.pk]),
        )

    def test_result_page_for_completed_session(self):
        session = InterviewSession.objects.create(
            friend_name="Taylor",
            target_role="Data Engineer",
            experience_level="1 year",
            skills="Python, SQL",
            resume="Worked on ETL pipelines.",
            job_description="Create data pipelines and support analytics.",
            status="completed",
        )
        response = self.client.get(reverse("interview:result", args=[session.pk]))
        self.assertEqual(response.status_code, 200)

    def test_placeholder_answers_receive_an_honest_fallback_report(self):
        session = InterviewSession.objects.create(
            friend_name="Casey",
            target_role="Java Developer",
            experience_level="1 year",
            skills="Java",
            resume="Built a small Java application.",
            job_description="Build and maintain Java services.",
            status="completed",
        )
        for number in range(1, 5):
            InterviewQuestion.objects.create(
                session=session,
                question_number=number,
                question=f"Question {number}",
                difficulty="medium",
                question_type="technical",
                answer="NA NA",
                score=0.0,
            )

        report = AIService().generate_report(session)

        self.assertEqual(report["overall_score"], 0.0)
        self.assertIn("did not address", report["summary"])
        self.assertIn("could be assessed", report["strengths"])

    def test_low_scoring_report_does_not_claim_generic_strengths(self):
        session = InterviewSession.objects.create(
            friend_name="Casey",
            target_role="Java Developer",
            experience_level="1 year",
            skills="Java",
            resume="Built a small Java application.",
            job_description="Build and maintain Java services.",
            status="completed",
        )
        for number in range(1, 5):
            InterviewQuestion.objects.create(
                session=session,
                question_number=number,
                question=f"Java question {number}",
                difficulty="medium",
                question_type="technical",
                answer="The weather is nice today.",
                score=1.0,
            )

        client = Mock()
        client.complete.return_value = "report"
        client.parse_json.return_value = {
            "overall_score": 8.0,
            "strengths": "Solid fundamentals and curiosity.",
            "weaknesses": "None",
            "recommended_topics": "Java",
            "summary": "Strong candidate.",
        }

        report = AIService(client=client).generate_report(session)

        self.assertEqual(report["overall_score"], 1.0)
        self.assertIn("No clear", report["strengths"])
        self.assertNotIn("Solid fundamentals", report["strengths"])

    def test_existing_low_score_report_replaces_legacy_generic_strengths(self):
        session = InterviewSession.objects.create(
            friend_name="Casey",
            target_role="Java Developer",
            experience_level="1 year",
            skills="Java",
            resume="Built a small Java application.",
            job_description="Build and maintain Java services.",
            status="completed",
        )
        for number in range(1, 5):
            InterviewQuestion.objects.create(
                session=session,
                question_number=number,
                question=f"Java question {number}",
                difficulty="medium",
                question_type="technical",
                answer="The weather is nice today.",
                score=1.0,
            )
        report = InterviewReport.objects.create(
            session=session,
            overall_score=8.0,
            strengths="Solid fundamentals and curiosity.",
            weaknesses="None",
            recommended_topics="Java",
            summary="Strong candidate.",
        )

        response = self.client.get(reverse("interview:result", args=[session.pk]))

        report.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(report.overall_score, 1.0)
        self.assertIn("No clear", report.strengths)

    def test_question_generation_excludes_recent_exact_repeats(self):
        previous_question = "Explain how you would optimize a Java database query."
        InterviewSession.objects.create(
            friend_name="Taylor",
            target_role="Java Developer",
            experience_level="1 year",
            skills="Java",
            resume="Built a Java application.",
            job_description="Build Java services.",
            status="completed",
        ).questions.create(
            question_number=1,
            question=previous_question,
            difficulty="medium",
            question_type="technical",
        )
        current_session = InterviewSession.objects.create(
            friend_name="Casey",
            target_role="Java Developer",
            experience_level="1 year",
            skills="Java",
            resume="Built a Java application.",
            job_description="Build Java services.",
            status="setup",
        )
        client = Mock()
        client.complete.return_value = "questions"
        client.parse_json.return_value = {
            "questions": [
                {"question": previous_question, "difficulty": "medium", "type": "technical"},
                {"question": "How would you design a cache invalidation strategy?", "difficulty": "hard", "type": "practical"},
            ]
        }

        questions = AIService(client=client).generate_questions(current_session)

        self.assertTrue(client.complete.called, repr((questions, client.mock_calls)))
        self.assertIn(previous_question, client.complete.call_args.args[0])
        self.assertEqual(len(questions), 1)
        self.assertNotEqual(questions[0]["question"], previous_question)

    @patch("interview.views.AIService.evaluate_answer")
    def test_follow_up_questions_stop_at_the_session_limit(self, mock_evaluate_answer):
        session = InterviewSession.objects.create(
            friend_name="Jordan",
            target_role="Backend Engineer",
            experience_level="2 years",
            skills="Python, Django",
            resume="Built APIs.",
            job_description="Build reliable backend services.",
            status="active",
        )
        for number in range(1, 5):
            InterviewQuestion.objects.create(
                session=session,
                question_number=number,
                question=f"Question {number}",
                difficulty="medium",
                question_type="technical",
            )

        mock_evaluate_answer.return_value = {
            "score": 7.0,
            "feedback": "Clear answer.",
            "follow_up_question": "How would you improve that approach?",
            "difficulty": "medium",
        }

        for question in session.questions.order_by("question_number"):
            self.client.post(
                reverse("interview:submit_answer", args=[session.pk]),
                {"question_id": question.pk, "answer": "My answer includes a concrete example."},
            )

        self.assertEqual(session.questions.count(), MAX_INTERVIEW_QUESTIONS)
        follow_up = session.questions.get(question_number=MAX_INTERVIEW_QUESTIONS)
        self.assertEqual(follow_up.question, "How would you improve that approach?")

        response = self.client.post(
            reverse("interview:submit_answer", args=[session.pk]),
            {"question_id": follow_up.pk, "answer": "I would add monitoring and tests."},
        )

        self.assertEqual(session.questions.count(), MAX_INTERVIEW_QUESTIONS)
        self.assertEqual(response["Location"], reverse("interview:result", args=[session.pk]))

    def test_existing_extra_questions_do_not_block_completion(self):
        session = InterviewSession.objects.create(
            friend_name="Morgan",
            target_role="Developer",
            experience_level="2 years",
            skills="Python",
            resume="Built services.",
            job_description="Build APIs.",
            status="active",
        )
        for number in range(1, MAX_INTERVIEW_QUESTIONS + 2):
            InterviewQuestion.objects.create(
                session=session,
                question_number=number,
                question=f"Question {number}",
                difficulty="medium",
                question_type="technical",
                answer="Complete" if number <= MAX_INTERVIEW_QUESTIONS else "",
                score=7.0 if number <= MAX_INTERVIEW_QUESTIONS else None,
            )

        response = self.client.get(reverse("interview:interview", args=[session.pk]))

        self.assertEqual(response["Location"], reverse("interview:result", args=[session.pk]))
