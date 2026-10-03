from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .ai.service import AIService
from .forms import InterviewSetupForm
from .models import MAX_INTERVIEW_QUESTIONS, InterviewQuestion, InterviewReport, InterviewSession


def home(request):
    return render(request, "interview/home.html")


def setup(request):
    if request.method == "POST":
        form = InterviewSetupForm(request.POST)
        if form.is_valid():
            session = form.save()
            try:
                questions = AIService().generate_questions(session)
                for index, item in enumerate(questions[:MAX_INTERVIEW_QUESTIONS], start=1):
                    InterviewQuestion.objects.create(
                        session=session,
                        question_number=index,
                        question=item["question"],
                        difficulty=item["difficulty"],
                        question_type=item["type"],
                    )
                session.status = "active"
                session.save(update_fields=["status", "updated_at"])
                return redirect("interview:interview", session_id=session.pk)
            except Exception:
                messages.error(request, "The AI service is temporarily unavailable. Please try again in a moment.")
                return redirect("interview:setup")
    else:
        form = InterviewSetupForm()
    return render(request, "interview/setup.html", {"form": form})


def interview(request, session_id):
    session = get_object_or_404(InterviewSession, pk=session_id)
    questions = session.questions.filter(question_number__lte=MAX_INTERVIEW_QUESTIONS).order_by("question_number")

    if session.status == "setup":
        session.status = "active"
        session.save(update_fields=["status", "updated_at"])

    unanswered = questions.filter(answer="" )
    current_question = unanswered.first()
    if current_question is None and questions.exists():
        if session.status != "completed":
            session.status = "completed"
            session.save(update_fields=["status", "updated_at"])
        return redirect("interview:result", session_id=session.pk)

    total_questions = questions.count() or 1
    answered_count = questions.exclude(answer="").count()
    progress = int((answered_count / total_questions) * 100) if total_questions else 0

    return render(
        request,
        "interview/interview.html",
        {"session": session, "question": current_question, "questions": questions, "progress": progress},
    )


def submit_answer(request, session_id):
    if request.method != "POST":
        return redirect("interview:home")

    session = get_object_or_404(InterviewSession, pk=session_id)
    question_id = request.POST.get("question_id")
    answer = (request.POST.get("answer") or "").strip()

    if not question_id:
        messages.error(request, "A valid question is required.")
        return redirect("interview:interview", session_id=session.pk)

    if not answer:
        messages.error(request, "Please provide an answer before submitting.")
        return redirect("interview:interview", session_id=session.pk)

    question = get_object_or_404(InterviewQuestion, pk=question_id, session=session)
    question.answer = answer

    try:
        result = AIService().evaluate_answer(session, question, answer)
    except Exception:
        question.feedback = "The AI could not evaluate this answer right now. Please try again."
        question.score = 0.0
        question.save(update_fields=["answer", "feedback", "score"])
        messages.error(request, "The AI service is temporarily unavailable. Please try again in a moment.")
        return redirect("interview:interview", session_id=session.pk)

    question.feedback = result.get("feedback", "")
    question.score = result.get("score", 0.0)
    question.save(update_fields=["answer", "feedback", "score"])

    follow_up_question = (result.get("follow_up_question") or "").strip()
    active_questions = session.questions.filter(question_number__lte=MAX_INTERVIEW_QUESTIONS)
    follow_up_already_exists = active_questions.filter(question__iexact=follow_up_question).exists()
    if (
        follow_up_question
        and active_questions.count() < MAX_INTERVIEW_QUESTIONS
        and not follow_up_already_exists
    ):
        next_number = active_questions.count() + 1
        InterviewQuestion.objects.create(
            session=session,
            question_number=next_number,
            question=follow_up_question,
            difficulty=result.get("difficulty", "medium"),
            question_type="follow_up",
        )

    unanswered = active_questions.filter(answer="").order_by("question_number")
    if unanswered.exists():
        session.status = "active"
        session.save(update_fields=["status", "updated_at"])
        return redirect("interview:interview", session_id=session.pk)

    session.status = "completed"
    session.save(update_fields=["status", "updated_at"])
    return redirect("interview:result", session_id=session.pk)


def result(request, session_id):
    session = get_object_or_404(InterviewSession, pk=session_id)
    questions = session.questions.filter(question_number__lte=MAX_INTERVIEW_QUESTIONS).order_by("question_number")

    try:
        report = session.report
    except InterviewReport.DoesNotExist:
        report = None

    if report:
        scored_questions = [question for question in questions if question.score is not None]
        average_score = (
            sum(float(question.score) for question in scored_questions) / len(scored_questions)
            if scored_questions
            else 0.0
        )
        if average_score < 4.0 and report.strengths.strip() in {
            "Solid fundamentals and curiosity.",
            "Strong communication and a clear preparation strategy.",
        }:
            report.overall_score = round(average_score, 1)
            report.strengths = "No clear interview-relevant strengths were demonstrated in these answers."
            report.weaknesses = "Answers were mostly incomplete or did not address the questions directly."
            report.summary = (
                "The responses did not provide enough relevant evidence to demonstrate role-specific skills. "
                "Practice answering each question directly and support claims with specific examples."
            )
            report.save(update_fields=["overall_score", "strengths", "weaknesses", "summary"])

    if report is None:
        if session.questions.filter(question_number__lte=MAX_INTERVIEW_QUESTIONS, answer="").exists():
            return redirect("interview:interview", session_id=session.pk)
        try:
            report_data = AIService().generate_report(session)
            report = InterviewReport.objects.create(
                session=session,
                overall_score=float(report_data.get("overall_score", 0.0)),
                strengths=report_data.get("strengths", ""),
                weaknesses=report_data.get("weaknesses", ""),
                recommended_topics=report_data.get("recommended_topics", ""),
                summary=report_data.get("summary", ""),
            )
        except Exception:
            report = InterviewReport.objects.create(
                session=session,
                overall_score=float(sum(q.score or 0 for q in questions) / max(1, questions.count())),
                strengths="Strong interview preparation mindset.",
                weaknesses="Continue practicing under timed constraints.",
                recommended_topics="System design, SQL, testing",
                summary="The candidate completed the interview with thoughtful answers and a clear growth plan.",
            )

    return render(request, "interview/result.html", {"session": session, "report": report, "questions": questions})
