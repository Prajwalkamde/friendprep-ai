from django.db import models


MAX_INTERVIEW_QUESTIONS = 5


class InterviewSession(models.Model):
    STATUS_CHOICES = [
        ("setup", "Setup"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    friend_name = models.CharField(max_length=120)
    target_role = models.CharField(max_length=120)
    experience_level = models.CharField(max_length=80)
    skills = models.TextField()
    resume = models.TextField()
    job_description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="setup")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"]) ]

    def __str__(self):
        return f"{self.friend_name} - {self.target_role}"


class InterviewQuestion(models.Model):
    QUESTION_TYPES = [
        ("technical", "Technical"),
        ("behavioral", "Behavioral"),
        ("practical", "Practical"),
        ("follow_up", "Follow Up"),
    ]

    session = models.ForeignKey(InterviewSession, related_name="questions", on_delete=models.CASCADE)
    question_number = models.PositiveIntegerField(default=1)
    question = models.TextField()
    difficulty = models.CharField(max_length=20, default="medium")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default="technical")
    answer = models.TextField(blank=True, default="")
    feedback = models.TextField(blank=True, default="")
    score = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["question_number"]
        indexes = [models.Index(fields=["session", "question_number"]) ]

    def __str__(self):
        return f"{self.question_number}. {self.question}"


class InterviewReport(models.Model):
    session = models.OneToOneField(InterviewSession, related_name="report", on_delete=models.CASCADE)
    overall_score = models.FloatField(default=0.0)
    strengths = models.TextField(blank=True, default="")
    weaknesses = models.TextField(blank=True, default="")
    recommended_topics = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.session.friend_name} report"
